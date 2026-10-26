"""Command line interface for videograph.

Usage:
    python -m videograph.cli analyze --input sample.mp4 --output results.json
    python -m videograph.cli qa --transcript transcript.json --query "What is the key takeaway?"
"""

from __future__ import annotations
import os
import json
import argparse
from pathlib import Path

from videograph.schemas import VideoAnalysisResult, Segment, TranscriptSegment
from videograph.ingest import ingest_media, get_media_duration
from videograph.transcribe import transcribe, parse_vtt_or_srt
from videograph.chunk import chunk_transcript
from videograph.extract import generate_chapters_and_summary, extract_full_graph
from videograph.grounding import filter_graph
from videograph.resolve import resolve_knowledge_graph
from videograph.qa import answer_question

ROOT_DIR = Path(__file__).resolve().parents[1]
DEMO_PATH = ROOT_DIR / "data" / "demo" / "demo_attention.json"


def process_video_pipeline(
    input_source: str,
    output_path: str = "output_analysis.json",
    model: str = "gemma-4-it",
    use_demo: bool = False,
) -> VideoAnalysisResult:
    """Run full videograph pipeline on local file, subtitles, or offline demo."""
    if use_demo:
        print("[*] Loading offline demo analysis artifact...")
        if not DEMO_PATH.exists():
            raise FileNotFoundError(f"Demo file not found at: {DEMO_PATH}")
        result = VideoAnalysisResult.model_validate_json(DEMO_PATH.read_text(encoding="utf-8"))
        grounded_graph, _ = filter_graph(result.graph, result.transcript)
        result = result.model_copy(update={"graph": grounded_graph})
        Path(output_path).write_text(result.model_dump_json(indent=2), encoding="utf-8")
        print(f"[+] Demo loaded successfully! Saved to: {output_path}")
        return result

    print(f"[*] Processing video source: {input_source}")

    title = "Video Analysis"
    duration = 0.0

    # 1. Check if input is a URL (requires Tanmmay's media downloader)
    if input_source.startswith("http://") or input_source.startswith("https://"):
        raise NotImplementedError(
            "Direct URL ingestion is not yet available. Please download the media file or upload subtitles."
        )

    file_path = input_source
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: {file_path}")

    title = Path(file_path).stem

    # 2. Check if input is a subtitle/transcript file directly
    ext = Path(file_path).suffix.lower()
    if ext in [".vtt", ".srt"]:
        content = Path(file_path).read_text(encoding="utf-8")
        segments = parse_vtt_or_srt(content)
        duration = segments[-1].end if segments else 0.0
    else:
        duration = get_media_duration(file_path)
        # Convert media to 16kHz WAV
        print(f"[*] Ingesting and converting media to WAV...")
        wav_path = ingest_media(file_path)
        print(f"[*] Converted audio to: {wav_path}")
        # Transcribe
        print("[*] Transcribing audio...")
        segments = transcribe(wav_path)

    print(f"[*] Transcribed {len(segments)} segments. Generating summary and chapters...")
    summary, chapters = generate_chapters_and_summary(segments, model=model)

    print("[*] Chunking transcript and extracting grounded knowledge graph...")
    chunks = chunk_transcript(segments)
    raw_graph = extract_full_graph(chunks, segments, model=model)

    print(f"[*] Extracted {len(raw_graph.nodes)} nodes and {len(raw_graph.edges)} edges. Verifying quote grounding...")
    grounded_graph, _ = filter_graph(raw_graph, segments)

    print(f"[*] Resolving entities...")
    resolved_graph = resolve_knowledge_graph(grounded_graph)

    result = VideoAnalysisResult(
        video_id=Path(file_path).stem,
        title=title,
        duration=duration,
        summary=summary,
        transcript=segments,
        chapters=chapters,
        graph=resolved_graph,
    )

    Path(output_path).write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"[+] Complete! Output saved to: {output_path}")
    return result


def main():
    parser = argparse.ArgumentParser(prog="videograph", description="Video to Grounded Knowledge Graph & Verified Q&A")
    subparsers = parser.add_subparsers(dest="command")

    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze video into transcript, chapters, summary, and KG")
    analyze_parser.add_argument("--input", default=None, help="Video file path, subtitles, or URL")
    analyze_parser.add_argument("--demo", action="store_true", help="Load precomputed offline demo analysis")
    analyze_parser.add_argument("--output", default="analysis.json", help="Output JSON path")
    analyze_parser.add_argument("--model", default="gemma-4-it", help="Gemini LLM model name")

    # QA command
    qa_parser = subparsers.add_parser("qa", help="Ask grounded question against transcript")
    qa_parser.add_argument("--transcript", required=True, help="Transcript JSON or VTT file")
    qa_parser.add_argument("--query", required=True, help="Question to ask")
    qa_parser.add_argument("--model", default="gemma-4-it", help="Gemini LLM model name")

    args = parser.parse_args()

    if args.command == "analyze":
        if not args.input and not args.demo:
            analyze_parser.error("either --input or --demo is required")
        process_video_pipeline(args.input or "demo", args.output, model=args.model, use_demo=args.demo)
    elif args.command == "qa":
        trans_path = Path(args.transcript)
        content = trans_path.read_text(encoding="utf-8")
        if trans_path.suffix.lower() in [".vtt", ".srt"]:
            segments = parse_vtt_or_srt(content)
        else:
            raw_data = json.loads(content)
            raw_segments = raw_data if isinstance(raw_data, list) else raw_data.get("transcript", [])
            segments = [
                Segment(
                    id=x.get("id", idx),
                    start=float(x.get("start", 0.0)),
                    end=float(x.get("end", 0.0)),
                    text=str(x.get("text", "")),
                )
                for idx, x in enumerate(raw_segments)
            ]

        ans = answer_question(args.query, segments, model=args.model)
        print(ans.model_dump_json(indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

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

from videograph.schemas import VideoAnalysisResult, TranscriptSegment
from videograph.ingest import extract_audio, download_video_or_audio, get_video_duration
from videograph.transcribe import transcribe_audio_file, parse_vtt_or_srt
from videograph.chunk import chunk_transcript
from videograph.extract import extract_summary_and_chapters, extract_full_graph
from videograph.resolve import resolve_knowledge_graph
from videograph.qa import answer_question


def process_video_pipeline(
    input_source: str,
    output_path: str = "output_analysis.json",
    model: str = "gemma-4-it",
) -> VideoAnalysisResult:
    """Run full end-to-end videograph pipeline on local file or URL."""
    print(f"[*] Processing video source: {input_source}")

    title = "Video Analysis"
    duration = 0.0

    # 1. Ingest / download if URL
    if input_source.startswith("http://") or input_source.startswith("https://"):
        download_dir = Path.home() / ".videograph_cache" / "downloads"
        file_path, video_title = download_video_or_audio(input_source, str(download_dir))
        title = video_title
    else:
        file_path = input_source
        title = Path(file_path).stem

    # 2. Check if input is a subtitle/transcript file directly
    ext = Path(file_path).suffix.lower()
    if ext in [".vtt", ".srt"]:
        content = Path(file_path).read_text(encoding="utf-8")
        segments = parse_vtt_or_srt(content)
        duration = segments[-1].end if segments else 0.0
    else:
        duration = get_video_duration(file_path)
        # Extract audio
        audio_path = extract_audio(file_path)
        print(f"[*] Extracted audio to: {audio_path}")
        # Transcribe
        print("[*] Transcribing audio with Gemini...")
        segments = transcribe_audio_file(audio_path)

    print(f"[*] Transcribed {len(segments)} segments. Generating summary and chapters...")
    summary, chapters = extract_summary_and_chapters(segments, model=model)

    print("[*] Chunking transcript and extracting grounded knowledge graph...")
    chunks = chunk_transcript(segments)
    raw_graph = extract_full_graph(chunks, segments, model=model)

    print(f"[*] Extracted {len(raw_graph.nodes)} nodes and {len(raw_graph.edges)} edges. Resolving entities...")
    resolved_graph = resolve_knowledge_graph(raw_graph)

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
    analyze_parser.add_argument("--input", required=True, help="Video file path or URL")
    analyze_parser.add_argument("--output", default="analysis.json", help="Output JSON path")
    analyze_parser.add_argument("--model", default="gemma-4-it", help="Gemini LLM model name")

    # QA command
    qa_parser = subparsers.add_parser("qa", help="Ask grounded question against transcript")
    qa_parser.add_argument("--transcript", required=True, help="Transcript JSON or VTT file")
    qa_parser.add_argument("--query", required=True, help="Question to ask")
    qa_parser.add_argument("--model", default="gemma-4-it", help="Gemini LLM model name")

    args = parser.parse_args()

    if args.command == "analyze":
        process_video_pipeline(args.input, args.output, model=args.model)
    elif args.command == "qa":
        trans_path = Path(args.transcript)
        content = trans_path.read_text(encoding="utf-8")
        if trans_path.suffix.lower() in [".vtt", ".srt"]:
            segments = parse_vtt_or_srt(content)
        else:
            raw_data = json.loads(content)
            if isinstance(raw_data, list):
                segments = [TranscriptSegment.model_validate(x) for x in raw_data]
            else:
                segments = [TranscriptSegment.model_validate(x) for x in raw_data.get("transcript", [])]

        ans = answer_question(args.query, segments, model=args.model)
        print(ans.model_dump_json(indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

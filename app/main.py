"""FastAPI application for videograph.

Exposes REST APIs for video analysis, knowledge graph visualization, and grounded Q&A.
"""

from __future__ import annotations
import os
import shutil
import uuid
from pathlib import Path
from typing import Dict, Optional, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from videograph.schemas import VideoAnalysisResult, QAResponse, TranscriptSegment
from videograph.graph import to_vis_network_data, compute_graph_metrics
from videograph.transcribe import parse_vtt_or_srt, transcribe_audio_file
from videograph.ingest import extract_audio, download_video_or_audio, get_video_duration
from videograph.chunk import chunk_transcript
from videograph.extract import extract_summary_and_chapters, extract_full_graph
from videograph.resolve import resolve_knowledge_graph
from videograph.qa import answer_question

app = FastAPI(
    title="Videograph API",
    description="Video to Grounded Knowledge Graph and Verified Q&A",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for analysis sessions (backed by local disk)
ANALYSIS_STORE: Dict[str, VideoAnalysisResult] = {}
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Mount static files
STATIC_DIR = Path("app") / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class QARequest(BaseModel):
    video_id: str
    question: str
    model: str = "gemma-4-it"


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>videograph frontend is loading...</h1>")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": "videograph", "version": "0.1.0"}


@app.post("/api/analyze/url")
async def analyze_url(url: str = Form(...), model: str = Form("gemma-4-it")):
    """Analyze a web/YouTube video by URL."""
    try:
        video_id = str(uuid.uuid4())[:8]
        file_path, title = download_video_or_audio(url, str(UPLOAD_DIR))
        duration = get_video_duration(file_path)
        audio_path = extract_audio(file_path)

        segments = transcribe_audio_file(audio_path)
        summary, chapters = extract_summary_and_chapters(segments, model=model)
        chunks = chunk_transcript(segments)
        raw_graph = extract_full_graph(chunks, segments, model=model)
        resolved_graph = resolve_knowledge_graph(raw_graph)

        result = VideoAnalysisResult(
            video_id=video_id,
            title=title,
            duration=duration,
            summary=summary,
            transcript=segments,
            chapters=chapters,
            graph=resolved_graph,
        )
        ANALYSIS_STORE[video_id] = result
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze/upload")
async def analyze_upload(
    file: UploadFile = File(...),
    model: str = Form("gemma-4-it"),
):
    """Analyze an uploaded video or subtitle (VTT/SRT) file."""
    try:
        video_id = str(uuid.uuid4())[:8]
        filename = file.filename or f"video_{video_id}.mp4"
        dest_path = UPLOAD_DIR / f"{video_id}_{filename}"

        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        ext = dest_path.suffix.lower()
        if ext in [".vtt", ".srt"]:
            content = dest_path.read_text(encoding="utf-8")
            segments = parse_vtt_or_srt(content)
            duration = segments[-1].end if segments else 0.0
            title = filename
        else:
            duration = get_video_duration(str(dest_path))
            audio_path = extract_audio(str(dest_path))
            segments = transcribe_audio_file(audio_path)
            title = filename

        summary, chapters = extract_summary_and_chapters(segments, model=model)
        chunks = chunk_transcript(segments)
        raw_graph = extract_full_graph(chunks, segments, model=model)
        resolved_graph = resolve_knowledge_graph(raw_graph)

        result = VideoAnalysisResult(
            video_id=video_id,
            title=title,
            duration=duration,
            summary=summary,
            transcript=segments,
            chapters=chapters,
            graph=resolved_graph,
        )
        ANALYSIS_STORE[video_id] = result
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analysis/{video_id}")
async def get_analysis(video_id: str):
    """Retrieve full analysis for a video."""
    if video_id not in ANALYSIS_STORE:
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    return ANALYSIS_STORE[video_id]


@app.get("/api/graph/{video_id}")
async def get_graph_data(video_id: str):
    """Get Vis.js formatted graph nodes, edges, and graph metrics."""
    if video_id not in ANALYSIS_STORE:
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    analysis = ANALYSIS_STORE[video_id]
    vis_data = to_vis_network_data(analysis.graph)
    metrics = compute_graph_metrics(analysis.graph)
    return {"vis": vis_data, "metrics": metrics}


@app.post("/api/qa", response_model=QAResponse)
async def query_video(req: QARequest):
    """Execute grounded question answering against a processed video transcript."""
    if req.video_id not in ANALYSIS_STORE:
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    analysis = ANALYSIS_STORE[req.video_id]
    qa_resp = answer_question(req.question, analysis.transcript, model=req.model)
    return qa_resp


@app.post("/api/sample/load")
async def load_sample_analysis():
    """Load a rich pre-computed sample for immediate demonstration."""
    from videograph.schemas import (
        KnowledgeNode,
        KnowledgeEdge,
        KnowledgeGraph,
        VideoChapter,
    )
    sample_id = "sample_attention"
    segments = [
        TranscriptSegment(id=0, start=0.0, end=7.5, text="Welcome to this breakdown of the Transformer architecture and attention mechanisms."),
        TranscriptSegment(id=1, start=7.5, end=18.0, text="Traditional recurrent neural networks suffered from vanishing gradients when processing long sequential dependencies."),
        TranscriptSegment(id=2, start=18.0, end=29.2, text="The breakthrough came with the 2017 paper Attention Is All You Need which introduced Multi-Head Self-Attention."),
        TranscriptSegment(id=3, start=29.2, end=42.0, text="Instead of recurrence, self-attention maps Query, Key, and Value vectors across token embeddings."),
        TranscriptSegment(id=4, start=42.0, end=56.5, text="Scaled Dot-Product Attention divides the dot products by the square root of dimension dk to prevent gradient saturation."),
        TranscriptSegment(id=5, start=56.5, end=70.0, text="Positional encodings inject sequence order information using sinusoidal frequencies or learned embeddings."),
        TranscriptSegment(id=6, start=70.0, end=84.0, text="Modern LLMs such as Gemma and Llama extend these foundations using FlashAttention and RMSNorm for accelerated GPU execution."),
    ]
    chapters = [
        VideoChapter(title="Introduction & RNN Limitations", start=0.0, end=18.0, summary="Explains sequential processing bottlenecks in traditional recurrent networks."),
        VideoChapter(title="The Self-Attention Revolution", start=18.0, end=42.0, summary="Introduces Query, Key, and Value projections in the Transformer architecture."),
        VideoChapter(title="Mathematical Foundations & Modern LLMs", start=42.0, end=84.0, summary="Details Scaled Dot-Product computation, Positional Encodings, and FlashAttention speedups."),
    ]
    nodes = [
        KnowledgeNode(id="transformer", label="Transformer", type="Technology", description="Foundational attention-based sequence model."),
        KnowledgeNode(id="rnn", label="Recurrent Neural Networks", type="Technology", description="Traditional sequential architectures limited by gradient decay."),
        KnowledgeNode(id="self_attention", label="Multi-Head Self-Attention", type="Concept", description="Parallel token relationship mapping mechanism."),
        KnowledgeNode(id="scaled_dot_product", label="Scaled Dot-Product Attention", type="Method", description="Attention formula scaling by sqrt(dk) to prevent saturation."),
        KnowledgeNode(id="positional_encoding", label="Positional Encoding", type="Method", description="Frequency or learned sequence order representations."),
        KnowledgeNode(id="flash_attention", label="FlashAttention", type="Tool", description="IO-aware GPU kernel acceleration for modern LLMs."),
    ]
    edges = [
        KnowledgeEdge(
            source="transformer",
            target="rnn",
            relation="IMPROVES_UPON",
            evidence_quote="Traditional recurrent neural networks suffered from vanishing gradients when processing long sequential dependencies",
            start_time=7.5,
            end_time=18.0,
            confidence=0.98,
        ),
        KnowledgeEdge(
            source="transformer",
            target="self_attention",
            relation="USES",
            evidence_quote="The breakthrough came with the 2017 paper Attention Is All You Need which introduced Multi-Head Self-Attention",
            start_time=18.0,
            end_time=29.2,
            confidence=0.99,
        ),
        KnowledgeEdge(
            source="self_attention",
            target="scaled_dot_product",
            relation="IMPLEMENTS",
            evidence_quote="Scaled Dot-Product Attention divides the dot products by the square root of dimension dk to prevent gradient saturation",
            start_time=42.0,
            end_time=56.5,
            confidence=0.96,
        ),
        KnowledgeEdge(
            source="transformer",
            target="positional_encoding",
            relation="REQUIRES",
            evidence_quote="Positional encodings inject sequence order information using sinusoidal frequencies",
            start_time=56.5,
            end_time=70.0,
            confidence=0.95,
        ),
        KnowledgeEdge(
            source="flash_attention",
            target="self_attention",
            relation="ACCELERATES",
            evidence_quote="Modern LLMs such as Gemma and Llama extend these foundations using FlashAttention and RMSNorm for accelerated GPU execution",
            start_time=70.0,
            end_time=84.0,
            confidence=0.97,
        ),
    ]
    result = VideoAnalysisResult(
        video_id=sample_id,
        title="Attention Mechanisms & Transformer Architecture Deep Dive",
        duration=84.0,
        summary="A comprehensive technical walkthrough of how the Transformer superseded recurrent architectures through Multi-Head Self-Attention. Covers mathematical normalization factors, positional encodings, and modern GPU execution techniques including FlashAttention.",
        transcript=segments,
        chapters=chapters,
        graph=KnowledgeGraph(nodes=nodes, edges=edges),
    )
    ANALYSIS_STORE[sample_id] = result
    return result

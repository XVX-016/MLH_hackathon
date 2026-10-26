"""Job-based FastAPI service for videograph."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from videograph.chunk import chunk_transcript
from videograph.extract import extract_full_graph, generate_chapters_and_summary
from videograph.grounding import filter_graph
from videograph.ingest import MAX_VIDEO_DURATION_SEC, get_media_duration, ingest_media
from videograph.qa import answer_question
from videograph.resolve import resolve_knowledge_graph
from videograph.schemas import QAResponse, VideoAnalysisResult
from videograph.transcribe import parse_vtt_or_srt, transcribe

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DEMO_DIR = DATA_DIR / "demo"
STATIC_DIR = Path(__file__).parent / "static"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

for directory in (UPLOAD_DIR, DEMO_DIR, STATIC_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="videograph", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

JOBS: Dict[str, Dict[str, Any]] = {}


class AskRequest(BaseModel):
    job_id: str
    question: str = Field(min_length=1)
    model: str = "gemma-4-it"


def _grounding_stats(result: VideoAnalysisResult) -> Dict[str, Any]:
    edges = result.graph.edges
    passed = sum(edge.grounded for edge in edges)
    return {
        "total_edges": len(edges),
        "grounded_edges": passed,
        "grounding_pass_rate": passed / len(edges) if edges else 1.0,
    }


def _read_demo_results() -> None:
    """Populate completed jobs from checked-in JSON only; never invoke APIs."""
    for path in DEMO_DIR.glob("*.json"):
        try:
            analysis = VideoAnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
            graph, _ = filter_graph(analysis.graph, analysis.transcript)
            analysis = analysis.model_copy(update={"graph": graph})
            JOBS[analysis.video_id] = {"status": "completed", "result": analysis, "demo": True}
        except Exception as error:  # A malformed demo must not stop service startup.
            logger.warning("Could not load demo %s: %s", path.name, error)


def _process_upload(job_id: str, path: Path, title: str, model: str) -> None:
    """Run the blocking pipeline after `/process` has returned its job ID."""
    JOBS[job_id]["status"] = "processing"
    try:
        extension = path.suffix.casefold()
        if extension in {".srt", ".vtt"}:
            segments = parse_vtt_or_srt(path.read_text(encoding="utf-8"))
            duration = segments[-1].end if segments else 0.0
        else:
            duration = get_media_duration(str(path))
            audio_path = ingest_media(str(path), output_wav_path=str(path.with_suffix(".wav")))
            segments = transcribe(audio_path)
        if duration > MAX_VIDEO_DURATION_SEC:
            raise ValueError(f"Video duration exceeds {MAX_VIDEO_DURATION_SEC:.0f} seconds")

        chunks = chunk_transcript(segments)
        raw_graph = extract_full_graph(chunks, segments, model=model)
        graph = resolve_knowledge_graph(raw_graph)
        graph, _ = filter_graph(graph, segments)
        summary, chapters = generate_chapters_and_summary(chunks, graph=graph, model=model)
        JOBS[job_id] = {
            "status": "completed",
            "result": VideoAnalysisResult(
                video_id=job_id,
                title=title,
                duration=duration,
                summary=summary,
                transcript=segments,
                chapters=chapters,
                graph=graph,
            ),
            "demo": False,
        }
    except Exception as error:
        logger.exception("Job %s failed", job_id)
        JOBS[job_id] = {"status": "failed", "error": str(error), "demo": False}


@app.on_event("startup")
def load_demos() -> None:
    _read_demo_results()


@app.get("/", response_class=HTMLResponse)
def serve_index() -> HTMLResponse:
    index = STATIC_DIR / "index.html"
    return HTMLResponse(index.read_text(encoding="utf-8")) if index.exists() else HTMLResponse("<h1>videograph</h1>")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "app": "videograph"}


@app.post("/process", status_code=202)
async def process(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = Form("gemma-4-it"),
) -> Dict[str, str]:
    """Save a bounded upload and enqueue analysis without blocking the response."""
    job_id = uuid.uuid4().hex
    filename = Path(file.filename or "upload").name
    destination = UPLOAD_DIR / f"{job_id}_{filename}"
    written = 0
    try:
        with destination.open("wb") as output:
            while block := await file.read(1024 * 1024):
                written += len(block)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload exceeds 100 MB limit")
                output.write(block)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    JOBS[job_id] = {"status": "queued", "demo": False}
    background_tasks.add_task(_process_upload, job_id, destination, filename, model)
    return {"job_id": job_id, "status": "queued"}


def _job_or_404(job_id: str) -> Dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/status/{job_id}")
def status(job_id: str) -> Dict[str, Any]:
    job = _job_or_404(job_id)
    response = {"job_id": job_id, "status": job["status"], "demo": job.get("demo", False)}
    if job["status"] == "failed":
        response["error"] = job["error"]
    return response


@app.get("/result/{job_id}")
def result(job_id: str) -> Dict[str, Any]:
    job = _job_or_404(job_id)
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job is {job['status']}")
    analysis: VideoAnalysisResult = job["result"]
    return {
        "video_id": analysis.video_id,
        "title": analysis.title,
        "duration": analysis.duration,
        "transcript": [segment.model_dump() for segment in analysis.transcript],
        "chapters": [chapter.model_dump() for chapter in analysis.chapters],
        "summary": analysis.summary,
        "graph": analysis.graph.model_dump(),
        "grounding": _grounding_stats(analysis),
        "demo": job.get("demo", False),
    }


@app.post("/ask", response_model=QAResponse)
def ask(request: AskRequest) -> QAResponse:
    job = _job_or_404(request.job_id)
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job is {job['status']}")
    analysis: VideoAnalysisResult = job["result"]
    return answer_question(request.question, analysis.transcript, graph=analysis.graph, model=request.model)

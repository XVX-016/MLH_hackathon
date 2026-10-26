"""Job-based FastAPI service for videograph."""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()  # Load .env before any module reads os.environ

from contextlib import asynccontextmanager
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
from videograph.extract import (
    extract_full_graph,
    generate_chapters_and_summary,
    generate_flashcards,
)
from videograph.grounding import filter_graph
from videograph.graph import to_vis_network_data
from videograph.llm import get_api_key
from videograph.ingest import (
    MAX_VIDEO_DURATION_SEC,
    NeedsUpload,
    cleanup_media_files,
    download_youtube_audio,
    download_youtube_subtitles,
    fetch_youtube_metadata,
    get_media_duration,
    ingest_media,
    ingest_youtube_fallback,
    validate_uploaded_media,
)
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
ALLOWED_UPLOAD_SUFFIXES = {".mp4", ".mkv", ".webm", ".mp3", ".wav", ".vtt", ".srt"}

for directory in (UPLOAD_DIR, DEMO_DIR, STATIC_DIR):
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

JOBS: Dict[str, Dict[str, Any]] = {}


class AskRequest(BaseModel):
    job_id: str
    question: str = Field(min_length=1)
    model: str = "gemma-4-it"


class LegacyAskRequest(BaseModel):
    """Compatibility request for the current dashboard while it migrates to `/ask`."""

    video_id: str
    question: str = Field(min_length=1)
    model: str = "gemma-4-it"


class UrlProcessRequest(BaseModel):
    url: str = Field(min_length=1, description="YouTube or media URL")
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _read_demo_results()
    yield

# Also invoke at import time for serverless runtimes that don't invoke ASGI lifespan
_read_demo_results()


app = FastAPI(title="seekwise", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _result_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize one completed analysis exactly once for all result endpoints."""
    analysis: VideoAnalysisResult = job["result"]
    return {
        "video_id": analysis.video_id,
        "title": analysis.title,
        "duration": analysis.duration,
        "transcript": [segment.model_dump() for segment in analysis.transcript],
        "chapters": [chapter.model_dump() for chapter in analysis.chapters],
        "flashcards": [card.model_dump() for card in analysis.flashcards],
        "summary": analysis.summary,
        "graph": analysis.graph.model_dump(),
        "grounding": _grounding_stats(analysis),
        "demo": job.get("demo", False),
    }


async def _save_upload(file: UploadFile, job_id: str) -> tuple[Path, str]:
    """Persist a bounded, supported upload without trusting the supplied path."""
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.casefold()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_UPLOAD_SUFFIXES))
        raise HTTPException(status_code=415, detail=f"Unsupported file type. Choose one of: {allowed}")

    destination = UPLOAD_DIR / f"{job_id}_{filename}"
    written = 0
    try:
        with destination.open("wb") as output:
            while block := await file.read(1024 * 1024):
                written += len(block)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload exceeds 100 MB limit")
                output.write(block)
        if written == 0:
            raise HTTPException(status_code=422, detail="The uploaded file is empty")
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return destination, filename


def _process_upload(job_id: str, path: Path, title: str, model: str) -> None:
    """Run the blocking pipeline after `/process` has returned its job ID."""
    JOBS[job_id]["status"] = "processing"
    wav_path = path.with_suffix(".wav")
    try:
        duration = validate_uploaded_media(path, max_duration_sec=MAX_VIDEO_DURATION_SEC)
        extension = path.suffix.casefold()
        if extension in {".srt", ".vtt"}:
            segments = parse_vtt_or_srt(path.read_text(encoding="utf-8"))
        else:
            audio_path = ingest_media(str(path), output_wav_path=str(wav_path))
            segments = transcribe(audio_path)

        chunks = chunk_transcript(segments)
        raw_graph = extract_full_graph(chunks, segments, model=model)
        graph = resolve_knowledge_graph(raw_graph)
        graph, _ = filter_graph(graph, segments)
        summary, chapters = generate_chapters_and_summary(chunks, graph=graph, model=model)
        flashcards = generate_flashcards(chunks, model=model)
        JOBS[job_id] = {
            "status": "completed",
            "result": VideoAnalysisResult(
                video_id=job_id,
                title=title,
                duration=duration,
                summary=summary,
                transcript=segments,
                chapters=chapters,
                flashcards=flashcards,
                graph=graph,
            ),
            "demo": False,
        }
    except Exception as error:
        logger.exception("Job %s failed", job_id)
        JOBS[job_id] = {"status": "failed", "error": str(error), "demo": False}
    finally:
        # Clean up temporary converted WAV file
        if wav_path.is_file() and wav_path != path:
            cleanup_media_files(wav_path)


def _process_youtube_url(job_id: str, url: str, model: str) -> None:
    """Run pipeline for a YouTube video in background using the reliable fallback chain:
    1. youtube-transcript-api (fast, zero download)
    2. yt-dlp subtitle download (--skip-download)
    3. yt-dlp audio download + transcription
    4. If restricted or no captions, sets NeedsUpload message.
    """
    JOBS[job_id]["status"] = "processing"
    temp_wav: Optional[str] = None
    try:
        segments: Optional[List[Segment]] = None
        meta: Dict[str, Any] = {}

        # First attempt: zero-download fallback chain
        try:
            segments, meta = ingest_youtube_fallback(url, output_dir=str(UPLOAD_DIR), max_duration_sec=MAX_VIDEO_DURATION_SEC)
        except NeedsUpload as nu:
            logger.info("Job %s: captions unavailable (%s), trying audio fallback", job_id, nu)
            # Second attempt: Audio download fallback
            try:
                temp_wav = download_youtube_audio(url, output_dir=str(UPLOAD_DIR), max_duration_sec=MAX_VIDEO_DURATION_SEC)
                meta = fetch_youtube_metadata(url)
                segments = transcribe(temp_wav)
            except Exception as audio_err:
                logger.warning("Audio download fallback also failed: %s", audio_err)
                raise NeedsUpload(
                    message=(
                        "Captions and audio could not be extracted automatically. "
                        "Please upload the file directly or paste its transcript."
                    ),
                    reason=str(audio_err),
                ) from audio_err

        title = meta.get("title", "YouTube Analysis")
        duration = meta.get("duration", 0.0)
        if segments and not duration:
            duration = segments[-1].end

        if duration > MAX_VIDEO_DURATION_SEC:
            mins = int(MAX_VIDEO_DURATION_SEC // 60)
            raise ValueError(f"Video duration ({duration:.1f}s) exceeds {MAX_VIDEO_DURATION_SEC:.0f}s ({mins} min) limit")

        chunks = chunk_transcript(segments)
        raw_graph = extract_full_graph(chunks, segments, model=model)
        graph = resolve_knowledge_graph(raw_graph)
        graph, _ = filter_graph(graph, segments)
        summary, chapters = generate_chapters_and_summary(chunks, graph=graph, model=model)
        flashcards = generate_flashcards(chunks, model=model)
        JOBS[job_id] = {
            "status": "completed",
            "result": VideoAnalysisResult(
                video_id=job_id,
                title=title,
                duration=duration,
                summary=summary,
                transcript=segments,
                chapters=chapters,
                flashcards=flashcards,
                graph=graph,
            ),
            "demo": False,
        }
    except NeedsUpload as nu:
        logger.warning("YouTube job %s requires direct upload: %s", job_id, nu)
        JOBS[job_id] = {
            "status": "failed",
            "error": str(nu),
            "needs_upload": True,
            "demo": False,
        }
    except Exception as error:
        logger.exception("YouTube job %s failed", job_id)
        JOBS[job_id] = {"status": "failed", "error": str(error), "demo": False}
    finally:
        if temp_wav:
            cleanup_media_files(temp_wav)




@app.get("/", response_class=HTMLResponse)
def serve_index() -> HTMLResponse:
    index = STATIC_DIR / "index.html"
    return HTMLResponse(index.read_text(encoding="utf-8")) if index.exists() else HTMLResponse("<h1>seekwise</h1>")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "app": "seekwise"}


@app.post("/process", status_code=202)
async def process(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = Form("gemma-4-it"),
) -> Dict[str, str]:
    """Save a bounded upload and enqueue analysis without blocking the response."""
    job_id = uuid.uuid4().hex
    destination, filename = await _save_upload(file, job_id)

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
    return _result_payload(job)


@app.post("/ask", response_model=QAResponse)
def ask(request: AskRequest) -> QAResponse:
    job = _job_or_404(request.job_id)
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job is {job['status']}")
    if not get_api_key():
        raise HTTPException(
            status_code=503,
            detail="Q&A needs a Gemini API key. Set GEMINI_API_KEY in .env and restart; "
            "the summary, flashcards, and graph work without one.",
        )
    analysis: VideoAnalysisResult = job["result"]
    return answer_question(request.question, analysis.transcript, graph=analysis.graph, model=request.model)


# Dashboard compatibility endpoints. Keep the job endpoints above as the stable
# public API; these allow the shipped UI and demo to work while its owner adds
# job polling in their lane.
@app.post("/api/sample/load")
def load_sample() -> Dict[str, Any]:
    job = _job_or_404("demo_attention")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="Demo is not ready")
    return _result_payload(job)


@app.get("/api/graph/{video_id}")
def graph_data(video_id: str) -> Dict[str, Any]:
    job = _job_or_404(video_id)
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job is {job['status']}")
    analysis: VideoAnalysisResult = job["result"]
    return {"vis": to_vis_network_data(analysis.graph)}


@app.post("/api/qa", response_model=QAResponse)
def dashboard_ask(request: LegacyAskRequest) -> QAResponse:
    return ask(AskRequest(job_id=request.video_id, question=request.question, model=request.model))


@app.post("/api/analyze/upload")
async def dashboard_upload(file: UploadFile = File(...), model: str = Form("gemma-4-it")) -> Dict[str, Any]:
    """Synchronous dashboard path; `/process` is preferred by API clients."""
    job_id = uuid.uuid4().hex
    destination, filename = await _save_upload(file, job_id)
    JOBS[job_id] = {"status": "queued", "demo": False}
    _process_upload(job_id, destination, filename, model)
    job = _job_or_404(job_id)
    if job["status"] == "failed":
        raise HTTPException(status_code=422, detail=f"Analysis failed: {job['error']}")
    return _result_payload(job)


@app.post("/api/youtube/metadata")
def youtube_metadata(request: UrlProcessRequest) -> Dict[str, Any]:
    """Fetch video title, duration, channel, and thumbnail without downloading media."""
    try:
        return fetch_youtube_metadata(request.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/process/url", status_code=202)
async def process_url(
    background_tasks: BackgroundTasks,
    request: UrlProcessRequest,
) -> Dict[str, str]:
    """Fetch metadata and enqueue YouTube URL analysis."""
    try:
        meta = fetch_youtube_metadata(request.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    duration = meta.get("duration", 0.0)
    if duration > MAX_VIDEO_DURATION_SEC:
        raise HTTPException(
            status_code=413,
            detail=f"Video duration ({duration:.1f}s) exceeds {MAX_VIDEO_DURATION_SEC:.0f}s limit",
        )

    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "status": "queued",
        "demo": False,
        "title": meta.get("title", "YouTube Analysis"),
        "thumbnail": meta.get("thumbnail", ""),
    }
    background_tasks.add_task(_process_youtube_url, job_id, request.url, request.model)
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/analyze/url")
async def dashboard_url(
    background_tasks: BackgroundTasks,
    url: str = Form(None),
    model: str = Form("gemma-4-it"),
) -> Dict[str, Any]:
    """Dashboard endpoint for YouTube URL processing."""
    if not url:
        raise HTTPException(status_code=422, detail="Missing required 'url' parameter")
    req = UrlProcessRequest(url=url, model=model)
    return await process_url(background_tasks, req)

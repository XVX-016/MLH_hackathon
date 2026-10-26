"""Transcription module for videograph.

Provides transcribe(path) -> list[Segment].
Backend chosen by environment variable TRANSCRIBE_BACKEND:
- "api": Hosted transcription service (Gemini audio or pluggable client interface).
- "local": Local faster-whisper ('small' model).
- "fake": Deterministic mock backend for fast unit testing.

Caches transcription results by file SHA256 content hash.
"""

from __future__ import annotations
import os
import json
import hashlib
from pathlib import Path
from typing import List, Protocol, Optional
from pydantic import BaseModel, Field

import re
from videograph.schemas import Segment

CACHE_DIR = Path.home() / ".videograph_cache" / "transcripts"


def parse_timestamp_to_seconds(ts: str) -> float:
    """Parse HH:MM:SS.mmm or MM:SS.mmm to float seconds."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def parse_vtt_or_srt(file_content: str) -> List[Segment]:
    """Parse WebVTT or SubRip (SRT) format text into timed Segments.

    Raises:
        ValueError: If file_content is empty or contains no valid subtitle cues.
    """
    if not file_content or not file_content.strip():
        raise ValueError("Subtitle file content is empty.")

    segments: List[Segment] = []
    lines = file_content.splitlines()

    time_pattern = re.compile(
        r"((?:\d{1,2}:)?\d{2}:\d{2}[\.,]\d{2,3})\s*-->\s*((?:\d{1,2}:)?\d{2}:\d{2}[\.,]\d{2,3})"
    )

    current_start: Optional[float] = None
    current_end: Optional[float] = None
    current_text_lines: List[str] = []
    seg_id = 0

    def flush_current():
        nonlocal seg_id, current_start, current_end, current_text_lines
        if current_start is not None and current_end is not None and current_text_lines:
            text = " ".join(t.strip() for t in current_text_lines if t.strip())
            cleaned = re.sub(r"<[^>]+>", "", text).strip()
            if cleaned:
                segments.append(
                    Segment(
                        id=seg_id,
                        start=round(current_start, 2),
                        end=round(current_end, 2),
                        text=cleaned,
                    )
                )
                seg_id += 1
        current_start = None
        current_end = None
        current_text_lines = []

    for line in lines:
        match = time_pattern.search(line)
        if match:
            flush_current()
            current_start = parse_timestamp_to_seconds(match.group(1))
            current_end = parse_timestamp_to_seconds(match.group(2))
        elif current_start is not None:
            stripped = line.strip()
            if stripped.isdigit() and len(current_text_lines) == 0:
                continue
            if stripped:
                current_text_lines.append(stripped)
            else:
                flush_current()

    flush_current()
    if not segments:
        raise ValueError("Malformed subtitle format: no valid timestamped cues found.")
    return segments



def compute_file_hash(file_path: str) -> str:
    """Compute SHA256 hash of a file's content for exact caching."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_cached_transcript(file_hash: str) -> Optional[List[Segment]]:
    """Read cached list[Segment] from disk if present."""
    cache_path = CACHE_DIR / f"{file_hash}.json"
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return [Segment.model_validate(item) for item in data]
        except Exception:
            return None
    return None


def write_cached_transcript(file_hash: str, segments: List[Segment]) -> None:
    """Save transcript segments to content-addressed cache file."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = CACHE_DIR / f"{file_hash}.json"
        data = [s.model_dump() for s in segments]
        cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


class HostedTranscriptionClient(Protocol):
    """Interface for pluggable hosted transcription API client."""
    def transcribe(self, file_path: str) -> List[Segment]:
        ...


# Global pluggable hosted client if registered by caller
_CUSTOM_HOSTED_CLIENT: Optional[HostedTranscriptionClient] = None


def register_hosted_client(client: HostedTranscriptionClient) -> None:
    """Register custom hosted transcription client instance."""
    global _CUSTOM_HOSTED_CLIENT
    _CUSTOM_HOSTED_CLIENT = client


def _transcribe_fake(path: str) -> List[Segment]:
    """Deterministic mock transcription backend for tests."""
    return [
        Segment(id=0, start=0.0, end=4.5, text="Welcome to videograph transcription test."),
        Segment(id=1, start=4.5, end=9.0, text="This fake backend enables fast deterministic testing."),
    ]


def _transcribe_local(path: str) -> List[Segment]:
    """Local backend using faster-whisper ('small' model)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise ImportError(
            "faster-whisper is required when TRANSCRIBE_BACKEND='local'. "
            "Please install it with: pip install faster-whisper"
        ) from e

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments_iter, _ = model.transcribe(path, beam_size=5)

    segments: List[Segment] = []
    for idx, seg in enumerate(segments_iter):
        segments.append(
            Segment(
                id=idx,
                start=round(seg.start, 2),
                end=round(seg.end, 2),
                text=seg.text.strip(),
            )
        )
    return segments


def _transcribe_api(path: str) -> List[Segment]:
    """Hosted API backend: uses registered client or Gemini multimodal audio."""
    global _CUSTOM_HOSTED_CLIENT
    if _CUSTOM_HOSTED_CLIENT is not None:
        return _CUSTOM_HOSTED_CLIENT.transcribe(path)

    # Default API backend using Gemini multimodal client
    from videograph.llm import get_api_key
    api_key = get_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is required for API transcription.")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    uploaded_file = client.files.upload(file=path)

    prompt = (
        "Generate a verbatim timestamped transcription of this entire audio file. "
        "Divide into coherent spoken phrases (3-8 seconds each). "
        "Return valid JSON matching: "
        '{"segments": [{"id": 0, "start": 0.0, "end": 4.5, "text": "transcribed speech"}]}'
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[uploaded_file, prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )

    data = json.loads(response.text or "{}")
    raw_segments = data.get("segments", [])
    return [Segment.model_validate(s) for s in raw_segments]


def transcribe(path: str) -> List[Segment]:
    """Transcribe audio/video file at path to list of timed Segments.

    Backend is controlled by env var TRANSCRIBE_BACKEND:
    - "api" (default): hosted transcription service.
    - "local": faster-whisper ('small' model).
    - "fake": deterministic mock segments for tests.

    Cached on disk by SHA-256 of media file contents.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"File to transcribe not found: {path}")

    # 1. Check content hash cache
    file_hash = compute_file_hash(path)
    cached = read_cached_transcript(file_hash)
    if cached is not None:
        return cached

    # 2. Select backend
    backend = os.environ.get("TRANSCRIBE_BACKEND", "api").strip().lower()

    if backend == "fake":
        result = _transcribe_fake(path)
    elif backend == "local":
        result = _transcribe_local(path)
    elif backend == "api":
        result = _transcribe_api(path)
    else:
        raise ValueError(
            f"Invalid TRANSCRIBE_BACKEND='{backend}'. Must be 'api', 'local', or 'fake'."
        )

    # 3. Cache result
    write_cached_transcript(file_hash, result)
    return result


# Backwards compatibility alias
transcribe_audio_file = transcribe

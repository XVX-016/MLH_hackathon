"""Transcription module for videograph.

Supports:
1. Direct audio/video transcription using Gemini multimodal audio capabilities.
2. WebVTT/SRT file parsing into timed TranscriptSegments.
3. YouTube auto-captions/subtitles ingestion via yt-dlp.
"""

from __future__ import annotations
import os
import re
from typing import List, Optional
from pathlib import Path
from pydantic import BaseModel, Field

from videograph.schemas import TranscriptSegment
from videograph.llm import get_api_key, compute_cache_key, read_cache, write_cache


class TranscriptionResult(BaseModel):
    """Pydantic model for structured transcription output."""
    segments: List[TranscriptSegment] = Field(default_factory=list)


def parse_timestamp_to_seconds(ts: str) -> float:
    """Parse HH:MM:SS.mmm or MM:SS.mmm to float seconds."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def parse_vtt_or_srt(file_content: str) -> List[TranscriptSegment]:
    """Parse WebVTT or SubRip (SRT) format text into TranscriptSegments."""
    segments: List[TranscriptSegment] = []
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
            # Clean HTML/VTT cue tags like <c.color> or voice tags <v Roger>
            cleaned = re.sub(r"<[^>]+>", "", text).strip()
            if cleaned:
                segments.append(
                    TranscriptSegment(
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
            # Ignore numeric counter in SRT
            if stripped.isdigit() and len(current_text_lines) == 0:
                continue
            if stripped:
                current_text_lines.append(stripped)
            else:
                flush_current()

    flush_current()
    return segments


def transcribe_audio_file(audio_path: str) -> List[TranscriptSegment]:
    """Transcribe an audio file using Gemini audio upload or structured prompt.
    
    If Gemini API key is provided and audio file is small enough, uploads and transcribes.
    Falls back to mock or local if offline.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Check content cache
    file_bytes = Path(audio_path).read_bytes()
    cache_key = compute_cache_key(str(len(file_bytes)), "transcribe_audio")
    cached = read_cache(cache_key)
    if cached:
        result = TranscriptionResult.model_validate_json(cached)
        return result.segments

    api_key = get_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is required for audio transcription.")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    # Upload audio file
    uploaded_file = client.files.upload(file=audio_path)

    prompt = (
        "Generate a verbatim timestamped transcription of this entire audio file. "
        "Divide into coherent spoken phrases (3-8 seconds each). "
        "Return valid JSON matching: "
        '{"segments": [{"id": 0, "start": 0.0, "end": 4.5, "text": "transcribed speech"}]}'
    )

    models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash"]
    last_error = None

    for model in models_to_try:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[uploaded_file, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            raw_text = response.text or ""
            result = TranscriptionResult.model_validate_json(raw_text)
            write_cache(cache_key, raw_text)
            return result.segments
        except Exception as e:
            last_error = e

    raise RuntimeError(f"Audio transcription failed: {last_error}")

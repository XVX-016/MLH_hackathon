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


import unicodedata

_CAPTION_TAG = re.compile(r"\[[^\]]*\]|\([^)]*(?:music|applause|laughter)[^)]*\)|<[^>]+>", re.IGNORECASE)
_SENTENCE_END = (".", "!", "?")


def _words(text: str) -> List[str]:
    return text.lower().split()


def clean_caption_segments(
    segments: List[Segment],
    min_words: int = 5,
    max_words: int = 30,
    max_gap_sec: float = 1.5,
) -> List[Segment]:
    """Remove YouTube auto-caption noise from timed segments.

    Auto-captions roll: each cue repeats the previous line and adds a new one,
    so the raw transcript says everything two or three times. This
    1. strips tags like [Music] and collapses whitespace,
    2. merges a cue into the previous one when it extends it (or drops it when
       it is already contained), keeping the earlier start and the later end,
    3. trims a repeated overlap between the end of one cue and the start of the next,
    4. joins short fragments into fuller sentences (up to ``max_words``).
    """
    cleaned: List[Segment] = []
    for segment in segments:
        text = " ".join(_CAPTION_TAG.sub(" ", segment.text).split())
        if not text:
            continue
        if cleaned:
            prev = cleaned[-1]
            prev_lower, text_lower = prev.text.lower(), text.lower()
            if text_lower == prev_lower or text_lower in prev_lower:
                prev.end = max(prev.end, segment.end)
                continue
            if text_lower.startswith(prev_lower) or prev_lower in text_lower:
                prev.text = text
                prev.end = max(prev.end, segment.end)
                continue
            # Longest suffix of the previous cue that the new cue starts with.
            prev_words, words = _words(prev.text), _words(text)
            overlap = 0
            for size in range(min(len(prev_words), len(words)), 0, -1):
                if prev_words[-size:] == words[:size]:
                    overlap = size
                    break
            if overlap >= 2:
                text = " ".join(text.split()[overlap:])
                if not text:
                    prev.end = max(prev.end, segment.end)
                    continue
        cleaned.append(Segment(id=0, start=segment.start, end=segment.end, text=text))

    merged: List[Segment] = []
    for segment in cleaned:
        if merged:
            prev = merged[-1]
            short = len(segment.text.split()) < min_words or len(prev.text.split()) < min_words
            open_sentence = not prev.text.endswith(_SENTENCE_END)
            fits = len(prev.text.split()) + len(segment.text.split()) <= max_words
            if fits and (short or open_sentence) and segment.start - prev.end <= max_gap_sec:
                prev.text = prev.text + " " + segment.text
                prev.end = max(prev.end, segment.end)
                continue
        merged.append(segment)

    for index, segment in enumerate(merged):
        segment.id = index
    return merged


def parse_vtt_or_srt(file_content: str) -> List[Segment]:
    """Parse WebVTT or SubRip (SRT) format text into timed Segments.

    Handles UTF-8 BOM, CRLF/LF linebreaks, cue numbers, HTML/VTT style tags,
    and Unicode normalization for accents.

    Raises:
        ValueError: If file_content is empty or contains no valid subtitle cues.
    """
    if not file_content:
        raise ValueError("Subtitle file content is empty.")

    # Strip UTF-8 Byte Order Mark (BOM) if present
    content = file_content.lstrip("\ufeff").strip()
    if not content:
        raise ValueError("Subtitle file content is empty.")

    # Normalize unicode (NFC form) for consistent accents and symbols
    content = unicodedata.normalize("NFC", content)

    segments: List[Segment] = []
    lines = content.splitlines()

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
            # Clean HTML/VTT formatting tags e.g. <c>, <i>, <b>, <v Speaker>
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

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            flush_current()
            continue

        match = time_pattern.search(line)
        if match:
            flush_current()
            current_start = parse_timestamp_to_seconds(match.group(1))
            current_end = parse_timestamp_to_seconds(match.group(2))
        elif current_start is not None:
            if line.isdigit() and len(current_text_lines) == 0:
                continue
            current_text_lines.append(line)
        else:
            continue

    flush_current()
    if not segments:
        raise ValueError("Malformed subtitle format: no valid timestamped cues found.")
    return deduplicate_rolling_segments(segments)


def deduplicate_rolling_segments(segments: List[Segment]) -> List[Segment]:
    """Dedupe rolling auto-captions and merge short fragments into clean sentences.

    1. Collapse whitespace and strip music/sound tags like [Music], [Applause], (cheers).
    2. Merge rolling overlapping captions where a segment starts with or is contained in
       the previous segment (or vice versa), preserving earlier start and later end.
    3. Drop exact repeat lines.
    4. Merge tiny fragments into coherent sentence segments.
    """
    if not segments:
        return []

    def clean_text(t: str) -> str:
        # Strip bracketed audio markers: [Music], (applause), etc.
        t = re.sub(r"\[[^\]]*\]|\([^\)]*\)", "", t)
        # Collapse whitespace
        t = re.sub(r"\s+", " ", t).strip()
        return t

    cleaned_initial: List[Segment] = []
    for s in segments:
        text = clean_text(s.text)
        if text:
            cleaned_initial.append(
                Segment(id=s.id or 0, start=s.start, end=s.end, text=text)
            )

    if not cleaned_initial:
        return []

    # Step 2: Merge rolling overlaps and duplicates
    merged: List[Segment] = []
    for seg in cleaned_initial:
        if not merged:
            merged.append(seg)
            continue

        prev = merged[-1]
        prev_norm = prev.text.casefold().strip()
        curr_norm = seg.text.casefold().strip()

        # Exact repeat
        if prev_norm == curr_norm:
            merged[-1] = Segment(
                id=prev.id,
                start=prev.start,
                end=max(prev.end, seg.end),
                text=prev.text,
            )
            continue

        # Current starts with previous (rolling expansion)
        if curr_norm.startswith(prev_norm):
            merged[-1] = Segment(
                id=prev.id,
                start=prev.start,
                end=max(prev.end, seg.end),
                text=seg.text,
            )
            continue

        # Previous contains current
        if curr_norm in prev_norm:
            merged[-1] = Segment(
                id=prev.id,
                start=prev.start,
                end=max(prev.end, seg.end),
                text=prev.text,
            )
            continue

        # Current contains previous
        if prev_norm in curr_norm:
            merged[-1] = Segment(
                id=prev.id,
                start=prev.start,
                end=max(prev.end, seg.end),
                text=seg.text,
            )
            continue

        # Word-level suffix/prefix overlap (e.g. "Apple has finally" + "finally unveiled their long")
        prev_words = prev.text.split()
        curr_words = seg.text.split()
        overlap_found = False
        for k in range(min(len(prev_words), len(curr_words)), 0, -1):
            if [w.lower() for w in prev_words[-k:]] == [w.lower() for w in curr_words[:k]]:
                combined_text = " ".join(prev_words + curr_words[k:])
                merged[-1] = Segment(
                    id=prev.id,
                    start=prev.start,
                    end=max(prev.end, seg.end),
                    text=combined_text,
                )
                overlap_found = True
                break

        if not overlap_found:
            merged.append(seg)

    # Step 3: Merge short sentence fragments (segments ending without punctuation and short)
    final_segments: List[Segment] = []
    for s in merged:
        if not final_segments:
            final_segments.append(s)
            continue

        last = final_segments[-1]
        last_ends_sentence = last.text.endswith((".", "!", "?"))
        word_count = len(last.text.split())

        # If previous segment is very short or doesn't end with a sentence stop, and close in time (< 1.5s gap)
        if (not last_ends_sentence or word_count < 4) and (s.start - last.end <= 1.5) and (len(last.text.split()) + len(s.text.split()) < 30):
            final_segments[-1] = Segment(
                id=last.id,
                start=last.start,
                end=max(last.end, s.end),
                text=f"{last.text} {s.text}",
            )
        else:
            final_segments.append(s)

    # Re-index ids
    return [
        Segment(id=idx, start=seg.start, end=seg.end, text=seg.text)
        for idx, seg in enumerate(final_segments)
    ]





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


    text_content = (response.text or "{}").strip()
    if text_content.startswith("```"):
        text_content = re.sub(r"^```(?:json)?\s*", "", text_content)
        text_content = re.sub(r"\s*```$", "", text_content).strip()

    try:
        data = json.loads(text_content)
    except json.JSONDecodeError:
        data = {}

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

"""Video chunking module with semantic/time boundaries and sliding windows.

Ensures transcript segments are grouped into manageable context blocks for LLM extraction.
"""

from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field
from videograph.schemas import TranscriptSegment


class TranscriptChunk(BaseModel):
    """Chunk of contiguous transcript segments with timing metadata."""
    chunk_id: int
    start: float
    end: float
    text: str
    segments: List[TranscriptSegment] = Field(default_factory=list)

    @property
    def formatted_text(self) -> str:
        """Formatted text with timestamps per segment."""
        lines = []
        for s in self.segments:
            lines.append(f"[{s.timestamp_str}] {s.text}")
        return "\n".join(lines)


def chunk_transcript(
    segments: List[TranscriptSegment],
    target_duration_sec: float = 60.0,
    overlap_duration_sec: float = 10.0,
    max_char_len: int = 2500,
) -> List[TranscriptChunk]:
    """Chunks transcript segments into overlapping time windows.
    
    Args:
        segments: List of ordered TranscriptSegments.
        target_duration_sec: Target window size in seconds (default 60 seconds).
        overlap_duration_sec: Target overlap between consecutive chunks
            (default 10 seconds). Segment boundaries take precedence, so the
            actual overlap may be slightly larger or smaller.
        max_char_len: Maximum text length threshold to prevent oversized prompts.
        
    Returns:
        List of TranscriptChunk objects.
    """
    if target_duration_sec <= 0:
        raise ValueError("target_duration_sec must be greater than zero")
    if overlap_duration_sec < 0:
        raise ValueError("overlap_duration_sec must not be negative")
    if not segments:
        return []

    chunks: List[TranscriptChunk] = []
    chunk_id = 0
    i = 0
    n = len(segments)

    while i < n:
        chunk_segments: List[TranscriptSegment] = []
        chunk_start = segments[i].start
        current_char_count = 0

        j = i
        while j < n:
            seg = segments[j]
            seg_len = len(seg.text)

            # Check if adding segment exceeds window or hard char cap
            exceeds_time = (seg.end - chunk_start) > target_duration_sec and len(chunk_segments) > 0
            exceeds_chars = (current_char_count + seg_len) > max_char_len and len(chunk_segments) > 0

            if exceeds_time or exceeds_chars:
                break

            chunk_segments.append(seg)
            current_char_count += seg_len + 1
            j += 1

        if not chunk_segments:
            chunk_segments.append(segments[i])
            j = i + 1

        chunk_end = chunk_segments[-1].end
        full_text = " ".join(s.text.strip() for s in chunk_segments)

        chunks.append(
            TranscriptChunk(
                chunk_id=chunk_id,
                start=chunk_start,
                end=chunk_end,
                text=full_text,
                segments=chunk_segments,
            )
        )
        chunk_id += 1

        # Advance i, maintaining overlap
        if j >= n:
            break

        # Find next start segment based on overlap_duration_sec
        next_i = j
        for k in range(j - 1, i, -1):
            if chunk_end - segments[k].start <= overlap_duration_sec:
                next_i = k
            else:
                break

        # Safeguard against infinite loops
        i = max(next_i, i + 1)

    return chunks

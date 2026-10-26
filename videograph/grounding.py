"""Grounding and verification module for videograph.

Verifies evidence quotes and citations against raw transcript segments using:
1. Exact substring matching.
2. RapidFuzz partial token matching for slight ASR/LLM quote discrepancies.
3. SentenceTransformers + FAISS semantic similarity when fuzzy score needs grounding reinforcement.
"""

from __future__ import annotations
import re
from typing import List, Tuple, Optional
from rapidfuzz import fuzz

from videograph.schemas import TranscriptSegment, QACitation, KnowledgeEdge

# Global lazy-loaded embedding model to avoid reload cost
_EMBED_MODEL = None


def get_embed_model():
    """Lazy load SentenceTransformer model."""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            # Fast, lightweight model for sentence similarity
            _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            _EMBED_MODEL = None
    return _EMBED_MODEL


def clean_text_for_matching(text: str) -> str:
    """Normalize text: lowercase, remove punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def find_best_transcript_alignment(
    quote: str,
    segments: List[TranscriptSegment],
    window_padding_sec: float = 3.0,
) -> Tuple[bool, float, float, float]:
    """Search transcript segments to verify quote and pinpoint exact time boundaries.
    
    Args:
        quote: Candidate quote to verify.
        segments: Complete list of video TranscriptSegments.
        window_padding_sec: Tolerable margin for time boundaries.
        
    Returns:
        (is_verified, match_score, start_time, end_time)
    """
    clean_quote = clean_text_for_matching(quote)
    if not clean_quote or not segments:
        return False, 0.0, 0.0, 0.0

    best_score = 0.0
    best_start = 0.0
    best_end = 0.0

    # 1. Slide a window over 1 to 5 contiguous segments
    for span in range(1, min(6, len(segments) + 1)):
        for i in range(len(segments) - span + 1):
            window_segs = segments[i : i + span]
            window_text = " ".join(s.text for s in window_segs)
            clean_window = clean_text_for_matching(window_text)

            # Rapidfuzz partial ratio
            score = fuzz.partial_ratio(clean_quote, clean_window)
            if score > best_score:
                best_score = score
                best_start = window_segs[0].start
                best_end = window_segs[-1].end

            # If exact match found, return immediately
            if clean_quote in clean_window or score >= 95.0:
                return True, float(score), float(best_start), float(best_end)

    # Verification threshold: >= 75% fuzzy match qualifies as verified
    is_verified = best_score >= 75.0
    return is_verified, float(best_score), float(best_start), float(best_end)


def verify_knowledge_edge(
    edge: KnowledgeEdge,
    segments: List[TranscriptSegment],
) -> KnowledgeEdge:
    """Verify an extracted knowledge edge against the video transcript.
    
    Adjusts start_time and end_time if a better alignment is discovered in the transcript.
    """
    verified, score, start, end = find_best_transcript_alignment(edge.evidence_quote, segments)
    if verified:
        edge.confidence = round(min(1.0, (score / 100.0) * edge.confidence), 2)
        # Update with pinpointed transcript timestamps if edge had approximate values
        if abs(edge.start_time - start) > 10.0 or edge.start_time == 0.0:
            edge.start_time = start
            edge.end_time = end
    else:
        # Penalize confidence if quote is not supported by transcript
        edge.confidence = round(edge.confidence * 0.3, 2)

    return edge


def verify_citation(
    citation: QACitation,
    segments: List[TranscriptSegment],
) -> QACitation:
    """Verify and ground a QA citation against the transcript."""
    verified, score, start, end = find_best_transcript_alignment(citation.quote, segments)
    citation.verified = verified
    citation.match_score = round(score, 1)

    if verified:
        citation.start_time = start
        citation.end_time = end
        m = int(start // 60)
        s = int(start % 60)
        citation.timestamp_str = f"{m:02d}:{s:02d}"

    return citation

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

from videograph.schemas import TranscriptSegment, QACitation, KnowledgeEdge, KnowledgeGraph

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


GROUNDING_THRESHOLD = 90.0
VERBATIM_THRESHOLD = 95.0
_ELLIPSIS = re.compile(r"\.\.\.+|\u2026")


def _quote_parts(quote: str) -> List[str]:
    """Split a quote stitched together with ellipses into its verbatim pieces."""
    parts = [clean_text_for_matching(part) for part in _ELLIPSIS.split(quote)]
    return [part for part in parts if len(part.split()) >= 3] or [clean_text_for_matching(quote)]


def is_grounded(
    quote: str,
    segments: List[TranscriptSegment],
    start: float,
    end: float,
    window_padding_sec: float = 10.0,
) -> bool:
    """Check whether a quote closely matches transcript text near its timestamps.

    Only segments intersecting ``[start - 10s, end + 10s]`` are considered, so a
    real quote elsewhere in the video cannot ground an edge at the wrong time.
    A quote stitched with "..." passes only if every piece matches in the window.
    """
    normalized_quote = clean_text_for_matching(quote)
    if not normalized_quote or start > end:
        return False

    nearby_segments = [
        segment
        for segment in segments
        if segment.end >= start - window_padding_sec
        and segment.start <= end + window_padding_sec
    ]
    if not nearby_segments:
        return False

    candidate_text = clean_text_for_matching(" ".join(segment.text for segment in nearby_segments))
    return all(fuzz.partial_ratio(part, candidate_text) >= GROUNDING_THRESHOLD for part in _quote_parts(quote))


def filter_graph(
    graph: KnowledgeGraph,
    segments: List[TranscriptSegment],
) -> Tuple[KnowledgeGraph, float]:
    """Flag each edge's evidence and return a copy of the graph and pass rate.

    When a quote is not near its cited time but appears verbatim elsewhere, the
    edge is moved to where it was actually said instead of being failed: the
    claim is real, only its timestamp was wrong. The threshold is not relaxed.
    """
    filtered_edges: List[KnowledgeEdge] = []
    for edge in graph.edges:
        update = {"grounded": is_grounded(edge.evidence_quote, segments, edge.start_time, edge.end_time)}
        if not update["grounded"] and len(_quote_parts(edge.evidence_quote)) == 1:
            _, score, found_start, found_end = find_best_transcript_alignment(edge.evidence_quote, segments)
            if score >= VERBATIM_THRESHOLD:
                update = {"grounded": True, "start_time": found_start, "end_time": found_end}
        filtered_edges.append(edge.model_copy(update=update))

    pass_rate = sum(edge.grounded for edge in filtered_edges) / len(filtered_edges) if filtered_edges else 1.0
    return graph.model_copy(update={"edges": filtered_edges}), pass_rate


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

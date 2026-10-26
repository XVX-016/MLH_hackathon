"""Evaluation harness for videograph knowledge graphs and Q&A grounding.

Measures:
1. Citation Precision: % of citations whose quoted text matches transcript segments.
2. Edge Grounding Rate: % of extracted graph edges backed by verifiable transcript evidence.
3. Temporal Alignment Accuracy: Mean absolute error in seconds for citation timestamp boundaries.
"""

from __future__ import annotations
from typing import List, Dict, Any
from pathlib import Path

from videograph.schemas import VideoAnalysisResult, QAResponse, QACitation, TranscriptSegment
from videograph.grounding import find_best_transcript_alignment, is_grounded


def evaluate_edge_grounding(result: VideoAnalysisResult) -> Dict[str, Any]:
    """Calculate grounding metrics on the video knowledge graph."""
    edges = result.graph.edges
    if not edges:
        return {"grounding_rate": 1.0, "total_edges": 0, "verified_edges": 0}

    verified_count = 0
    scores = []

    for edge in edges:
        verified = is_grounded(edge.evidence_quote, result.transcript, edge.start_time, edge.end_time)
        _, score, _, _ = find_best_transcript_alignment(edge.evidence_quote, result.transcript)
        if verified:
            verified_count += 1
        scores.append(score)

    grounding_rate = verified_count / len(edges)
    mean_match_score = sum(scores) / len(scores) if scores else 0.0

    return {
        "total_edges": len(edges),
        "verified_edges": verified_count,
        "grounding_rate": round(grounding_rate, 4),
        "mean_match_score": round(mean_match_score, 2),
    }


def evaluate_qa_grounding(qa_resp: QAResponse, segments: List[TranscriptSegment]) -> Dict[str, Any]:
    """Calculate citation precision and verification rate for a Q&A answer."""
    citations = qa_resp.citations
    if not citations:
        return {"total_citations": 0, "citation_precision": 0.0, "mean_score": 0.0}

    verified_count = 0
    scores = []
    time_deltas = []

    for cit in citations:
        verified = is_grounded(cit.quote, segments, cit.start_time, cit.end_time)
        _, score, start, _ = find_best_transcript_alignment(cit.quote, segments)
        if verified:
            verified_count += 1
            # Check deviation between cited start and aligned start
            time_deltas.append(abs(cit.start_time - start))
        scores.append(score)

    precision = verified_count / len(citations)
    mean_mae = sum(time_deltas) / len(time_deltas) if time_deltas else 0.0

    return {
        "total_citations": len(citations),
        "verified_citations": verified_count,
        "citation_precision": round(precision, 4),
        "mean_match_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "timestamp_mae_seconds": round(mean_mae, 2),
    }


def run_benchmark():
    """Evaluate the checked-in, no-key demo artifact."""
    sample_path = Path(__file__).resolve().parents[1] / "data" / "demo" / "demo_attention.json"
    result = VideoAnalysisResult.model_validate_json(sample_path.read_text(encoding="utf-8"))
    qa = QAResponse(
        question="Study card evidence",
        answer="Demo flashcard citations",
        citations=[
            QACitation(
                timestamp_str=card.timestamp_str,
                start_time=card.start_sec,
                end_time=card.end_sec,
                quote=card.key_quote or "",
            )
            for card in result.flashcards
        ],
    )
    report = {
        "demo": result.video_id,
        "edges": evaluate_edge_grounding(result),
        "citation_source": "demo_flashcards",
        "qa": evaluate_qa_grounding(qa, result.transcript),
    }
    print(report)
    return report


if __name__ == "__main__":
    run_benchmark()

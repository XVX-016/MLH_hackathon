"""Evaluation harness for videograph knowledge graphs and Q&A grounding.

Measures:
1. Citation Precision: % of citations whose quoted text matches transcript segments.
2. Edge Grounding Rate: % of extracted graph edges backed by verifiable transcript evidence.
3. Temporal Alignment Accuracy: Mean absolute error in seconds for citation timestamp boundaries.
"""

from __future__ import annotations
import json
from typing import List, Dict, Any
from pathlib import Path

from videograph.schemas import VideoAnalysisResult, QAResponse, TranscriptSegment
from videograph.grounding import find_best_transcript_alignment


def evaluate_edge_grounding(result: VideoAnalysisResult) -> Dict[str, Any]:
    """Calculate grounding metrics on the video knowledge graph."""
    edges = result.graph.edges
    if not edges:
        return {"grounding_rate": 1.0, "total_edges": 0, "verified_edges": 0}

    verified_count = 0
    scores = []

    for edge in edges:
        verified, score, _, _ = find_best_transcript_alignment(edge.evidence_quote, result.transcript)
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
        verified, score, start, end = find_best_transcript_alignment(cit.quote, segments)
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
    """Run evaluation on benchmark sample."""
    sample_path = Path("tests") / "sample_benchmark.json"
    print(f"[*] Running evaluation harness on benchmark...")
    # Synthetic verification demo
    segments = [
        TranscriptSegment(id=0, start=0.0, end=10.0, text="Attention mechanisms allow dynamic contextual token weighting."),
        TranscriptSegment(id=1, start=10.0, end=25.0, text="Multi-head projection allows parallel representation subspaces."),
    ]
    qa = QAResponse(
        question="How does multi-head projection help?",
        answer="It enables parallel subspaces [00:10].",
        citations=[{
            "timestamp_str": "00:10",
            "start_time": 10.0,
            "end_time": 25.0,
            "quote": "Multi-head projection allows parallel representation subspaces",
            "verified": True,
            "match_score": 100.0,
        }]
    )
    qa_eval = evaluate_qa_grounding(qa, segments)
    print(f"[+] QA Grounding Metrics: {qa_eval}")
    return qa_eval


if __name__ == "__main__":
    run_benchmark()

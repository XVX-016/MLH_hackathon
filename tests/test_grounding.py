"""Tests for strict timestamp-window grounding."""

from videograph.grounding import filter_graph, is_grounded
from videograph.schemas import KnowledgeEdge, KnowledgeGraph, KnowledgeNode, TranscriptSegment


SEGMENTS = [
    TranscriptSegment(
        id=0,
        start=10.0,
        end=18.0,
        text="Transformers use multi-head self-attention mechanisms for context.",
    )
]


def test_is_grounded_accepts_exact_quote() -> None:
    assert is_grounded("Transformers use multi-head self-attention mechanisms", SEGMENTS, 10.0, 18.0)


def test_is_grounded_accepts_light_paraphrase() -> None:
    assert is_grounded("Transformers use multi head self attention mechanisms", SEGMENTS, 10.0, 18.0)


def test_filter_graph_flags_fabricated_quote_and_reports_rate() -> None:
    graph = KnowledgeGraph(
        nodes=[KnowledgeNode(id="transformer", label="Transformer"), KnowledgeNode(id="attention", label="Attention")],
        edges=[
            KnowledgeEdge(
                source="transformer", target="attention", relation="USES",
                evidence_quote="Transformers use multi-head self-attention mechanisms",
                start_time=10.0, end_time=18.0,
            ),
            KnowledgeEdge(
                source="transformer", target="attention", relation="INVENTED",
                evidence_quote="Transformers were invented on Mars by robots.",
                start_time=10.0, end_time=18.0,
            ),
        ],
    )

    filtered, pass_rate = filter_graph(graph, SEGMENTS)

    assert [edge.grounded for edge in filtered.edges] == [True, False]
    assert pass_rate == 0.5

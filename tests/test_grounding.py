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


LONG_SEGMENTS = [
    TranscriptSegment(id=0, start=0.0, end=8.0, text="Welcome back to the channel, today we test mystery keys."),
    TranscriptSegment(id=1, start=100.0, end=108.0, text="I was just spamming the strength attribute the whole time."),
    TranscriptSegment(id=2, start=200.0, end=208.0, text="I know BioShock is a big game in the series."),
    TranscriptSegment(id=3, start=260.0, end=268.0, text="I did not even know it was a shooter at first."),
]


def _edge(quote: str, start: float, end: float) -> KnowledgeEdge:
    return KnowledgeEdge(source="a", target="b", relation="says", evidence_quote=quote, start_time=start, end_time=end)


def test_verbatim_quote_at_wrong_time_is_moved_not_failed() -> None:
    graph = KnowledgeGraph(nodes=[KnowledgeNode(id="a", label="A"), KnowledgeNode(id="b", label="B")],
                           edges=[_edge("I was just spamming the strength attribute the whole time", 20.0, 25.0)])
    filtered, rate = filter_graph(graph, LONG_SEGMENTS)
    assert rate == 1.0
    assert filtered.edges[0].start_time == 100.0 and filtered.edges[0].end_time == 108.0


def test_ellipsis_stitched_quote_needs_every_piece_near_the_cited_time() -> None:
    stitched = "I did not even know it was a shooter... I know BioShock is a big game"
    assert not is_grounded(stitched, LONG_SEGMENTS, 260.0, 268.0)  # second piece was said 60s earlier
    graph = KnowledgeGraph(nodes=[KnowledgeNode(id="a", label="A"), KnowledgeNode(id="b", label="B")],
                           edges=[_edge(stitched, 260.0, 268.0)])
    filtered, rate = filter_graph(graph, LONG_SEGMENTS)
    assert rate == 0.0 and not filtered.edges[0].grounded  # never re-anchored to a single piece

"""Tests for evidence-preserving NetworkX and vis-network output."""

from videograph.graph import build_networkx_graph, compute_louvain_communities, to_vis_network_data
from videograph.resolve import resolve_chunk_extraction
from videograph.schemas import ChunkExtraction, Entity, Relation


def test_graph_contains_evidence_mentions_communities_and_vis_data() -> None:
    extraction = ChunkExtraction(
        entities=[Entity(name="GPT-4", type="Model"), Entity(name="Transformer", type="Architecture")],
        relations=[
            Relation(
                subject="GPT-4", predicate="USES", object="Transformer",
                quote="GPT-4 uses a Transformer.", start_sec=12.0, end_sec=15.0,
            )
        ],
    )

    graph = build_networkx_graph(resolve_chunk_extraction(extraction))
    edge = next(iter(graph.edges(data=True)))[2]

    assert edge["evidence"] == [{"quote": "GPT-4 uses a Transformer.", "start": 12.0, "end": 15.0}]
    assert graph.nodes["GPT-4"]["mentions"] == [12.0]
    assert set(compute_louvain_communities(extraction)) == {"GPT-4", "Transformer"}

    vis = to_vis_network_data(extraction)
    assert vis["nodes"][0]["size"] > 16
    assert vis["edges"][0]["title"] == "GPT-4 uses a Transformer."
    assert vis["edges"][0]["evidence"][0]["start"] == 12.0

"""Focused contract checks for the Faariz-owned explorer surface."""

from pathlib import Path

from videograph.graph import to_vis_network_data
from videograph.schemas import KnowledgeEdge, KnowledgeGraph, KnowledgeNode


def test_vis_edges_preserve_timestamped_evidence() -> None:
    graph = KnowledgeGraph(
        nodes=[KnowledgeNode(id="a", label="A"), KnowledgeNode(id="b", label="B")],
        edges=[
            KnowledgeEdge(
                source="a",
                target="b",
                relation="USES",
                evidence_quote="A uses B.",
                start_time=12.0,
                end_time=15.0,
                grounded=True,
            )
        ],
    )

    edge = to_vis_network_data(graph)["edges"][0]
    assert edge["from"] == "a"
    assert edge["to"] == "b"
    assert edge["evidence_quote"] == "A uses B."
    assert edge["start_time"] == 12.0


def test_static_explorer_targets_job_api_and_timestamp_controls() -> None:
    javascript = Path("app/static/app.js").read_text(encoding="utf-8")
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    for route in ("/process", "/status/", "/result/", "/ask"):
        assert route in javascript
    for element in ("video-player", "graph-network", "transcript-list", "qa-form"):
        assert element in html
    assert "timeupdate" in javascript
    assert "selectEdge" in javascript
    assert "selectNode" in javascript

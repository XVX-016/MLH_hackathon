"""Focused contract checks for the Faariz-owned explorer surface."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from eval.evaluate import evaluate_edge_grounding, evaluate_qa_grounding, run_benchmark
from videograph.graph import to_vis_network_data
from videograph.schemas import KnowledgeEdge, KnowledgeGraph, KnowledgeNode, QACitation, QAResponse, VideoAnalysisResult


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
    assert 'fetch("/api/youtube/metadata"' in javascript
    for element in ("video-player", "graph-network", "transcript-list", "qa-form", "form-url", "flashcards-list"):
        assert element in html
    for view in ("panel-summary", "panel-flashcards", "panel-graph"):
        assert view in html
    assert "renderFlashcards" in javascript
    assert "selectTab" in javascript
    assert "timeupdate" in javascript
    assert "selectEdge" in javascript
    assert "selectNode" in javascript


def test_landing_page_starts_with_hero_and_hidden_results() -> None:
    with TestClient(app) as client:
        html = client.get("/").text

    assert '<section id="hero"' in html
    assert '<svg class="hero-grid"' in html
    assert 'id="btn-load-sample"' in html
    assert 'id="btn-upload"' in html
    assert 'id="processing-card"' in html
    assert '<div id="results" class="results-view" hidden>' in html


def test_demo_evaluation_rejects_a_quote_at_the_wrong_timestamp() -> None:
    result = VideoAnalysisResult.model_validate_json(Path("data/demo/demo_attention.json").read_text(encoding="utf-8"))
    wrong_edge = result.graph.edges[0].model_copy(update={"start_time": 70.0, "end_time": 76.0})
    wrong_result = result.model_copy(update={"graph": result.graph.model_copy(update={"edges": [wrong_edge]})})
    citation = QACitation(timestamp_str="01:10", start_time=70.0, end_time=76.0, quote=wrong_edge.evidence_quote)
    response = QAResponse(question="What does attention select?", answer="Values", citations=[citation])

    assert evaluate_edge_grounding(wrong_result)["grounding_rate"] == 0.0
    assert evaluate_qa_grounding(response, result.transcript)["citation_precision"] == 0.0


def test_demo_evaluation_has_precise_citations() -> None:
    report = run_benchmark()

    assert report["citation_source"] == "demo_flashcards"
    assert report["qa"]["total_citations"] == 3
    assert report["qa"]["citation_precision"] == 1.0
    assert report["edges"]["grounding_rate"] == 1.0


def test_brand_wordmark_and_favicon_are_served() -> None:
    with TestClient(app) as client:
        html = client.get("/").text
        favicon = client.get("/static/logo.svg")

    assert "<title>seekwise" in html
    assert 'class="wordmark"' in html and "wordmark-seek" in html and "wordmark-i" in html
    assert favicon.status_code == 200
    assert "<svg" in favicon.text


def test_brief_framing_uses_only_fields_in_the_result_payload() -> None:
    javascript = Path("app/static/app.js").read_text(encoding="utf-8")
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    for element in ("brief-glance", "brief-headline", "brief-concepts", "brief-takeaways"):
        assert f'id="{element}"' in html
    assert "function renderBrief" in javascript
    assert "verifiedFlashcards(data.flashcards" in javascript

    with TestClient(app) as client:
        payload = client.get("/result/demo_attention").json()
    # The brief is derived client-side from these existing contract fields.
    for field in ("summary", "duration", "chapters", "flashcards", "transcript", "graph", "grounding"):
        assert field in payload
    assert {"total_edges", "grounded_edges"} <= set(payload["grounding"])


def test_page_routes_and_job_id_are_wired() -> None:
    javascript = Path("app/static/app.js").read_text(encoding="utf-8")
    assert '"hashchange", applyRoute' in javascript
    for page in ("summary", "flashcards", "graph"):
        assert f"{page}:" in javascript.split("var PAGE_TITLES", 1)[1].split("};", 1)[0]
    # /ask is keyed by job id; uploads and URL jobs must pass theirs through.
    assert "currentJobId = jobId || data.video_id" in javascript
    assert "job_id: currentJobId" in javascript

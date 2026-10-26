"""Hardik's contract tests for the complete local demo workflow."""

from fastapi.testclient import TestClient

from app.main import JOBS, app


def test_demo_to_graph_workflow() -> None:
    JOBS.clear()
    with TestClient(app) as client:
        sample = client.post("/api/sample/load")
        assert sample.status_code == 200
        payload = sample.json()
        assert payload["demo"] is True
        assert payload["video_id"] == "demo_attention"
        assert payload["grounding"]["grounding_pass_rate"] == 1.0

        graph = client.get("/api/graph/demo_attention")
        assert graph.status_code == 200
        edge = graph.json()["vis"]["edges"][0]
        assert edge["evidence_quote"]
        assert edge["timestamp_str"] == "00:13"


def test_upload_validation_rejects_unsupported_media() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/process",
            files={"file": ("unsafe.exe", b"not media", "application/octet-stream")},
        )
    assert response.status_code == 415


def test_url_endpoint_explains_the_supported_path() -> None:
    with TestClient(app) as client:
        response = client.post("/api/analyze/url", data={"url": "https://example.com/video.mp4"})
    assert response.status_code == 501
    assert "upload" in response.json()["detail"].lower()

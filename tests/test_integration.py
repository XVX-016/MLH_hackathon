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
        assert payload["grounding"]["grounding_pass_rate"] == 1.0
        assert len(payload["flashcards"]) == 3
        assert "attention" in payload["flashcards"][0]["question"].lower()

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


def test_cli_demo_pipeline(tmp_path) -> None:
    from videograph.cli import process_video_pipeline
    output_path = tmp_path / "cli_demo_output.json"
    result = process_video_pipeline(
        input_source="demo",
        output_path=str(output_path),
        use_demo=True,
    )
    assert result.video_id == "demo_attention"
    assert len(result.transcript) > 0
    assert len(result.chapters) > 0
    assert len(result.graph.edges) > 0
    assert output_path.exists()


def test_cli_rejects_missing_file(tmp_path) -> None:
    import pytest
    from videograph.cli import process_video_pipeline

    with pytest.raises(FileNotFoundError):
        process_video_pipeline(
            input_source=str(tmp_path / "non_existent.mp4"),
            output_path=str(tmp_path / "out.json"),
        )


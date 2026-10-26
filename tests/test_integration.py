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


def test_youtube_metadata_and_url_process_endpoints(monkeypatch) -> None:
    fake_meta = {
        "title": "Attention is All You Need",
        "duration": 120.0,
        "channel": "AI Research",
        "thumbnail": "https://example.com/thumb.jpg",
        "url": "https://www.youtube.com/watch?v=mock_video",
    }
    monkeypatch.setattr("app.main.fetch_youtube_metadata", lambda url: fake_meta)
    monkeypatch.setattr(
        "app.main._process_youtube_url",
        lambda job_id, url, model: JOBS.update({job_id: {"status": "completed", "demo": False}}),
    )

    with TestClient(app) as client:
        # Test metadata endpoint
        meta_res = client.post("/api/youtube/metadata", json={"url": "https://www.youtube.com/watch?v=mock_video"})
        assert meta_res.status_code == 200
        assert meta_res.json()["title"] == "Attention is All You Need"
        assert meta_res.json()["duration"] == 120.0

        # Test process/url endpoint
        proc_res = client.post("/process/url", json={"url": "https://www.youtube.com/watch?v=mock_video"})
        assert proc_res.status_code == 202
        data = proc_res.json()
        assert "job_id" in data
        assert data["status"] == "queued"

        # Check job in status endpoint
        job_id = data["job_id"]
        status_res = client.get(f"/status/{job_id}")
        assert status_res.status_code == 200
        assert status_res.json()["status"] in ("queued", "processing", "completed")


def test_youtube_url_rejects_exceeding_duration(monkeypatch) -> None:
    fake_meta = {
        "title": "Super Long Video",
        "duration": 9999.0,
        "channel": "Long Channel",
        "thumbnail": "",
        "url": "https://www.youtube.com/watch?v=long_video",
    }
    monkeypatch.setattr("app.main.fetch_youtube_metadata", lambda url: fake_meta)

    with TestClient(app) as client:
        res = client.post("/process/url", json={"url": "https://www.youtube.com/watch?v=long_video"})
        assert res.status_code == 413
        assert "exceeds" in res.json()["detail"].lower()


def test_youtube_url_process_handles_needsupload(monkeypatch) -> None:
    from app.main import _process_youtube_url
    from videograph.ingest import NeedsUpload

    JOBS.clear()
    job_id = "test_needs_upload_job"
    JOBS[job_id] = {"status": "queued"}

    # Mock ingest_youtube_fallback to raise NeedsUpload
    def mock_fail(url, **kw):
        raise NeedsUpload("Captions unavailable", reason="no_captions")

    monkeypatch.setattr("app.main.ingest_youtube_fallback", mock_fail)
    # Mock audio fallback also failing
    monkeypatch.setattr(
        "app.main.download_youtube_audio",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Audio restricted")),
    )

    _process_youtube_url(job_id, "https://www.youtube.com/watch?v=mock_no_caps", "gemini-2.5-flash")

    assert JOBS[job_id]["status"] == "failed"
    assert JOBS[job_id].get("needs_upload") is True
    assert "upload the file directly" in JOBS[job_id]["error"].lower()


def test_upload_pipeline_validation_and_cleanup(tmp_path, monkeypatch) -> None:
    from app.main import _process_upload

    JOBS.clear()
    job_id = "test_upload_validation_job"
    JOBS[job_id] = {"status": "queued"}

    # Uploaded media with duration exceeding 15 minutes (960s)
    dummy_media = tmp_path / "long_upload.mp4"
    dummy_media.write_bytes(b"dummy mp4 bytes")

    monkeypatch.setattr("videograph.ingest.get_media_duration", lambda path: 960.0)

    _process_upload(job_id, dummy_media, "Long Video", "gemini-2.5-flash")

    assert JOBS[job_id]["status"] == "failed"
    assert "exceeds maximum allowed 900" in JOBS[job_id]["error"]



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



def test_health_reports_seekwise() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.json() == {"status": "ok", "app": "seekwise"}


def test_ask_without_api_key_explains_instead_of_crashing(monkeypatch) -> None:
    # get_api_key() also reads .env, so stub it rather than the environment.
    monkeypatch.setattr("app.main.get_api_key", lambda: "")
    with TestClient(app) as client:
        response = client.post("/ask", json={"job_id": "demo_attention", "question": "What is attention?"})
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]

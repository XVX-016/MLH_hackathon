"""Smoke tests for the job API and local-only demo result."""

from fastapi.testclient import TestClient

from app.main import JOBS, app


def test_health_and_precomputed_demo_result() -> None:
    JOBS.clear()
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        status = client.get("/status/demo_attention")
        assert status.status_code == 200
        assert status.json()["demo"] is True

        result = client.get("/result/demo_attention")
        assert result.status_code == 200
        payload = result.json()
        assert payload["grounding"]["grounding_pass_rate"] == 1.0
        assert payload["graph"]["edges"][0]["grounded"] is True

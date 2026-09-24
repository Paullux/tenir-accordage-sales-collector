from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_TOKEN


def test_health_is_public(app_client: TestClient):
    resp = app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_status_is_public(app_client: TestClient):
    resp = app_client.get("/v1/status")
    assert resp.status_code == 200


def test_stats_requires_bearer_token(app_client: TestClient):
    resp = app_client.get("/v1/stats")
    assert resp.status_code == 401


def test_stats_rejects_wrong_token(app_client: TestClient):
    resp = app_client.get("/v1/stats", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401


def test_stats_accepts_correct_token(app_client: TestClient):
    resp = app_client.get("/v1/stats", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
    assert resp.status_code == 200


def test_sync_requires_bearer_token(app_client: TestClient):
    resp = app_client.post("/v1/sync")
    assert resp.status_code == 401


def test_sync_accepts_correct_token(app_client: TestClient):
    resp = app_client.post("/v1/sync", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
    assert resp.status_code == 202

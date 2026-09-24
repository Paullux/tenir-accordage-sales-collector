from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.importer import import_platform_files
from tests.conftest import TEST_TOKEN

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_stats_shape_matches_wordpress_plugin_contract(app_client: TestClient):
    resp = app_client.get("/v1/stats", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
    assert resp.status_code == 200
    body = resp.json()

    assert set(body.keys()) == {"currency", "platforms", "updated_at"}
    assert body["currency"] == "EUR"
    assert isinstance(body["updated_at"], str)

    assert set(body["platforms"].keys()) == {"amazon", "kobo", "fnac", "google"}
    for entry in body["platforms"].values():
        assert set(entry.keys()) == {"sales", "revenue"}
        assert isinstance(entry["sales"], int)
        assert isinstance(entry["revenue"], (int, float))

    # Fnac cannot be reliably attributed from Kobo's report and must always
    # be reported as zero rather than a guessed figure.
    assert body["platforms"]["fnac"] == {"sales": 0, "revenue": 0.0}


def test_status_shape_matches_plugin_contract(app_client: TestClient):
    resp = app_client.get("/v1/status")
    assert resp.status_code == 200
    body = resp.json()

    assert set(body.keys()) == {"amazon", "kobo", "google"}
    for entry in body.values():
        assert set(entry.keys()) == {"status", "last_sync"}
        assert entry["status"] in {"ok", "needs_auth", "error", "never_synced", "syncing"}


def test_stats_reflects_imported_totals(app_client: TestClient, data_dir: Path, settings):
    import app.main as main_module

    dest = data_dir / "imports" / "amazon" / "sample_kdp_report.csv"
    dest.write_bytes((FIXTURES_DIR / "amazon" / "sample_kdp_report.csv").read_bytes())

    db = next(iter(main_module._db_instances.values()))
    import_platform_files("amazon", db, settings)

    resp = app_client.get("/v1/stats", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
    body = resp.json()
    assert body["platforms"]["amazon"] == {"sales": 4, "revenue": 7.8}

"""API tests for the React demo backend (FastAPI wrapper). Uses a temp database."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CARBONOS_DB", str(tmp_path / "api.db"))
    import api.server as server
    server._conn = None
    with TestClient(server.app) as c:
        yield c
    if server._conn is not None:
        server._conn.close()
    server._conn = None


def test_bootstrap_matches_hand_calculation_and_never_invents(client):
    b = client.get("/api/bootstrap").json()
    assert b["ready"] and b["snapshot"]["assessed_total_kg_co2e"] == 38325.0
    assert b["snapshot"]["inventory_status"] == "incomplete"
    assert b["pitch"]["pilotAmountInr"] == 60000
    assert b["sample_previews"]["err"]["n_valid"] == 2 and b["sample_previews"]["err"]["n_rejected"] == 8


def test_plain_formula_writes_unit_conversion_into_sentence(client):
    b = client.get("/api/bootstrap").json()
    elec = next(r for r in b["results"] if r["source_reference"] == "DEMO-BILL-001")
    assert elec["plain_formula"] == "12,500 kWh × 0.70 kgCO₂e/kWh = 8,750 kg"
    diesel = next(r for r in b["results"] if r["source_reference"] == "DEMO-DSL-003")
    assert diesel["plain_formula"] == "0.9 kL = 900 L × 2.50 kgCO₂e/L = 2,250 kg"
    assert elec["recompute_matches"] is True and elec["fictional"] is True


def test_gaps_have_no_number_and_no_zero(client):
    b = client.get("/api/bootstrap").json()
    gaps = [r for r in b["results"] if r["status"] != "calculated"]
    assert {g["status"] for g in gaps} == {"missing_factor", "not_assessed", "missing_activity_data"}
    assert all(g["result_value"] is None and g["plain_formula"] is None for g in gaps)


def test_what_if_uses_real_engine_and_does_not_persist(client):
    b = client.get("/api/bootstrap").json()
    rid = next(r for r in b["results"] if r["source_reference"] == "DEMO-BILL-001")["id"]
    w = client.post("/api/what-if", json={"result_id": rid, "quantity": 13500}).json()
    assert w["kg_before"] == 8750.0 and w["kg_after"] == 9450.0
    assert w["plain_formula"] == "13,500 kWh × 0.70 kgCO₂e/kWh = 9,450 kg"
    assert w["category_kg_after"] == 32900.0 and w["total_kg_after"] == 39025.0
    assert client.get("/api/bootstrap").json()["snapshot"]["assessed_total_kg_co2e"] == 38325.0


def test_close_gap_creates_factor_snapshot_and_reports_closed(client):
    b = client.post("/api/demo/close-gap").json()
    assert b["gap_closed"] is True
    assert b["snapshot"]["assessed_total_kg_co2e"] == 62325.0  # + 12 t x 2000 kg/t (fictional)
    coal = next(f for f in b["factors"] if f["id"] == "EF-COAL-DEMO-001")
    assert coal["status"] == "illustrative" and coal["provenance"] == "synthetic_demo"
    assert len(b["snapshots"]) == 2  # old calculation kept
    assert client.post("/api/demo/close-gap").json()["gap_closed"] is False  # confetti only for a real closure


def test_reset_restores_pristine_demo(client):
    client.post("/api/demo/close-gap")
    b = client.post("/api/reset").json()
    assert b["snapshot"]["assessed_total_kg_co2e"] == 38325.0 and len(b["snapshots"]) == 1
    assert not any(f["id"] == "EF-COAL-DEMO-001" for f in b["factors"])


def test_import_preview_and_commit_row_level(client):
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data", "demo_activities_with_errors.csv")
    data = open(path, "rb").read()
    pv = client.post("/api/import/preview", files={"file": ("e.csv", data, "text/csv")}).json()
    assert pv["n_valid"] == 2 and pv["n_rejected"] == 8
    b = client.post("/api/import/commit", files={"file": ("e.csv", data, "text/csv")}).json()
    assert b["import_result"]["imported"] == 2 and b["import_result"]["rejected"] == 8
    assert b["snapshot"]["assessed_total_kg_co2e"] == 44675.0
    assert b["gap_closed"] is False


def test_export_zip_and_report(client):
    sid = client.get("/api/bootstrap").json()["snapshot"]["id"]
    z = client.get(f"/api/export/{sid}")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip" and z.content[:2] == b"PK"
    assert "Partial assessed total" in client.get(f"/api/report/{sid}").json()["markdown"]


def test_concurrent_requests_do_not_break_the_shared_connection(client):
    from concurrent.futures import ThreadPoolExecutor
    rid = client.get("/api/bootstrap").json()["results"][0]["id"]

    def hit(i):
        return client.post("/api/what-if", json={"result_id": rid, "quantity": 100 + i}).status_code

    with ThreadPoolExecutor(8) as ex:
        assert set(ex.map(hit, range(40))) == {200}

"""Traceability and calculation-history tests (sections 5.6 and 13.3)."""
import io
import sqlite3
import zipfile

import pytest

import calculations as calc
import database as db
import reporting
import seed_data
from conftest import ELEC_FACTOR


@pytest.fixture
def seeded(conn, period):
    db.create_factor(conn, dict(ELEC_FACTOR))
    rid = db.add_activity(conn, period, dict(activity_date="2026-01-01", category="purchased_electricity",
                                              activity_name="Grid electricity", quantity=12500, unit="kWh",
                                              source_reference="DEMO-BILL-001", provenance="synthetic_demo"))
    sid = db.run_calculation(conn, period)
    return {"period": period, "rid": rid, "sid": sid}


def _res(conn, sid, rid):
    return next(r for r in db.get_results(conn, sid) if r["activity_record_id"] == rid)


def test_result_links_to_activity_and_factor_snapshot(conn, seeded):
    r = _res(conn, seeded["sid"], seeded["rid"])
    assert r["activity_record_id"] == seeded["rid"]
    assert r["factor_id"] == "EF-ELECTRICITY-DEMO-001"
    assert r["factor_value_snapshot"] == 0.70
    assert r["factor_numerator_unit_snapshot"] == "kgCO2e" and r["factor_denominator_unit_snapshot"] == "kWh"
    assert r["factor_snapshot"]["status"] == "illustrative"
    assert r["activity_snapshot"]["source_reference"] == "DEMO-BILL-001"


def test_formula_units_timestamp_engine_version_retained(conn, seeded):
    r = _res(conn, seeded["sid"], seeded["rid"])
    assert "12500 kWh" in r["formula_description"] and "kgCO2e" in r["formula_description"]
    assert r["result_value"] == 8750.0 and r["result_unit"] == "kgCO2e"
    assert r["calculated_at"] and r["engine_version"] == calc.ENGINE_VERSION
    snap = db.get_snapshot(conn, seeded["sid"])
    assert snap["created_at"] and snap["engine_version"] == calc.ENGINE_VERSION


def test_REQUIRED_snapshot_survives_activity_edit(conn, seeded):
    """Spec 5.6: a snapshot keeps its original quantity after the live record is edited."""
    before = _res(conn, seeded["sid"], seeded["rid"])
    db.update_activity(conn, seeded["rid"], {"quantity": 99999})
    assert db.get_activity(conn, seeded["rid"])["quantity"] == 99999.0       # live record changed
    after = _res(conn, seeded["sid"], seeded["rid"])
    assert after["input_quantity_snapshot"] == 12500.0
    assert after["result_value"] == before["result_value"] == 8750.0
    assert after["activity_snapshot"]["quantity"] == 12500.0
    assert calc.recompute_from_snapshot(after) == 8750.0                      # still reproducible


def test_REQUIRED_snapshot_survives_factor_edit(conn, seeded):
    db.update_factor(conn, "EF-ELECTRICITY-DEMO-001", {"value": 0.99})
    assert db.get_factor(conn, "EF-ELECTRICITY-DEMO-001")["value"] == 0.99
    after = _res(conn, seeded["sid"], seeded["rid"])
    assert after["factor_value_snapshot"] == 0.70 and after["factor_snapshot"]["value"] == 0.70
    assert after["result_value"] == 8750.0
    assert calc.recompute_from_snapshot(after) == 8750.0


def test_new_calculation_creates_new_snapshot_and_keeps_old(conn, seeded):
    db.update_activity(conn, seeded["rid"], {"quantity": 20000})
    sid2 = db.run_calculation(conn, seeded["period"])
    assert sid2 != seeded["sid"]
    assert _res(conn, sid2, seeded["rid"])["result_value"] == 14000.0
    assert _res(conn, seeded["sid"], seeded["rid"])["result_value"] == 8750.0   # old preserved
    assert [s["id"] for s in db.list_snapshots(conn, seeded["period"])] == [sid2, seeded["sid"]]


def test_compare_snapshots_shows_delta(conn, seeded):
    db.update_activity(conn, seeded["rid"], {"quantity": 20000})
    sid2 = db.run_calculation(conn, seeded["period"])
    cmp = db.compare_snapshots(conn, seeded["sid"], sid2)
    assert cmp["old_total"] == 8750.0 and cmp["new_total"] == 14000.0 and cmp["delta_total"] == 5250.0
    row = cmp["rows"][0]
    assert row["old_quantity"] == 12500.0 and row["new_quantity"] == 20000.0 and row["delta_kg_co2e"] == 5250.0


def test_stale_flag_after_activity_factor_and_import_changes(conn, seeded):
    snap = db.get_snapshot(conn, seeded["sid"])
    assert db.is_stale(conn, snap) is False
    db.update_activity(conn, seeded["rid"], {"quantity": 1})
    assert db.is_stale(conn, snap) is True
    sid2 = db.run_calculation(conn, seeded["period"])
    assert db.is_stale(conn, db.get_snapshot(conn, sid2)) is False
    db.update_factor(conn, "EF-ELECTRICITY-DEMO-001", {"value": 0.5})
    assert db.is_stale(conn, db.get_snapshot(conn, sid2)) is True


def test_running_calculation_or_exporting_does_not_mark_stale(conn, seeded):
    db.log_event(conn, "report_exported", "calculation_snapshot", seeded["sid"], "export")
    assert db.is_stale(conn, db.get_snapshot(conn, seeded["sid"])) is False


def test_snapshots_and_results_are_immutable_at_database_level(conn, seeded):
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute("UPDATE calculation_results SET result_value=1 WHERE snapshot_id=?", (seeded["sid"],))
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute("DELETE FROM calculation_snapshots WHERE id=?", (seeded["sid"],))
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM audit_events")


def test_audit_events_record_changes_with_previous_and_new(conn, seeded):
    db.update_activity(conn, seeded["rid"], {"quantity": 777})
    ev = next(e for e in db.list_events(conn) if e["event_type"] == "activity_edited")
    assert '"quantity": 12500.0' in ev["previous_value_json"] and '"quantity": 777.0' in ev["new_value_json"]
    types = {e["event_type"] for e in db.list_events(conn)}
    assert {"activity_created", "factor_created", "calculation_run", "activity_edited"} <= types


def test_exports_include_provenance_and_factor_references(conn, seeded):
    df = reporting.calculation_details_df(conn, seeded["sid"])
    row = df.iloc[0]
    assert row["activity_provenance"] == "synthetic_demo" and row["factor_provenance"] == "synthetic_demo"
    assert row["factor_id"] == "EF-ELECTRICITY-DEMO-001" and row["factor_status"] == "illustrative"
    assert row["calculation_snapshot_id"] == seeded["sid"] and row["engine_version"] == calc.ENGINE_VERSION
    assert row["source_reference"] == "DEMO-BILL-001" and row["result"] == 8750.0
    fr = reporting.factor_references_df(conn, seeded["sid"])
    assert list(fr["id"]) == ["EF-ELECTRICITY-DEMO-001"]


def test_export_reflects_snapshot_not_live_data(conn, seeded):
    db.update_activity(conn, seeded["rid"], {"quantity": 5})
    df = reporting.calculation_details_df(conn, seeded["sid"])
    assert df.iloc[0]["quantity"] == 12500.0 and df.iloc[0]["result"] == 8750.0


def test_bundle_contains_all_exports_and_limitations(conn, seeded):
    z = zipfile.ZipFile(io.BytesIO(reporting.export_bundle(conn, seeded["sid"])))
    names = set(z.namelist())
    assert {"factory_summary.csv", "category_summary.csv", "calculation_details.csv",
            "data_quality_and_unresolved.csv", "factor_references.csv", "activity_data_live.csv",
            "assumptions_and_limitations.txt", "report.md"} <= names
    md = z.read("report.md").decode()
    assert "SYNTHETIC DEMONSTRATION" in md and "INCOMPLETE INVENTORY" in md
    assert "not been independently verified or certified" in md
    assert "Partial assessed total" in md


def test_demo_dataset_numbers_and_unresolved_visibility(conn):
    ids = seed_data.load_demo(conn)
    sid = db.run_calculation(conn, ids["current_period_id"])
    snap = db.get_snapshot(conn, sid)
    # hand calc: electricity 46,000 kWh x 0.70 = 32,200; diesel 800+750+900 L x 2.50 = 6,125
    assert snap["assessed_total_kg_co2e"] == 38325.0
    assert snap["inventory_status"] == "incomplete"
    by = {c["category"]: c for c in snap["summary"]["inventory"]["categories"]}
    assert by["other_fossil_fuels"]["completeness"] == "unresolved"
    assert by["bagasse_combustion"]["completeness"] == "not_assessed"
    assert by["refrigerants"]["completeness"] == "unresolved"
    assert by["wastewater_effluent"]["completeness"] == "not_assessed"
    unresolved = reporting.unresolved_df(conn, snap)
    assert {"other_fossil_fuels", "refrigerants", "wastewater_effluent"} <= set(unresolved["category"].dropna())
    assert snap["summary"]["is_synthetic"] is True
    with pytest.raises(db.ValidationError):
        seed_data.load_demo(conn)                       # not loadable twice


def test_demo_real_mode_calculates_nothing_numeric(conn):
    ids = seed_data.load_demo(conn)
    sid = db.run_calculation(conn, ids["current_period_id"], reporting_mode="real")
    snap = db.get_snapshot(conn, sid)
    assert snap["assessed_total_kg_co2e"] is None        # synthetic data never reaches a "real" total
    assert all(r["result_value"] is None for r in db.get_results(conn, sid))

"""End-to-end UI tests: run the real Streamlit script headlessly with AppTest."""
import os

import pytest
from streamlit.testing.v1 import AppTest

import database as db

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
PAGES = ["Overview", "Setup", "Activity data", "CSV import", "Emission factors",
         "Calculations & traceability", "History", "Reports & export"]


@pytest.fixture
def at(tmp_path, monkeypatch):
    monkeypatch.setenv("CARBONOS_DB", str(tmp_path / "ui.db"))
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    return app


def _btn(app, label_part):
    return next(b for b in app.button if label_part in b.label)


def _goto(app, page):
    app.sidebar.radio(key="page").set_value(page).run()
    assert not app.exception, [e.value for e in app.exception]


def _all_text(app):
    parts = []
    for coll in (app.markdown, app.warning, app.error, app.success, app.info, app.caption, app.metric):
        for el in coll:
            parts.append(str(getattr(el, "value", "")))
            if hasattr(el, "label"):
                parts.append(str(el.label))
    return "\n".join(parts)


def test_empty_database_launches_and_offers_demo(at):
    assert not at.exception
    assert any("Welcome" in h.value for h in at.header)
    assert any("Load FICTIONAL" in b.label for b in at.button)


def test_full_demo_workflow(at):
    # 1. load demo, synthetic banner is visible
    _btn(at, "Load FICTIONAL").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("SYNTHETIC DEMONSTRATION" in w.value for w in at.warning)

    # 2. before any calculation, no numbers are invented
    assert any("No calculation has been run" in i.value for i in at.info)

    # 3. run calculation -> partial total is labelled partial and matches the hand calculation
    _btn(at, "Run calculation").click().run()
    assert not at.exception, [e.value for e in at.exception]
    txt = _all_text(at)
    assert "INCOMPLETE INVENTORY" in txt
    labels = {m.label: m.value for m in at.metric}
    assert labels["Partial assessed total"] == "38.325 t CO₂e"
    assert labels["Unresolved records"] == "3"
    assert any("Electricity per tonne of cane crushed" in k and v == "9.200" for k, v in labels.items())

    # 4. every screen renders without exceptions
    for page in PAGES:
        _goto(at, page)

    # 5. reverse traceability: pick a result on the Calculations screen
    _goto(at, "Calculations & traceability")
    assert at.selectbox(key="trace_calcs").value is not None       # default selection renders a full trace
    assert any("Reproduced from stored snapshot values" in c.value for c in at.caption)

    # 6. edit a record -> stale warning -> recalc -> two snapshots, old preserved
    _goto(at, "Activity data")
    first_id = at.selectbox(key="edit_sel").value
    q_key = f"e_q_{first_id}"
    at.text_input(key=q_key).set_value("20000")
    _btn(at, "Save changes").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert db.get_activity(db.connect(os.environ["CARBONOS_DB"]), first_id)["quantity"] == 20000.0

    _goto(at, "Overview")
    assert any("predates the latest" in w.value for w in at.warning)
    _btn(at, "Run calculation").click().run()
    assert not at.exception
    c = db.connect(os.environ["CARBONOS_DB"])
    period_id = db.list_periods(c)[0]["id"]
    snaps = db.list_snapshots(c, period_id)
    assert len(snaps) == 2
    old, new = snaps[1], snaps[0]
    assert old["assessed_total_kg_co2e"] == 38325.0
    assert new["assessed_total_kg_co2e"] != old["assessed_total_kg_co2e"]
    assert db.get_results(c, old["id"])[0]["input_quantity_snapshot"] == 12500.0    # preserved

    # 7. history page compares snapshots
    _goto(at, "History")
    assert any("Assessed total" in m.label for m in at.metric)

    # 8. reports page renders the report preview with limitations
    _goto(at, "Reports & export")
    assert any("not been independently verified" in m.value for m in at.markdown)


def test_manual_entry_validation_and_success(at):
    _btn(at, "Load FICTIONAL").click().run()
    _goto(at, "Activity data")
    at.text_input(key="add_name").set_value("Test bill")
    at.text_input(key="add_qty").set_value("12,500")
    _btn(at, "Add record").click().run()
    assert any("comma" in e.value for e in at.error)                     # understandable error shown
    at.text_input(key="add_name").set_value("Test bill")
    at.text_input(key="add_qty").set_value("1000")
    _btn(at, "Add record").click().run()
    assert not at.exception
    c = db.connect(os.environ["CARBONOS_DB"])
    assert any(a["activity_name"] == "Test bill" and a["quantity"] == 1000.0
               for a in db.list_activities(c, db.list_periods(c)[0]["id"]))


def test_missing_quantity_manual_record_is_incomplete_not_zero(at):
    _btn(at, "Load FICTIONAL").click().run()
    _goto(at, "Activity data")
    at.text_input(key="add_name").set_value("Pending bill")
    at.checkbox(key="add_missing").set_value(True)
    _btn(at, "Add record").click().run()
    c = db.connect(os.environ["CARBONOS_DB"])
    rec = next(a for a in db.list_activities(c, db.list_periods(c)[0]["id"]) if a["activity_name"] == "Pending bill")
    assert rec["quantity"] is None and rec["status"] == "missing_activity_data"


def test_real_reporting_mode_blocks_synthetic_data(at):
    _btn(at, "Load FICTIONAL").click().run()
    at.sidebar.radio(key="mode_radio").set_value("Real reporting — verified factors only").run()
    assert any("Real-reporting mode" in i.value for i in at.info)
    _btn(at, "Run calculation").click().run()
    assert not at.exception
    labels = {m.label: m.value for m in at.metric}
    assert labels["Partial assessed total"] == "—"           # nothing synthetic reaches a 'real' total
    c = db.connect(os.environ["CARBONOS_DB"])
    snap = db.latest_snapshot(c, db.list_periods(c)[0]["id"])
    assert snap["reporting_mode"] == "real" and snap["assessed_total_kg_co2e"] is None


def test_factor_edit_through_ui_does_not_rewrite_old_snapshot(at):
    _btn(at, "Load FICTIONAL").click().run()
    _btn(at, "Run calculation").click().run()
    _goto(at, "Emission factors")
    at.selectbox(key="edit_factor_sel").select("EF-ELECTRICITY-DEMO-001").run()
    at.text_input(key="ev_EF-ELECTRICITY-DEMO-001").set_value("0.5")
    _btn(at, "Save factor").click().run()
    assert not at.exception, [e.value for e in at.exception]
    c = db.connect(os.environ["CARBONOS_DB"])
    assert db.get_factor(c, "EF-ELECTRICITY-DEMO-001")["value"] == 0.5
    snap = db.latest_snapshot(c, db.list_periods(c)[0]["id"])
    assert snap["assessed_total_kg_co2e"] == 38325.0         # old snapshot untouched
    assert db.is_stale(c, snap)

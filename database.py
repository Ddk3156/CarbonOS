"""SQLite persistence for CarbonOS Sugar: schema, CRUD, snapshots, audit events.

Calculation snapshots are append-only. Triggers abort UPDATE/DELETE on
snapshot, result and audit tables. This is an application-level safeguard,
NOT tamper-proofing: anyone with file access can drop the triggers.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from typing import Any, Optional

import calculations as calc

DEFAULT_DB_PATH = os.environ.get("CARBONOS_DB", "carbonos.db")

# Events that change inputs and therefore make an existing snapshot stale.
CHANGE_EVENTS = (
    "activity_created", "activity_edited", "csv_imported",
    "factor_created", "factor_edited", "period_created", "period_edited",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS factories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    location TEXT,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reporting_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factory_id INTEGER NOT NULL REFERENCES factories(id),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    boundary_description TEXT,
    cane_crushed_t REAL CHECK (cane_crushed_t IS NULL OR cane_crushed_t >= 0),
    sugar_produced_t REAL CHECK (sugar_produced_t IS NULL OR sugar_produced_t >= 0),
    excluded_categories_json TEXT NOT NULL DEFAULT '{}',
    data_source_notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (end_date >= start_date)
);
CREATE TABLE IF NOT EXISTS activity_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factory_id INTEGER NOT NULL REFERENCES factories(id),
    reporting_period_id INTEGER NOT NULL REFERENCES reporting_periods(id),
    activity_date TEXT NOT NULL,
    category TEXT NOT NULL,
    activity_name TEXT NOT NULL CHECK (length(trim(activity_name)) > 0),
    quantity REAL CHECK (quantity IS NULL OR quantity >= 0),
    unit TEXT NOT NULL,
    source_reference TEXT,
    source_row_reference TEXT,
    provenance TEXT NOT NULL CHECK (provenance IN ('user_provided','synthetic_demo','unknown')),
    notes TEXT,
    status TEXT NOT NULL CHECK (status IN ('valid','missing_activity_data')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS emission_factors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    value REAL NOT NULL CHECK (value >= 0),
    numerator_unit TEXT NOT NULL,
    denominator_unit TEXT NOT NULL,
    gas_basis TEXT,
    geography TEXT,
    applicable_year INTEGER,
    source_organization TEXT,
    source_document TEXT,
    source_url TEXT,
    source_reference TEXT,
    publication_date TEXT,
    status TEXT NOT NULL CHECK (status IN ('verified_for_use','needs_review','illustrative','deprecated')),
    provenance TEXT NOT NULL CHECK (provenance IN
        ('user_provided','published_factor','published_benchmark','synthetic_demo','derived','unknown')),
    is_active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calculation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factory_id INTEGER NOT NULL REFERENCES factories(id),
    reporting_period_id INTEGER NOT NULL REFERENCES reporting_periods(id),
    created_at TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    reporting_mode TEXT NOT NULL CHECK (reporting_mode IN ('demo','real')),
    inventory_status TEXT NOT NULL,
    assessed_total_kg_co2e REAL,
    unresolved_count INTEGER NOT NULL,
    audit_watermark INTEGER NOT NULL,
    summary_json TEXT NOT NULL,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS calculation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES calculation_snapshots(id),
    activity_record_id INTEGER NOT NULL REFERENCES activity_records(id),
    factor_id TEXT,
    input_quantity_snapshot REAL,
    input_unit_snapshot TEXT,
    factor_value_snapshot REAL,
    factor_numerator_unit_snapshot TEXT,
    factor_denominator_unit_snapshot TEXT,
    conversion_description TEXT,
    formula_description TEXT,
    result_value REAL,
    result_unit TEXT,
    status TEXT NOT NULL,
    message TEXT,
    provenance_snapshot TEXT NOT NULL,
    activity_snapshot_json TEXT NOT NULL,
    factor_snapshot_json TEXT,
    warnings_json TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    calculated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    period_id INTEGER,
    created_at TEXT NOT NULL,
    description TEXT NOT NULL,
    previous_value_json TEXT,
    new_value_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_activity_period ON activity_records(reporting_period_id);
CREATE INDEX IF NOT EXISTS idx_results_snapshot ON calculation_results(snapshot_id);

CREATE TRIGGER IF NOT EXISTS trg_snapshots_no_update BEFORE UPDATE ON calculation_snapshots
BEGIN SELECT RAISE(ABORT, 'calculation_snapshots are immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_snapshots_no_delete BEFORE DELETE ON calculation_snapshots
BEGIN SELECT RAISE(ABORT, 'calculation_snapshots are immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_results_no_update BEFORE UPDATE ON calculation_results
BEGIN SELECT RAISE(ABORT, 'calculation_results are immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_results_no_delete BEFORE DELETE ON calculation_results
BEGIN SELECT RAISE(ABORT, 'calculation_results are immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events are append-only'); END;
"""


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def connect(path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _row(r: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(r) if r is not None else None


def _rows(rs) -> list[dict]:
    return [dict(r) for r in rs]


def _j(obj: Any) -> Optional[str]:
    return None if obj is None else json.dumps(obj, default=str, sort_keys=True)


def _log(conn, event_type: str, entity_type: str, entity_id: Any, description: str,
         previous: Any = None, new: Any = None, period_id: Optional[int] = None) -> int:
    cur = conn.execute(
        "INSERT INTO audit_events(event_type, entity_type, entity_id, period_id, created_at, description,"
        " previous_value_json, new_value_json) VALUES (?,?,?,?,?,?,?,?)",
        (event_type, entity_type, None if entity_id is None else str(entity_id), period_id,
         now_iso(), description, _j(previous), _j(new)))
    return cur.lastrowid


def log_event(conn, event_type: str, entity_type: str, entity_id: Any, description: str,
              previous: Any = None, new: Any = None, period_id: Optional[int] = None) -> int:
    """Public wrapper (used e.g. for report exports)."""
    with conn:
        return _log(conn, event_type, entity_type, entity_id, description, previous, new, period_id)


# --------------------------------------------------------------------------
# Factories and periods
# --------------------------------------------------------------------------
def create_factory(conn, name: str, location: Optional[str] = None, notes: Optional[str] = None,
                   is_synthetic: bool = False) -> int:
    if not (name or "").strip():
        raise ValidationError(["Factory name is required."])
    with conn:
        cur = conn.execute(
            "INSERT INTO factories(name, location, is_synthetic, notes, created_at) VALUES (?,?,?,?,?)",
            (name.strip(), location, int(is_synthetic), notes, now_iso()))
        _log(conn, "factory_created", "factory", cur.lastrowid, f"Factory '{name.strip()}' created.")
        return cur.lastrowid


def get_factory(conn, factory_id: int) -> Optional[dict]:
    return _row(conn.execute("SELECT * FROM factories WHERE id=?", (factory_id,)).fetchone())


def list_factories(conn) -> list[dict]:
    return _rows(conn.execute("SELECT * FROM factories ORDER BY id"))


def _validate_period(start, end, cane, sugar, excluded) -> list[str]:
    errs = []
    s, e = calc.parse_date(start), calc.parse_date(end)
    if s is None:
        errs.append("Period start date must be a valid YYYY-MM-DD date.")
    if e is None:
        errs.append("Period end date must be a valid YYYY-MM-DD date.")
    if s and e and e < s:
        errs.append("Period end date cannot be before the start date.")
    for v, lbl in ((cane, "Cane crushed"), (sugar, "Sugar produced")):
        if v is not None and (not isinstance(v, (int, float)) or v < 0):
            errs.append(f"{lbl} must be a number ≥ 0 or left blank (blank means unknown, not zero).")
    for c in (excluded or {}):
        if c not in calc.CATEGORIES:
            errs.append(f"Unknown excluded category '{c}'.")
    return errs


def create_period(conn, factory_id: int, start_date: str, end_date: str,
                  boundary_description: Optional[str] = None, cane_crushed_t: Optional[float] = None,
                  sugar_produced_t: Optional[float] = None, excluded_categories: Optional[dict] = None,
                  data_source_notes: Optional[str] = None) -> int:
    errs = _validate_period(start_date, end_date, cane_crushed_t, sugar_produced_t, excluded_categories)
    if errs:
        raise ValidationError(errs)
    ts = now_iso()
    with conn:
        cur = conn.execute(
            "INSERT INTO reporting_periods(factory_id, start_date, end_date, boundary_description, cane_crushed_t,"
            " sugar_produced_t, excluded_categories_json, data_source_notes, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (factory_id, start_date, end_date, boundary_description, cane_crushed_t, sugar_produced_t,
             _j(excluded_categories or {}), data_source_notes, ts, ts))
        pid = cur.lastrowid
        _log(conn, "period_created", "reporting_period", pid,
             f"Reporting period {start_date} to {end_date} created.", period_id=pid)
        return pid


def get_period(conn, period_id: int) -> Optional[dict]:
    return _row(conn.execute("SELECT * FROM reporting_periods WHERE id=?", (period_id,)).fetchone())


def list_periods(conn, factory_id: Optional[int] = None) -> list[dict]:
    if factory_id is None:
        return _rows(conn.execute("SELECT * FROM reporting_periods ORDER BY start_date DESC"))
    return _rows(conn.execute("SELECT * FROM reporting_periods WHERE factory_id=? ORDER BY start_date DESC",
                              (factory_id,)))


def update_period(conn, period_id: int, **changes) -> None:
    prev = get_period(conn, period_id)
    if prev is None:
        raise ValidationError(["Reporting period not found."])
    new = {**prev, **changes}
    excl = changes.get("excluded_categories")
    if excl is None:
        excl = json.loads(prev["excluded_categories_json"])
    errs = _validate_period(new["start_date"], new["end_date"], new["cane_crushed_t"],
                            new["sugar_produced_t"], excl)
    # A category that already has records cannot be excluded from the boundary.
    have = {r["category"] for r in conn.execute(
        "SELECT DISTINCT category FROM activity_records WHERE reporting_period_id=?", (period_id,))}
    for c in excl:
        if c in have:
            errs.append(f"'{calc.CATEGORIES[c]['label']}' has activity records and cannot be excluded from the boundary.")
    if errs:
        raise ValidationError(errs)
    with conn:
        conn.execute(
            "UPDATE reporting_periods SET start_date=?, end_date=?, boundary_description=?, cane_crushed_t=?,"
            " sugar_produced_t=?, excluded_categories_json=?, data_source_notes=?, updated_at=? WHERE id=?",
            (new["start_date"], new["end_date"], new["boundary_description"], new["cane_crushed_t"],
             new["sugar_produced_t"], _j(excl), new["data_source_notes"], now_iso(), period_id))
        _log(conn, "period_edited", "reporting_period", period_id, "Reporting period edited.",
             previous=prev, new=get_period(conn, period_id), period_id=period_id)


# --------------------------------------------------------------------------
# Activity records
# --------------------------------------------------------------------------
def _insert_activity(conn, period: dict, clean: dict) -> int:
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO activity_records(factory_id, reporting_period_id, activity_date, category, activity_name,"
        " quantity, unit, source_reference, source_row_reference, provenance, notes, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (period["factory_id"], period["id"], clean["activity_date"], clean["category"], clean["activity_name"],
         clean["quantity"], clean["unit"], clean["source_reference"], clean["source_row_reference"],
         clean["provenance"], clean["notes"], clean["status"], ts, ts))
    return cur.lastrowid


def add_activity(conn, period_id: int, rec: dict, allow_missing_quantity: bool = False) -> int:
    period = get_period(conn, period_id)
    if period is None:
        raise ValidationError(["Reporting period not found."])
    clean, errs = calc.validate_activity_input(rec, period, allow_missing_quantity)
    if errs:
        raise ValidationError(errs)
    with conn:
        rid = _insert_activity(conn, period, clean)
        _log(conn, "activity_created", "activity_record", rid,
             f"Activity record created: {clean['activity_name']} ({clean['category']}).",
             new=get_activity(conn, rid), period_id=period_id)
        return rid


def get_activity(conn, record_id: int) -> Optional[dict]:
    return _row(conn.execute("SELECT * FROM activity_records WHERE id=?", (record_id,)).fetchone())


def list_activities(conn, period_id: int, category: Optional[str] = None,
                    status: Optional[str] = None) -> list[dict]:
    q, args = "SELECT * FROM activity_records WHERE reporting_period_id=?", [period_id]
    if category:
        q += " AND category=?"; args.append(category)
    if status:
        q += " AND status=?"; args.append(status)
    return _rows(conn.execute(q + " ORDER BY activity_date, id", args))


def update_activity(conn, record_id: int, changes: dict, allow_missing_quantity: bool = True) -> None:
    prev = get_activity(conn, record_id)
    if prev is None:
        raise ValidationError(["Activity record not found."])
    period = get_period(conn, prev["reporting_period_id"])
    merged = {k: prev[k] for k in ("activity_date", "category", "activity_name", "quantity", "unit",
                                   "source_reference", "source_row_reference", "provenance", "notes")}
    merged.update(changes)
    clean, errs = calc.validate_activity_input(merged, period, allow_missing_quantity)
    if errs:
        raise ValidationError(errs)
    with conn:
        conn.execute(
            "UPDATE activity_records SET activity_date=?, category=?, activity_name=?, quantity=?, unit=?,"
            " source_reference=?, source_row_reference=?, provenance=?, notes=?, status=?, updated_at=? WHERE id=?",
            (clean["activity_date"], clean["category"], clean["activity_name"], clean["quantity"], clean["unit"],
             clean["source_reference"], clean["source_row_reference"], clean["provenance"], clean["notes"],
             clean["status"], now_iso(), record_id))
        _log(conn, "activity_edited", "activity_record", record_id,
             f"Activity record #{record_id} edited.", previous=prev, new=get_activity(conn, record_id),
             period_id=prev["reporting_period_id"])


def bulk_add_activities(conn, period_id: int, records: list[dict], filename: str,
                       rejected: list[dict]) -> list[int]:
    """Insert already-validated import rows in ONE transaction and log ONE csv_imported event.
    Rows are re-validated here so the database never trusts the caller."""
    period = get_period(conn, period_id)
    if period is None:
        raise ValidationError(["Reporting period not found."])
    cleaned = []
    for rec in records:
        clean, errs = calc.validate_activity_input(rec, period, allow_missing_quantity=False)
        if errs:
            raise ValidationError([f"Row {rec.get('source_row_reference')}: {e}" for e in errs])
        cleaned.append(clean)
    ids = []
    with conn:
        for clean in cleaned:
            ids.append(_insert_activity(conn, period, clean))
        _log(conn, "csv_imported", "import", filename,
             f"CSV '{filename}' imported: {len(ids)} records imported, {len(rejected)} rows rejected.",
             new={"filename": filename, "imported_record_ids": ids,
                  "rejected_rows": [{"row": r["row_number"], "errors": r["errors"]} for r in rejected]},
             period_id=period_id)
    return ids


# --------------------------------------------------------------------------
# Emission factors
# --------------------------------------------------------------------------
_FACTOR_COLS = ("id", "name", "category", "value", "numerator_unit", "denominator_unit", "gas_basis",
                "geography", "applicable_year", "source_organization", "source_document", "source_url",
                "source_reference", "publication_date", "status", "provenance", "is_active", "notes")


def _next_factor_id(conn) -> str:
    n = conn.execute("SELECT COUNT(*) FROM emission_factors WHERE id LIKE 'EF-USER-%'").fetchone()[0] + 1
    while conn.execute("SELECT 1 FROM emission_factors WHERE id=?", (f"EF-USER-{n:04d}",)).fetchone():
        n += 1
    return f"EF-USER-{n:04d}"


def _deactivate_others(conn, category: str, keep_id: str) -> None:
    conn.execute("UPDATE emission_factors SET is_active=0, updated_at=? WHERE category=? AND id<>? AND is_active=1",
                 (now_iso(), category, keep_id))


def create_factor(conn, rec: dict) -> str:
    rec = dict(rec)
    rec.setdefault("is_active", 1)
    errs = calc.validate_factor_record(rec)
    fid = (rec.get("id") or "").strip() or _next_factor_id(conn)
    if conn.execute("SELECT 1 FROM emission_factors WHERE id=?", (fid,)).fetchone():
        errs.append(f"Factor ID '{fid}' already exists.")
    if errs:
        raise ValidationError(errs)
    ts = now_iso()
    with conn:
        vals = [fid if c == "id" else rec.get(c) for c in _FACTOR_COLS]
        conn.execute(f"INSERT INTO emission_factors({','.join(_FACTOR_COLS)}, created_at, updated_at)"
                     f" VALUES ({','.join('?' * len(_FACTOR_COLS))},?,?)", (*vals, ts, ts))
        if rec["is_active"]:
            _deactivate_others(conn, rec["category"], fid)
        _log(conn, "factor_created", "emission_factor", fid, f"Emission factor {fid} created.",
             new=get_factor(conn, fid))
    return fid


def get_factor(conn, factor_id: str) -> Optional[dict]:
    return _row(conn.execute("SELECT * FROM emission_factors WHERE id=?", (factor_id,)).fetchone())


def list_factors(conn) -> list[dict]:
    return _rows(conn.execute("SELECT * FROM emission_factors ORDER BY category, id"))


def update_factor(conn, factor_id: str, changes: dict) -> None:
    prev = get_factor(conn, factor_id)
    if prev is None:
        raise ValidationError(["Factor not found."])
    merged = {**prev, **changes, "id": factor_id}
    errs = calc.validate_factor_record(merged)
    if errs:
        raise ValidationError(errs)
    with conn:
        sets = ", ".join(f"{c}=?" for c in _FACTOR_COLS if c != "id")
        conn.execute(f"UPDATE emission_factors SET {sets}, updated_at=? WHERE id=?",
                     (*[merged.get(c) for c in _FACTOR_COLS if c != "id"], now_iso(), factor_id))
        if merged["is_active"]:
            _deactivate_others(conn, merged["category"], factor_id)
        _log(conn, "factor_edited", "emission_factor", factor_id, f"Emission factor {factor_id} edited.",
             previous=prev, new=get_factor(conn, factor_id))


# --------------------------------------------------------------------------
# Calculation snapshots
# --------------------------------------------------------------------------
def _audit_watermark(conn, period_id: int) -> int:
    ph = ",".join("?" * len(CHANGE_EVENTS))
    r = conn.execute(f"SELECT COALESCE(MAX(id),0) FROM audit_events WHERE event_type IN ({ph})"
                     " AND (period_id IS NULL OR period_id=?)", (*CHANGE_EVENTS, period_id)).fetchone()
    return r[0]


def _previous_period(conn, period: dict) -> Optional[dict]:
    return _row(conn.execute(
        "SELECT * FROM reporting_periods WHERE factory_id=? AND end_date < ? ORDER BY end_date DESC LIMIT 1",
        (period["factory_id"], period["start_date"])).fetchone())


def run_calculation(conn, period_id: int, reporting_mode: str = "demo", notes: Optional[str] = None) -> int:
    """Calculate every activity record in the period and store an immutable snapshot."""
    if reporting_mode not in ("demo", "real"):
        raise ValidationError(["reporting_mode must be 'demo' or 'real'."])
    period = get_period(conn, period_id)
    if period is None:
        raise ValidationError(["Reporting period not found."])
    factory = get_factory(conn, period["factory_id"])
    activities = list_activities(conn, period_id)
    factors = list_factors(conn)
    factors_by_id = {f["id"]: f for f in factors}
    ts = now_iso()

    results = []
    for a in activities:
        f, sel_warn = calc.select_factor(a["category"], factors)
        r = calc.calculate_record(a, f, reporting_mode=reporting_mode, calculated_at=ts)
        r["warnings"] += sel_warn
        results.append(r)

    excluded = json.loads(period["excluded_categories_json"] or "{}")
    inv = calc.summarize_inventory(activities, results, excluded)
    intensity = calc.energy_intensity(activities, period)

    previous = None
    prev_period = _previous_period(conn, period)
    if prev_period:
        prev_int = calc.energy_intensity(list_activities(conn, prev_period["id"]), prev_period)
        previous = {"label": f"previous period {prev_period['start_date']} to {prev_period['end_date']}",
                    "intensity": {i["key"]: i for i in prev_int}}
    anomalies = calc.find_anomalies(activities, results, period, intensity, previous)
    recs = calc.build_recommendations(anomalies, intensity, inv)

    summary = {
        "factory": {"id": factory["id"], "name": factory["name"], "location": factory["location"],
                    "is_synthetic": bool(factory["is_synthetic"])},
        "period": {k: period[k] for k in ("id", "start_date", "end_date", "boundary_description",
                                          "cane_crushed_t", "sugar_produced_t", "data_source_notes")},
        "excluded_categories": excluded,
        "reporting_mode": reporting_mode,
        "inventory": inv, "intensity": intensity, "anomalies": anomalies, "recommendations": recs,
        "previous_period_compared": previous["label"] if previous else None,
        "is_synthetic": inv["is_synthetic"] or bool(factory["is_synthetic"]),
        "synthetic_label": calc.SYNTHETIC_LABEL,
    }

    with conn:
        wm = _audit_watermark(conn, period_id)
        cur = conn.execute(
            "INSERT INTO calculation_snapshots(factory_id, reporting_period_id, created_at, engine_version,"
            " reporting_mode, inventory_status, assessed_total_kg_co2e, unresolved_count, audit_watermark,"
            " summary_json, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (period["factory_id"], period_id, ts, calc.ENGINE_VERSION, reporting_mode, inv["inventory_status"],
             inv["totals"]["assessed_kg_co2e"], inv["unresolved_count"], wm, _j(summary), notes))
        sid = cur.lastrowid
        act_by_id = {a["id"]: a for a in activities}
        for r in results:
            fid = r["factor_id"]
            conn.execute(
                "INSERT INTO calculation_results(snapshot_id, activity_record_id, factor_id, input_quantity_snapshot,"
                " input_unit_snapshot, factor_value_snapshot, factor_numerator_unit_snapshot,"
                " factor_denominator_unit_snapshot, conversion_description, formula_description, result_value,"
                " result_unit, status, message, provenance_snapshot, activity_snapshot_json, factor_snapshot_json,"
                " warnings_json, engine_version, calculated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sid, r["activity_record_id"], fid, r["input_quantity_snapshot"], r["input_unit_snapshot"],
                 r["factor_value_snapshot"], r["factor_numerator_unit_snapshot"],
                 r["factor_denominator_unit_snapshot"], r["conversion_description"], r["formula_description"],
                 r["result_value"], r["result_unit"], r["status"], r["message"], _j(r["provenance_snapshot"]),
                 _j(act_by_id[r["activity_record_id"]]), _j(factors_by_id.get(fid)) if fid else None,
                 _j(r["warnings"]), r["engine_version"], r["calculated_at"]))
        _log(conn, "calculation_run", "calculation_snapshot", sid,
             f"Calculation run created snapshot #{sid} ({reporting_mode} mode): "
             f"{len(results)} records, status {inv['inventory_status']}.",
             new={"snapshot_id": sid, "assessed_total_kg_co2e": inv["totals"]["assessed_kg_co2e"]},
             period_id=period_id)
    return sid


def get_snapshot(conn, snapshot_id: int) -> Optional[dict]:
    r = _row(conn.execute("SELECT * FROM calculation_snapshots WHERE id=?", (snapshot_id,)).fetchone())
    if r:
        r["summary"] = json.loads(r["summary_json"])
    return r


def list_snapshots(conn, period_id: int) -> list[dict]:
    return _rows(conn.execute(
        "SELECT id, created_at, engine_version, reporting_mode, inventory_status, assessed_total_kg_co2e,"
        " unresolved_count FROM calculation_snapshots WHERE reporting_period_id=? ORDER BY id DESC", (period_id,)))


def latest_snapshot(conn, period_id: int) -> Optional[dict]:
    r = conn.execute("SELECT id FROM calculation_snapshots WHERE reporting_period_id=? ORDER BY id DESC LIMIT 1",
                     (period_id,)).fetchone()
    return get_snapshot(conn, r["id"]) if r else None


def get_results(conn, snapshot_id: int) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM calculation_results WHERE snapshot_id=? ORDER BY id", (snapshot_id,)):
        d = dict(r)
        d["provenance_snapshot"] = json.loads(d["provenance_snapshot"])
        d["activity_snapshot"] = json.loads(d["activity_snapshot_json"])
        d["factor_snapshot"] = json.loads(d["factor_snapshot_json"]) if d["factor_snapshot_json"] else None
        d["warnings"] = json.loads(d["warnings_json"])
        out.append(d)
    return out


def is_stale(conn, snapshot: dict) -> bool:
    """True if inputs changed after this snapshot was calculated."""
    ph = ",".join("?" * len(CHANGE_EVENTS))
    r = conn.execute(
        f"SELECT 1 FROM audit_events WHERE id > ? AND event_type IN ({ph}) AND (period_id IS NULL OR period_id=?) LIMIT 1",
        (snapshot["audit_watermark"], *CHANGE_EVENTS, snapshot["reporting_period_id"])).fetchone()
    return r is not None


def compare_snapshots(conn, old_id: int, new_id: int) -> dict:
    old, new = get_snapshot(conn, old_id), get_snapshot(conn, new_id)
    ro = {r["activity_record_id"]: r for r in get_results(conn, old_id)}
    rn = {r["activity_record_id"]: r for r in get_results(conn, new_id)}
    rows = []
    for rid in sorted(set(ro) | set(rn)):
        a, b = ro.get(rid), rn.get(rid)
        av = a["result_value"] if a else None
        bv = b["result_value"] if b else None
        delta = (bv - av) if (av is not None and bv is not None) else None
        rows.append({
            "activity_record_id": rid,
            "old_quantity": a["input_quantity_snapshot"] if a else None,
            "new_quantity": b["input_quantity_snapshot"] if b else None,
            "old_factor": a["factor_value_snapshot"] if a else None,
            "new_factor": b["factor_value_snapshot"] if b else None,
            "old_status": a["status"] if a else "not in snapshot",
            "new_status": b["status"] if b else "not in snapshot",
            "old_kg_co2e": av, "new_kg_co2e": bv, "delta_kg_co2e": delta,
        })
    ot, nt = old["assessed_total_kg_co2e"], new["assessed_total_kg_co2e"]
    return {"old_id": old_id, "new_id": new_id, "rows": rows, "old_total": ot, "new_total": nt,
            "delta_total": (nt - ot) if (ot is not None and nt is not None) else None}


def list_events(conn, limit: int = 500) -> list[dict]:
    return _rows(conn.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)))

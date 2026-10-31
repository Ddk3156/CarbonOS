"""FastAPI wrapper around the existing CarbonOS Sugar Python modules.

Does not reimplement calculation, import, or reporting logic.
"""
from __future__ import annotations

import functools
import json
import os
import sys
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import calculations as calc  # noqa: E402
import database as db  # noqa: E402
import imports  # noqa: E402
import reporting  # noqa: E402
import seed_data  # noqa: E402

PITCH_PATH = ROOT / "pitch.config.json"
FALLBACK_PATH = ROOT / "api" / "fallback" / "bootstrap.json"
WEB_FALLBACK_PATH = ROOT / "web" / "public" / "fallback" / "bootstrap.json"
WEB_DIST = ROOT / "web" / "dist"
SAMPLE_DIR = ROOT / "sample_data"
LOCK = threading.RLock()  # one shared SQLite connection: serialise every handler


def locked(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        with LOCK:
            return fn(*a, **k)
    return wrapper


# Fictional, unsourced, demo-only factor used ONLY by /api/demo/close-gap.
COAL_DEMO_FACTOR = {
    "id": "EF-COAL-DEMO-001", "name": "Synthetic coal factor (demo only)",
    "category": "other_fossil_fuels", "value": 2000.0, "numerator_unit": "kgCO2e", "denominator_unit": "t",
    "gas_basis": "CO2e (synthetic)", "geography": "Synthetic demonstration only", "applicable_year": None,
    "source_organization": None, "source_document": None, "source_url": None, "source_reference": None,
    "status": "illustrative", "provenance": "synthetic_demo",
    "notes": "Fictional round number, no source. Added only by the demo's 'close a gap' action. Not a published coal factor.",
}

app = FastAPI(title="CarbonOS Sugar API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_conn: Optional[Any] = None


def _db_path() -> str:
    return os.environ.get("CARBONOS_DB", str(ROOT / "carbonos-demo.db"))


def conn():
    global _conn
    if _conn is None:
        _conn = db.connect(_db_path())
    return _conn


def load_pitch() -> dict:
    with open(PITCH_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def json_safe(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return str(obj)


def err(exc: Exception, status: int = 400):
    if isinstance(exc, db.ValidationError):
        return JSONResponse({"ok": False, "errors": exc.errors}, status_code=status)
    return JSONResponse({"ok": False, "errors": [str(exc)]}, status_code=status)


def current_context(c):
    factories = db.list_factories(c)
    factory = next((f for f in factories if f.get("is_synthetic")), factories[0] if factories else None)
    if factory is None:
        return None
    periods = db.list_periods(c, factory["id"])
    if not periods:
        return None
    current = next((p for p in periods if p["start_date"] >= "2026-01-01"), periods[0])
    return factory, current, periods


def ensure_demo_and_snapshot(c) -> None:
    if not seed_data.demo_exists(c):
        seed_data.load_demo(c, include_current_records=True)
    ctx = current_context(c)
    if ctx is None:
        return
    _factory, period, _periods = ctx
    if db.latest_snapshot(c, period["id"]) is None:
        db.run_calculation(c, period["id"], reporting_mode="demo")


def decorate_result(c, snap: dict, r: dict) -> dict:
    recomputed = None
    matches = None
    if r.get("status") == calc.CALCULATED:
        recomputed = calc.recompute_from_snapshot(r)
        stored = r.get("result_value")
        matches = recomputed is not None and stored is not None and abs(recomputed - stored) < 1e-9
    a = r.get("activity_snapshot") or {}
    f = r.get("factor_snapshot")
    plain = None
    if r.get("status") == calc.CALCULATED and r.get("result_value") is not None:
        q = r.get("input_quantity_snapshot")
        u = r.get("input_unit_snapshot") or ""
        fv = r.get("factor_value_snapshot")
        nu = r.get("factor_numerator_unit_snapshot") or "kgCO2e"
        du = r.get("factor_denominator_unit_snapshot") or ""
        plain = plain_formula(q, u, fv, nu, du, r["result_value"])
    return {
        **r,
        "recomputed_kg": recomputed,
        "recompute_matches": matches,
        "plain_formula": plain,
        "source_reference": a.get("source_reference"),
        "activity_name": a.get("activity_name"),
        "activity_date": a.get("activity_date"),
        "category": a.get("category"),
        "category_label": calc.CATEGORIES.get(a.get("category"), {}).get("label", a.get("category")),
        "fictional": bool((a.get("provenance") == "synthetic_demo") or (f and f.get("provenance") == "synthetic_demo")),
        "factor_source": reporting._factor_source(f),
        "snapshot_id": snap["id"],
        "snapshot_created_at": snap["created_at"],
        "engine_version": r.get("engine_version"),
        "reporting_mode": snap.get("reporting_mode"),
        "stale": db.is_stale(c, snap),
    }


def _fnum(v: Any) -> str:
    """Factor values: whole numbers plain, otherwise at least two decimals (0.70, 2.50)."""
    n = float(v)
    if abs(n - round(n)) < 1e-12:
        return f"{int(round(n)):,}"
    t = f"{n:,.4f}".rstrip("0")
    return t + "0" if len(t.split(".")[1]) == 1 else t


def plain_formula(q: Any, unit: Any, fv: Any, nu: Any, du: Any, result: Any) -> str:
    """Plain-language sentence. Any unit conversion the engine applies is written into it."""
    u, d = calc.normalize_unit(unit), calc.normalize_unit(du)
    left = f"{_num(q)} {unit}"
    conv = getattr(calc, "CONVERSIONS", {})
    if u and d and u != d and (u, d) in conv:
        left += f" = {_num(float(Decimal(str(q)) * Decimal(str(conv[(u, d)]))))} {du}"
    num = (nu or "kgCO2e").replace("CO2e", "CO₂e")
    return f"{left} × {_fnum(fv)} {num}/{du} = {_num(result)} kg"


def _num(v: Any) -> str:
    if v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n)):,}"
    return f"{n:,.2f}".rstrip("0").rstrip(".")


def build_bootstrap(c) -> dict:
    pitch = load_pitch()
    ctx = current_context(c)
    if ctx is None:
        return {"ok": True, "ready": False, "pitch": pitch, "synthetic_label": calc.SYNTHETIC_LABEL}
    factory, period, periods = ctx
    snap = db.latest_snapshot(c, period["id"])
    results = [decorate_result(c, snap, r) for r in db.get_results(c, snap["id"])] if snap else []
    activities = db.list_activities(c, period["id"])
    factors = db.list_factors(c)
    snapshots = db.list_snapshots(c, period["id"])
    md = reporting.markdown_report(c, snap["id"]) if snap else None
    sample_ok = (SAMPLE_DIR / "demo_activities.csv").read_text(encoding="utf-8")
    sample_err = (SAMPLE_DIR / "demo_activities_with_errors.csv").read_text(encoding="utf-8")
    previews = {
        "ok": {"ok": True, **imports.parse_csv(sample_ok, "demo_activities.csv", period, activities)},
        "err": {"ok": True, **imports.parse_csv(sample_err, "demo_activities_with_errors.csv", period, activities)},
    }
    return json_safe({
        "ok": True,
        "ready": True,
        "sample_previews": previews,
        "pitch": pitch,
        "synthetic_label": calc.SYNTHETIC_LABEL,
        "engine_version": calc.ENGINE_VERSION,
        "categories": {k: {"label": v["label"], "units": list(v["units"]), "method": v["method"], "note": v["note"]}
                       for k, v in calc.CATEGORIES.items()},
        "factory": factory,
        "period": period,
        "periods": periods,
        "snapshot": snap,
        "stale": db.is_stale(c, snap) if snap else False,
        "results": results,
        "activities": activities,
        "factors": factors,
        "snapshots": snapshots,
        "report_markdown": md,
        "sample_csv": sample_ok,
        "sample_csv_with_errors": sample_err,
        "hand_check": {
            "electricity_kwh": 46000,
            "electricity_kg": 32200,
            "diesel_l": 2450,
            "diesel_kg": 6125,
            "partial_kg": 38325,
            "partial_t": 38.325,
            "note": "Electricity 46,000 kWh × 0.70 = 32,200 kg; diesel 800 + 750 L + 0.9 kL (=900 L) × 2.50 = 6,125 kg; partial assessed total 38,325 kg = 38.325 t CO₂e — fictional, illustrative factors.",
        },
    })


def write_fallback(payload: dict) -> None:
    text = json.dumps(payload, indent=2, default=str)
    for path in (FALLBACK_PATH, WEB_FALLBACK_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def write_pristine_fallback() -> None:
    """Fallback JSON is always built from a fresh in-memory demo, never from a mutated live DB."""
    mem = db.connect(":memory:")
    ensure_demo_and_snapshot(mem)
    write_fallback(build_bootstrap(mem))
    mem.close()


@app.on_event("startup")
def startup():
    global _conn
    path = _db_path()
    if os.environ.get("CARBONOS_KEEP_DB") != "1" and path != ":memory:":
        p = Path(path)
        if p.exists():
            p.unlink()
        _conn = None
    ensure_demo_and_snapshot(conn())
    try:
        write_pristine_fallback()
    except Exception:
        pass


@app.get("/api/health")
@locked
def health():
    return {"ok": True}


@app.get("/api/bootstrap")
@locked
def bootstrap():
    try:
        return build_bootstrap(conn())
    except Exception as e:
        if FALLBACK_PATH.exists():
            return json.loads(FALLBACK_PATH.read_text(encoding="utf-8"))
        return err(e, 500)


@app.post("/api/ensure-demo")
@locked
def ensure_demo():
    try:
        ensure_demo_and_snapshot(conn())
        return build_bootstrap(conn())
    except Exception as e:
        return err(e, 500)


@app.post("/api/calculate")
@locked
def calculate(reporting_mode: str = Query("demo")):
    try:
        c = conn()
        ctx = current_context(c)
        if ctx is None:
            raise db.ValidationError(["No factory or period."])
        _f, period, _p = ctx
        sid = db.run_calculation(c, period["id"], reporting_mode=reporting_mode)
        payload = build_bootstrap(c)
        payload["created_snapshot_id"] = sid
        return payload
    except Exception as e:
        return err(e)


@app.post("/api/what-if")
@locked
def what_if(body: dict):
    """Preview a quantity change on one result using the real engine. Does not persist."""
    try:
        c = conn()
        ctx = current_context(c)
        if ctx is None:
            raise db.ValidationError(["No factory or period."])
        _f, period, _p = ctx
        snap = db.latest_snapshot(c, period["id"])
        if snap is None:
            raise db.ValidationError(["No snapshot."])
        rid = int(body["result_id"])
        new_qty = body["quantity"]
        target = next((r for r in db.get_results(c, snap["id"]) if r["id"] == rid), None)
        if target is None:
            raise HTTPException(404, "Result not found")
        activity = dict(target["activity_snapshot"])
        activity["quantity"] = new_qty
        factor = target["factor_snapshot"]
        preview = calc.calculate_record(activity, factor, reporting_mode=snap["reporting_mode"])
        before = target.get("result_value")
        after = preview.get("result_value")
        plain = None
        if after is not None:
            plain = plain_formula(new_qty, activity.get("unit"), preview.get("factor_value_snapshot"),
                                  preview.get("factor_numerator_unit_snapshot"),
                                  preview.get("factor_denominator_unit_snapshot"), after)
        cat_key = activity.get("category")
        others = [r for r in db.get_results(c, snap["id"]) if r["id"] != rid]
        cat_before = sum(r["result_value"] or 0 for r in db.get_results(c, snap["id"])
                         if r["activity_snapshot"]["category"] == cat_key and r["result_value"] is not None)
        cat_after_parts = [r["result_value"] for r in others
                           if r["activity_snapshot"]["category"] == cat_key and r["result_value"] is not None]
        if after is not None:
            cat_after_parts.append(after)
        total_before = snap["assessed_total_kg_co2e"]
        total_after_parts = [r["result_value"] for r in others if r["result_value"] is not None]
        if after is not None:
            total_after_parts.append(after)
        return json_safe({
            "ok": True,
            "result_id": rid,
            "quantity_before": target.get("input_quantity_snapshot"),
            "quantity_after": new_qty,
            "unit": activity.get("unit"),
            "kg_before": before,
            "kg_after": after,
            "status": preview.get("status"),
            "message": preview.get("message"),
            "plain_formula": plain,
            "engine_formula": preview.get("formula_description"),
            "category_kg_before": cat_before,
            "category_kg_after": sum(cat_after_parts) if cat_after_parts else None,
            "total_kg_before": total_before,
            "total_kg_after": sum(total_after_parts) if total_after_parts else None,
        })
    except Exception as e:
        return err(e)


@app.patch("/api/activities/{record_id}")
@locked
def patch_activity(record_id: int, body: dict):
    try:
        c = conn()
        allow = body.get("quantity") is None
        db.update_activity(c, record_id, {"quantity": body.get("quantity")}, allow_missing_quantity=allow)
        return {"ok": True}
    except Exception as e:
        return err(e)


@app.post("/api/import/preview")
async def import_preview(file: UploadFile = File(...)):
    try:
        c = conn()
        ctx = current_context(c)
        if ctx is None:
            raise db.ValidationError(["No factory or period."])
        _f, period, _p = ctx
        content = await file.read()
        with LOCK:
            pv = imports.parse_csv(content, file.filename or "upload.csv", period, db.list_activities(c, period["id"]))
        return json_safe({"ok": True, **pv})
    except Exception as e:
        return err(e)


@app.post("/api/import/commit")
async def import_commit(file: UploadFile = File(...)):
    try:
        content = await file.read()
        with LOCK:
            return _commit_upload(content, file.filename or "upload.csv")
    except Exception as e:
        return err(e)


def _commit_upload(content: bytes, filename: str):
    try:
        c = conn()
        ctx = current_context(c)
        if ctx is None:
            raise db.ValidationError(["No factory or period."])
        _f, period, _p = ctx
        pv = imports.parse_csv(content, filename, period, db.list_activities(c, period["id"]))
        out = imports.commit_import(c, period["id"], pv)
        before_unresolved = None
        snap = db.latest_snapshot(c, period["id"])
        if snap:
            before_unresolved = snap["unresolved_count"]
        sid = db.run_calculation(c, period["id"], reporting_mode="demo")
        after = db.get_snapshot(c, sid)
        closed = False
        if before_unresolved is not None and after is not None:
            closed = after["unresolved_count"] < before_unresolved
        payload = build_bootstrap(c)
        payload["import_result"] = out
        payload["gap_closed"] = closed
        return json_safe(payload)
    except Exception as e:
        return err(e)


@app.post("/api/import/preview-text")
@locked
def import_preview_text(filename: str = Form(...), csv_text: str = Form(...)):
    try:
        c = conn()
        ctx = current_context(c)
        if ctx is None:
            raise db.ValidationError(["No factory or period."])
        _f, period, _p = ctx
        pv = imports.parse_csv(csv_text, filename, period, db.list_activities(c, period["id"]))
        return json_safe({"ok": True, **pv})
    except Exception as e:
        return err(e)


@app.post("/api/reset")
@locked
def reset():
    """Restore the pristine fictional demo (used between demo runs and by tests)."""
    global _conn
    try:
        if _conn is not None:
            _conn.close()
        _conn = None
        path = _db_path()
        if path != ":memory:" and Path(path).exists():
            Path(path).unlink()
        c = conn()
        ensure_demo_and_snapshot(c)
        return build_bootstrap(c)
    except Exception as e:
        return err(e, 500)


@app.post("/api/demo/close-gap")
@locked
def close_gap():
    """Demo action: add ONE fictional, unsourced coal factor so a real gap closes (see COAL_DEMO_FACTOR)."""
    try:
        c = conn()
        ctx = current_context(c)
        if ctx is None:
            raise db.ValidationError(["No factory or period."])
        _f, period, _p = ctx
        before = db.latest_snapshot(c, period["id"])
        if db.get_factor(c, COAL_DEMO_FACTOR["id"]) is None:
            db.create_factor(c, dict(COAL_DEMO_FACTOR))
        sid = db.run_calculation(c, period["id"], reporting_mode="demo")
        after = db.get_snapshot(c, sid)
        payload = build_bootstrap(c)
        payload["created_snapshot_id"] = sid
        payload["gap_closed"] = bool(before and after["unresolved_count"] < before["unresolved_count"])
        return json_safe(payload)
    except Exception as e:
        return err(e)


@app.get("/api/report/{snapshot_id}")
@locked
def report(snapshot_id: int):
    try:
        md = reporting.markdown_report(conn(), snapshot_id)
        return {"ok": True, "markdown": md}
    except Exception as e:
        return err(e)


@app.get("/api/export/{snapshot_id}")
@locked
def export_zip(snapshot_id: int):
    try:
        c = conn()
        data = reporting.export_bundle(c, snapshot_id)
        db.log_event(c, "report_exported", "calculation_snapshot", snapshot_id,
                     f"Exported zip bundle for snapshot #{snapshot_id}.")
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="snapshot{snapshot_id}_exports.zip"'})
    except Exception as e:
        return err(e)


@app.get("/api/fallback/bootstrap.json")
@locked
def fallback_file():
    if FALLBACK_PATH.exists():
        return json.loads(FALLBACK_PATH.read_text(encoding="utf-8"))
    return build_bootstrap(conn())


if WEB_DIST.exists():  # `npm --prefix web run build` once, then uvicorn alone serves the whole demo on :8000
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")

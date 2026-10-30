"""CarbonOS Sugar — Streamlit prototype UI.

All numbers shown here come from stored calculation snapshots or live database
rows; there are no hard-coded totals. Calculation logic lives in calculations.py.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import pandas as pd
import streamlit as st

import calculations as calc
import database as db
import imports
import reporting
import seed_data

st.set_page_config(page_title="CarbonOS Sugar (prototype)", page_icon="🌿", layout="wide")

PAGES = ["Overview", "Setup", "Activity data", "CSV import", "Emission factors",
         "Calculations & traceability", "History", "Reports & export"]
STATUS_ICON = {"calculated": "✅", "missing_activity_data": "🕳️", "missing_factor": "❓", "unit_mismatch": "⛔",
               "illustrative_factor": "🧪", "needs_review": "🔎", "not_assessed": "➖", "valid": "✅"}
STATUS_HELP = {
    "calculated": "Numeric result produced.",
    "missing_activity_data": "Quantity missing — never treated as zero.",
    "missing_factor": "No usable emission factor — never treated as zero.",
    "unit_mismatch": "Units incompatible and no documented conversion — rejected.",
    "illustrative_factor": "Factor is illustrative; blocked in real-reporting mode.",
    "needs_review": "Value or provenance needs human review before it can be calculated.",
    "not_assessed": "Category/method not supported or no data in the MVP.",
}


@st.cache_resource
def _connection(path: str):
    return db.connect(path)


def conn():
    return _connection(os.environ.get("CARBONOS_DB", db.DEFAULT_DB_PATH))


def flash(msg: str, level: str = "success") -> None:
    st.session_state.setdefault("_flash", []).append((level, msg))


def show_flash() -> None:
    for level, msg in st.session_state.pop("_flash", []):
        getattr(st, level)(msg)


def kg_t(kg) -> str:
    return "—" if kg is None else f"{calc.kg_to_tonnes(kg):,.3f} t CO₂e"


def kg_fmt(kg) -> str:
    return "—" if kg is None else f"{kg:,.2f} kg CO₂e"


def show_errors(exc: db.ValidationError) -> None:
    for e in exc.errors:
        st.error(e)


# --------------------------------------------------------------------------
# Shared widgets
# --------------------------------------------------------------------------
def top_banners(c, factory: dict, period: dict) -> None:
    acts = db.list_activities(c, period["id"])
    if factory["is_synthetic"] or any(a["provenance"] == "synthetic_demo" for a in acts):
        st.warning(calc.SYNTHETIC_LABEL, icon="🧪")
    if st.session_state.get("mode") == "real":
        st.info("Real-reporting mode: only `verified_for_use` factors and non-synthetic activity records "
                "are calculated. Everything else stays unresolved.")


def run_calc_button(c, period_id: int, key: str) -> None:
    if st.button("▶ Run calculation (creates a new snapshot)", key=key, type="primary"):
        try:
            sid = db.run_calculation(c, period_id, reporting_mode=st.session_state.get("mode", "demo"))
            flash(f"Calculation complete — snapshot #{sid} created. Previous snapshots are preserved.")
            st.rerun()
        except db.ValidationError as e:
            show_errors(e)


def stale_notice(c, snap: dict) -> None:
    if db.is_stale(c, snap):
        st.warning("This calculation predates the latest activity-data, factor or period change. "
                   "Run a new calculation to refresh it.", icon="⏱️")


def render_trace(c, snap: dict, r: dict) -> None:
    a, f = r["activity_snapshot"], r["factor_snapshot"]
    st.markdown(f"#### Trace for activity record #{r['activity_record_id']} — {a['activity_name']}")
    icon = STATUS_ICON.get(r["status"], "")
    if r["result_value"] is not None:
        st.success(f"**{r['result_value']:,.4f} {r['result_unit']}**  ({calc.kg_to_tonnes(r['result_value']):,.6f} t CO₂e)")
    else:
        st.error(f"{icon} **No numeric result — status `{r['status']}`.** {r['message']}")
    for w in r["warnings"]:
        st.warning(w)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**1 · Activity record (as stored in this snapshot)**")
        st.table(pd.DataFrame({"field": ["Record ID", "Date", "Category", "Quantity", "Unit", "Source reference",
                                         "Source file/row", "Provenance", "Notes"],
                               "value": [a["id"], a["activity_date"], a["category"], a.get("quantity"), a["unit"],
                                         a.get("source_reference"), a.get("source_row_reference"),
                                         a["provenance"], a.get("notes")]}).astype(str).set_index("field"))
        live = db.get_activity(c, r["activity_record_id"])
        if live and live["quantity"] != a.get("quantity"):
            st.info(f"The live record now says quantity = {live['quantity']}; this snapshot keeps {a.get('quantity')}.")
    with c2:
        st.markdown("**2 · Emission factor (snapshot)**")
        if f:
            st.table(pd.DataFrame({"field": ["Factor ID", "Name", "Value", "Units", "Status", "Provenance",
                                             "Geography", "Year", "Source", "Notes"],
                                   "value": [f["id"], f["name"], f["value"],
                                             f"{f['numerator_unit']} / {f['denominator_unit']}", f["status"],
                                             f["provenance"], f.get("geography"), f.get("applicable_year"),
                                             reporting._factor_source(f), f.get("notes")]}).astype(str).set_index("field"))
        else:
            st.write("No factor applied (none available or none usable).")
    st.markdown("**3 · Formula and conversion**")
    st.code(r["formula_description"] or "No calculation performed.", language="text")
    st.write("Conversion applied:", r["conversion_description"] or "none")
    st.markdown("**4 · Calculation metadata**")
    st.write(f"Snapshot **#{snap['id']}** · calculated at `{r['calculated_at']}` (UTC) · engine "
             f"`{r['engine_version']}` · mode `{snap['reporting_mode']}` · provenance: activity "
             f"`{r['provenance_snapshot']['activity']}`, factor `{r['provenance_snapshot']['factor']}`, result `derived`")
    if r["status"] == calc.CALCULATED:
        re_val = calc.recompute_from_snapshot(r)
        if re_val == r["result_value"]:
            st.caption(f"✔ Reproduced from stored snapshot values alone: {re_val:,.4f} kg CO₂e (matches).")
        else:
            st.error("Recomputing from the snapshot does NOT match the stored result.")


def trace_picker(c, snap: dict, key: str, only_status: str | None = None) -> None:
    results = db.get_results(c, snap["id"])
    if only_status:
        results = [r for r in results if r["status"] == only_status]
    if not results:
        st.info("No results to trace.")
        return
    labels = {r["id"]: f"#{r['activity_record_id']} · {r['activity_snapshot']['activity_date']} · "
                       f"{r['activity_snapshot']['activity_name']} · {STATUS_ICON.get(r['status'], '')} {r['status']}"
                       + (f" · {r['result_value']:,.2f} kg CO₂e" if r["result_value"] is not None else "")
              for r in results}
    rid = st.selectbox("Select a result to trace back to its source data", list(labels), format_func=labels.get,
                       key=f"trace_{key}")
    render_trace(c, snap, next(r for r in results if r["id"] == rid))


def results_df(c, snap: dict) -> pd.DataFrame:
    rows = []
    for r in db.get_results(c, snap["id"]):
        a = r["activity_snapshot"]
        rows.append({"Record": r["activity_record_id"], "Date": a["activity_date"], "Category": a["category"],
                     "Activity": a["activity_name"], "Quantity": r["input_quantity_snapshot"],
                     "Unit": r["input_unit_snapshot"], "Factor": r["factor_id"],
                     "Result": r["result_value"], "Result unit": r["result_unit"],
                     "Status": f"{STATUS_ICON.get(r['status'], '')} {r['status']}",
                     "Warnings": " | ".join(r["warnings"]) or None,
                     "Snapshot": snap["id"], "Calculated at": r["calculated_at"], "Engine": r["engine_version"]})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
def page_overview(c, factory, period):
    st.header("Overview")
    top_banners(c, factory, period)
    left, right = st.columns([3, 1])
    left.markdown(f"**{factory['name']}**  \nReporting period **{period['start_date']} → {period['end_date']}**  \n"
                  f"Boundary (as entered): {period['boundary_description'] or '_not supplied_'}")
    with right:
        run_calc_button(c, period["id"], "run_overview")
    snap = db.latest_snapshot(c, period["id"])
    if snap is None:
        st.info("No calculation has been run for this period yet. Add activity data, then run a calculation.")
        _recent_records(c, period)
        return
    stale_notice(c, snap)
    s = snap["summary"]
    inv, t = s["inventory"], s["inventory"]["totals"]
    if snap["inventory_status"] == "incomplete":
        st.error("**INCOMPLETE INVENTORY.** The figure below is a *partial assessed total* — it covers only the "
                 "records that could be calculated and is NOT the factory's total emissions.", icon="⚠️")
    else:
        st.success("All declared categories have calculated records. Coverage of the whole period is not verified "
                   "and the inventory has not been independently verified.")
    m = st.columns(5)
    m[0].metric(t["total_label"], kg_t(t["assessed_kg_co2e"]), help=kg_fmt(t["assessed_kg_co2e"]))
    m[1].metric("Unresolved records", inv["unresolved_records"])
    m[2].metric("Categories not fully assessed", len(t["unresolved_categories"]))
    m[3].metric("Records calculated", t["n_calculated"])
    m[4].metric("Snapshot", f"#{snap['id']}", help=f"{snap['created_at']} · engine {snap['engine_version']} · {snap['reporting_mode']} mode")
    if t["synthetic_demo_kg_co2e"]:
        st.caption(f"Of the assessed total, {kg_t(t['synthetic_demo_kg_co2e'])} rests on synthetic demonstration "
                   "records and/or illustrative factors.")

    st.subheader("Energy intensity (factory-wide)")
    cols = st.columns(len(s["intensity"]))
    for col, i in zip(cols, s["intensity"]):
        if i["value"] is not None:
            col.metric(i["label"], f"{i['value']:,.3f}", help=f"{i['unit']} · {i['scope']}")
            col.caption(i["unit"])
        else:
            col.metric(i["label"], "n/a")
            col.caption(i["reason"])

    st.subheader("Emissions by category")
    cat_df = pd.DataFrame([{
        "Category": cc["label"], "Records": cc["n_records"], "Calculated": cc["n_calculated"],
        "Unresolved": cc["n_unresolved"],
        "Assessed (kg CO₂e)": None if cc["assessed_kg_co2e"] is None else round(cc["assessed_kg_co2e"], 2),
        "Status": cc["completeness"], "Note": cc["note"]} for cc in inv["categories"]])
    st.dataframe(cat_df, hide_index=True, width="stretch")
    plot = cat_df.dropna(subset=["Assessed (kg CO₂e)"])
    if not plot.empty:
        st.bar_chart(plot.set_index("Category")["Assessed (kg CO₂e)"])
        st.caption("Only categories with calculated results are charted. Unresolved and not-assessed categories "
                   "are NOT zero — see the table above.")

    st.subheader("Trace a result")
    trace_picker(c, snap, "overview")

    st.subheader("Data-quality flags")
    for a in s["anomalies"]:
        fn = {"high": st.error, "medium": st.warning}.get(a["severity"], st.info)
        fn(f"**{a['code']}** — {a['message']}  \n_Why flagged: {a['why_flagged']}_")
    with st.expander(f"Recommendations ({len(s['recommendations'])}) — observation-based or labelled generic"):
        for rec in s["recommendations"]:
            st.markdown(f"**{rec['title']}** · _{rec['basis']}_")
            for k in ("observation", "evidence", "why_it_matters", "suggested_action", "expected_benefit",
                      "confidence", "assumptions", "verification", "required_additional_data", "limitation"):
                st.markdown(f"- **{k.replace('_', ' ').capitalize()}:** {rec[k]}")
            st.divider()
    _recent_records(c, period)


def _recent_records(c, period):
    st.subheader("Recent activity records (live)")
    acts = db.list_activities(c, period["id"])[-8:]
    if acts:
        st.dataframe(pd.DataFrame(acts)[["id", "activity_date", "category", "activity_name", "quantity", "unit",
                                         "provenance", "status"]], hide_index=True, width="stretch")
    else:
        st.info("No activity records yet — add one on **Activity data** or import a CSV.")


def page_setup(c, factory, period):
    st.header("Setup — factory and reporting period")
    if factory:
        top_banners(c, factory, period) if period else None
    with st.expander("Load the FICTIONAL synthetic demo dataset", expanded=factory is None):
        st.warning(calc.SYNTHETIC_LABEL)
        st.write("Creates a fictional mill, two periods, two illustrative factors and fictional records.")
        skip = st.checkbox("Skip current-period records (so I can import `sample_data/demo_activities.csv` myself)")
        if st.button("Load synthetic demo dataset"):
            try:
                seed_data.load_demo(c, include_current_records=not skip)
                flash("Fictional demo dataset loaded.")
                st.rerun()
            except db.ValidationError as e:
                show_errors(e)
    st.subheader("Add a factory")
    with st.form("new_factory"):
        name = st.text_input("Factory name")
        loc = st.text_input("Location (optional)")
        notes = st.text_area("Notes / data sources (optional)")
        if st.form_submit_button("Create factory"):
            try:
                db.create_factory(c, name, loc or None, notes or None)
                flash(f"Factory '{name}' created.")
                st.rerun()
            except db.ValidationError as e:
                show_errors(e)
    factories = db.list_factories(c)
    if factories:
        st.subheader("Add a reporting period")
        with st.form("new_period"):
            fsel = st.selectbox("Factory", [f["id"] for f in factories],
                                format_func=lambda i: next(f["name"] for f in factories if f["id"] == i))
            d1, d2 = st.columns(2)
            start = d1.date_input("Start date", dt.date(2026, 1, 1))
            end = d2.date_input("End date", dt.date(2026, 3, 31))
            boundary = st.text_area("Reporting-boundary description")
            p1, p2 = st.columns(2)
            cane = p1.text_input("Cane crushed (t) — blank = unknown")
            sugar = p2.text_input("Sugar produced (t) — blank = unknown")
            if st.form_submit_button("Create period"):
                cq, ce = calc.parse_quantity(cane)
                sq, se = calc.parse_quantity(sugar)
                if ce or se:
                    st.error(ce or se)
                else:
                    try:
                        db.create_period(c, fsel, start.isoformat(), end.isoformat(), boundary or None, cq, sq)
                        flash("Reporting period created.")
                        st.rerun()
                    except db.ValidationError as e:
                        show_errors(e)
    if period:
        st.subheader(f"Edit selected period ({period['start_date']} → {period['end_date']})")
        pid = period["id"]
        boundary = st.text_area("Boundary description", period["boundary_description"] or "", key=f"b_{pid}")
        p1, p2 = st.columns(2)
        cane = p1.text_input("Cane crushed (t) — blank = unknown",
                             "" if period["cane_crushed_t"] is None else str(period["cane_crushed_t"]), key=f"c_{pid}")
        sugar = p2.text_input("Sugar produced (t) — blank = unknown",
                              "" if period["sugar_produced_t"] is None else str(period["sugar_produced_t"]), key=f"s_{pid}")
        notes = st.text_area("Data-source notes", period["data_source_notes"] or "", key=f"n_{pid}")
        excluded = json.loads(period["excluded_categories_json"] or "{}")
        used = {a["category"] for a in db.list_activities(c, pid)}
        choices = [k for k in calc.CATEGORIES if k not in used]
        sel = st.multiselect("Categories you declare OUTSIDE this boundary (shown as excluded, never hidden)",
                             choices, default=[k for k in excluded if k in choices],
                             format_func=lambda k: calc.CATEGORIES[k]["label"], key=f"x_{pid}")
        reasons = {k: st.text_input(f"Reason for excluding {calc.CATEGORIES[k]['label']}", excluded.get(k, ""),
                                    key=f"xr_{pid}_{k}") for k in sel}
        if st.button("Save period changes", key=f"save_{pid}"):
            cq, ce = calc.parse_quantity(cane)
            sq, se = calc.parse_quantity(sugar)
            if ce or se:
                st.error(ce or se)
            elif any(not v.strip() for v in reasons.values()):
                st.error("Give a reason for every excluded category.")
            else:
                try:
                    db.update_period(c, pid, boundary_description=boundary or None, cane_crushed_t=cq,
                                     sugar_produced_t=sq, data_source_notes=notes or None,
                                     excluded_categories={k: v.strip() for k, v in reasons.items()})
                    flash("Period updated. Existing snapshots may now be out of date.")
                    st.rerun()
                except db.ValidationError as e:
                    show_errors(e)


def page_activity(c, factory, period):
    st.header("Activity data")
    top_banners(c, factory, period)
    f1, f2 = st.columns(2)
    fcat = f1.selectbox("Filter by category", ["All"] + list(calc.CATEGORIES),
                        format_func=lambda k: k if k == "All" else calc.CATEGORIES[k]["label"])
    fstat = f2.selectbox("Filter by status", ["All", "valid", "missing_activity_data"])
    acts = db.list_activities(c, period["id"], None if fcat == "All" else fcat, None if fstat == "All" else fstat)
    st.caption(f"Reporting period {period['start_date']} → {period['end_date']} · {len(acts)} record(s) shown")
    if acts:
        st.dataframe(pd.DataFrame(acts).drop(columns=["factory_id", "reporting_period_id"]), hide_index=True,
                     width="stretch")
    else:
        st.info("No records match. Add one below or import a CSV.")

    st.subheader("Add a record")
    cat = st.selectbox("Category", list(calc.CATEGORIES), format_func=lambda k: calc.CATEGORIES[k]["label"],
                       key="add_cat")
    meta = calc.CATEGORIES[cat]
    if not meta["method"]:
        st.warning(meta["note"])
    default_prov = 1 if factory["is_synthetic"] else 0
    with st.form("add_activity", clear_on_submit=False):
        d = st.date_input("Activity date", dt.date.fromisoformat(period["start_date"]), key="add_date")
        name = st.text_input("Activity name", key="add_name")
        qc1, qc2, qc3 = st.columns(3)
        qty = qc1.text_input("Quantity (plain number)", key="add_qty")
        unit = qc2.selectbox("Unit", list(meta["units"]), key="add_unit")
        missing = qc3.checkbox("Quantity not yet available (record as incomplete)", key="add_missing")
        src = st.text_input("Source / supporting reference (bill no., log, document)", key="add_src")
        prov = st.selectbox("Provenance", list(calc.ACTIVITY_PROVENANCE), index=default_prov, key="add_prov")
        notes = st.text_area("Notes", key="add_notes")
        if st.form_submit_button("Add record"):
            rec = dict(activity_date=d.isoformat(), category=cat, activity_name=name,
                       quantity=None if missing else qty, unit=unit, source_reference=src or None,
                       provenance=prov, notes=notes or None)
            try:
                rid = db.add_activity(c, period["id"], rec, allow_missing_quantity=missing)
                flash(f"Record #{rid} added. Run a calculation to include it.")
                st.rerun()
            except db.ValidationError as e:
                show_errors(e)

    if acts:
        st.subheader("Edit a record")
        rid = st.selectbox("Record", [a["id"] for a in acts],
                           format_func=lambda i: next(f"#{a['id']} · {a['activity_date']} · {a['activity_name']}"
                                                      for a in acts if a["id"] == i), key="edit_sel")
        rec = db.get_activity(c, rid)
        units = list(calc.CATEGORIES[rec["category"]]["units"])
        with st.form(f"edit_activity_{rid}"):
            e_date = st.date_input("Activity date", dt.date.fromisoformat(rec["activity_date"]), key=f"e_d_{rid}")
            e_name = st.text_input("Activity name", rec["activity_name"], key=f"e_n_{rid}")
            e1, e2, e3 = st.columns(3)
            e_qty = e1.text_input("Quantity", "" if rec["quantity"] is None else f"{rec['quantity']:g}", key=f"e_q_{rid}")
            e_unit = e2.selectbox("Unit", units, index=units.index(rec["unit"]) if rec["unit"] in units else 0,
                                  key=f"e_u_{rid}")
            e_missing = e3.checkbox("Quantity not available", rec["quantity"] is None, key=f"e_m_{rid}")
            e_src = st.text_input("Source reference", rec["source_reference"] or "", key=f"e_s_{rid}")
            provs = list(calc.ACTIVITY_PROVENANCE)
            e_prov = st.selectbox("Provenance", provs, index=provs.index(rec["provenance"]), key=f"e_p_{rid}")
            e_notes = st.text_area("Notes", rec["notes"] or "", key=f"e_nt_{rid}")
            if st.form_submit_button("Save changes"):
                try:
                    db.update_activity(c, rid, dict(activity_date=e_date.isoformat(), activity_name=e_name,
                                                    quantity=None if e_missing else e_qty, unit=e_unit,
                                                    source_reference=e_src or None, provenance=e_prov,
                                                    notes=e_notes or None), allow_missing_quantity=e_missing)
                    flash(f"Record #{rid} updated. The latest calculation may now be out of date — run a new "
                          "calculation to create a new snapshot (old snapshots are kept).", "warning")
                    st.rerun()
                except db.ValidationError as e:
                    show_errors(e)


def page_import(c, factory, period):
    st.header("CSV import")
    top_banners(c, factory, period)
    st.write("Required columns: " + ", ".join(f"`{x}`" for x in imports.REQUIRED_COLUMNS)
             + ". Optional: `source_reference`, `notes`. Dates `YYYY-MM-DD`; quantities plain numbers "
               "(no thousands separators); units and categories must match exactly the lists below.")
    with st.expander("Valid categories and units"):
        st.table(pd.DataFrame([{"category": k, "units": ", ".join(v["units"])} for k, v in calc.CATEGORIES.items()]))
    d1, d2, d3 = st.columns(3)
    d1.download_button("⬇ Template CSV", imports.TEMPLATE_CSV, "carbonos_template.csv", "text/csv")
    for col, fname, label in ((d2, "demo_activities.csv", "⬇ Sample CSV (fictional)"),
                              (d3, "demo_activities_with_errors.csv", "⬇ Sample CSV with errors (fictional)")):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data", fname)
        if os.path.exists(p):
            with open(p, "rb") as fh:
                col.download_button(label, fh.read(), fname, "text/csv")
    up = st.file_uploader("Upload a CSV", type=["csv"])
    if up is None:
        st.info("Upload a file to preview and validate it. Nothing is saved until you confirm.")
        return
    pv = imports.parse_csv(up.getvalue(), up.name, period, db.list_activities(c, period["id"]))
    if pv["header_errors"]:
        for e in pv["header_errors"]:
            st.error(e)
        return
    if pv["ignored_columns"]:
        st.warning("These columns are not part of the import contract and will be ignored: "
                   + ", ".join(pv["ignored_columns"]))
    m = st.columns(3)
    m[0].metric("Rows read", pv["n_rows"])
    m[1].metric("Valid", pv["n_valid"])
    m[2].metric("Rejected", pv["n_rejected"])
    prev_df = pd.DataFrame([{"Line": r["row_number"], "Result": r["status"].upper(),
                             "Errors": " ; ".join(r["errors"]), **{k: v for k, v in r["raw"].items()}}
                            for r in pv["rows"]])
    st.dataframe(prev_df, hide_index=True, width="stretch")
    if pv["n_rejected"]:
        st.warning(f"{pv['n_rejected']} row(s) will NOT be imported (see Errors). They will be listed in History.")
    if pv["n_valid"] and st.button(f"Confirm import of {pv['n_valid']} valid row(s)", type="primary"):
        try:
            out = imports.commit_import(c, period["id"], pv)
            flash(f"Imported {out['imported']} record(s); rejected {out['rejected']} row(s). "
                  "Run a calculation to include them.")
            st.rerun()
        except db.ValidationError as e:
            show_errors(e)


def page_factors(c, factory, period):
    st.header("Emission-factor library")
    st.info("The prototype ships **no real emission factors**. The demo factors are fictional and marked "
            "`illustrative`. Enter a real factor only after verifying its value, unit, geography, year, boundary and "
            "gases against the source (starting points: CEA CO₂ Baseline Database, TERI sugar-sector report, GHG "
            "Protocol). Marking a factor `verified_for_use` is YOUR attestation — the app cannot verify it.")
    factors = db.list_factors(c)
    if factors:
        df = pd.DataFrame(factors)
        df["units"] = df["numerator_unit"] + " / " + df["denominator_unit"]
        df["source"] = [reporting._factor_source(f) for f in factors]
        st.dataframe(df[["id", "name", "category", "value", "units", "geography", "applicable_year", "source",
                         "provenance", "status", "is_active", "updated_at"]], hide_index=True, width="stretch")
    else:
        st.warning("No factors yet. Categories without a factor stay `missing_factor` (never zero).")

    st.subheader("Add a factor")
    with st.form("add_factor"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name")
        cat = c2.selectbox("Category", list(calc.CATEGORIES), format_func=lambda k: calc.CATEGORIES[k]["label"])
        v1, v2, v3 = st.columns(3)
        val = v1.text_input("Value")
        num = v2.selectbox("Numerator unit", ["kgCO2e", "tCO2e"])
        den = v3.selectbox("Denominator unit", ["kWh", "MWh", "GJ", "L", "kL", "m3", "kg", "t", "tkm", "kg_COD"])
        g1, g2, g3 = st.columns(3)
        geo = g1.text_input("Geography")
        year = g2.text_input("Applicable year")
        gas = g3.text_input("Gas / emissions basis (e.g. CO2e)")
        s1, s2 = st.columns(2)
        org = s1.text_input("Source organisation")
        doc = s2.text_input("Source document title")
        s3, s4 = st.columns(2)
        url = s3.text_input("Source URL")
        ref = s4.text_input("Page / table / section")
        p1, p2 = st.columns(2)
        status = p1.selectbox("Status", ["needs_review", "illustrative", "verified_for_use", "deprecated"])
        prov = p2.selectbox("Provenance", list(calc.PROVENANCE_VALUES), index=list(calc.PROVENANCE_VALUES).index("user_provided"))
        notes = st.text_area("Notes and limitations")
        active = st.checkbox("Use for calculations (deactivates other factors in this category)", True)
        if st.form_submit_button("Add factor"):
            try:
                fid = db.create_factor(c, _factor_form(name, cat, val, num, den, geo, year, gas, org, doc, url, ref,
                                                       status, prov, notes, active))
                flash(f"Factor {fid} added. Existing snapshots may now be out of date.")
                st.rerun()
            except (db.ValidationError, ValueError) as e:
                for m in (e.errors if isinstance(e, db.ValidationError) else [str(e)]):
                    st.error(m)

    if factors:
        st.subheader("Edit a factor")
        fid = st.selectbox("Factor", [f["id"] for f in factors], key="edit_factor_sel")
        f = db.get_factor(c, fid)
        st.caption("Editing changes the live factor only. Existing calculation snapshots keep the value they used.")
        with st.form(f"edit_factor_{fid}"):
            e1, e2, e3 = st.columns(3)
            e_val = e1.text_input("Value", repr(f["value"]), key=f"ev_{fid}")
            nums = ["kgCO2e", "tCO2e"]
            e_num = e2.selectbox("Numerator unit", nums + ([f["numerator_unit"]] if f["numerator_unit"] not in nums else []),
                                 index=(nums + [f["numerator_unit"]]).index(f["numerator_unit"]), key=f"en_{fid}")
            e_den = e3.text_input("Denominator unit", f["denominator_unit"], key=f"ed_{fid}")
            e_geo = st.text_input("Geography", f["geography"] or "", key=f"eg_{fid}")
            e_year = st.text_input("Applicable year", "" if f["applicable_year"] is None else str(f["applicable_year"]), key=f"ey_{fid}")
            e_org = st.text_input("Source organisation", f["source_organization"] or "", key=f"eo_{fid}")
            e_doc = st.text_input("Source document", f["source_document"] or "", key=f"edc_{fid}")
            e_url = st.text_input("Source URL", f["source_url"] or "", key=f"eu_{fid}")
            e_ref = st.text_input("Page / table / section", f["source_reference"] or "", key=f"er_{fid}")
            sts = ["needs_review", "illustrative", "verified_for_use", "deprecated"]
            e_status = st.selectbox("Status", sts, index=sts.index(f["status"]), key=f"es_{fid}")
            pvs = list(calc.PROVENANCE_VALUES)
            e_prov = st.selectbox("Provenance", pvs, index=pvs.index(f["provenance"]), key=f"ep_{fid}")
            e_notes = st.text_area("Notes", f["notes"] or "", key=f"enn_{fid}")
            e_active = st.checkbox("Active", bool(f["is_active"]), key=f"ea_{fid}")
            if st.form_submit_button("Save factor"):
                try:
                    rec = _factor_form(f["name"], f["category"], e_val, e_num, e_den, e_geo, e_year,
                                       f["gas_basis"] or "", e_org, e_doc, e_url, e_ref, e_status, e_prov, e_notes,
                                       e_active)
                    rec.pop("id", None)
                    db.update_factor(c, fid, rec)
                    flash(f"Factor {fid} updated. Existing snapshots keep the old value; the latest calculation "
                          "may now be out of date.", "warning")
                    st.rerun()
                except (db.ValidationError, ValueError) as e:
                    for m in (e.errors if isinstance(e, db.ValidationError) else [str(e)]):
                        st.error(m)


def _factor_form(name, cat, val, num, den, geo, year, gas, org, doc, url, ref, status, prov, notes, active) -> dict:
    v = str(val).strip()
    if not v:
        raise ValueError("Factor value is required.")
    try:
        value = float(v)
    except ValueError:
        raise ValueError(f"Factor value '{v}' is not a number.")
    y = str(year).strip()
    if y and not y.isdigit():
        raise ValueError("Applicable year must be a number such as 2024.")
    return {"name": name, "category": cat, "value": value, "numerator_unit": num, "denominator_unit": den,
            "geography": geo or None, "applicable_year": int(y) if y else None, "gas_basis": gas or None,
            "source_organization": org or None, "source_document": doc or None, "source_url": url or None,
            "source_reference": ref or None, "status": status, "provenance": prov, "notes": notes or None,
            "is_active": int(active)}


def page_calcs(c, factory, period):
    st.header("Calculations & traceability")
    top_banners(c, factory, period)
    run_calc_button(c, period["id"], "run_calcs")
    snaps = db.list_snapshots(c, period["id"])
    if not snaps:
        st.info("No snapshots yet. Run a calculation.")
        return
    sid = st.selectbox("Snapshot", [s["id"] for s in snaps], format_func=lambda i: next(
        f"#{s['id']} · {s['created_at'][:19]} UTC · {s['reporting_mode']} mode · {s['inventory_status']}"
        for s in snaps if s["id"] == i), key="calc_snap")
    snap = db.get_snapshot(c, sid)
    stale_notice(c, snap)
    st.caption(f"Snapshot #{snap['id']} · calculated {snap['created_at']} UTC · engine {snap['engine_version']} · "
               f"{snap['reporting_mode']} mode")
    st.dataframe(results_df(c, snap), hide_index=True, width="stretch")
    with st.expander("Status meanings"):
        for k, v in STATUS_HELP.items():
            st.write(f"{STATUS_ICON[k]} `{k}` — {v}")
    trace_picker(c, snap, "calcs")


def page_history(c, factory, period):
    st.header("History")
    st.caption("An ordinary append-only database table (enforced by triggers). Not tamper-proof.")
    ev = db.list_events(c)
    if ev:
        st.dataframe(pd.DataFrame(ev)[["id", "created_at", "event_type", "entity_type", "entity_id", "description"]],
                     hide_index=True, width="stretch")
        with st.expander("Previous / new values for an event"):
            eid = st.selectbox("Event", [e["id"] for e in ev], key="ev_sel")
            e = next(x for x in ev if x["id"] == eid)
            st.write("Previous"); st.code(e["previous_value_json"] or "—", language="json")
            st.write("New"); st.code(e["new_value_json"] or "—", language="json")
    else:
        st.info("No events yet.")
    st.subheader("Compare calculation snapshots")
    snaps = db.list_snapshots(c, period["id"])
    if len(snaps) < 2:
        st.info("Run at least two calculations for this period to compare snapshots.")
        return
    ids = [s["id"] for s in snaps]
    a, b = st.columns(2)
    old = a.selectbox("Older snapshot", ids, index=min(1, len(ids) - 1), format_func=lambda i: f"#{i}", key="cmp_old")
    new = b.selectbox("Newer snapshot", ids, index=0, format_func=lambda i: f"#{i}", key="cmp_new")
    if old == new:
        st.info("Select two different snapshots.")
        return
    cmp = db.compare_snapshots(c, old, new)
    m = st.columns(3)
    m[0].metric(f"Assessed total #{old}", kg_t(cmp["old_total"]))
    m[1].metric(f"Assessed total #{new}", kg_t(cmp["new_total"]))
    m[2].metric("Change", "—" if cmp["delta_total"] is None else f"{cmp['delta_total']:+,.2f} kg CO₂e")
    st.dataframe(pd.DataFrame(cmp["rows"]), hide_index=True, width="stretch")


def _log_export(sid: int, kind: str):
    db.log_event(conn(), "report_exported", "calculation_snapshot", sid, f"Exported {kind} for snapshot #{sid}.")


def page_reports(c, factory, period):
    st.header("Reports & export")
    top_banners(c, factory, period)
    snaps = db.list_snapshots(c, period["id"])
    if not snaps:
        st.info("Run a calculation first; reports are generated from stored snapshots.")
        return
    sid = st.selectbox("Snapshot to export", [s["id"] for s in snaps], format_func=lambda i: f"#{i}", key="rep_snap")
    snap = db.get_snapshot(c, sid)
    stale_notice(c, snap)
    if snap["inventory_status"] == "incomplete":
        st.error("This snapshot is an INCOMPLETE inventory; exports label the total as a partial assessed total.")
    items = {
        "Factory summary (CSV)": ("factory_summary.csv", reporting.df_to_csv(reporting.summary_df(snap))),
        "Category summary (CSV)": ("category_summary.csv", reporting.df_to_csv(reporting.category_summary_df(snap))),
        "Calculation details (CSV)": ("calculation_details.csv", reporting.df_to_csv(reporting.calculation_details_df(c, sid))),
        "Data quality & unresolved (CSV)": ("data_quality_and_unresolved.csv", reporting.df_to_csv(reporting.unresolved_df(c, snap))),
        "Factor references (CSV)": ("factor_references.csv", reporting.df_to_csv(reporting.factor_references_df(c, sid))),
        "Activity data, live (CSV)": ("activity_data_live.csv", reporting.df_to_csv(reporting.activity_data_df(c, period["id"]))),
    }
    cols = st.columns(3)
    for i, (label, (fname, data)) in enumerate(items.items()):
        cols[i % 3].download_button(label, data, f"snapshot{sid}_{fname}", "text/csv", key=f"dl_{i}",
                                    on_click=_log_export, args=(sid, fname))
    md = reporting.markdown_report(c, sid)
    d1, d2 = st.columns(2)
    d1.download_button("Full report (Markdown)", md, f"snapshot{sid}_report.md", "text/markdown", key="dl_md",
                       on_click=_log_export, args=(sid, "report.md"))
    d2.download_button("All exports (ZIP)", reporting.export_bundle(c, sid), f"snapshot{sid}_exports.zip",
                       "application/zip", key="dl_zip", on_click=_log_export, args=(sid, "zip bundle"))
    st.caption("Exports are built from the stored snapshot, not from live data, except 'Activity data, live'.")
    with st.expander("Report preview", expanded=True):
        st.markdown(md)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    c = conn()
    st.session_state.setdefault("mode", "demo")
    st.sidebar.title("🌿 CarbonOS Sugar")
    st.sidebar.caption("Prototype · not independently verified or certified · not validated in an operating mill")
    mode_label = st.sidebar.radio(
        "Reporting mode", ["Demo — illustrative factors allowed", "Real reporting — verified factors only"],
        index=0 if st.session_state["mode"] == "demo" else 1, key="mode_radio")
    st.session_state["mode"] = "demo" if mode_label.startswith("Demo") else "real"

    factories = db.list_factories(c)
    factory = period = None
    if factories:
        fid = st.sidebar.selectbox("Factory", [f["id"] for f in factories],
                                   format_func=lambda i: next(f["name"] for f in factories if f["id"] == i), key="factory_sel")
        factory = db.get_factory(c, fid)
        periods = db.list_periods(c, fid)
        if periods:
            pid = st.sidebar.selectbox("Reporting period", [p["id"] for p in periods],
                                       format_func=lambda i: next(f"{p['start_date']} → {p['end_date']}" for p in periods if p["id"] == i),
                                       key="period_sel")
            period = db.get_period(c, pid)
    page = st.sidebar.radio("Screen", PAGES, key="page")

    show_flash()
    if page == "Setup":
        page_setup(c, factory, period)
    elif factory is None:
        st.header("Welcome to CarbonOS Sugar")
        st.info("No factory exists yet. Open **Setup** to create a factory, or load the fictional demo dataset.")
        if st.button("Load FICTIONAL synthetic demo dataset"):
            seed_data.load_demo(c)
            flash("Fictional demo dataset loaded.")
            st.rerun()
    elif period is None:
        st.info("This factory has no reporting period. Create one on the **Setup** screen.")
    else:
        {"Overview": page_overview, "Activity data": page_activity, "CSV import": page_import,
         "Emission factors": page_factors, "Calculations & traceability": page_calcs,
         "History": page_history, "Reports & export": page_reports}[page](c, factory, period)
    st.sidebar.divider()
    st.sidebar.caption("Boundary: factory-level inventory & energy performance. Not a product carbon footprint.")


main()

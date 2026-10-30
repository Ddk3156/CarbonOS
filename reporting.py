"""Reports and exports. Everything numeric is built from a stored calculation
snapshot (never from live activity or factor rows), so an export reproduces
exactly what was calculated at that time."""
from __future__ import annotations

import io
import json
import zipfile
from typing import Optional

import pandas as pd

import calculations as calc
import database as db

LIMITATIONS = (
    "This report reflects the activity data, emission factors, and reporting boundary recorded in "
    "CarbonOS Sugar at the time of calculation. Results may be incomplete where activity data, emission "
    "factors, or categories have not been assessed. Synthetic demonstration records and illustrative "
    "factors are not suitable for real-world reporting. This prototype has not been independently "
    "verified or certified, has not been validated in an operating sugar mill, and its audit history is "
    "an ordinary database table, not tamper-proof. Users must review the methodology, source factors, "
    "and boundary before using results for external disclosure."
)

ASSUMPTIONS = [
    "Emissions (kgCO2e) = activity quantity × emission factor; only explicitly defined unit conversions are applied and recorded.",
    "Missing quantities, missing factors and unsupported categories are reported as unresolved and are never treated as zero.",
    "Electricity is reported at factory level; no allocation to process stages is made.",
    "Bagasse (biogenic) and wastewater categories are not assessed in this prototype.",
    "Category 'all_records_calculated' means every recorded record calculated; it does not verify that records cover the whole period.",
    "Reporting boundary and production quantities are as entered by the user and have not been verified.",
]


def _factor_source(f: Optional[dict]) -> Optional[str]:
    if not f:
        return None
    parts = [f.get("source_organization"), f.get("source_document"), f.get("source_reference"), f.get("source_url")]
    s = " | ".join(str(p) for p in parts if p)
    return s or "No source recorded"


def calculation_details_df(conn, snapshot_id: int) -> pd.DataFrame:
    rows = []
    for r in db.get_results(conn, snapshot_id):
        a, f = r["activity_snapshot"], r["factor_snapshot"]
        rows.append({
            "activity_record_id": r["activity_record_id"], "activity_date": a["activity_date"],
            "category": a["category"], "activity_name": a["activity_name"],
            "quantity": r["input_quantity_snapshot"], "input_unit": r["input_unit_snapshot"],
            "source_reference": a.get("source_reference"), "source_row_reference": a.get("source_row_reference"),
            "activity_provenance": r["provenance_snapshot"]["activity"],
            "factor_id": r["factor_id"], "factor_value": r["factor_value_snapshot"],
            "factor_numerator_unit": r["factor_numerator_unit_snapshot"],
            "factor_denominator_unit": r["factor_denominator_unit_snapshot"],
            "factor_source": _factor_source(f), "factor_status": f.get("status") if f else None,
            "factor_provenance": r["provenance_snapshot"]["factor"],
            "formula_description": r["formula_description"], "conversion_description": r["conversion_description"],
            "result": r["result_value"], "result_unit": r["result_unit"],
            "calculation_status": r["status"], "message": r["message"],
            "warnings": " | ".join(r["warnings"]),
            "calculation_snapshot_id": snapshot_id, "calculated_at": r["calculated_at"],
            "engine_version": r["engine_version"],
        })
    return pd.DataFrame(rows)


def summary_df(snap: dict) -> pd.DataFrame:
    s = snap["summary"]
    t = s["inventory"]["totals"]
    total = t["assessed_kg_co2e"]
    rows = [
        ("factory_name", s["factory"]["name"]),
        ("factory_location", s["factory"]["location"]),
        ("reporting_period_start", s["period"]["start_date"]),
        ("reporting_period_end", s["period"]["end_date"]),
        ("boundary_description", s["period"]["boundary_description"]),
        ("calculation_snapshot_id", snap["id"]),
        ("calculation_timestamp_utc", snap["created_at"]),
        ("calculation_engine_version", snap["engine_version"]),
        ("reporting_mode", snap["reporting_mode"]),
        ("inventory_completeness_status", snap["inventory_status"]),
        ("total_label", t["total_label"]),
        ("assessed_total_kgCO2e", total),
        ("assessed_total_tCO2e", calc.kg_to_tonnes(total) if total is not None else None),
        ("synthetic_demo_portion_kgCO2e", t["synthetic_demo_kg_co2e"]),
        ("records_calculated", t["n_calculated"]),
        ("records_needing_review", t["n_needs_review"]),
        ("records_not_calculated", t["n_not_calculated"]),
        ("unresolved_categories", ", ".join(t["unresolved_categories"]) or "none"),
        ("excluded_categories_user_declared", json.dumps(s["excluded_categories"]) if s["excluded_categories"] else "none"),
        ("synthetic_data_warning", s["synthetic_label"] if s["is_synthetic"] else "No synthetic records in this snapshot"),
        ("limitations", LIMITATIONS),
    ]
    for i in s["intensity"]:
        rows.append((f"intensity_{i['key']}", f"{i['value']:.6g} {i['unit']}" if i["value"] is not None
                     else f"not calculable: {i['reason']}"))
    return pd.DataFrame(rows, columns=["field", "value"])


def category_summary_df(snap: dict) -> pd.DataFrame:
    rows = []
    for c in snap["summary"]["inventory"]["categories"]:
        rows.append({
            "category": c["category"], "category_name": c["label"], "activity_records": c["n_records"],
            "calculated_records": c["n_calculated"], "unresolved_records": c["n_unresolved"],
            "assessed_emissions": c["assessed_kg_co2e"], "unit": c["unit"],
            "provenance": "; ".join(c["factor_provenance"]), "warnings": " | ".join(c["warnings"]),
            "completeness_status": c["completeness"], "note": c["note"],
            "calculation_snapshot_id": snap["id"],
        })
    return pd.DataFrame(rows)


def unresolved_df(conn, snap: dict) -> pd.DataFrame:
    """Data-quality export: unresolved records + unresolved categories."""
    rows = []
    for r in db.get_results(conn, snap["id"]):
        if r["status"] != calc.CALCULATED:
            a = r["activity_snapshot"]
            rows.append({"item_type": "record", "category": a["category"], "activity_record_id": r["activity_record_id"],
                         "name": a["activity_name"], "status": r["status"], "explanation": r["message"]})
    for c in snap["summary"]["inventory"]["categories"]:
        if c["completeness"] in ("not_assessed", "unresolved", "partial") and c["n_records"] == 0:
            rows.append({"item_type": "category", "category": c["category"], "activity_record_id": None,
                         "name": c["label"], "status": c["completeness"], "explanation": c["note"]})
    for a in snap["summary"]["anomalies"]:
        rows.append({"item_type": "flag", "category": None, "activity_record_id": a["activity_record_id"],
                     "name": a["code"], "status": a["severity"], "explanation": a["message"] + " Why: " + a["why_flagged"]})
    return pd.DataFrame(rows, columns=["item_type", "category", "activity_record_id", "name", "status", "explanation"])


def factor_references_df(conn, snapshot_id: int) -> pd.DataFrame:
    seen, rows = set(), []
    for r in db.get_results(conn, snapshot_id):
        f = r["factor_snapshot"]
        if f and f["id"] not in seen:
            seen.add(f["id"])
            rows.append({k: f.get(k) for k in ("id", "name", "category", "value", "numerator_unit",
                                               "denominator_unit", "gas_basis", "geography", "applicable_year",
                                               "source_organization", "source_document", "source_url",
                                               "source_reference", "publication_date", "status", "provenance",
                                               "notes")})
    return pd.DataFrame(rows)


def activity_data_df(conn, period_id: int) -> pd.DataFrame:
    """LIVE activity data (not snapshot) for the period."""
    return pd.DataFrame(db.list_activities(conn, period_id))


def anomalies_df(snap: dict) -> pd.DataFrame:
    return pd.DataFrame(snap["summary"]["anomalies"])


def df_to_csv(df: pd.DataFrame) -> str:
    return df.to_csv(index=False)


def _md_table(df: pd.DataFrame, cols: list[str]) -> str:
    if df.empty:
        return "_None._\n"
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df[cols].iterrows():
        out.append("| " + " | ".join("" if pd.isna(v) else str(v).replace("|", "/").replace("\n", " ") for v in r) + " |")
    return "\n".join(out) + "\n"


def markdown_report(conn, snapshot_id: int) -> str:
    snap = db.get_snapshot(conn, snapshot_id)
    s = snap["summary"]
    t = s["inventory"]["totals"]
    total = t["assessed_kg_co2e"]
    L = []
    L.append(f"# CarbonOS Sugar — Emissions Report (snapshot #{snapshot_id})\n")
    if s["is_synthetic"]:
        L.append(f"> **{s['synthetic_label']}**\n")
    L.append(f"- **Factory:** {s['factory']['name']} ({s['factory']['location'] or 'location not supplied'})")
    L.append(f"- **Reporting period:** {s['period']['start_date']} to {s['period']['end_date']}")
    L.append(f"- **Boundary (as entered):** {s['period']['boundary_description'] or 'not supplied'}")
    L.append(f"- **Calculated at (UTC):** {snap['created_at']}  |  **Engine version:** {snap['engine_version']}  |  **Mode:** {snap['reporting_mode']}")
    L.append("")
    L.append("## Inventory status\n")
    if snap["inventory_status"] == "incomplete":
        L.append("**INCOMPLETE INVENTORY.** The figure below is a *partial assessed total*, not the factory's total emissions.\n")
    else:
        L.append("All declared categories have calculated records. Coverage of the full period is not verified.\n")
    if total is not None:
        L.append(f"- **{t['total_label']}:** {total:,.3f} kgCO2e ({calc.kg_to_tonnes(total):,.5f} tCO2e)")
        L.append(f"- Of which based on synthetic/illustrative inputs: {t['synthetic_demo_kg_co2e']:,.3f} kgCO2e")
    else:
        L.append("- No emissions could be calculated.")
    L.append(f"- Records calculated: {t['n_calculated']}; needing review: {t['n_needs_review']}; not calculated: {t['n_not_calculated']}")
    L.append(f"- Unresolved categories: {', '.join(t['unresolved_categories']) or 'none'}")
    if s["excluded_categories"]:
        L.append("- Categories the user excluded from the boundary (not assessed): "
                 + "; ".join(f"{k} ({v})" for k, v in s["excluded_categories"].items()))
    L.append("\n## Category summary\n")
    L.append(_md_table(category_summary_df(snap), ["category_name", "activity_records", "calculated_records",
                                                    "unresolved_records", "assessed_emissions", "unit",
                                                    "completeness_status"]))
    L.append("## Energy indicators (factory-wide)\n")
    for i in s["intensity"]:
        L.append(f"- {i['label']}: " + (f"{i['value']:.4g} {i['unit']}" if i["value"] is not None
                                          else f"not calculable — {i['reason']}"))
    L.append("\n## Provenance summary\n")
    results = db.get_results(conn, snapshot_id)
    act_prov, fac_prov = {}, {}
    for r in results:
        act_prov[r["provenance_snapshot"]["activity"]] = act_prov.get(r["provenance_snapshot"]["activity"], 0) + 1
        if r["status"] == calc.CALCULATED:
            fp = r["provenance_snapshot"]["factor"]
            fac_prov[fp] = fac_prov.get(fp, 0) + 1
    L.append(f"- Activity records by provenance: {json.dumps(act_prov)}")
    L.append(f"- Calculated results by factor provenance: {json.dumps(fac_prov)}")
    L.append(f"- Derived results (calculated from stored values): {t['n_calculated']}")
    L.append(f"- Missing or unresolved: {t['n_not_calculated']} records, {len(t['unresolved_categories'])} categories")
    L.append("\n## Calculation details\n")
    L.append(_md_table(calculation_details_df(conn, snapshot_id),
                       ["activity_record_id", "activity_date", "category", "quantity", "input_unit", "factor_id",
                        "factor_value", "result", "result_unit", "calculation_status", "activity_provenance"]))
    L.append("## Factor references\n")
    L.append(_md_table(factor_references_df(conn, snapshot_id), ["id", "value", "numerator_unit", "denominator_unit",
                                                                 "status", "provenance", "source_organization"]))
    L.append("## Data-quality flags\n")
    for a in s["anomalies"]:
        L.append(f"- [{a['severity']}] **{a['code']}** — {a['message']} _Why flagged: {a['why_flagged']}_")
    L.append("\n## Recommendations\n")
    for rec in s["recommendations"]:
        L.append(f"### {rec['title']} ({rec['basis']})\n")
        for k in ("observation", "evidence", "why_it_matters", "suggested_action", "expected_benefit",
                  "confidence", "assumptions", "verification", "required_additional_data", "limitation"):
            L.append(f"- **{k.replace('_', ' ').capitalize()}:** {rec[k]}")
        L.append("")
    L.append("## Assumptions\n")
    L += [f"- {a}" for a in ASSUMPTIONS]
    L.append("\n## Limitations\n")
    L.append(LIMITATIONS + "\n")
    return "\n".join(L)


def export_bundle(conn, snapshot_id: int) -> bytes:
    """ZIP of every export for one snapshot."""
    snap = db.get_snapshot(conn, snapshot_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("factory_summary.csv", df_to_csv(summary_df(snap)))
        z.writestr("category_summary.csv", df_to_csv(category_summary_df(snap)))
        z.writestr("calculation_details.csv", df_to_csv(calculation_details_df(conn, snapshot_id)))
        z.writestr("data_quality_and_unresolved.csv", df_to_csv(unresolved_df(conn, snap)))
        z.writestr("factor_references.csv", df_to_csv(factor_references_df(conn, snapshot_id)))
        z.writestr("activity_data_live.csv", df_to_csv(activity_data_df(conn, snap["reporting_period_id"])))
        z.writestr("assumptions_and_limitations.txt",
                   "ASSUMPTIONS\n" + "\n".join(f"- {a}" for a in ASSUMPTIONS) + "\n\nLIMITATIONS\n" + LIMITATIONS + "\n")
        z.writestr("report.md", markdown_report(conn, snapshot_id))
    return buf.getvalue()

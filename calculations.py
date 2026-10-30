"""CarbonOS Sugar calculation engine.

Pure Python: no Streamlit, no database. Accepts plain dict records and returns
plain dict results so it can be tested alone and later wrapped by an API.

Accounting rules enforced here (see METHODOLOGY.md):
  * missing quantity / missing factor never becomes zero
  * incompatible units are rejected, never guessed
  * only explicitly defined conversions are applied, and they are recorded
  * illustrative / synthetic inputs are labelled and blocked in real-reporting mode
  * partial totals are labelled as partial
"""
from __future__ import annotations

import datetime as dt
import math
import re
import statistics
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

ENGINE_VERSION = "0.1.0"
RESULT_UNIT = "kgCO2e"

SYNTHETIC_LABEL = (
    "SYNTHETIC DEMONSTRATION — fictional activity data and illustrative factor. "
    "Not suitable for real factory reporting."
)

# --------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------
PROVENANCE_VALUES = (
    "user_provided", "published_factor", "published_benchmark",
    "synthetic_demo", "derived", "unknown",
)
# Provenance values that make sense for a raw activity record.
ACTIVITY_PROVENANCE = ("user_provided", "synthetic_demo", "unknown")
FACTOR_STATUSES = ("verified_for_use", "needs_review", "illustrative", "deprecated")
RECORD_STATUSES = ("valid", "missing_activity_data")

# Result / data-quality statuses (documented in METHODOLOGY.md)
CALCULATED = "calculated"
MISSING_ACTIVITY = "missing_activity_data"
MISSING_FACTOR = "missing_factor"
UNIT_MISMATCH = "unit_mismatch"
ILLUSTRATIVE_FACTOR = "illustrative_factor"
NEEDS_REVIEW = "needs_review"
NOT_ASSESSED = "not_assessed"
STALE = "stale"          # applied to a snapshot, not to a single result
VALID = "valid"

# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------
_ALL_UNITS = ("kWh", "MWh", "GJ", "L", "kL", "m3", "kg", "t", "tkm", "kg_COD")

CATEGORIES: dict[str, dict[str, Any]] = {
    "purchased_electricity": {
        "label": "Purchased electricity", "units": ("kWh", "MWh"), "method": True,
        "note": "Factory-level grid electricity. Not allocated to process stages.",
    },
    "diesel": {
        "label": "Diesel combustion", "units": ("L", "kL"), "method": True,
        "note": "Calculates only if a diesel factor has been entered in the factor library.",
    },
    "other_fossil_fuels": {
        "label": "Other fossil fuels", "units": ("L", "kL", "kg", "t", "m3"), "method": True,
        "note": "Calculates only where a factor with a compatible unit is documented.",
    },
    "bagasse_combustion": {
        "label": "Bagasse combustion", "units": ("kg", "t"), "method": False,
        "note": ("Not assessed in the MVP: biogenic CO2 and non-CO2 (CH4/N2O) treatment "
                 "is not implemented. Bagasse is never added to the fossil total."),
    },
    "purchased_steam_energy": {
        "label": "Purchased steam or other energy", "units": ("t", "kg", "GJ", "MWh", "kWh"),
        "method": True, "note": "Calculates only with an appropriate documented factor.",
    },
    "cane_transport": {
        "label": "Cane transport", "units": ("tkm",), "method": True,
        "note": "Tonne-km records; calculates only if the boundary includes it and a factor exists.",
    },
    "wastewater_effluent": {
        "label": "Wastewater and effluent", "units": ("m3", "kg_COD"), "method": False,
        "note": "Not assessed in the MVP: no treatment-emissions method implemented.",
    },
    "refrigerants": {
        "label": "Refrigerants", "units": ("kg",), "method": True,
        "note": "Calculates only with a documented factor (e.g. GWP-based kgCO2e/kg).",
    },
    "other_sources": {
        "label": "Other sources", "units": _ALL_UNITS, "method": False,
        "note": "Recorded as unresolved until a method is supported.",
    },
}

FUEL_CATEGORIES = ("diesel", "other_fossil_fuels")

# --------------------------------------------------------------------------
# Units and conversions (only these are ever applied)
# --------------------------------------------------------------------------
UNIT_SYNONYMS = {
    "kwh": "kWh", "mwh": "MWh", "gj": "GJ",
    "l": "L", "litre": "L", "litres": "L", "liter": "L", "liters": "L",
    "kl": "kL", "m3": "m3", "m³": "m3",
    "kg": "kg", "t": "t", "tonne": "t", "tonnes": "t",
    "tkm": "tkm", "t-km": "tkm", "kg_cod": "kg_COD",
}

# (from_unit, to_unit) -> multiplier. Note: no volume<->mass conversions
# (that would need a documented density) and no energy<->fuel conversions.
CONVERSIONS: dict[tuple[str, str], Decimal] = {
    ("MWh", "kWh"): Decimal("1000"), ("kWh", "MWh"): Decimal("0.001"),
    ("kL", "L"): Decimal("1000"), ("L", "kL"): Decimal("0.001"),
    ("t", "kg"): Decimal("1000"), ("kg", "t"): Decimal("0.001"),
}

# Factor numerator units the engine can express as kgCO2e.
NUMERATOR_TO_KG: dict[str, Decimal] = {"kgCO2e": Decimal("1"), "tCO2e": Decimal("1000")}


def normalize_unit(unit: Any) -> Optional[str]:
    """Return the canonical unit string, or None if missing/unrecognised."""
    if unit is None:
        return None
    s = str(unit).strip()
    if not s:
        return None
    return UNIT_SYNONYMS.get(s.lower())


def normalize_numerator(unit: Any) -> Optional[str]:
    """Canonicalise an emissions unit like 'kg CO2e'. Returns None if unsupported."""
    if unit is None:
        return None
    s = str(unit).strip().replace("₂", "2").replace(" ", "").lower()
    return {"kgco2e": "kgCO2e", "tco2e": "tCO2e"}.get(s)


class UnitMismatch(Exception):
    pass


def _dec(x: Any) -> Decimal:
    return Decimal(str(x))


def _fmt(d: Decimal) -> str:
    s = format(d.normalize(), "f")
    return s


def _compute(quantity: Any, input_unit: str, factor_value: Any,
             numerator_unit: str, denominator_unit: str) -> tuple[Decimal, str, str]:
    """Core arithmetic shared by calculation and snapshot re-computation.

    Returns (result_kg_co2e, conversion_description, formula_description).
    Raises UnitMismatch for anything not explicitly convertible.
    """
    in_u = normalize_unit(input_unit)
    den_u = normalize_unit(denominator_unit)
    num_u = normalize_numerator(numerator_unit)
    if in_u is None:
        raise UnitMismatch(f"Activity unit '{input_unit}' is missing or not recognised.")
    if den_u is None:
        raise UnitMismatch(f"Factor denominator unit '{denominator_unit}' is missing or not recognised.")
    if num_u is None:
        raise UnitMismatch(
            f"Factor numerator unit '{numerator_unit}' is not supported (expected kgCO2e or tCO2e)."
        )
    conv_notes: list[str] = []
    if in_u == den_u:
        act_mult = Decimal("1")
    elif (in_u, den_u) in CONVERSIONS:
        act_mult = CONVERSIONS[(in_u, den_u)]
        conv_notes.append(f"Activity quantity converted {in_u} → {den_u} (× {_fmt(act_mult)}).")
    else:
        raise UnitMismatch(
            f"The selected factor is not compatible with this unit: activity is in {in_u}, "
            f"factor is per {den_u}, and no documented conversion exists."
        )
    num_mult = NUMERATOR_TO_KG[num_u]
    if num_u != "kgCO2e":
        conv_notes.append(f"Factor numerator converted {num_u} → kgCO2e (× {_fmt(num_mult)}).")

    q, f = _dec(quantity), _dec(factor_value)
    result = q * act_mult * f * num_mult
    conversion = " ".join(conv_notes) if conv_notes else "None"
    formula = (
        f"Emissions (kgCO2e) = quantity ({_fmt(q)} {in_u})"
        + (f" × {_fmt(act_mult)} [{in_u}→{den_u}]" if act_mult != 1 else "")
        + f" × factor ({_fmt(f)} {num_u}/{den_u})"
        + (f" × {_fmt(num_mult)} [{num_u}→kgCO2e]" if num_mult != 1 else "")
        + f" = {_fmt(result)} kgCO2e"
    )
    return result, conversion, formula


def kg_to_tonnes(kg: float) -> float:
    """Display/export conversion only. Calculations stay in kgCO2e."""
    return float(Decimal(str(kg)) / Decimal("1000"))


def recompute_from_snapshot(result_row: dict) -> Optional[float]:
    """Re-derive a stored result from ONLY its snapshot fields (no live data)."""
    if result_row.get("status") != CALCULATED:
        return None
    value, _, _ = _compute(
        result_row["input_quantity_snapshot"], result_row["input_unit_snapshot"],
        result_row["factor_value_snapshot"], result_row["factor_numerator_unit_snapshot"],
        result_row["factor_denominator_unit_snapshot"],
    )
    return float(value)


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(value: Any) -> Optional[dt.date]:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    s = str(value or "").strip()
    if not _DATE_RE.match(s):
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def parse_quantity(value: Any) -> tuple[Optional[float], Optional[str]]:
    """Return (quantity, error). Empty -> (None, None). Never guesses formats."""
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, "Quantity must be a number."
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None, "Quantity must be a finite number."
        d = _dec(value)
    else:
        s = str(value).strip()
        if s == "":
            return None, None
        if "," in s:
            return None, ("Quantity contains a comma. Use a plain number without thousands "
                          "separators (e.g. 12500 or 12500.5).")
        try:
            d = Decimal(s)
        except InvalidOperation:
            return None, f"Quantity '{s}' is not a number."
        if not d.is_finite():
            return None, "Quantity must be a finite number."
    if d < 0:
        return None, "Negative quantities are rejected for all supported categories."
    return float(d), None


def validate_activity_input(rec: dict, period: Optional[dict] = None,
                            allow_missing_quantity: bool = False) -> tuple[dict, list[str]]:
    """Validate and clean one activity record. Returns (clean, errors)."""
    errors: list[str] = []
    clean: dict[str, Any] = {}

    d = parse_date(rec.get("activity_date"))
    if rec.get("activity_date") in (None, ""):
        errors.append("Activity date is required (format YYYY-MM-DD).")
    elif d is None:
        errors.append(f"Activity date '{rec.get('activity_date')}' is not a valid YYYY-MM-DD date.")
    else:
        clean["activity_date"] = d.isoformat()
        if period:
            start, end = parse_date(period["start_date"]), parse_date(period["end_date"])
            if start and end and not (start <= d <= end):
                errors.append(
                    f"Activity date {d.isoformat()} is outside the reporting period "
                    f"{start.isoformat()} to {end.isoformat()}."
                )

    cat = str(rec.get("category") or "").strip()
    if not cat:
        errors.append("Category is required.")
    elif cat not in CATEGORIES:
        errors.append(f"Unknown category '{cat}'. Valid: {', '.join(CATEGORIES)}.")
    else:
        clean["category"] = cat

    name = str(rec.get("activity_name") or "").strip()
    if not name:
        errors.append("Activity name is required.")
    clean["activity_name"] = name

    qty, qerr = parse_quantity(rec.get("quantity"))
    if qerr:
        errors.append(qerr)
    elif qty is None and not allow_missing_quantity:
        errors.append("Quantity is required before this activity can be calculated.")
    clean["quantity"] = qty

    raw_unit = rec.get("unit")
    unit = normalize_unit(raw_unit)
    if raw_unit in (None, "") or not str(raw_unit).strip():
        errors.append("Unit is required.")
    elif unit is None:
        errors.append(f"Unit '{raw_unit}' is not recognised. Valid: {', '.join(_ALL_UNITS)}.")
    else:
        if cat in CATEGORIES and unit not in CATEGORIES[cat]["units"]:
            errors.append(
                f"Unit '{unit}' is not valid for {CATEGORIES[cat]['label']}. "
                f"Valid: {', '.join(CATEGORIES[cat]['units'])}."
            )
        clean["unit"] = unit

    prov = str(rec.get("provenance") or "").strip()
    if not prov:
        errors.append("Provenance is required.")
    elif prov not in ACTIVITY_PROVENANCE:
        errors.append(f"Provenance '{prov}' is not valid for activity data. Valid: {', '.join(ACTIVITY_PROVENANCE)}.")
    clean["provenance"] = prov

    clean["source_reference"] = (str(rec.get("source_reference")).strip() or None) if rec.get("source_reference") is not None else None
    clean["source_row_reference"] = rec.get("source_row_reference")
    clean["notes"] = (str(rec.get("notes")).strip() or None) if rec.get("notes") is not None else None
    clean["status"] = "valid" if clean.get("quantity") is not None else "missing_activity_data"
    return clean, errors


def validate_factor_record(f: dict) -> list[str]:
    """Hard validation for a factor record. Returns a list of error strings."""
    errors: list[str] = []
    if not str(f.get("name") or "").strip():
        errors.append("Factor name is required.")
    if f.get("category") not in CATEGORIES:
        errors.append("A valid category is required.")
    try:
        v = Decimal(str(f.get("value")))
        if not v.is_finite() or v < 0:
            errors.append("Factor value must be a finite number ≥ 0.")
    except (InvalidOperation, TypeError):
        errors.append("Factor value must be numeric.")
    if not str(f.get("numerator_unit") or "").strip():
        errors.append("Numerator unit is required (e.g. kgCO2e).")
    if normalize_unit(f.get("denominator_unit")) is None:
        errors.append(f"Denominator unit '{f.get('denominator_unit')}' is missing or not recognised.")
    if f.get("status") not in FACTOR_STATUSES:
        errors.append(f"Status must be one of {', '.join(FACTOR_STATUSES)}.")
    if f.get("provenance") not in PROVENANCE_VALUES:
        errors.append(f"Provenance must be one of {', '.join(PROVENANCE_VALUES)}.")
    if f.get("provenance") == "synthetic_demo" and f.get("status") not in ("illustrative", "deprecated"):
        errors.append("A synthetic_demo factor must stay 'illustrative' (or 'deprecated').")
    if f.get("status") == "verified_for_use":
        missing = [k for k in ("source_organization", "source_document", "geography")
                   if not str(f.get(k) or "").strip()]
        if not f.get("applicable_year"):
            missing.append("applicable_year")
        if not (str(f.get("source_url") or "").strip() or str(f.get("source_reference") or "").strip()):
            missing.append("source_url or source_reference")
        if missing:
            errors.append("Cannot mark 'verified_for_use' without: " + ", ".join(missing) + ".")
        if f.get("provenance") in ("synthetic_demo", "unknown"):
            errors.append("A 'verified_for_use' factor cannot have synthetic_demo or unknown provenance.")
    return errors


# --------------------------------------------------------------------------
# Factor selection and single-record calculation
# --------------------------------------------------------------------------
def select_factor(category: str, factors: list[dict]) -> tuple[Optional[dict], list[str]]:
    """Pick the active, non-deprecated factor for a category (or None)."""
    cands = [f for f in factors
             if f.get("category") == category and f.get("is_active", 1)
             and f.get("status") != "deprecated"]
    if not cands:
        return None, []
    cands.sort(key=lambda f: (str(f.get("updated_at") or ""), str(f.get("id"))))
    chosen = cands[-1]
    warns = []
    if len(cands) > 1:
        warns.append(f"{len(cands)} active factors exist for this category; used {chosen['id']} (most recently updated).")
    return chosen, warns


def is_synthetic(activity: dict, factor: Optional[dict]) -> bool:
    return (activity.get("provenance") == "synthetic_demo"
            or (factor is not None and (factor.get("provenance") == "synthetic_demo"
                                        or factor.get("status") == "illustrative")))


def _result_shell(activity: dict, factor: Optional[dict], status: str, message: str,
                  calculated_at: str, warnings: Optional[list[str]] = None) -> dict:
    return {
        "activity_record_id": activity.get("id"),
        "factor_id": factor.get("id") if factor else None,
        "input_quantity_snapshot": activity.get("quantity"),
        "input_unit_snapshot": activity.get("unit"),
        "factor_value_snapshot": factor.get("value") if factor else None,
        "factor_numerator_unit_snapshot": factor.get("numerator_unit") if factor else None,
        "factor_denominator_unit_snapshot": factor.get("denominator_unit") if factor else None,
        "conversion_description": None,
        "formula_description": None,
        "result_value": None,
        "result_unit": None,
        "status": status,
        "message": message,
        "factor_status_snapshot": factor.get("status") if factor else None,
        "synthetic": is_synthetic(activity, factor),
        "provenance_snapshot": {
            "activity": activity.get("provenance"),
            "factor": factor.get("provenance") if factor else None,
            "result": "derived",
        },
        "warnings": list(warnings or []),
        "engine_version": ENGINE_VERSION,
        "calculated_at": calculated_at,
    }


def calculate_record(activity: dict, factor: Optional[dict], *,
                     reporting_mode: str = "demo", calculated_at: Optional[str] = None) -> dict:
    """Calculate emissions for one activity record. Never raises for bad data;
    returns a result dict whose status explains what happened."""
    ts = calculated_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
    shell = lambda status, msg, warns=None: _result_shell(activity, factor, status, msg, ts, warns)  # noqa: E731
    cat = activity.get("category")

    if cat not in CATEGORIES:
        return shell(NEEDS_REVIEW, f"Unknown category '{cat}'.")
    if not CATEGORIES[cat]["method"]:
        return shell(NOT_ASSESSED, "Not assessed — emission factor or required activity data unavailable. "
                                   + CATEGORIES[cat]["note"])

    qty = activity.get("quantity")
    if qty is None:
        return shell(MISSING_ACTIVITY, "Quantity is required before this activity can be calculated.")
    q, qerr = parse_quantity(qty)
    if qerr or q is None:
        return shell(NEEDS_REVIEW, qerr or "Quantity is not usable.")
    if normalize_unit(activity.get("unit")) is None:
        return shell(NEEDS_REVIEW, "Activity unit is missing or not recognised; no unit is assumed.")

    if reporting_mode == "real":
        if activity.get("provenance") == "synthetic_demo":
            return shell(NEEDS_REVIEW, "Synthetic demonstration records cannot be used in real-reporting mode.")
        if activity.get("provenance") in (None, "", "unknown"):
            return shell(NEEDS_REVIEW, "Activity provenance has not been established; review before real reporting.")

    if factor is None:
        return shell(MISSING_FACTOR, "No suitable emission factor is available for this category.")
    try:
        fv = Decimal(str(factor.get("value")))
        if not fv.is_finite() or fv < 0:
            raise InvalidOperation
    except (InvalidOperation, TypeError):
        return shell(MISSING_FACTOR, "The factor has no usable numeric value.")
    if factor.get("status") == "deprecated":
        return shell(MISSING_FACTOR, "The only available factor is deprecated.")

    warnings: list[str] = []
    fstatus = factor.get("status")
    if reporting_mode == "real":
        if fstatus == "illustrative" or factor.get("provenance") == "synthetic_demo":
            return shell(ILLUSTRATIVE_FACTOR,
                         "This factor is illustrative and must not be used for real reporting.")
        if fstatus != "verified_for_use":
            return shell(NEEDS_REVIEW, "The factor is marked 'needs_review'; real-reporting mode "
                                       "requires 'verified_for_use'.")
    else:
        if fstatus == "illustrative":
            warnings.append("Factor is illustrative — not for real reporting.")
        elif fstatus == "needs_review":
            warnings.append("Factor is marked needs_review.")
    if activity.get("provenance") == "synthetic_demo":
        warnings.append("The result shown is based on synthetic demonstration data.")
    if q == 0:
        warnings.append("Quantity is zero — confirm that zero was actually recorded, not a missing value.")

    try:
        value, conversion, formula = _compute(
            q, activity["unit"], factor["value"],
            factor.get("numerator_unit"), factor.get("denominator_unit"))
    except UnitMismatch as e:
        return shell(UNIT_MISMATCH, str(e), warnings)

    res = shell(CALCULATED, "Calculated.", warnings)
    res.update(result_value=float(value), result_unit=RESULT_UNIT,
               conversion_description=conversion, formula_description=formula)
    return res


# --------------------------------------------------------------------------
# Inventory completeness and totals
# --------------------------------------------------------------------------
def summarize_inventory(activities: list[dict], results: list[dict],
                        excluded: Optional[dict] = None) -> dict:
    """Category summaries, totals and completeness status.

    A category is only 'all_records_calculated' when every recorded activity in
    it calculated. This says nothing about whether the records cover the whole
    period; coverage is not verified by the prototype.
    """
    excluded = excluded or {}
    res_by_act = {r["activity_record_id"]: r for r in results}
    cats = []
    unresolved_categories: list[str] = []
    for key, meta in CATEGORIES.items():
        recs = [a for a in activities if a["category"] == key]
        rs = [res_by_act[a["id"]] for a in recs if a["id"] in res_by_act]
        calc = [r for r in rs if r["status"] == CALCULATED]
        unresolved = [r for r in rs if r["status"] != CALCULATED]
        warns = sorted({w for r in rs for w in r["warnings"]})
        provs = sorted({f"activity:{r['provenance_snapshot']['activity']}" for r in rs}
                       | {f"factor:{r['provenance_snapshot']['factor']}" for r in calc})
        if key in excluded and not recs:
            comp, note = "excluded", f"Excluded from declared boundary: {excluded[key]}"
        elif not recs:
            comp = "not_assessed"
            note = ("No activity data recorded." if meta["method"]
                    else "No method implemented in the MVP; no activity data recorded.")
        elif not meta["method"]:
            comp, note = "not_assessed", meta["note"]
        elif len(calc) == len(rs):
            comp, note = "all_records_calculated", "All recorded activity records calculated; period coverage not verified."
        elif calc:
            comp, note = "partial", f"{len(unresolved)} of {len(rs)} records not calculated."
        else:
            comp, note = "unresolved", f"None of {len(rs)} records could be calculated."
        if comp not in ("all_records_calculated", "excluded"):
            unresolved_categories.append(key)
        cats.append({
            "category": key, "label": meta["label"], "n_records": len(recs),
            "n_calculated": len(calc), "n_unresolved": len(unresolved),
            "assessed_kg_co2e": sum(r["result_value"] for r in calc) if calc else None,
            "unit": RESULT_UNIT, "factor_provenance": provs, "warnings": warns,
            "completeness": comp, "note": note,
        })

    calc_all = [r for r in results if r["status"] == CALCULATED]
    synth = sum(r["result_value"] for r in calc_all if r["synthetic"])
    total = sum(r["result_value"] for r in calc_all)
    status_counts: dict[str, int] = {}
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    unresolved_records = len(results) - len(calc_all)
    incomplete = bool(unresolved_categories)
    return {
        "categories": cats,
        "totals": {
            "assessed_kg_co2e": total if calc_all else None,
            "synthetic_demo_kg_co2e": synth if calc_all else None,
            "non_synthetic_kg_co2e": total - synth if calc_all else None,
            "n_calculated": len(calc_all),
            "n_needs_review": status_counts.get(NEEDS_REVIEW, 0) + status_counts.get(UNIT_MISMATCH, 0)
                              + status_counts.get(ILLUSTRATIVE_FACTOR, 0),
            "n_not_calculated": unresolved_records,
            "status_counts": status_counts,
            "unresolved_categories": unresolved_categories,
            "total_label": "Partial assessed total" if incomplete else "Assessed total (declared boundary)",
        },
        "inventory_status": "incomplete" if incomplete else "all_declared_categories_calculated",
        "unresolved_records": unresolved_records,
        "unresolved_count": unresolved_records + len(unresolved_categories),
        "is_synthetic": any(r["synthetic"] for r in results) if results else False,
    }


# --------------------------------------------------------------------------
# Energy intensity
# --------------------------------------------------------------------------
def _sum_in_unit(records: list[dict], target_unit: str) -> tuple[Optional[Decimal], Optional[str]]:
    total = Decimal("0")
    for a in records:
        if a.get("quantity") is None:
            return None, "at least one record has no quantity recorded"
        u = normalize_unit(a.get("unit"))
        if u == target_unit:
            total += _dec(a["quantity"])
        elif (u, target_unit) in CONVERSIONS:
            total += _dec(a["quantity"]) * CONVERSIONS[(u, target_unit)]
        else:
            return None, f"record unit {a.get('unit')} cannot be converted to {target_unit}"
    return total, None


def energy_intensity(activities: list[dict], period: dict) -> list[dict]:
    """Factory-wide intensity indicators. Each carries a value or a reason."""
    out = []
    specs = [
        ("electricity_per_cane", "Electricity per tonne of cane crushed", "purchased_electricity", "kWh",
         "cane_crushed_t", "t cane crushed"),
        ("electricity_per_sugar", "Electricity per tonne of sugar produced", "purchased_electricity", "kWh",
         "sugar_produced_t", "t sugar produced"),
        ("diesel_per_cane", "Diesel per tonne of cane crushed", "diesel", "L",
         "cane_crushed_t", "t cane crushed"),
    ]
    for key, label, cat, num_unit, den_field, den_label in specs:
        recs = [a for a in activities if a["category"] == cat]
        denom = period.get(den_field)
        ind = {"key": key, "label": label, "value": None, "unit": f"{num_unit}/{den_label}",
               "numerator": None, "numerator_unit": num_unit, "denominator": denom,
               "denominator_label": den_label, "reason": None, "provenance": "derived",
               "scope": "Factory-wide; not allocated to process stages",
               "synthetic": any(a["provenance"] == "synthetic_demo" for a in recs)}
        if not recs:
            ind["reason"] = f"No {CATEGORIES[cat]['label'].lower()} records, so this cannot be calculated."
        elif denom is None:
            ind["reason"] = "The production denominator is missing, so energy intensity cannot be calculated."
        elif denom <= 0:
            ind["reason"] = "The production denominator is zero or negative, so intensity cannot be calculated."
        else:
            total, why = _sum_in_unit(recs, num_unit)
            if total is None:
                ind["reason"] = f"Numerator incomplete: {why}."
            else:
                ind["numerator"] = float(total)
                ind["value"] = float(total / _dec(denom))
        out.append(ind)
    return out


# --------------------------------------------------------------------------
# Transparent anomaly checks (no ML)
# --------------------------------------------------------------------------
def find_anomalies(activities: list[dict], results: list[dict], period: dict,
                   intensity: list[dict], previous: Optional[dict] = None,
                   record_threshold: float = 0.5, intensity_threshold: float = 0.2) -> list[dict]:
    flags: list[dict] = []
    res_by_act = {r["activity_record_id"]: r for r in results}

    def add(code, severity, record_id, message, why, **extra):
        flags.append({"code": code, "severity": severity, "activity_record_id": record_id,
                      "message": message, "why_flagged": why, **extra})

    unapproved: dict[tuple, list] = {}
    for a in activities:
        r = res_by_act.get(a["id"])
        if a.get("quantity") is None:
            add("MISSING_QUANTITY", "high", a["id"],
                f"Record #{a['id']} ({a['activity_name']}) has no quantity.",
                "Missing activity data is not treated as zero; the record cannot be calculated.")
        if not a.get("source_reference"):
            add("NO_SOURCE_REFERENCE", "low", a["id"],
                f"Record #{a['id']} has no source reference.",
                "Traceability to a bill, log or document is weaker without a source reference.")
        if r and r["status"] == MISSING_FACTOR and a["category"] in FUEL_CATEGORIES:
            add("FUEL_NO_FACTOR", "high", a["id"],
                f"Fuel record #{a['id']} ({a['activity_name']}) has no usable emission factor.",
                "Fuel use is recorded but no factor is available, so it contributes no calculated emissions.")
        if r and r["status"] == CALCULATED and r["factor_status_snapshot"] in ("illustrative", "needs_review"):
            unapproved.setdefault((r["factor_id"], r["factor_status_snapshot"]), []).append(a["id"])

    for (fid, fstat), ids in unapproved.items():
        add("FACTOR_NOT_APPROVED", "medium", None,
            f"Factor {fid} is marked '{fstat}' and was used by {len(ids)} record(s): "
            + ", ".join(f"#{i}" for i in ids) + ".",
            "Factors that are illustrative or need review are not approved for real reporting.")

    # Duplicate-looking records
    seen: dict[tuple, int] = {}
    for a in activities:
        key = (a["activity_date"], a["category"], a.get("quantity"), a["unit"])
        if a.get("quantity") is not None and key in seen:
            add("DUPLICATE_LOOKING", "medium", a["id"],
                f"Record #{a['id']} looks like a duplicate of #{seen[key]} (same date, category, quantity, unit).",
                "Identical date, category, quantity and unit on two records can indicate double entry.")
        else:
            seen.setdefault(key, a["id"])

    # Outliers against the median of the same category in this period
    for cat in CATEGORIES:
        meta = CATEGORIES[cat]
        base = meta["units"][0]
        vals = []
        for a in activities:
            if a["category"] != cat or a.get("quantity") is None:
                continue
            u = normalize_unit(a.get("unit"))
            if u == base:
                vals.append((a, _dec(a["quantity"])))
            elif (u, base) in CONVERSIONS:
                vals.append((a, _dec(a["quantity"]) * CONVERSIONS[(u, base)]))
        if len(vals) >= 3:
            med = statistics.median([v for _, v in vals])
            if med > 0:
                for a, v in vals:
                    dev = float((v - med) / med)
                    if abs(dev) > record_threshold:
                        direction = "above" if dev > 0 else "below"
                        add("OUTLIER_VS_MEDIAN", "medium", a["id"],
                            f"Record #{a['id']} ({a['activity_name']}, {a['activity_date']}) is "
                            f"{abs(dev):.0%} {direction} the median of this period's {meta['label'].lower()} records.",
                            f"Compared with the median ({float(med):g} {base}) of {len(vals)} records; "
                            f"threshold ±{record_threshold:.0%}. This does not establish a fault.")

    # Zero production with positive energy
    for fld, lbl in (("cane_crushed_t", "cane crushed"), ("sugar_produced_t", "sugar produced")):
        if period.get(fld) == 0:
            if any(a.get("quantity") and a["category"] in ("purchased_electricity", "diesel") for a in activities):
                add("ZERO_PRODUCTION_WITH_ENERGY", "high", None,
                    f"Production ({lbl}) is recorded as zero while energy use is positive.",
                    "Energy consumption without production is unusual and may reflect a data-entry or period problem.")

    # Trend versus previous period
    cur = {i["key"]: i for i in intensity}
    if previous and previous.get("intensity"):
        compared = False
        for key, pi in previous["intensity"].items():
            ci = cur.get(key)
            if ci and ci["value"] is not None and pi["value"] is not None and pi["value"] > 0:
                compared = True
                change = (ci["value"] - pi["value"]) / pi["value"]
                if abs(change) > intensity_threshold:
                    add("INTENSITY_CHANGE", "medium", None,
                        f"{ci['label']} changed by {change:+.0%} versus {previous['label']} "
                        f"({pi['value']:.4g} → {ci['value']:.4g} {ci['unit']}).",
                        f"Threshold ±{intensity_threshold:.0%}. Boundaries and production units are "
                        f"user-entered; confirm they are comparable before drawing conclusions.",
                        change=change)
        if not compared:
            add("TREND_UNAVAILABLE", "info", None,
                "Trend comparison unavailable: no comparable intensity in the previous period.",
                "Both periods need the same numerator and production denominator.")
    else:
        add("TREND_UNAVAILABLE", "info", None,
            "Trend comparison unavailable: no previous reporting period with data exists.",
            "A historical baseline is required to compare energy intensity over time.")
    return flags


# --------------------------------------------------------------------------
# Recommendations (observation-based or labelled generic)
# --------------------------------------------------------------------------
def build_recommendations(anomalies: list[dict], intensity: list[dict], inventory: dict) -> list[dict]:
    recs: list[dict] = []

    for a in anomalies:
        if a["code"] == "INTENSITY_CHANGE":
            increased = a.get("change", 0) > 0
            recs.append({
                "title": "Investigate a change in energy intensity" if not increased
                         else "Investigate an increase in energy intensity",
                "basis": "observation",
                "observation": a["message"],
                "evidence": "Recorded energy and production values for both periods (see Calculations).",
                "why_it_matters": "A change in energy per unit of production can indicate operating, metering or data differences.",
                "suggested_action": "Review operating schedules, equipment loading, maintenance and metering for both periods.",
                "expected_benefit": "Not quantified — no supportable estimate from the available data.",
                "confidence": "Preliminary",
                "assumptions": "Both periods use comparable boundaries and production definitions.",
                "verification": "Compare validated meter readings and production records over a consistent operating period.",
                "required_additional_data": "Validated meter data; production data on a consistent basis.",
                "limitation": "This observation does not establish the cause of the change.",
            })
        elif a["code"] == "OUTLIER_VS_MEDIAN":
            recs.append({
                "title": f"Check record #{a['activity_record_id']} against its source document",
                "basis": "observation",
                "observation": a["message"],
                "evidence": a["why_flagged"],
                "why_it_matters": "An unusual value may be a genuine operating event or a data-entry or billing issue.",
                "suggested_action": "Compare the record with the original bill or log and with operating events in that month.",
                "expected_benefit": "Not quantified.",
                "confidence": "Preliminary",
                "assumptions": "Other records in the period are representative.",
                "verification": "Confirm against the source document and meter readings.",
                "required_additional_data": "Original bill/log; operating log for the period.",
                "limitation": "A deviation from the median is not proof of a fault.",
            })
        elif a["code"] == "MISSING_QUANTITY":
            recs.append({
                "title": f"Obtain the missing quantity for record #{a['activity_record_id']}",
                "basis": "observation",
                "observation": a["message"],
                "evidence": "Record exists without a quantity.",
                "why_it_matters": "Missing data is not zero; the inventory stays incomplete until it is supplied.",
                "suggested_action": "Locate the source record (log, invoice, maintenance entry) and enter the quantity.",
                "expected_benefit": "Not applicable (data completeness).",
                "confidence": "High that data is missing",
                "assumptions": "The activity actually occurred in this period.",
                "verification": "Check the entered value against the source document.",
                "required_additional_data": "The missing quantity and its source.",
                "limitation": "None.",
            })

    if inventory["totals"]["unresolved_categories"]:
        names = ", ".join(CATEGORIES[c]["label"] for c in inventory["totals"]["unresolved_categories"])
        recs.append({
            "title": "Close inventory gaps (generic suggestion)",
            "basis": "generic",
            "observation": f"These categories are not fully assessed: {names}.",
            "evidence": "Category summary in the snapshot.",
            "why_it_matters": "The assessed total is partial and cannot be read as the factory's complete emissions.",
            "suggested_action": "For each category, collect activity data and source a documented, verified factor, "
                                "or declare it outside the boundary with a reason.",
            "expected_benefit": "Not quantified.",
            "confidence": "N/A (generic)",
            "assumptions": "Each listed category is relevant to the mill's boundary.",
            "verification": "Reviewer reproduces each category from source records and factors.",
            "required_additional_data": "Activity records and verified factors per category.",
            "limitation": "Generic suggestion, not derived from a specific observation.",
        })
    if any(c["category"] == "purchased_electricity" and c["n_calculated"] for c in inventory["categories"]):
        recs.append({
            "title": "Add sub-metering to enable process-stage analysis (generic suggestion)",
            "basis": "generic",
            "observation": "Electricity is recorded at factory level only.",
            "evidence": "Activity records cover whole-factory bills.",
            "why_it_matters": "Process-stage allocation requires stage-level measurements; none are assumed here.",
            "suggested_action": "Identify whether existing sub-meters (e.g. cane preparation, mills, evaporation) can be logged.",
            "expected_benefit": "Not quantified.",
            "confidence": "N/A (generic)",
            "assumptions": "Sub-meters exist or can be installed.",
            "verification": "Sum of sub-meters reconciles with the main meter.",
            "required_additional_data": "Stage-level meter readings.",
            "limitation": "Generic suggestion, not derived from the recorded data.",
        })
    return recs

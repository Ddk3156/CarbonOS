"""Synthetic demonstration dataset for CarbonOS Sugar.

EVERYTHING in this file is FICTIONAL. The factory does not exist, the
quantities are invented, and the two emission factors are round illustrative
numbers, NOT published factors. Do not use any of it for real reporting.

Run `python seed_data.py` to create a demo database (default: carbonos.db).
"""
from __future__ import annotations

import argparse
import csv
import os

import calculations as calc
import database as db

DEMO_FACTORY_NAME = "DEMO Sugar Mill (FICTIONAL)"
DEMO_LOCATION = "Fictional location — not a real facility"
DEMO_BOUNDARY = ("FICTIONAL demo boundary: factory-gate purchased electricity and diesel records only. "
                 "Other categories are shown as not assessed.")

CSV_COLUMNS = ["activity_date", "category", "activity_name", "quantity", "unit",
               "source_reference", "provenance", "notes"]
_NOTE = "Fictional demonstration record"

# Current period (2026-01-01 .. 2026-03-31)
DEMO_ACTIVITIES = [
    ("2026-01-01", "purchased_electricity", "Grid electricity", "12500", "kWh", "DEMO-BILL-001", _NOTE),
    ("2026-02-01", "purchased_electricity", "Grid electricity", "13100", "kWh", "DEMO-BILL-002", _NOTE),
    ("2026-03-01", "purchased_electricity", "Grid electricity", "20400", "kWh", "DEMO-BILL-003",
     _NOTE + " (deliberately high month to demonstrate an outlier flag)"),
    ("2026-01-15", "diesel", "Generator diesel", "800", "L", "DEMO-DSL-001", _NOTE),
    ("2026-02-12", "diesel", "Generator diesel", "750", "L", "DEMO-DSL-002", _NOTE),
    ("2026-03-10", "diesel", "Generator diesel", "0.9", "kL", "DEMO-DSL-003",
     _NOTE + " (kL on purpose, to demonstrate a recorded unit conversion)"),
    ("2026-02-20", "other_fossil_fuels", "Coal for boiler start-up (fictional)", "12", "t", "DEMO-FUEL-001",
     _NOTE + " (no factor in the library on purpose, so it stays unresolved)"),
    ("2026-02-28", "bagasse_combustion", "Bagasse burned in boiler (fictional)", "1800", "t", "DEMO-BAG-001",
     _NOTE + " (bagasse is not assessed in the MVP)"),
]
# Previous period (2025-10-01 .. 2025-12-31), used only for the trend comparison.
DEMO_PRIOR_ACTIVITIES = [
    ("2025-10-01", "purchased_electricity", "Grid electricity", "10800", "kWh", "DEMO-BILL-P01", _NOTE),
    ("2025-11-01", "purchased_electricity", "Grid electricity", "11200", "kWh", "DEMO-BILL-P02", _NOTE),
    ("2025-12-01", "purchased_electricity", "Grid electricity", "11000", "kWh", "DEMO-BILL-P03", _NOTE),
]

DEMO_FACTORS = [
    {"id": "EF-ELECTRICITY-DEMO-001", "name": "Synthetic electricity emissions factor",
     "category": "purchased_electricity", "value": 0.70, "numerator_unit": "kgCO2e",
     "denominator_unit": "kWh", "gas_basis": "CO2e (synthetic)", "geography": "Synthetic demonstration only",
     "applicable_year": None, "source_organization": None, "source_document": None, "source_url": None,
     "source_reference": None, "status": "illustrative", "provenance": "synthetic_demo",
     "notes": "Fictional demonstration value. NOT a current Indian grid factor. Not for real reporting."},
    {"id": "EF-DIESEL-DEMO-001", "name": "Synthetic diesel emissions factor",
     "category": "diesel", "value": 2.50, "numerator_unit": "kgCO2e",
     "denominator_unit": "L", "gas_basis": "CO2e (synthetic)", "geography": "Synthetic demonstration only",
     "applicable_year": None, "source_organization": None, "source_document": None, "source_url": None,
     "source_reference": None, "status": "illustrative", "provenance": "synthetic_demo",
     "notes": "Fictional round number chosen for the demo. NOT a published diesel factor. Not for real reporting."},
]

ERROR_DEMO_ROWS = [  # for sample_data/demo_activities_with_errors.csv
    ("2026-03-15", "purchased_electricity", "Grid electricity", "8000", "kWh", "DEMO-BILL-004", "synthetic_demo", "VALID row"),
    ("2026-13-45", "purchased_electricity", "Grid electricity", "9000", "kWh", "DEMO-BAD-01", "synthetic_demo", "ERROR: invalid date"),
    ("2026-03-16", "purchased_electricity", "Grid electricity", "abc", "kWh", "DEMO-BAD-02", "synthetic_demo", "ERROR: non-numeric quantity"),
    ("2026-03-17", "purchased_electricity", "Grid electricity", "9000", "gallons", "DEMO-BAD-03", "synthetic_demo", "ERROR: unknown unit"),
    ("2026-03-18", "steam_misc", "Mystery steam", "50", "t", "DEMO-BAD-04", "synthetic_demo", "ERROR: unknown category"),
    ("2026-03-19", "diesel", "Generator diesel", "-5", "L", "DEMO-BAD-05", "synthetic_demo", "ERROR: negative quantity"),
    ("2026-03-20", "purchased_electricity", "Grid electricity", "12,500", "kWh", "DEMO-BAD-06", "synthetic_demo", "ERROR: comma in quantity"),
    ("2027-01-05", "purchased_electricity", "Grid electricity", "9000", "kWh", "DEMO-BAD-07", "synthetic_demo", "ERROR: outside period"),
    ("2026-03-21", "diesel", "Generator diesel", "300", "L", "DEMO-DSL-004", "synthetic_demo", "VALID row"),
    ("2026-03-21", "diesel", "Generator diesel", "300", "L", "DEMO-DSL-004", "synthetic_demo", "ERROR: duplicate of previous row"),
]


def demo_exists(conn) -> bool:
    return any(f["name"] == DEMO_FACTORY_NAME for f in db.list_factories(conn))


def load_demo(conn, include_current_records: bool = True) -> dict:
    """Create the fictional factory, two periods, illustrative factors and records."""
    if demo_exists(conn):
        raise db.ValidationError(["The demo dataset is already loaded in this database."])
    fid = db.create_factory(conn, DEMO_FACTORY_NAME, DEMO_LOCATION,
                            notes="FICTIONAL demonstration factory. " + calc.SYNTHETIC_LABEL, is_synthetic=True)
    prior = db.create_period(conn, fid, "2025-10-01", "2025-12-31", DEMO_BOUNDARY,
                             cane_crushed_t=5200, sugar_produced_t=520,
                             data_source_notes="FICTIONAL synthetic data.")
    cur = db.create_period(conn, fid, "2026-01-01", "2026-03-31", DEMO_BOUNDARY,
                           cane_crushed_t=5000, sugar_produced_t=500,
                           data_source_notes="FICTIONAL synthetic data.")
    for f in DEMO_FACTORS:
        db.create_factor(conn, f)
    for row in DEMO_PRIOR_ACTIVITIES:
        d, c, n, q, u, s, notes = row
        db.add_activity(conn, prior, dict(activity_date=d, category=c, activity_name=n, quantity=q, unit=u,
                                          source_reference=s, provenance="synthetic_demo", notes=notes))
    if include_current_records:
        for d, c, n, q, u, s, notes in DEMO_ACTIVITIES:
            db.add_activity(conn, cur, dict(activity_date=d, category=c, activity_name=n, quantity=q, unit=u,
                                            source_reference=s, provenance="synthetic_demo", notes=notes))
        # One manual record with NO quantity, to demonstrate missing-data handling.
        db.add_activity(conn, cur, dict(activity_date="2026-03-05", category="refrigerants",
                                        activity_name="Refrigerant top-up (quantity not yet available)",
                                        quantity=None, unit="kg", source_reference="DEMO-REF-001",
                                        provenance="synthetic_demo",
                                        notes=_NOTE + " (quantity missing on purpose)"),
                        allow_missing_quantity=True)
    db.log_event(conn, "demo_loaded", "factory", fid, "Synthetic demonstration dataset loaded (FICTIONAL).")
    return {"factory_id": fid, "current_period_id": cur, "prior_period_id": prior}


def write_sample_csvs(directory: str = "sample_data") -> list[str]:
    os.makedirs(directory, exist_ok=True)
    paths = []
    p = os.path.join(directory, "demo_activities.csv")
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for d, c, n, q, u, s, notes in DEMO_ACTIVITIES:
            w.writerow([d, c, n, q, u, s, "synthetic_demo", notes])
    paths.append(p)
    p = os.path.join(directory, "demo_activities_with_errors.csv")
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for r in ERROR_DEMO_ROWS:
            w.writerow(r)
    paths.append(p)
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description="Create a CarbonOS Sugar demo database (FICTIONAL data).")
    ap.add_argument("--db", default=db.DEFAULT_DB_PATH)
    ap.add_argument("--no-current-records", action="store_true",
                    help="Skip current-period records so you can import sample_data/demo_activities.csv yourself.")
    ap.add_argument("--write-sample-csvs", action="store_true")
    args = ap.parse_args()
    if args.write_sample_csvs:
        print("Wrote:", ", ".join(write_sample_csvs()))
        return
    conn = db.connect(args.db)
    ids = load_demo(conn, include_current_records=not args.no_current_records)
    print(f"Loaded FICTIONAL demo data into {args.db}: {ids}")


if __name__ == "__main__":
    main()

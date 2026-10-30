"""CSV import: parse, validate every row, preview, then commit only valid rows.

Nothing is dropped silently: every rejected row is returned with its file line
number and plain-language errors, and the commit logs rejected rows in history.
"""
from __future__ import annotations

import csv
import io
from typing import Optional, Union

import calculations as calc
import database as db

REQUIRED_COLUMNS = ["activity_date", "category", "activity_name", "quantity", "unit", "provenance"]
OPTIONAL_COLUMNS = ["source_reference", "notes"]
ALL_COLUMNS = REQUIRED_COLUMNS[:4] + ["unit", "source_reference", "provenance", "notes"]

TEMPLATE_CSV = (
    ",".join(ALL_COLUMNS) + "\n"
    "2026-01-01,purchased_electricity,Grid electricity,12500,kWh,DEMO-BILL-001,synthetic_demo,"
    "Fictional demonstration record\n"
)


def _dup_key(rec: dict) -> tuple:
    return (rec.get("activity_date"), rec.get("category"), rec.get("quantity"), rec.get("unit"),
            rec.get("source_reference"))


def parse_csv(content: Union[bytes, str], filename: str, period: dict,
              existing: Optional[list[dict]] = None) -> dict:
    """Return a preview dict. Does not touch the database."""
    preview = {"filename": filename, "header_errors": [], "ignored_columns": [], "rows": [],
               "n_rows": 0, "n_valid": 0, "n_rejected": 0}
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            preview["header_errors"].append("File is not valid UTF-8 text. Re-save the CSV as UTF-8.")
            return preview
    else:
        text = content.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        preview["header_errors"].append("The file is empty or has no header row.")
        return preview
    headers = [(h or "").strip().lower() for h in reader.fieldnames]
    reader.fieldnames = headers
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        preview["header_errors"].append("Missing required column(s): " + ", ".join(missing)
                                        + ". Required: " + ", ".join(REQUIRED_COLUMNS) + ".")
    preview["ignored_columns"] = [h for h in headers if h and h not in REQUIRED_COLUMNS + OPTIONAL_COLUMNS]
    if missing:
        return preview

    seen: dict[tuple, str] = {}
    existing_keys = {}
    for e in (existing or []):
        existing_keys.setdefault(_dup_key(e), e["id"])

    for raw in reader:
        line = reader.line_num
        errors: list[str] = []
        extra = raw.pop(None, None)
        if extra:
            errors.append("Row has more fields than the header; check for unquoted commas.")
        values = {k: (v if v is not None else "") for k, v in raw.items()}
        if not any(str(v).strip() for v in values.values()):
            errors.append("Row is empty.")
            rec = None
        else:
            rec_in = {k: values.get(k) for k in REQUIRED_COLUMNS + OPTIONAL_COLUMNS}
            rec_in["source_row_reference"] = f"{filename}:line {line}"
            rec, verrs = calc.validate_activity_input(rec_in, period, allow_missing_quantity=False)
            errors += verrs
            if not errors:
                key = _dup_key(rec)
                if key in seen:
                    errors.append(f"Duplicate of {seen[key]} in this file.")
                elif key in existing_keys:
                    errors.append(f"Duplicate of existing activity record #{existing_keys[key]}.")
                else:
                    seen[key] = f"line {line}"
        preview["rows"].append({"row_number": line, "raw": values, "record": rec if not errors else None,
                                "errors": errors, "status": "valid" if not errors else "rejected"})
    preview["n_rows"] = len(preview["rows"])
    preview["n_valid"] = sum(1 for r in preview["rows"] if r["status"] == "valid")
    preview["n_rejected"] = preview["n_rows"] - preview["n_valid"]
    return preview


def commit_import(conn, period_id: int, preview: dict) -> dict:
    """Insert valid rows only. Refuses if the header was invalid."""
    if preview["header_errors"]:
        raise db.ValidationError(preview["header_errors"])
    valid = [r["record"] for r in preview["rows"] if r["status"] == "valid"]
    rejected = [r for r in preview["rows"] if r["status"] == "rejected"]
    if not valid:
        raise db.ValidationError(["No valid rows to import."])
    ids = db.bulk_add_activities(conn, period_id, valid, preview["filename"], rejected)
    return {"imported": len(ids), "rejected": len(rejected), "record_ids": ids,
            "rejected_rows": [(r["row_number"], r["errors"]) for r in rejected]}

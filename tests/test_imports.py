"""CSV import tests (section 13.4)."""
import os

import pytest

import database as db
import imports

HEADER = "activity_date,category,activity_name,quantity,unit,source_reference,provenance,notes\n"
SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")


@pytest.fixture
def per(conn, period):
    return db.get_period(conn, period)


def test_valid_csv_imports_successfully(conn, period, per):
    csv_text = HEADER + ("2026-01-01,purchased_electricity,Grid electricity,12500,kWh,DEMO-BILL-001,"
                         "synthetic_demo,Fictional demonstration record\n")
    pv = imports.parse_csv(csv_text, "t.csv", per)
    assert pv["n_valid"] == 1 and pv["n_rejected"] == 0 and not pv["header_errors"]
    out = imports.commit_import(conn, period, pv)
    assert out["imported"] == 1
    rec = db.list_activities(conn, period)[0]
    assert rec["quantity"] == 12500.0 and rec["unit"] == "kWh" and rec["provenance"] == "synthetic_demo"
    ev = next(e for e in db.list_events(conn) if e["event_type"] == "csv_imported")
    assert "1 records imported" in ev["description"]


def test_imported_records_keep_source_file_and_row_reference(conn, period, per):
    csv_text = HEADER + "2026-01-01,diesel,Gen,10,L,B1,user_provided,\n2026-01-02,diesel,Gen,11,L,B2,user_provided,\n"
    imports.commit_import(conn, period, imports.parse_csv(csv_text, "bills.csv", per))
    refs = [r["source_row_reference"] for r in db.list_activities(conn, period)]
    assert refs == ["bills.csv:line 2", "bills.csv:line 3"]


def test_missing_required_headers_reported(per):
    pv = imports.parse_csv("activity_date,category\n2026-01-01,diesel\n", "t.csv", per)
    assert pv["header_errors"] and "quantity" in pv["header_errors"][0] and "unit" in pv["header_errors"][0]
    assert pv["rows"] == []


def test_commit_refused_on_header_errors(conn, period, per):
    pv = imports.parse_csv("a,b\n1,2\n", "t.csv", per)
    with pytest.raises(db.ValidationError):
        imports.commit_import(conn, period, pv)


def test_row_level_errors_identify_the_row(per):
    csv_text = HEADER + (
        "2026-01-01,diesel,Gen,10,L,B1,user_provided,\n"            # line 2 valid
        "2026-13-45,diesel,Gen,10,L,B2,user_provided,\n"            # line 3 invalid date
        "2026-01-03,diesel,Gen,abc,L,B3,user_provided,\n"           # line 4 non-numeric
        "2026-01-04,diesel,Gen,10,gallons,B4,user_provided,\n"      # line 5 invalid unit
        "2026-01-05,bogus,Gen,10,L,B5,user_provided,\n"             # line 6 invalid category
        "2026-01-06,diesel,Gen,10,L,B6,made_up,\n"                  # line 7 invalid provenance
        "2026-01-07,diesel,,10,L,B7,user_provided,\n"               # line 8 empty required field
    )
    pv = imports.parse_csv(csv_text, "t.csv", per)
    assert pv["n_valid"] == 1 and pv["n_rejected"] == 6
    by_line = {r["row_number"]: r["errors"] for r in pv["rows"]}
    assert any("not a valid" in e for e in by_line[3])
    assert any("not a number" in e for e in by_line[4])
    assert any("not recognised" in e for e in by_line[5])
    assert any("Unknown category" in e for e in by_line[6])
    assert any("Provenance" in e for e in by_line[7])
    assert any("Activity name is required" in e for e in by_line[8])
    assert by_line[2] == []


def test_invalid_rows_are_never_silently_dropped(conn, period, per):
    csv_text = HEADER + "2026-01-01,diesel,Gen,10,L,B1,user_provided,\n2026-01-02,diesel,Gen,x,L,B2,user_provided,\n"
    pv = imports.parse_csv(csv_text, "t.csv", per)
    out = imports.commit_import(conn, period, pv)
    assert out["imported"] == 1 and out["rejected"] == 1 and out["rejected_rows"][0][0] == 3
    ev = next(e for e in db.list_events(conn) if e["event_type"] == "csv_imported")
    assert '"row": 3' in ev["new_value_json"]                # rejected row is in the audit history


def test_blank_quantity_is_rejected_not_zero(per):
    pv = imports.parse_csv(HEADER + "2026-01-01,diesel,Gen,,L,B1,user_provided,\n", "t.csv", per)
    assert pv["n_valid"] == 0 and any("Quantity is required" in e for e in pv["rows"][0]["errors"])


def test_duplicate_rows_in_file_and_against_database(conn, period, per):
    row = "2026-01-01,diesel,Gen,10,L,B1,user_provided,\n"
    pv = imports.parse_csv(HEADER + row + row, "t.csv", per)
    assert pv["n_valid"] == 1 and "Duplicate" in pv["rows"][1]["errors"][0]
    imports.commit_import(conn, period, pv)
    pv2 = imports.parse_csv(HEADER + row, "again.csv", per, existing=db.list_activities(conn, period))
    assert pv2["n_valid"] == 0 and "existing activity record" in pv2["rows"][0]["errors"][0]


def test_unknown_columns_are_reported_not_silently_ignored(per):
    pv = imports.parse_csv(HEADER.strip() + ",extra_col\n" + "2026-01-01,diesel,Gen,10,L,B1,user_provided,,zzz\n",
                           "t.csv", per)
    assert pv["ignored_columns"] == ["extra_col"] and pv["n_valid"] == 1


def test_row_with_too_many_fields_rejected(per):
    pv = imports.parse_csv(HEADER + "2026-01-01,diesel,Gen,10,L,B1,user_provided,note,EXTRA\n", "t.csv", per)
    assert pv["n_valid"] == 0 and any("more fields" in e for e in pv["rows"][0]["errors"])


def test_bom_and_bytes_input(per):
    pv = imports.parse_csv(("\ufeff" + HEADER + "2026-01-01,diesel,Gen,10,L,B1,user_provided,\n").encode("utf-8"),
                           "t.csv", per)
    assert pv["n_valid"] == 1


def test_non_utf8_reported(per):
    pv = imports.parse_csv(b"\xff\xfe\x00bad", "t.csv", per)
    assert pv["header_errors"]


def test_template_is_importable_and_labelled_fictional(per):
    pv = imports.parse_csv(imports.TEMPLATE_CSV, "template.csv", per)
    assert pv["n_valid"] == 1 and "Fictional" in imports.TEMPLATE_CSV


def test_shipped_sample_csv_imports_cleanly(conn, period, per):
    with open(os.path.join(SAMPLE_DIR, "demo_activities.csv"), "rb") as fh:
        pv = imports.parse_csv(fh.read(), "demo_activities.csv", per)
    assert pv["n_rejected"] == 0 and pv["n_valid"] == 8
    assert all(r["record"]["provenance"] == "synthetic_demo" for r in pv["rows"])


def test_shipped_error_sample_reports_every_bad_row(per):
    with open(os.path.join(SAMPLE_DIR, "demo_activities_with_errors.csv"), "rb") as fh:
        pv = imports.parse_csv(fh.read(), "demo_activities_with_errors.csv", per)
    assert pv["n_valid"] == 2 and pv["n_rejected"] == 8
    assert all(r["errors"] for r in pv["rows"] if r["status"] == "rejected")

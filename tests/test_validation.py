"""Data-quality tests (section 13.2)."""
import calculations as calc
from conftest import ELEC_FACTOR, act


def good(**kw):
    base = {"activity_date": "2026-01-01", "category": "purchased_electricity", "activity_name": "Grid",
            "quantity": "12500", "unit": "kWh", "provenance": "user_provided"}
    base.update(kw)
    return base


def errs(**kw):
    return calc.validate_activity_input(good(**kw))[1]


def test_valid_record_has_no_errors():
    clean, e = calc.validate_activity_input(good())
    assert e == [] and clean["quantity"] == 12500.0 and clean["status"] == "valid"


def test_unknown_category():
    assert any("Unknown category" in e for e in errs(category="steam_misc"))


def test_missing_date():
    assert any("date is required" in e for e in errs(activity_date=""))


def test_invalid_date():
    assert any("not a valid" in e for e in errs(activity_date="2026-13-45"))
    assert any("not a valid" in e for e in errs(activity_date="01/02/2026"))   # formats are not guessed


def test_non_numeric_quantity():
    assert any("not a number" in e for e in errs(quantity="abc"))


def test_comma_quantity_rejected_not_guessed():
    assert any("comma" in e for e in errs(quantity="12,500"))


def test_missing_unit_and_unknown_unit():
    assert any("Unit is required" in e for e in errs(unit=""))
    assert any("not recognised" in e for e in errs(unit="gallons"))


def test_unit_must_suit_category():
    assert any("not valid for" in e for e in errs(unit="L"))        # litres for electricity


def test_missing_quantity_only_allowed_when_explicit():
    assert any("required" in e for e in errs(quantity=""))
    clean, e = calc.validate_activity_input(good(quantity=""), allow_missing_quantity=True)
    assert e == [] and clean["quantity"] is None and clean["status"] == "missing_activity_data"


def test_outside_period_rejected():
    period = {"start_date": "2026-01-01", "end_date": "2026-03-31"}
    _, e = calc.validate_activity_input(good(activity_date="2027-01-01"), period)
    assert any("outside the reporting period" in x for x in e)


def test_activity_provenance_values():
    assert any("Provenance" in e for e in errs(provenance="published_factor"))


def test_incompatible_factor_blocks_calculation():
    r = calc.calculate_record(act(), dict(ELEC_FACTOR, denominator_unit="t"))
    assert r["status"] == calc.UNIT_MISMATCH


def test_illustrative_factor_blocked_in_real_reporting_mode():
    r = calc.calculate_record(act(provenance="user_provided"), dict(ELEC_FACTOR), reporting_mode="real")
    assert r["status"] == calc.ILLUSTRATIVE_FACTOR and r["result_value"] is None
    assert "must not be used for real reporting" in r["message"]


def test_synthetic_activity_blocked_in_real_reporting_mode():
    verified = dict(ELEC_FACTOR, status="verified_for_use", provenance="published_factor")
    r = calc.calculate_record(act(), verified, reporting_mode="real")
    assert r["status"] == calc.NEEDS_REVIEW


def test_verified_factor_with_real_activity_calculates_in_real_mode():
    verified = dict(ELEC_FACTOR, status="verified_for_use", provenance="published_factor")
    r = calc.calculate_record(act(provenance="user_provided"), verified, reporting_mode="real")
    assert r["status"] == calc.CALCULATED


def test_cannot_mark_factor_verified_without_source():
    f = dict(ELEC_FACTOR, status="verified_for_use", provenance="published_factor")
    e = calc.validate_factor_record(f)
    assert any("Cannot mark 'verified_for_use'" in x for x in e)


def test_synthetic_factor_cannot_be_verified():
    f = dict(ELEC_FACTOR, status="verified_for_use", source_organization="x", source_document="y",
             source_reference="z", applicable_year=2024)
    assert any("synthetic_demo" in x for x in calc.validate_factor_record(f))


def test_missing_production_quantity_blocks_intensity():
    period = {"cane_crushed_t": None, "sugar_produced_t": None}
    ind = {i["key"]: i for i in calc.energy_intensity([act()], period)}
    assert ind["electricity_per_cane"]["value"] is None
    assert "production denominator is missing" in ind["electricity_per_cane"]["reason"]


def test_intensity_not_computed_when_numerator_incomplete():
    period = {"cane_crushed_t": 5000, "sugar_produced_t": 500}
    ind = {i["key"]: i for i in calc.energy_intensity([act(), act(id=2, quantity=None)], period)}
    assert ind["electricity_per_cane"]["value"] is None
    assert "Numerator incomplete" in ind["electricity_per_cane"]["reason"]


def test_intensity_value():
    period = {"cane_crushed_t": 5000, "sugar_produced_t": 500}
    ind = {i["key"]: i for i in calc.energy_intensity([act(quantity=10000)], period)}
    assert ind["electricity_per_cane"]["value"] == 2.0
    assert ind["electricity_per_sugar"]["value"] == 20.0


def test_zero_production_flag_with_positive_energy():
    period = {"cane_crushed_t": 0, "sugar_produced_t": None}
    flags = calc.find_anomalies([act()], [], period, calc.energy_intensity([act()], period))
    assert any(f["code"] == "ZERO_PRODUCTION_WITH_ENERGY" for f in flags)


def test_duplicate_looking_records_flagged():
    a, b = act(id=1), act(id=2)
    flags = calc.find_anomalies([a, b], [], {"cane_crushed_t": 1}, [], None)
    assert any(f["code"] == "DUPLICATE_LOOKING" and f["activity_record_id"] == 2 for f in flags)


def test_trend_unavailable_without_history():
    flags = calc.find_anomalies([act()], [], {"cane_crushed_t": 1}, [], None)
    assert any(f["code"] == "TREND_UNAVAILABLE" for f in flags)


def _inv(acts, factors):
    res = []
    for a in acts:
        f, _ = calc.select_factor(a["category"], factors)
        res.append(calc.calculate_record(a, f))
    return calc.summarize_inventory(acts, res)


def test_partial_inventory_is_labelled_partial_and_missing_is_not_zero():
    acts = [act(id=1), act(id=2, category="diesel", unit="L", quantity=100)]
    inv = _inv(acts, [dict(ELEC_FACTOR)])
    assert inv["inventory_status"] == "incomplete"
    assert inv["totals"]["total_label"] == "Partial assessed total"
    assert inv["totals"]["assessed_kg_co2e"] == 8750.0           # diesel NOT counted as 0
    assert inv["unresolved_records"] == 1
    by = {c["category"]: c for c in inv["categories"]}
    assert by["diesel"]["completeness"] == "unresolved" and by["diesel"]["assessed_kg_co2e"] is None
    assert by["wastewater_effluent"]["completeness"] == "not_assessed"


def test_no_calculated_records_means_none_total_not_zero():
    inv = _inv([act(quantity=None)], [dict(ELEC_FACTOR)])
    assert inv["totals"]["assessed_kg_co2e"] is None


def test_only_resolved_or_excluded_categories_allow_non_incomplete_status():
    acts = [act(id=1)]
    excluded = {c: "out of scope" for c in calc.CATEGORIES if c != "purchased_electricity"}
    res = [calc.calculate_record(acts[0], dict(ELEC_FACTOR))]
    assert calc.summarize_inventory(acts, res, excluded)["inventory_status"] == "all_declared_categories_calculated"
    assert calc.summarize_inventory(acts, res, {})["inventory_status"] == "incomplete"

"""Calculation tests A-H from the specification (section 13.1)."""
from decimal import Decimal

import pytest

import calculations as calc
from conftest import ELEC_FACTOR, act


def test_A_basic_multiplication_synthetic():
    r = calc.calculate_record(act(), dict(ELEC_FACTOR))
    assert r["status"] == calc.CALCULATED
    assert r["result_value"] == 8750.0
    assert r["result_unit"] == "kgCO2e"
    assert r["synthetic"] is True                      # marked as synthetic demonstration
    assert any("synthetic" in w.lower() for w in r["warnings"])
    assert any("illustrative" in w.lower() for w in r["warnings"])


def test_B_conversion_to_tonnes():
    assert calc.kg_to_tonnes(8750.0) == 8.75


def test_C_explicit_zero_calculates_to_zero_with_warning():
    r = calc.calculate_record(act(quantity=0), dict(ELEC_FACTOR))
    assert r["status"] == calc.CALCULATED and r["result_value"] == 0.0
    assert any("zero" in w.lower() for w in r["warnings"])


def test_D_missing_quantity_no_numeric_result():
    r = calc.calculate_record(act(quantity=None), dict(ELEC_FACTOR))
    assert r["status"] == calc.MISSING_ACTIVITY
    assert r["result_value"] is None
    assert "required" in r["message"].lower()


def test_E_missing_factor_unresolved_no_numeric_result():
    r = calc.calculate_record(act(), None)
    assert r["status"] == calc.MISSING_FACTOR
    assert r["result_value"] is None


def test_F_unit_mismatch_rejected():
    f = dict(ELEC_FACTOR, denominator_unit="L")        # per litre, activity in kWh
    r = calc.calculate_record(act(), f)
    assert r["status"] == calc.UNIT_MISMATCH
    assert r["result_value"] is None
    assert "not compatible" in r["message"]


def test_F2_litres_vs_tonne_factor_needs_documented_conversion():
    diesel = {"id": "D", "category": "diesel", "value": 3.0, "numerator_unit": "kgCO2e",
              "denominator_unit": "t", "status": "illustrative", "provenance": "synthetic_demo"}
    r = calc.calculate_record(act(category="diesel", quantity=100, unit="L"), diesel)
    assert r["status"] == calc.UNIT_MISMATCH           # no density conversion is defined


def test_G_negative_quantity_rejected():
    r = calc.calculate_record(act(quantity=-5), dict(ELEC_FACTOR))
    assert r["status"] == calc.NEEDS_REVIEW and r["result_value"] is None
    _, errs = calc.validate_activity_input(act(quantity=-5, id=None))
    assert any("Negative" in e for e in errs)


def test_H_precision_full_precision_stored_rounding_only_for_display():
    f = dict(ELEC_FACTOR, value=0.123456789)
    r = calc.calculate_record(act(quantity=1234.5678), f)
    exact = float(Decimal("1234.5678") * Decimal("0.123456789"))
    assert r["result_value"] == exact                  # no intermediate rounding
    assert r["input_quantity_snapshot"] == 1234.5678 and r["factor_value_snapshot"] == 0.123456789
    assert f"{r['result_value']:.2f}" == "152.42"      # rounding happens only when formatting


def test_binary_float_error_is_avoided():
    f = dict(ELEC_FACTOR, value=0.1)
    assert calc.calculate_record(act(quantity=3), f)["result_value"] == 0.3


def test_recorded_unit_conversion_mwh_to_kwh():
    r = calc.calculate_record(act(quantity=12.5, unit="MWh"), dict(ELEC_FACTOR))
    assert r["result_value"] == 8750.0
    assert "MWh → kWh" in r["conversion_description"]


def test_tco2e_factor_numerator_is_converted_not_confused_with_kg():
    f = dict(ELEC_FACTOR, value=0.0007, numerator_unit="tCO2e")
    r = calc.calculate_record(act(), f)
    assert r["result_value"] == pytest.approx(8750.0)
    assert "tCO2e → kgCO2e" in r["conversion_description"]


def test_unsupported_numerator_rejected():
    f = dict(ELEC_FACTOR, numerator_unit="kgCO2")     # CO2 only, not CO2e
    assert calc.calculate_record(act(), f)["status"] == calc.UNIT_MISMATCH


def test_unsupported_categories_are_not_assessed_not_zero():
    for cat, unit in (("bagasse_combustion", "t"), ("wastewater_effluent", "m3"), ("other_sources", "kg")):
        r = calc.calculate_record(act(category=cat, unit=unit, quantity=10), dict(ELEC_FACTOR, category=cat))
        assert r["status"] == calc.NOT_ASSESSED and r["result_value"] is None


def test_recompute_from_snapshot_fields_only():
    r = calc.calculate_record(act(), dict(ELEC_FACTOR))
    assert calc.recompute_from_snapshot(r) == r["result_value"]


def test_deprecated_factor_is_not_selected_or_used():
    f = dict(ELEC_FACTOR, status="deprecated")
    assert calc.select_factor("purchased_electricity", [f])[0] is None
    assert calc.calculate_record(act(), f)["status"] == calc.MISSING_FACTOR

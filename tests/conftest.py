import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db  # noqa: E402


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def period(conn):
    """Empty FICTIONAL factory + one period, no factors."""
    fid = db.create_factory(conn, "TEST Mill (FICTIONAL)", is_synthetic=True)
    pid = db.create_period(conn, fid, "2026-01-01", "2026-03-31", "test boundary",
                           cane_crushed_t=5000, sugar_produced_t=500)
    return pid


ELEC_FACTOR = {"id": "EF-ELECTRICITY-DEMO-001", "name": "Synthetic electricity factor",
               "category": "purchased_electricity", "value": 0.70, "numerator_unit": "kgCO2e",
               "denominator_unit": "kWh", "geography": "Synthetic demonstration only",
               "status": "illustrative", "provenance": "synthetic_demo", "is_active": 1,
               "notes": "Fictional"}


@pytest.fixture
def elec_factor():
    return dict(ELEC_FACTOR)


def act(**kw):
    base = {"id": 1, "activity_date": "2026-01-01", "category": "purchased_electricity",
            "activity_name": "Grid electricity", "quantity": 12500, "unit": "kWh",
            "source_reference": "DEMO-BILL-001", "provenance": "synthetic_demo"}
    base.update(kw)
    return base

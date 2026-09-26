import copy

import pytest

from engine import build_baselines, router

FIXTURES = [
    {"channel": "Phone", "category": "Billing - disputed amount", "priority": "P3", "region": "Ashford",
     "entry_system": "SYS-05"},
    {"channel": "Web form", "category": "Billing - estimated read", "priority": "P2", "region": "Barrowdale",
     "entry_system": "SYS-03"},
    {"channel": "Email", "category": "Other", "priority": "P3", "region": "Fenwick", "entry_system": "SYS-04"},
    {"channel": "Regulator referral", "category": "Supply - interruption", "priority": "P1", "region": "Dunmoor"},
    {"channel": "Social", "category": "Water - pressure or quality", "priority": "P2", "region": "Eastmarch",
     "entry_system": "SYS-01"},
]


@pytest.fixture(scope="module")
def tables():
    return build_baselines.load()


@pytest.mark.parametrize("intake", FIXTURES)
def test_route_shape_and_invariants(intake, tables):
    t = router.route(intake, tables)
    assert t["owner"]["system"] == "SYS-04 CaseTrack"
    assert t["owner"]["team"] == router.TEAMS[intake["category"]]
    assert 1 <= len(t["resolution_path"]) <= 3
    shares = [p["share"] for p in t["resolution_path"]]
    assert shares == sorted(shares, reverse=True) and sum(shares) <= 1.0001
    assert 0 <= t["info_only_likelihood"] <= 1
    # Routing never makes things worse than the legacy path.
    assert t["expected_days"]["routed"] <= t["expected_days"]["legacy"]
    assert t["breach_risk"]["routed"] <= t["breach_risk"]["legacy"]
    assert t["cost"]["routed"] <= t["cost"]["legacy"]
    assert t["reasons"]


def test_casetrack_entry_has_no_transfer_risk(tables):
    t = router.route(FIXTURES[2], tables)
    assert t["legacy_route"]["transfer_risk"] == 0
    assert t["expected_days"]["routed"] == t["expected_days"]["legacy"]
    assert t["cost"]["legacy"] == t["cost"]["routed"] == 68.0


def test_non_casetrack_transfer_risk_is_about_46pct(tables):
    t = router.route(FIXTURES[0], tables)
    assert 0.44 <= t["legacy_route"]["transfer_risk"] <= 0.49
    assert t["cost"]["legacy"] > 68.0


def test_default_entry_from_channel(tables):
    t = router.route(FIXTURES[3], tables)
    assert t["legacy_route"]["entry_system"].startswith("SYS-05")


def test_barrowdale_billing_links_aurora_and_meterhub(tables):
    t = router.route(FIXTURES[1], tables)
    assert t["owner"]["linked_systems"] == ["SYS-01 Aurora Billing", "SYS-06 MeterHub"]
    assert any("no smart meters" in r for r in t["reasons"])


def test_alert_context_is_attached(tables):
    alert = {"alert_id": "SIM-x", "summary": "Estimated-read complaints up in Barrowdale (z = 4.0)"}
    t = router.route(FIXTURES[1], tables, {"region_alert": alert, "account_prior_complaints": 2})
    assert t["context"]["region_alert_id"] == "SIM-x"
    assert t["context"]["account_prior_complaints"] == 2
    assert any("Active alert" in r for r in t["reasons"])


def test_outcome_fields_are_ignored(tables):
    """Leakage guard: outcome fields on the intake must not change the result."""
    base = router.route(FIXTURES[0], tables)
    leaky = copy.deepcopy(FIXTURES[0])
    leaky.update(days_to_close=200, sla_breach=1, reopened=1, resolution_action="Refund or credit applied",
                 date_closed="2026-01-01", bill_correction_value=999.0)
    assert router.route(leaky, tables) == base


def test_route_is_pure(tables):
    snapshot = copy.deepcopy(tables)
    router.route(FIXTURES[0], tables)
    assert tables == snapshot

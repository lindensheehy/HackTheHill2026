from engine import build_baselines, cost_model
from jobs import detect_alerts


def test_transfer_penalty_matches_evidence():
    tp = cost_model.transfer_penalty()
    assert round(tp["days"]["transferred"], 1) == 38.2
    assert round(tp["days"]["not"], 1) == 23.0
    assert tp["per_avoided"]["gbp"] == 53.0


def test_survival_curves_are_probabilities_ending_at_one():
    for key, c in build_baselines.load()["breach_survival"].items():
        p = c["p_breach_given_age"]
        assert len(p) == c["sla_days"] + 1
        assert all(0 <= x <= 1 for x in p)
        assert p[-1] == 1.0     # still open at the deadline -> certain to breach


def test_casetrack_never_transfers():
    assert build_baselines.load()["transfer_rate"]["SYS-04"]["rate"] == 0.0


def test_injected_scenario_is_detected_and_connected():
    try:
        alerts = detect_alerts.inject_scenario()
        grouped = [a for a in alerts if a["regions"] == ["Barrowdale", "Dunmoor"]]
        assert grouped, "scenario should fire in both regions together"
        assert all(set(a["shared_systems"]) == {"SYS-01", "SYS-06"} for a in grouped)
        assert any(a["signal"] == "complaints:Billing - estimated read" for a in grouped)
    finally:
        detect_alerts.reset_scenario()


def test_real_feed_is_quiet_now():
    """Honesty check from the plan: no live (last 2 months) real alerts at z >= 3."""
    active = [a for a in detect_alerts.group(detect_alerts.detect(detect_alerts.build_panel()))
              if a["status"] == "active"]
    assert len(active) <= 2

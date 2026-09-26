import pandas as pd
import pytest

from engine import queue_score

AS_OF = "2026-09-30"
CFG = {"priority_weight": {"P1": 3, "P2": 2, "P3": 1}, "transferred_bonus": 0.25, "alert_bonus": 0.25,
       "amber_days": 2, "imminence_horizon_days": 20}
# Flat survival: 80% of still-open cases go on to breach, at any age.
SURVIVAL = {f"{p}|{t}": {"sla_days": s, "p_breach_given_age": [0.8] * (s + 1)}
            for p, s in (("P1", 5), ("P2", 10), ("P3", 20)) for t in (0, 1)}


def case(cid, priority, age, transferred=0):
    sla = {"P1": 5, "P2": 10, "P3": 20}[priority]
    return {"complaint_id": cid, "priority": priority, "sla_days": sla, "transferred_between_systems": transferred,
            "date_opened": pd.Timestamp(AS_OF) - pd.Timedelta(days=age)}


def ranked(*cases, strict=False):
    df = queue_score.score_frame(pd.DataFrame(cases), SURVIVAL, CFG, as_of=AS_OF)
    return list(queue_score.rank(df, strict=strict)["complaint_id"]), df.set_index("complaint_id")


def test_timing_from_dates_not_flag():
    _, df = ranked(case("a", "P3", 21))
    r = df.loc["a"]
    assert r.age_days == 21 and r.overdue_days == 1 and r.breached
    assert r.overdue_state == "red"


def test_p1_slightly_overdue_beats_p3_equally_overdue_in_days():
    order, _ = ranked(case("p3", "P3", 28), case("p1", "P1", 7))   # both a few days over
    assert order[0] == "p1"


def test_overdue_ratio_puts_priorities_on_one_scale():
    # P1 two days over (ratio 0.4, w=3) vs P3 eight days over (ratio 0.4, w=1): P1 first.
    order, df = ranked(case("p3", "P3", 28), case("p1", "P1", 7))
    assert df.loc["p1", "overdue_ratio"] == pytest.approx(df.loc["p3", "overdue_ratio"])
    assert order == ["p1", "p3"]


def test_very_overdue_p3_can_outrank_barely_overdue_p1():
    order, _ = ranked(case("p1", "P1", 6), case("p3", "P3", 120))   # P3 is 100 days over
    assert order[0] == "p3"


def test_breached_always_outranks_not_yet_breached_same_priority():
    # Score must rise continuously through the deadline, not drop to ~0 just after it.
    order, df = ranked(case("before", "P3", 19), case("after", "P3", 21))
    assert order == ["after", "before"]
    assert df.loc["after", "queue_score"] > df.loc["before", "queue_score"]


def test_not_yet_breached_ordering_by_imminence():
    order, df = ranked(case("fresh", "P2", 1), case("close", "P2", 9))
    assert order == ["close", "fresh"]
    assert df.loc["close", "overdue_state"] == "amber"
    assert df.loc["fresh", "overdue_state"] == "green"


def test_transferred_bonus_breaks_ties():
    order, _ = ranked(case("plain", "P2", 15), case("moved", "P2", 15, transferred=1))
    assert order == ["moved", "plain"]


def test_strict_mode_is_priority_then_overdue_days():
    order, _ = ranked(case("p3", "P3", 120), case("p1a", "P1", 6), case("p1b", "P1", 9), strict=True)
    assert order == ["p1b", "p1a", "p3"]


def test_every_row_has_a_reason():
    _, df = ranked(case("a", "P1", 2), case("b", "P3", 40, transferred=1))
    assert all(len(w) >= 1 for w in df["why"])
    assert any("transferred" in s for s in df.loc["b", "why"])


def test_fresh_p1_outranks_fresh_p3():
    order, df = ranked(case("p3", "P3", 0), case("p1", "P1", 0))
    assert order == ["p1", "p3"]
    assert df.loc["p1", "queue_score"] > 0

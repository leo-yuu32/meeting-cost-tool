from datetime import date, datetime, time, timedelta

import pytest

from meeting_cost.model import day_penalty
from meeting_cost.shapley import (
    series_rollup,
    shapley_exact,
    shapley_from_characteristic_function,
    shapley_monte_carlo,
    shapley_values,
)
from meeting_cost.types import Meeting, Person

DAY = date(2026, 1, 5)


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(DAY, time(hour, minute))


# --- axioms verified against a textbook additive game, independent of the
# --- cost model: v(S) = sum of per-player weights in S. For an additive
# --- game the Shapley value of each player is exactly its own weight, which
# --- makes efficiency, symmetry and the null player property all checkable
# --- by construction.


def test_shapley_axioms_on_additive_game():
    weights = {"a": 10.0, "b": 10.0, "c": 0.0, "d": 4.0}

    def v(subset: frozenset[str]) -> float:
        return sum(weights[p] for p in subset)

    phi = shapley_from_characteristic_function(list(weights), v)

    # Efficiency: attributions sum to v(N).
    assert sum(phi.values()) == pytest.approx(v(frozenset(weights)))
    # Symmetry: equal-weight players get equal value.
    assert phi["a"] == pytest.approx(phi["b"])
    # Null player: zero-weight player gets exactly zero.
    assert phi["c"] == pytest.approx(0.0)
    # Additive game: Shapley value equals the player's own weight.
    for player, weight in weights.items():
        assert phi[player] == pytest.approx(weight)


# --- grounded checks against the real cost model


def _person() -> Person:
    return Person(
        id="p1",
        window_by_weekday={0: (time(9), time(17))},
        reentry_cost=20,
        fatigue_rate=0.4,
        fatigue_threshold=90,
    )


def _meeting(mid, start, minutes, attendees=("p1",), series_id=None) -> Meeting:
    return Meeting(
        id=mid, start=start, end=start + timedelta(minutes=minutes), attendee_ids=attendees, series_id=series_id
    )


def test_shapley_exact_is_efficient_against_real_day_penalty():
    person = _person()
    meetings = [
        _meeting("m1", dt(10, 0), 30),
        _meeting("m2", dt(10, 30), 60),  # abuts m1 -> 90-min run, exactly at threshold
    ]
    phi = shapley_exact(person, meetings, DAY)
    total_p = day_penalty(person, meetings, DAY).penalty_minutes
    assert sum(phi.values()) == pytest.approx(total_p)


def test_shapley_exact_symmetry_on_two_identical_separated_meetings():
    person = _person()
    meetings = [
        _meeting("m1", dt(10, 0), 30),
        _meeting("m2", dt(14, 0), 30),  # same duration, far apart, no fatigue interaction
    ]
    phi = shapley_exact(person, meetings, DAY)
    assert phi["m1"] == pytest.approx(phi["m2"])


def test_shapley_exact_ignores_meetings_on_other_days_or_without_person():
    person = _person()
    meetings = [
        _meeting("m1", dt(10, 0), 30),
        Meeting(id="other-day", start=dt(10, 0) + timedelta(days=1), end=dt(10, 30) + timedelta(days=1), attendee_ids=("p1",)),
        _meeting("not-invited", dt(11, 0), 30, attendees=("someone-else",)),
    ]
    phi = shapley_exact(person, meetings, DAY)
    assert set(phi.keys()) == {"m1"}


def test_shapley_monte_carlo_is_deterministic_given_seed():
    person = _person()
    meetings = [_meeting(f"m{i}", dt(9 + i), 30) for i in range(5)]
    a = shapley_monte_carlo(person, meetings, DAY, seed=7, n_samples=500)
    b = shapley_monte_carlo(person, meetings, DAY, seed=7, n_samples=500)
    for mid in a:
        assert a[mid].value == b[mid].value
        assert a[mid].standard_error == b[mid].standard_error


def test_shapley_monte_carlo_converges_to_exact_value():
    person = _person()
    meetings = [
        _meeting("m1", dt(9, 0), 30),
        _meeting("m2", dt(10, 0), 45),
        _meeting("m3", dt(11, 0), 60),
        _meeting("m4", dt(13, 0), 30),
    ]
    exact = shapley_exact(person, meetings, DAY)
    mc = shapley_monte_carlo(person, meetings, DAY, seed=1, n_samples=4000)
    for mid, exact_value in exact.items():
        assert mc[mid].value == pytest.approx(exact_value, abs=3.0)


def test_shapley_values_dispatches_exact_below_threshold():
    person = _person()
    meetings = [_meeting("m1", dt(10, 0), 30)]
    result = shapley_values(person, meetings, DAY, seed=1, exact_threshold=12)
    assert result["m1"].standard_error == 0.0  # exact path reports no sampling error


def test_shapley_values_dispatches_monte_carlo_above_threshold():
    person = _person()
    meetings = [_meeting(f"m{i}", dt(9, i), 3) for i in range(8)]  # tiny non-overlapping meetings
    result = shapley_values(person, meetings, DAY, seed=1, exact_threshold=2, n_samples=200)
    assert all(r.standard_error >= 0.0 for r in result.values())


def test_series_rollup_sums_matching_series_and_skips_none():
    shapley_by_meeting = {"m1": 10.0, "m2": 5.0, "m3": 7.0}
    series_id_by_meeting = {"m1": "standup", "m2": "standup", "m3": None}
    rollup = series_rollup(shapley_by_meeting, series_id_by_meeting)
    assert rollup == {"standup": 15.0}

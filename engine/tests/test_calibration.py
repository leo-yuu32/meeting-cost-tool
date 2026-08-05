from datetime import date, datetime, time, timedelta

import pytest

from meeting_cost.calibration import (
    ParamGrid,
    WeekObservation,
    spearman_correlation,
    spearman_fit,
    week_penalty,
)
from meeting_cost.types import Meeting, Person

WEEK_START = date(2026, 1, 5)  # a Monday


def dt(day_offset: int, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(WEEK_START + timedelta(days=day_offset), time(hour, minute))


def person(pid="p1") -> Person:
    # Working Monday only, to keep week_penalty easy to reason about by hand.
    return Person(id=pid, window_by_weekday={0: (time(9), time(17))})


def meeting(mid, start, minutes, attendees=("p1",)) -> Meeting:
    return Meeting(id=mid, start=start, end=start + timedelta(minutes=minutes), attendee_ids=attendees)


def test_week_penalty_sums_only_the_working_day():
    p = person()
    meetings = [meeting("m1", dt(0, 10, 0), 30), meeting("m2", dt(0, 10, 30), 60)]
    # Same two-meeting worked example as test_model.py: P = 110 on the one working day.
    assert week_penalty(p, meetings, WEEK_START, reentry_cost=20, fatigue_rate=0.4, fatigue_threshold=90) == pytest.approx(110)


def test_spearman_correlation_perfect_positive_and_negative():
    assert spearman_correlation([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert spearman_correlation([1, 2, 3], [30, 20, 10]) == pytest.approx(-1.0)


def test_spearman_correlation_handles_ties():
    # Not a monotone sequence, but not degenerate either - just check it runs
    # and stays within the valid correlation range.
    corr = spearman_correlation([1, 1, 2, 3], [5, 6, 6, 1])
    assert -1.0 <= corr <= 1.0


def test_spearman_correlation_rejects_mismatched_or_too_short_input():
    with pytest.raises(ValueError):
        spearman_correlation([1, 2], [1])
    with pytest.raises(ValueError):
        spearman_correlation([1], [1])


def test_calibration_reentry_cost_flips_which_week_looks_worse():
    # Person A: one 60-min meeting -> P(c) = 60 + c (closed-form interior slot).
    # Person B: six 2-min meetings, each isolated and interior -> P(c) = 6*(2+c) = 12 + 6c.
    # At c=0, A's week looks worse (60 > 12); by c=20, B's does (132 > 80).
    person_a = person("a")
    meetings_a = [meeting("a1", dt(0, 12, 0), 60, attendees=("a",))]

    person_b = person("b")
    small_starts = [(9, 30), (10, 30), (11, 30), (12, 30), (13, 30), (14, 30)]
    meetings_b = [
        meeting(f"b{i}", dt(0, h, m), 2, attendees=("b",)) for i, (h, m) in enumerate(small_starts)
    ]

    # self_reported_rank: higher = "felt worse". Fixed to match A > B ordering,
    # i.e. matches the true P ordering only when c is small.
    observations = [
        WeekObservation(person=person_a, meetings=meetings_a, week_start=WEEK_START, self_reported_rank=2),
        WeekObservation(person=person_b, meetings=meetings_b, week_start=WEEK_START, self_reported_rank=1),
    ]

    grid_low_c = ParamGrid(reentry_costs=[0], fatigue_rates=[0.4], fatigue_thresholds=[90])
    grid_high_c = ParamGrid(reentry_costs=[20], fatigue_rates=[0.4], fatigue_thresholds=[90])

    result_low_c = spearman_fit(observations, grid_low_c)
    result_high_c = spearman_fit(observations, grid_high_c)

    assert result_low_c.best.correlation == pytest.approx(1.0)
    assert result_high_c.best.correlation == pytest.approx(-1.0)


def test_spearman_fit_grid_results_match_independent_computation():
    p1, p2, p3 = person("p1"), person("p2"), person("p3")
    obs = [
        WeekObservation(
            person=p1,
            meetings=[meeting("m1", dt(0, 9, 0), 30, attendees=("p1",))],
            week_start=WEEK_START,
            self_reported_rank=1,
        ),
        WeekObservation(
            person=p2,
            meetings=[meeting("m2", dt(0, 9, 0), 90, attendees=("p2",))],
            week_start=WEEK_START,
            self_reported_rank=3,
        ),
        WeekObservation(
            person=p3,
            meetings=[
                meeting("m3a", dt(0, 9, 0), 30, attendees=("p3",)),
                meeting("m3b", dt(0, 12, 0), 30, attendees=("p3",)),
            ],
            week_start=WEEK_START,
            self_reported_rank=2,
        ),
    ]
    grid = ParamGrid(reentry_costs=[0, 20], fatigue_rates=[0.3, 0.5], fatigue_thresholds=[60, 90])
    result = spearman_fit(obs, grid)

    assert len(result.all_results) == 2 * 2 * 2
    for gp in result.all_results:
        penalties = [
            week_penalty(o.person, o.meetings, o.week_start, gp.reentry_cost, gp.fatigue_rate, gp.fatigue_threshold)
            for o in obs
        ]
        expected = spearman_correlation(penalties, [o.self_reported_rank for o in obs])
        assert gp.correlation == pytest.approx(expected)

    assert result.best in result.all_results
    assert abs(result.best.correlation) == pytest.approx(max(abs(r.correlation) for r in result.all_results))


def test_spearman_fit_requires_at_least_two_observations():
    p = person()
    obs = [
        WeekObservation(
            person=p,
            meetings=[meeting("m1", dt(0, 9, 0), 30)],
            week_start=WEEK_START,
            self_reported_rank=1,
        )
    ]
    with pytest.raises(ValueError):
        spearman_fit(obs, ParamGrid(reentry_costs=[20], fatigue_rates=[0.4], fatigue_thresholds=[90]))

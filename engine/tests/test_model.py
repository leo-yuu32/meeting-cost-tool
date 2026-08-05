from datetime import date, datetime, time

import pytest

from meeting_cost.model import (
    compute_gaps,
    compute_runs,
    day_penalty,
    fatigue,
    gap_yield,
    usable_focus_time,
)
from meeting_cost.types import Interval, Meeting, Person

DAY = date(2026, 1, 5)  # a Monday


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(DAY, time(hour, minute))


def window() -> Interval:
    return Interval(dt(9), dt(17))


def test_gap_yield():
    assert gap_yield(60, reentry_cost=20) == 40
    assert gap_yield(10, reentry_cost=20) == 0  # floored at zero
    assert gap_yield(20, reentry_cost=20) == 0


def test_compute_gaps_no_meetings_is_whole_window():
    gaps = compute_gaps(window(), [])
    assert gaps == [window()]


def test_compute_gaps_single_meeting_splits_window():
    meeting = Interval(dt(10), dt(11))
    gaps = compute_gaps(window(), [meeting])
    assert gaps == [Interval(dt(9), dt(10)), Interval(dt(11), dt(17))]


def test_compute_runs_merges_overlapping_and_abutting():
    # overlapping
    runs = compute_runs([Interval(dt(10), dt(11)), Interval(dt(10, 30), dt(11, 30))])
    assert runs == [Interval(dt(10), dt(11, 30))]
    # abutting (touching endpoints) also merges into one run
    runs = compute_runs([Interval(dt(10), dt(10, 30)), Interval(dt(10, 30), dt(11, 30))])
    assert runs == [Interval(dt(10), dt(11, 30))]
    # a real gap keeps them separate
    runs = compute_runs([Interval(dt(10), dt(10, 30)), Interval(dt(11), dt(11, 30))])
    assert runs == [Interval(dt(10), dt(10, 30)), Interval(dt(11), dt(11, 30))]


def test_compute_gaps_clips_meetings_partially_outside_window():
    # starts before 09:00, ends inside the window
    meeting = Interval(dt(8), dt(9, 30))
    gaps = compute_gaps(window(), [meeting])
    assert gaps == [Interval(dt(9, 30), dt(17))]


def test_fatigue_zero_below_threshold():
    runs = [Interval(dt(10), dt(11, 30))]  # 90 min, exactly at threshold
    assert fatigue(runs, fatigue_threshold=90, fatigue_rate=0.4) == 0


def test_fatigue_above_threshold():
    runs = [Interval(dt(10), dt(12, 15))]  # 135 min
    assert fatigue(runs, fatigue_threshold=90, fatigue_rate=0.4) == pytest.approx(18.0)


def test_usable_focus_time_empty_day():
    assert usable_focus_time(window(), [], reentry_cost=20, fatigue_rate=0.4, fatigue_threshold=90) == 460


def _person() -> Person:
    return Person(
        id="p1",
        window_by_weekday={0: (time(9), time(17))},
        reentry_cost=20,
        fatigue_rate=0.4,
        fatigue_threshold=90,
    )


def _meeting(mid: str, start_h: int, start_m: int, end_h: int, end_m: int) -> Meeting:
    return Meeting(
        id=mid,
        start=dt(start_h, start_m),
        end=dt(end_h, end_m),
        attendee_ids=("p1",),
    )


def test_day_penalty_worked_example():
    person = _person()

    empty = day_penalty(person, [], DAY)
    assert empty.usable_focus_minutes == 460
    assert empty.penalty_minutes == 0

    two_meetings = [
        _meeting("m1", 10, 0, 10, 30),
        _meeting("m2", 10, 30, 11, 30),
    ]
    result_two = day_penalty(person, two_meetings, DAY)
    assert result_two.fatigue_minutes == 0
    assert result_two.usable_focus_minutes == pytest.approx(350)
    assert result_two.penalty_minutes == pytest.approx(110)

    three_meetings = two_meetings + [_meeting("m3", 11, 30, 12, 15)]
    result_three = day_penalty(person, three_meetings, DAY)
    assert result_three.fatigue_minutes == pytest.approx(18)
    assert result_three.usable_focus_minutes == pytest.approx(287)
    assert result_three.penalty_minutes == pytest.approx(173)

    marginal_third_meeting = result_three.penalty_minutes - result_two.penalty_minutes
    assert marginal_third_meeting == pytest.approx(63)


def test_day_penalty_non_working_day_is_zero():
    person = _person()  # only Monday (0) has a window
    tuesday = date(2026, 1, 6)
    result = day_penalty(person, [], tuesday)
    assert result.is_working_day is False
    assert result.penalty_minutes == 0


def test_day_penalty_filters_by_attendee_and_date():
    person = _person()
    other_persons_meeting = Meeting(
        id="m1", start=dt(10), end=dt(11), attendee_ids=("someone-else",)
    )
    result = day_penalty(person, [other_persons_meeting], DAY)
    assert result.penalty_minutes == 0

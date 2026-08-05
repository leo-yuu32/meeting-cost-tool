from datetime import date, datetime, time, timedelta

import pytest

from meeting_cost.marginal import marginal_cost, marginal_cost_for_person
from meeting_cost.types import Meeting, Person

DAY = date(2026, 1, 5)
C = 20.0


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(DAY, time(hour, minute))


def person() -> Person:
    return Person(
        id="p1",
        window_by_weekday={0: (time(9), time(17))},
        reentry_cost=C,
        fatigue_rate=0.4,
        fatigue_threshold=90,
    )


def meeting(mid: str, start: datetime, minutes: int, attendees=("p1",)) -> Meeting:
    return Meeting(id=mid, start=start, end=start + timedelta(minutes=minutes), attendee_ids=attendees)


# Bounding meetings at 09:00-09:30 and 16:30-17:00 leave a single isolated
# gap 09:30-16:30 (g=420 min). All runs involved stay well under the 90-min
# fatigue threshold, so fatigue is provably zero throughout and the
# single-gap closed form applies exactly.
def _bounded_existing():
    return [
        meeting("bound-left", dt(9, 0), 30),
        meeting("bound-right", dt(16, 30), 30),
    ]


@pytest.mark.parametrize(
    "start_offset_min,duration_min,expected_cost,label",
    [
        (40, 30, 30 + C, "a>=c, b>=c -> D+c"),  # a=40, b=350
        (0, 30, 30 + 0, "a<c, b>=c -> D+a"),  # a=0 (touches left), b=390
        (380, 30, 30 + 10, "a>=c, b<c -> D+b"),  # a=380, b=10
    ],
)
def test_single_gap_closed_form_rows_1_to_3(start_offset_min, duration_min, expected_cost, label):
    existing = _bounded_existing()
    candidate_start = dt(9, 30) + timedelta(minutes=start_offset_min)
    candidate = meeting("candidate", candidate_start, duration_min)

    result = marginal_cost_for_person(person(), existing, candidate, DAY)
    assert result.cost_minutes == pytest.approx(expected_cost), label


def test_single_gap_closed_form_row_4_both_fragments_below_c():
    # A small isolated 25-minute gap (g), all runs well under the fatigue
    # threshold, so g - c is the closed-form cost when both fragments < c.
    existing = [
        meeting("left", dt(10, 0), 60),  # 10:00-11:00
        meeting("right", dt(11, 25), 50),  # 11:25-12:15, gap = 11:00-11:25 (25 min)
    ]
    candidate = meeting("candidate", dt(11, 10), 5)  # a=10, b=10

    result = marginal_cost_for_person(person(), existing, candidate, DAY)
    assert result.cost_minutes == pytest.approx(25 - C)


def test_marginal_cost_sums_across_attendees_and_returns_day_state():
    alice = person()
    bob = Person(
        id="bob",
        window_by_weekday={0: (time(9), time(17))},
        reentry_cost=C,
        fatigue_rate=0.4,
        fatigue_threshold=90,
    )
    candidate = meeting("m1", dt(10, 0), 30, attendees=("p1", "bob"))
    result = marginal_cost([alice, bob], {}, candidate)

    assert len(result.per_attendee) == 2
    assert result.total_cost_minutes == pytest.approx(sum(a.cost_minutes for a in result.per_attendee))
    for attendee_cost in result.per_attendee:
        assert attendee_cost.day_state.is_working_day is True
        assert attendee_cost.longest_remaining_block_minutes > 0


def test_marginal_cost_ignores_non_attendees():
    alice = person()
    not_invited = Person(id="ghost", window_by_weekday={0: (time(9), time(17))})
    candidate = meeting("m1", dt(10, 0), 30, attendees=("p1",))
    result = marginal_cost([alice, not_invited], {}, candidate)
    assert [a.person_id for a in result.per_attendee] == ["p1"]

from datetime import date, datetime, time, timedelta

import pytest

from meeting_cost.slots import attendee_sensitivity, duration_sensitivity, rank_slots
from meeting_cost.types import Interval, Meeting, Person

DAY = date(2026, 1, 5)
C = 20.0


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(DAY, time(hour, minute))


def person(pid="p1", reentry_cost=C, fatigue_rate=0.4, fatigue_threshold=90) -> Person:
    return Person(
        id=pid,
        window_by_weekday={0: (time(9), time(17))},
        reentry_cost=reentry_cost,
        fatigue_rate=fatigue_rate,
        fatigue_threshold=fatigue_threshold,
    )


def meeting(mid, start, minutes, attendees) -> Meeting:
    return Meeting(id=mid, start=start, end=start + timedelta(minutes=minutes), attendee_ids=attendees)


def test_rank_slots_ties_interior_and_ranks_edges_cheaper():
    # Same isolated 420-min gap (09:30-16:30) as the closed-form marginal
    # cost tests: bounding meetings at the edges, no fatigue involved.
    p = person()
    existing = {
        "p1": [
            meeting("bound-left", dt(9, 0), 30, ("p1",)),
            meeting("bound-right", dt(16, 30), 30, ("p1",)),
        ]
    }
    gap = Interval(dt(9, 30), dt(16, 30))
    results = rank_slots(
        people=[p],
        existing_by_person=existing,
        duration_minutes=30,
        attendee_ids=["p1"],
        candidate_window=gap,
        grid_minutes=15,
    )

    by_start = {r.start: r for r in results}
    edge = by_start[dt(9, 30)]  # a=0 -> cost = D + a = 30
    interior_1 = by_start[dt(10, 0)]  # a=30 >= c, b >= c -> cost = D + c = 50
    interior_2 = by_start[dt(12, 0)]  # also interior -> cost = D + c = 50

    assert edge.total_cost_minutes == pytest.approx(30)
    assert interior_1.total_cost_minutes == pytest.approx(50)
    assert interior_2.total_cost_minutes == pytest.approx(50)

    # Interior slots are genuinely tied: same cost, same rank.
    assert interior_1.rank == interior_2.rank
    # The cheaper edge slot ranks strictly better (lower rank number).
    assert edge.rank < interior_1.rank
    # Ranking is ascending by cost.
    assert [r.total_cost_minutes for r in results] == sorted(r.total_cost_minutes for r in results)


def test_duration_sensitivity_cost_increases_with_duration_in_interior():
    p = person()
    existing = {"p1": []}
    results = duration_sensitivity(
        people=[p],
        existing_by_person=existing,
        slot_start=dt(11, 0),
        attendee_ids=["p1"],
        durations=[15, 30, 60],
    )
    costs = [r.total_cost_minutes for r in results]
    assert costs == sorted(costs)
    assert costs[0] < costs[-1]


def test_attendee_sensitivity_ranks_most_expensive_attendee_first():
    # p1 has a small 30-min gap (10:00-10:30) either side of the slot; both
    # fragments (a=5, b=10) fall below c=20, so the closed form gives
    # g - c = 30 - 20 = 10.
    # p2 has a wide-open day, so the slot lands in a gap interior:
    # D + c = 15 + 20 = 35. p2 is the more expensive attendee to include.
    p1 = person("p1")
    p2 = person("p2")
    existing = {
        "p1": [
            meeting("p1-left", dt(9, 0), 60, ("p1",)),  # 09:00-10:00
            meeting("p1-right", dt(10, 30), 60, ("p1",)),  # 10:30-11:30, gap 10:00-10:30 (30 min)
        ],
        "p2": [],
    }
    results = attendee_sensitivity(
        people=[p1, p2],
        existing_by_person=existing,
        slot_start=dt(10, 5),
        duration_minutes=15,
        attendee_ids=["p1", "p2"],
    )
    assert [r.person_id for r in results] == ["p2", "p1"]
    assert results[0].rank == 1
    assert results[0].cost_minutes == pytest.approx(35)
    assert results[1].cost_minutes == pytest.approx(10)

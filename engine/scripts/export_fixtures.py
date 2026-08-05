"""Export JSON fixtures for the front end mock-up (CLAUDE.md section 6, "Synthetic calendar generator" / "React mock-up").

Run from engine/: python scripts/export_fixtures.py
Writes into engine/fixtures/, which the front end copies/imports directly -
there is no live server (CLAUDE.md: "mock-up of the scheduling experience,
not an integration").
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from meeting_cost.api import get_attribution, get_day_penalty, get_sensitivities, get_slot_ranking
from meeting_cost.synthetic import generate_week
from meeting_cost.types import Interval, Meeting, Person

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

DAY = date(2026, 1, 5)  # a Monday


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(DAY, time(hour, minute))


def export_worked_example() -> None:
    """The hand-verified scenario from CLAUDE.md's closed form / model.py's tests:
    one person, three meetings booked in sequence, P = 0 -> 110 -> 173."""
    person = Person(
        id="worked-example-person",
        window_by_weekday={0: (time(9), time(17))},
        reentry_cost=20,
        fatigue_rate=0.4,
        fatigue_threshold=90,
    )
    m1 = Meeting(id="m1", start=_dt(10, 0), end=_dt(10, 30), attendee_ids=("worked-example-person",))
    m2 = Meeting(id="m2", start=_dt(10, 30), end=_dt(11, 30), attendee_ids=("worked-example-person",))
    m3 = Meeting(id="m3", start=_dt(11, 30), end=_dt(12, 15), attendee_ids=("worked-example-person",))

    empty_state = get_day_penalty(person, [], DAY)
    two_meeting_state = get_day_penalty(person, [m1, m2], DAY)
    three_meeting_state = get_day_penalty(person, [m1, m2, m3], DAY)

    fixture = {
        "description": (
            "Hand-verified reference scenario: penalty after 0, 2 and 3 "
            "back-to-back meetings for one person on one day. "
            "P: 0 -> 110 -> 173; marginal cost of the third meeting: 63."
        ),
        "states": {
            "empty": empty_state,
            "two_meetings": two_meeting_state,
            "three_meetings": three_meeting_state,
        },
        "marginal_cost_of_third_meeting": (
            three_meeting_state["penalty_minutes"] - two_meeting_state["penalty_minutes"]
        ),
    }
    _write("worked_example.json", fixture)


def export_booking_scenario() -> None:
    """A synthetic multi-person week, used to drive the organiser booking mock-up:
    slot ranking, sensitivities and attribution for a specific meeting query."""
    person_ids = ["alice", "bob", "carol", "dave"]
    week_start = DAY  # Monday
    people, meetings = generate_week(
        person_ids,
        week_start,
        seed=2026,
        meetings_per_day=(1, 3),
        meeting_length_minutes=(15, 60),
    )
    existing_by_person = {p.id: [m for m in meetings if p.id in m.attendee_ids] for p in people}

    organiser_attendees = ["alice", "bob", "carol"]
    candidate_window = Interval(_dt(9, 0), _dt(17, 0))
    slot_ranking = get_slot_ranking(
        people=people,
        existing_by_person=existing_by_person,
        duration_minutes=30,
        attendee_ids=organiser_attendees,
        candidate_window=candidate_window,
        grid_minutes=15,
    )

    best_slot = min(slot_ranking["slots"], key=lambda s: s["total_cost_minutes"])
    sensitivities = get_sensitivities(
        people=people,
        existing_by_person=existing_by_person,
        slot_start=datetime.fromisoformat(best_slot["start"]),
        attendee_ids=organiser_attendees,
        duration_minutes=30,
        durations=[15, 30, 45, 60, 90],
    )

    alice = next(p for p in people if p.id == "alice")
    alice_meetings = existing_by_person["alice"]
    attribution = get_attribution(alice, alice_meetings, DAY, seed=2026)

    fixture = {
        "description": (
            "Synthetic week for 4 people (seed=2026), used to demo the "
            "organiser booking view: ranked slots for a 30-min meeting "
            "among alice/bob/carol, sensitivities for the cheapest slot, "
            "and alice's Shapley attribution for the query day."
        ),
        "person_ids": person_ids,
        "week_start": week_start.isoformat(),
        "candidate_meeting": {
            "duration_minutes": 30,
            "attendee_ids": organiser_attendees,
        },
        "slot_ranking": slot_ranking,
        "best_slot_sensitivities": sensitivities,
        "attribution_example": {"person_id": "alice", "date": DAY.isoformat(), **attribution},
    }
    _write("booking_scenario.json", fixture)


def _write(filename: str, data: dict) -> None:
    FIXTURES_DIR.mkdir(exist_ok=True)
    path = FIXTURES_DIR / filename
    path.write_text(json.dumps(data, indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    export_worked_example()
    export_booking_scenario()

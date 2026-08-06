"""Per-person marginal-cost lookup table for the front end (CLAUDE.md section 2, "Marginal cost").

Cost(m) = SUM over attendees p of Cost_p(m | M_p) is additive in the
attendees, and Cost_p depends only on person p's own calendar - not on who
else is invited. That means the whole (slot, duration) x (attendee) cost
surface can be precomputed per person once, and the front end sums over
whatever attendee subset the organiser is currently trying, without the
engine ever needing to know the candidate invite list in advance. This
script does not fix an attendee list or precompute any totals; it only
computes and exports Cost_p and the resulting longest remaining usable
block, one person at a time, reusing marginal_cost_for_person from
marginal.py for the actual model logic.

Run from engine/: python scripts/export_lookup.py
Writes into web/public/scenarios/lookup.json - a static fixture, matching
CLAUDE.md's "mock-up, not an integration."
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from meeting_cost.marginal import marginal_cost_for_person
from meeting_cost.synthetic import generate_week
from meeting_cost.types import Meeting

DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "web" / "public" / "scenarios" / "lookup.json"
)

DEFAULT_SEED = 2026
DEFAULT_PERSON_IDS = ["alice", "bob", "carol", "dave"]
DEFAULT_WEEK_START = date(2026, 1, 5)  # a Monday
DEFAULT_WORKING_WINDOW = (time(9), time(17))
DEFAULT_GRID_MINUTES = 15
DEFAULT_DURATIONS: tuple[int, ...] = (30, 45, 60)
DEFAULT_MEETINGS_PER_DAY = (1, 3)
DEFAULT_MEETING_LENGTH_MINUTES = (15, 60)


def _minutes_from_midnight(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def build_lookup(
    seed: int = DEFAULT_SEED,
    person_ids: list[str] | None = None,
    week_start: date = DEFAULT_WEEK_START,
    working_window: tuple[time, time] = DEFAULT_WORKING_WINDOW,
    grid_minutes: int = DEFAULT_GRID_MINUTES,
    durations: tuple[int, ...] = DEFAULT_DURATIONS,
    meetings_per_day: tuple[int, int] = DEFAULT_MEETINGS_PER_DAY,
    meeting_length_minutes: tuple[int, int] = DEFAULT_MEETING_LENGTH_MINUTES,
) -> dict:
    """Build the lookup table as a plain, JSON-serializable dict.

    `week_start` doubles as the single query day (assumed to be the Monday
    generate_week treats it as). Slots are grid points where every duration
    in `durations` fits before the window closes, so (person, slot,
    duration) is always a valid key regardless of which duration is picked.
    """
    if person_ids is None:
        person_ids = list(DEFAULT_PERSON_IDS)

    people, meetings = generate_week(
        person_ids,
        week_start,
        seed=seed,
        meetings_per_day=meetings_per_day,
        meeting_length_minutes=meeting_length_minutes,
        working_window=working_window,
    )
    existing_by_person = {p.id: [m for m in meetings if p.id in m.attendee_ids] for p in people}

    day = week_start
    window_start = datetime.combine(day, working_window[0])
    window_end = datetime.combine(day, working_window[1])
    max_duration = max(durations)

    slot_starts: list[datetime] = []
    cursor = window_start
    step = timedelta(minutes=grid_minutes)
    while cursor + timedelta(minutes=max_duration) <= window_end:
        slot_starts.append(cursor)
        cursor += step

    costs: dict[str, dict[str, dict[str, float]]] = {}
    longest_block: dict[str, dict[str, dict[str, float]]] = {}

    for person in people:
        existing = existing_by_person[person.id]
        costs[person.id] = {}
        longest_block[person.id] = {}
        for slot_start in slot_starts:
            slot_key = str(_minutes_from_midnight(slot_start))
            costs[person.id][slot_key] = {}
            longest_block[person.id][slot_key] = {}
            for duration in durations:
                candidate = Meeting(
                    id=f"lookup-{person.id}-{slot_key}-{duration}",
                    start=slot_start,
                    end=slot_start + timedelta(minutes=duration),
                    attendee_ids=(person.id,),
                )
                result = marginal_cost_for_person(person, existing, candidate, day)
                duration_key = str(duration)
                costs[person.id][slot_key][duration_key] = result.cost_minutes
                longest_block[person.id][slot_key][duration_key] = result.longest_remaining_block_minutes

    return {
        "seed": seed,
        "day": day.isoformat(),
        "people": [{"id": p.id, "display_name": p.id.capitalize()} for p in people],
        "slots": [_minutes_from_midnight(s) for s in slot_starts],
        "durations": list(durations),
        "costs": costs,
        "longest_block": longest_block,
    }


def write_lookup(output_path: Path = DEFAULT_OUTPUT_PATH, **kwargs) -> Path:
    data = build_lookup(**kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2))
    return output_path


if __name__ == "__main__":
    written = write_lookup()
    print(f"wrote {written}")

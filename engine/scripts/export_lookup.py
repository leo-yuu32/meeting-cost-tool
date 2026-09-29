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

A low Cost_p does not imply a slot is bookable - a candidate that overlaps
an existing meeting can merge into it and come out cheap (or even free),
which is a correct cost but an infeasible slot. Feasibility is a separate,
literal overlap check against the person's own calendar (see _is_busy),
exported as its own "busy" table rather than inferred from cost.

"meetings" carries each person's existing meeting intervals for the query
day (id, start/end in minutes from midnight, the same unit "slots" uses)
so the front end can draw them without re-deriving anything from cost or
busy - this is the calendar itself, not a derived value.

"window" is the working window W the model actually priced against, read
from the generated Person objects rather than hardcoded, so a front-end
time axis bounded on it never shows time the model didn't charge for.
If people have differing windows for the day, this is their union - see
_window_union_minutes and the CLAUDE.md section 7 note it points at.

"attribution" and "day_penalty" are retrospective, not prospective - per
CLAUDE.md's rule (marginal for prospective slot ranking, Shapley for
retrospective ranking), these are Shapley-attributed against each
person's actual booked meetings for the day, reusing shapley_values from
shapley.py directly. Nothing here recomputes phi_i; this module only
shapes shapley.py's and model.py's own output into the export.

Run from engine/: python scripts/export_lookup.py
Writes into web/public/scenarios/lookup.json - a static fixture, matching
CLAUDE.md's "mock-up, not an integration."
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from meeting_cost.marginal import marginal_cost_for_person
from meeting_cost.model import day_penalty
from meeting_cost.shapley import shapley_values
from meeting_cost.synthetic import generate_week
from meeting_cost.types import Meeting, Person

DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "web" / "public" / "scenarios" / "lookup.json"
)

DEFAULT_SEED = 2026
DEFAULT_PERSON_IDS = ["alice", "bob", "carol", "dave"]
DEFAULT_WEEK_START = date(2026, 1, 5)  # a Monday
DEFAULT_WORKING_WINDOW = (time(9), time(17))
DEFAULT_GRID_MINUTES = 30
DEFAULT_DURATIONS: tuple[int, ...] = (30, 45, 60)
# Joint bookability (every attendee free) decays multiplicatively with
# attendee count, so it is far more sensitive to per-person meeting volume
# than the per-person busy fraction alone suggests. (1, 3) owned meetings
# of (15, 60) minutes each left only 24% of 60-min candidate slots
# bookable across 4 people (measured via report_scenario below) -
# unusable for a scheduler view. (0, 2) meetings of (15, 30) minutes
# brought that to ~52-60% at seed=2026 (the 15 lower bound was moot once
# synthetic.py started snapping durations to {30, 60, 90}; only 30 was
# ever eligible in that range). (1, 3) meetings of (30, 60) minutes -
# bumped again for a few more meetings per person, with 60 now eligible
# alongside 30 and 90 still excluded - is the current setting; see
# report_scenario's output for the resulting joint bookability and cost
# spread, since this pushes bookability down from the previous ~60%.
# other_attendee_probability (synthetic.py) was checked separately and is
# not the lever: holding it at 0.0 with the original (1,3)/(15,60) volume
# still left joint bookability at 24%, because one person's own meetings
# were already enough to saturate it.
DEFAULT_MEETINGS_PER_DAY = (1, 3)
DEFAULT_MEETING_LENGTH_MINUTES = (30, 60)
# synthetic.py's own default (3, 2, 1) makes 60 roughly 2-in-5 once both
# 30 and 60 are eligible - too many 60-min meetings for this scenario's
# attendee count. (5, 1, 1) - only the first two entries matter while 90
# stays excluded by DEFAULT_MEETING_LENGTH_MINUTES - makes it 1-in-6
# instead. See report_scenario's output for the resulting counts.
DEFAULT_DURATION_WEIGHTS: tuple[float, ...] = (5.0, 1.0, 1.0)


def _minutes_from_midnight(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def _window_union_minutes(people: list[Person], weekday: int) -> tuple[int, int]:
    """Union of every person's working window on `weekday`, in minutes from midnight.

    People without a window that day (non-working) don't contribute to the
    union - matching how day_penalty treats an absent weekday as P=0, not
    as a zero-width window. CLAUDE.md section 7 does not define how to
    reconcile differing per-person windows on a shared view; union is a
    display convenience here, not a modelled decision.
    """
    starts = []
    ends = []
    for p in people:
        w = p.window_by_weekday.get(weekday)
        if w is None:
            continue
        starts.append(w[0].hour * 60 + w[0].minute)
        ends.append(w[1].hour * 60 + w[1].minute)
    if not starts:
        raise ValueError(f"no person has a working window on weekday {weekday}")
    return min(starts), max(ends)


def _is_busy(existing: list[Meeting], slot_start: datetime, slot_end: datetime) -> bool:
    """True if any of the person's existing meetings overlaps [slot_start, slot_end).

    Computed directly from the calendar, independent of cost: a slot can be
    cheap (e.g. the candidate abuts or is absorbed into an existing run) and
    still be unbookable because it actually overlaps something already
    there. Touching (zero-overlap) is not busy - only real time overlap is.
    """
    return any(m.start < slot_end and m.end > slot_start for m in existing)


def build_lookup(
    seed: int = DEFAULT_SEED,
    person_ids: list[str] | None = None,
    week_start: date = DEFAULT_WEEK_START,
    working_window: tuple[time, time] = DEFAULT_WORKING_WINDOW,
    grid_minutes: int = DEFAULT_GRID_MINUTES,
    durations: tuple[int, ...] = DEFAULT_DURATIONS,
    meetings_per_day: tuple[int, int] = DEFAULT_MEETINGS_PER_DAY,
    meeting_length_minutes: tuple[int, int] = DEFAULT_MEETING_LENGTH_MINUTES,
    duration_weights: tuple[float, ...] = DEFAULT_DURATION_WEIGHTS,
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
        duration_weights=duration_weights,
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
    busy: dict[str, dict[str, dict[str, bool]]] = {}

    for person in people:
        existing = existing_by_person[person.id]
        costs[person.id] = {}
        longest_block[person.id] = {}
        busy[person.id] = {}
        for slot_start in slot_starts:
            slot_key = str(_minutes_from_midnight(slot_start))
            costs[person.id][slot_key] = {}
            longest_block[person.id][slot_key] = {}
            busy[person.id][slot_key] = {}
            for duration in durations:
                slot_end = slot_start + timedelta(minutes=duration)
                candidate = Meeting(
                    id=f"lookup-{person.id}-{slot_key}-{duration}",
                    start=slot_start,
                    end=slot_end,
                    attendee_ids=(person.id,),
                )
                result = marginal_cost_for_person(person, existing, candidate, day)
                duration_key = str(duration)
                costs[person.id][slot_key][duration_key] = result.cost_minutes
                longest_block[person.id][slot_key][duration_key] = result.longest_remaining_block_minutes
                busy[person.id][slot_key][duration_key] = _is_busy(existing, slot_start, slot_end)

    meetings_export: dict[str, list[dict]] = {}
    for person in people:
        day_meetings = sorted(
            (m for m in existing_by_person[person.id] if m.start.date() == day),
            key=lambda m: m.start,
        )
        meetings_export[person.id] = [
            {
                "id": m.id,
                "start": _minutes_from_midnight(m.start),
                "end": _minutes_from_midnight(m.end),
            }
            for m in day_meetings
        ]

    window_start_min, window_end_min = _window_union_minutes(people, day.weekday())

    attribution: dict[str, dict[str, float]] = {}
    day_penalty_export: dict[str, float] = {}
    retention: dict[str, float] = {}
    clear_day_yield: dict[str, float] = {}
    for person in people:
        existing = existing_by_person[person.id]
        estimates = shapley_values(person, existing, day, seed=seed)
        attribution[person.id] = {mid: est.value for mid, est in estimates.items()}
        result = day_penalty(person, existing, day)
        day_penalty_export[person.id] = result.penalty_minutes
        clear_day_yield[person.id] = result.empty_day_usable_minutes
        # retention = U(M) / U(empty) = 1 - P(M) / U(empty), derived from the
        # same day_penalty result rather than recomputing U(M) separately
        # (one source of truth for both figures).
        retention[person.id] = (
            1.0 - result.penalty_minutes / result.empty_day_usable_minutes
            if result.empty_day_usable_minutes
            else 0.0
        )

    return {
        "seed": seed,
        "day": day.isoformat(),
        "people": [{"id": p.id, "display_name": p.id.capitalize()} for p in people],
        "slots": [_minutes_from_midnight(s) for s in slot_starts],
        "durations": list(durations),
        "costs": costs,
        "longest_block": longest_block,
        "busy": busy,
        "meetings": meetings_export,
        "window": {"start": window_start_min, "end": window_end_min},
        "attribution": attribution,
        "day_penalty": day_penalty_export,
        "retention": retention,
        "clear_day_yield": clear_day_yield,
    }


def write_lookup(output_path: Path = DEFAULT_OUTPUT_PATH, **kwargs) -> Path:
    data = build_lookup(**kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2))
    return output_path


def report_scenario(data: dict) -> None:
    """Print per-person busy fraction, joint bookable fraction, and cost
    spread across bookable slots, for each duration in the scenario.

    A tuning tool, not a test - run by hand (or via this module's __main__)
    against candidate generate_week/build_lookup parameters instead of
    guessing whether a change made joint availability more realistic.
    Joint bookable fraction is what matters for the scheduler view: it
    decays multiplicatively with attendee count, so it can be far lower
    than any individual person's own busy fraction would suggest.
    """
    people = [p["id"] for p in data["people"]]
    slots = data["slots"]
    n_slots = len(slots)

    print(f"seed={data['seed']} day={data['day']} people={people} slots={n_slots}")

    for duration in data["durations"]:
        dkey = str(duration)
        print(f"\n-- duration {duration} min --")

        for person in people:
            busy_count = sum(1 for s in slots if data["busy"][person][str(s)][dkey])
            print(f"  {person}: busy fraction = {busy_count / n_slots:.2f}")

        bookable_slots = [
            s for s in slots if not any(data["busy"][p][str(s)][dkey] for p in people)
        ]
        joint_fraction = len(bookable_slots) / n_slots
        print(f"  joint bookable fraction (all {len(people)}): {joint_fraction:.2f}")

        if bookable_slots:
            costs = sorted(
                sum(data["costs"][p][str(s)][dkey] for p in people) for s in bookable_slots
            )
            n = len(costs)
            median = costs[n // 2] if n % 2 else (costs[n // 2 - 1] + costs[n // 2]) / 2
            print(f"  cost across bookable slots: min={costs[0]:.0f} median={median:.0f} max={costs[-1]:.0f}")
        else:
            print("  no slot is bookable for all attendees at this duration")


if __name__ == "__main__":
    data = build_lookup()
    report_scenario(data)
    output_path = DEFAULT_OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2))
    print(f"\nwrote {output_path}")

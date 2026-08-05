"""JSON contract between the engine and the front end (CLAUDE.md section 4, "Engine inputs and outputs").

This is the only module that shapes engine results into plain, JSON-serializable
dicts. Everything upstream is pure Python model logic operating on the
dataclasses in types.py/model.py/marginal.py/slots.py/shapley.py; everything
downstream (fixtures, the React app) only ever sees what these functions
return.

Per-attendee costs are for the organiser at booking time only (CLAUDE.md
section 4) - callers must not forward get_slot_ranking's or
get_sensitivities' per-attendee breakdowns to an attendee-facing surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date as date_
from datetime import datetime

from meeting_cost.marginal import AttendeeMarginalCost, marginal_cost
from meeting_cost.model import DayPenaltyResult, day_penalty
from meeting_cost.shapley import (
    DEFAULT_EXACT_THRESHOLD,
    DEFAULT_MONTE_CARLO_SAMPLES,
    series_rollup,
    shapley_values,
)
from meeting_cost.slots import (
    attendee_sensitivity,
    duration_sensitivity,
    rank_slots,
)
from meeting_cost.types import Interval, Meeting, Person


def _interval_json(iv: Interval) -> dict:
    return {"start": iv.start.isoformat(), "end": iv.end.isoformat(), "minutes": iv.minutes}


def _day_penalty_json(result: DayPenaltyResult) -> dict:
    return {
        "person_id": result.person_id,
        "date": result.date.isoformat(),
        "is_working_day": result.is_working_day,
        "window_minutes": result.window_minutes,
        "penalty_minutes": result.penalty_minutes,
        "usable_focus_minutes": result.usable_focus_minutes,
        "fatigue_minutes": result.fatigue_minutes,
        "gaps": [
            {"interval": _interval_json(g.interval), "yield_minutes": g.yield_minutes} for g in result.gaps
        ],
        "runs": [
            {"interval": _interval_json(r.interval), "fatigue_minutes": r.fatigue_minutes} for r in result.runs
        ],
    }


def _attendee_marginal_json(a: AttendeeMarginalCost) -> dict:
    return {
        "person_id": a.person_id,
        "cost_minutes": a.cost_minutes,
        "longest_remaining_block_minutes": a.longest_remaining_block_minutes,
        "day_state": _day_penalty_json(a.day_state),
    }


def get_day_penalty(
    person: Person,
    meetings: Sequence[Meeting],
    date: date_,
    reentry_cost: float | None = None,
    fatigue_rate: float | None = None,
    fatigue_threshold: float | None = None,
) -> dict:
    result = day_penalty(person, meetings, date, reentry_cost, fatigue_rate, fatigue_threshold)
    return _day_penalty_json(result)


def get_slot_ranking(
    people: Sequence[Person],
    existing_by_person: dict[str, Sequence[Meeting]],
    duration_minutes: int,
    attendee_ids: Sequence[str],
    candidate_window: Interval,
    grid_minutes: int = 15,
) -> dict:
    slots = rank_slots(people, existing_by_person, duration_minutes, attendee_ids, candidate_window, grid_minutes)
    return {
        "duration_minutes": duration_minutes,
        "attendee_ids": list(attendee_ids),
        "grid_minutes": grid_minutes,
        "slots": [
            {
                "start": s.start.isoformat(),
                "end": s.end.isoformat(),
                "total_cost_minutes": s.total_cost_minutes,
                "rank": s.rank,
                "per_attendee": [_attendee_marginal_json(a) for a in s.per_attendee],
            }
            for s in slots
        ],
    }


def get_sensitivities(
    people: Sequence[Person],
    existing_by_person: dict[str, Sequence[Meeting]],
    slot_start: datetime,
    attendee_ids: Sequence[str],
    duration_minutes: int,
    durations: Sequence[int],
) -> dict:
    by_duration = duration_sensitivity(people, existing_by_person, slot_start, attendee_ids, durations)
    by_attendee = attendee_sensitivity(people, existing_by_person, slot_start, duration_minutes, attendee_ids)
    return {
        "slot_start": slot_start.isoformat(),
        "duration_sensitivity": [
            {
                "duration_minutes": d.duration_minutes,
                "total_cost_minutes": d.total_cost_minutes,
                "per_attendee": [_attendee_marginal_json(a) for a in d.per_attendee],
            }
            for d in by_duration
        ],
        "attendee_sensitivity": [
            {"person_id": a.person_id, "cost_minutes": a.cost_minutes, "rank": a.rank} for a in by_attendee
        ],
    }


def get_attribution(
    person: Person,
    meetings: Sequence[Meeting],
    date: date_,
    seed: int,
    exact_threshold: int = DEFAULT_EXACT_THRESHOLD,
    n_samples: int = DEFAULT_MONTE_CARLO_SAMPLES,
) -> dict:
    values = shapley_values(person, meetings, date, seed=seed, exact_threshold=exact_threshold, n_samples=n_samples)
    day_meetings = [m for m in meetings if m.start.date() == date and person.id in m.attendee_ids]
    series_id_by_meeting = {m.id: m.series_id for m in day_meetings}
    rollup = series_rollup({mid: est.value for mid, est in values.items()}, series_id_by_meeting)
    return {
        "person_id": person.id,
        "date": date.isoformat(),
        "shapley": {
            mid: {"value": est.value, "standard_error": est.standard_error} for mid, est in values.items()
        },
        "series_rollup": rollup,
    }

"""Prospective slot ranking and sensitivities (CLAUDE.md section 4, "Slot ranking" / "Sensitivities").

Rule from CLAUDE.md: marginal cost drives prospective slot ranking; Shapley
(see shapley.py) is for retrospective ranking only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from meeting_cost.marginal import AttendeeMarginalCost, marginal_cost
from meeting_cost.types import Interval, Meeting, Person

# Costs are derived from whole-minute interval arithmetic; rounding avoids
# spurious tie-breaks from float noise when grouping equal-cost slots.
_TIE_ROUND_DECIMALS = 6


@dataclass(frozen=True)
class SlotResult:
    start: datetime
    end: datetime
    total_cost_minutes: float
    rank: int  # dense rank ascending by cost; tied costs share a rank
    per_attendee: list[AttendeeMarginalCost] = field(default_factory=list)


def rank_slots(
    people: Sequence[Person],
    existing_by_person: dict[str, Sequence[Meeting]],
    duration_minutes: int,
    attendee_ids: Sequence[str],
    candidate_window: Interval,
    grid_minutes: int = 15,
) -> list[SlotResult]:
    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=grid_minutes)

    candidates = []
    start = candidate_window.start
    idx = 0
    while start + duration <= candidate_window.end:
        candidate = Meeting(
            id=f"slot-candidate-{idx}",
            start=start,
            end=start + duration,
            attendee_ids=tuple(attendee_ids),
        )
        mc = marginal_cost(people, existing_by_person, candidate)
        candidates.append((start, start + duration, mc))
        start += step
        idx += 1

    ordered = sorted(candidates, key=lambda c: c[2].total_cost_minutes)
    results: list[SlotResult] = []
    rank = 0
    prev_cost: float | None = None
    for slot_start, slot_end, mc in ordered:
        cost = round(mc.total_cost_minutes, _TIE_ROUND_DECIMALS)
        if prev_cost is None or cost != prev_cost:
            rank += 1
            prev_cost = cost
        results.append(
            SlotResult(
                start=slot_start,
                end=slot_end,
                total_cost_minutes=mc.total_cost_minutes,
                rank=rank,
                per_attendee=mc.per_attendee,
            )
        )
    return results


@dataclass(frozen=True)
class DurationSensitivityResult:
    duration_minutes: int
    total_cost_minutes: float
    per_attendee: list[AttendeeMarginalCost] = field(default_factory=list)


def duration_sensitivity(
    people: Sequence[Person],
    existing_by_person: dict[str, Sequence[Meeting]],
    slot_start: datetime,
    attendee_ids: Sequence[str],
    durations: Sequence[int],
) -> list[DurationSensitivityResult]:
    results = []
    for d in durations:
        candidate = Meeting(
            id=f"duration-candidate-{d}",
            start=slot_start,
            end=slot_start + timedelta(minutes=d),
            attendee_ids=tuple(attendee_ids),
        )
        mc = marginal_cost(people, existing_by_person, candidate)
        results.append(
            DurationSensitivityResult(
                duration_minutes=d, total_cost_minutes=mc.total_cost_minutes, per_attendee=mc.per_attendee
            )
        )
    return results


@dataclass(frozen=True)
class AttendeeSensitivityResult:
    person_id: str
    cost_minutes: float
    rank: int  # 1 = most expensive attendee to include


def attendee_sensitivity(
    people: Sequence[Person],
    existing_by_person: dict[str, Sequence[Meeting]],
    slot_start: datetime,
    duration_minutes: int,
    attendee_ids: Sequence[str],
) -> list[AttendeeSensitivityResult]:
    candidate = Meeting(
        id="attendee-sensitivity-candidate",
        start=slot_start,
        end=slot_start + timedelta(minutes=duration_minutes),
        attendee_ids=tuple(attendee_ids),
    )
    mc = marginal_cost(people, existing_by_person, candidate)
    ordered = sorted(mc.per_attendee, key=lambda a: a.cost_minutes, reverse=True)
    return [
        AttendeeSensitivityResult(person_id=a.person_id, cost_minutes=a.cost_minutes, rank=i + 1)
        for i, a in enumerate(ordered)
    ]

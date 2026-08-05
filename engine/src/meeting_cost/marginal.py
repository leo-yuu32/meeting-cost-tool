"""Marginal cost of booking a candidate meeting (CLAUDE.md section 2, "Marginal cost").

Marginal cost is a function of calendar state, not a property of the meeting -
it depends on what is already booked and the order booking happened in. Post-
booking day state is always returned alongside the cost so it isn't the only
signal available (an organiser who only sees marginal cost is incentivised to
book early to claim cheap slots).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date as date_

from meeting_cost.model import DayPenaltyResult, day_penalty
from meeting_cost.types import Meeting, Person


@dataclass(frozen=True)
class AttendeeMarginalCost:
    person_id: str
    cost_minutes: float  # Cost_p(m | M)
    longest_remaining_block_minutes: float
    day_state: DayPenaltyResult  # post-booking P(M + m), for explainability


@dataclass(frozen=True)
class MarginalCostResult:
    total_cost_minutes: float  # Cost(m)
    per_attendee: list[AttendeeMarginalCost] = field(default_factory=list)


def marginal_cost_for_person(
    person: Person,
    existing: Sequence[Meeting],
    candidate: Meeting,
    date: date_,
) -> AttendeeMarginalCost:
    before = day_penalty(person, existing, date)
    after = day_penalty(person, list(existing) + [candidate], date)
    longest_block = max((g.interval.minutes for g in after.gaps), default=0.0)
    return AttendeeMarginalCost(
        person_id=person.id,
        cost_minutes=after.penalty_minutes - before.penalty_minutes,
        longest_remaining_block_minutes=longest_block,
        day_state=after,
    )


def marginal_cost(
    people: Sequence[Person],
    existing_by_person: dict[str, Sequence[Meeting]],
    candidate: Meeting,
) -> MarginalCostResult:
    date = candidate.start.date()
    attendees = [p for p in people if p.id in candidate.attendee_ids]
    per_attendee = [
        marginal_cost_for_person(p, existing_by_person.get(p.id, []), candidate, date)
        for p in attendees
    ]
    total = sum(a.cost_minutes for a in per_attendee)
    return MarginalCostResult(total_cost_minutes=total, per_attendee=per_attendee)

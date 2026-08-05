"""Retrospective attribution by Shapley value (CLAUDE.md section 2, "Retrospective attribution").

Rule from CLAUDE.md: marginal cost drives prospective slot ranking (see
slots.py); Shapley value is for retrospective ranking of meetings and
recurring series only - marginal cost depends on booking order and cannot be
used to rank meetings against each other after the fact.

The players in a person-day's game are that person's meetings on that day;
the characteristic function is P (day_penalty.penalty_minutes) evaluated on
subsets of those meetings.
"""

from __future__ import annotations

import itertools
import math
import random
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date as date_

from meeting_cost.model import day_penalty
from meeting_cost.types import Meeting, Person

DEFAULT_EXACT_THRESHOLD = 12  # spec: exact is fine up to roughly n=12
DEFAULT_MONTE_CARLO_SAMPLES = 2000


def shapley_from_characteristic_function(
    players: Sequence[str], v: Callable[[frozenset[str]], float]
) -> dict[str, float]:
    """Exact Shapley values for an arbitrary characteristic function `v`.

    The combinatorial core used by shapley_exact - kept generic so the
    efficiency/symmetry/null-player axioms can be verified directly against
    textbook characteristic functions, independent of the cost model.
    """
    n = len(players)
    cache: dict[frozenset[str], float] = {}

    def v_cached(subset: frozenset[str]) -> float:
        if subset not in cache:
            cache[subset] = v(subset)
        return cache[subset]

    phi: dict[str, float] = {}
    for i in players:
        others = [p for p in players if p != i]
        total = 0.0
        for r in range(len(others) + 1):
            weight = math.factorial(r) * math.factorial(n - r - 1) / math.factorial(n)
            for subset in itertools.combinations(others, r):
                s = frozenset(subset)
                total += weight * (v_cached(s | {i}) - v_cached(s))
        phi[i] = total
    return phi


def _day_meetings(person: Person, meetings: Sequence[Meeting], date: date_) -> list[Meeting]:
    return [m for m in meetings if m.start.date() == date and person.id in m.attendee_ids]


def shapley_exact(person: Person, meetings: Sequence[Meeting], date: date_) -> dict[str, float]:
    """phi_i per meeting id, for `person`'s meetings on `date`. n * 2^(n-1) evaluations of P."""
    day_meetings = _day_meetings(person, meetings, date)
    by_id = {m.id: m for m in day_meetings}

    def v(subset: frozenset[str]) -> float:
        return day_penalty(person, [by_id[i] for i in subset], date).penalty_minutes

    return shapley_from_characteristic_function(list(by_id.keys()), v)


@dataclass(frozen=True)
class ShapleyEstimate:
    value: float
    standard_error: float


def shapley_monte_carlo(
    person: Person,
    meetings: Sequence[Meeting],
    date: date_,
    seed: int,
    n_samples: int = DEFAULT_MONTE_CARLO_SAMPLES,
) -> dict[str, ShapleyEstimate]:
    """Monte Carlo Shapley over sampled permutations, with a reported standard error.

    Deterministic given `seed` (a single random.Random instance is used).
    """
    day_meetings = _day_meetings(person, meetings, date)
    by_id = {m.id: m for m in day_meetings}
    ids = list(by_id.keys())
    if not ids:
        return {}

    rng = random.Random(seed)
    samples: dict[str, list[float]] = {i: [] for i in ids}
    for _ in range(n_samples):
        order = ids[:]
        rng.shuffle(order)
        prefix: list[Meeting] = []
        prev_p = 0.0  # P(empty set) = 0 by construction (U(empty) - U(empty))
        for mid in order:
            prefix.append(by_id[mid])
            new_p = day_penalty(person, prefix, date).penalty_minutes
            samples[mid].append(new_p - prev_p)
            prev_p = new_p

    result: dict[str, ShapleyEstimate] = {}
    for mid, values in samples.items():
        mean = statistics.fmean(values)
        se = statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0
        result[mid] = ShapleyEstimate(value=mean, standard_error=se)
    return result


def shapley_values(
    person: Person,
    meetings: Sequence[Meeting],
    date: date_,
    seed: int,
    exact_threshold: int = DEFAULT_EXACT_THRESHOLD,
    n_samples: int = DEFAULT_MONTE_CARLO_SAMPLES,
) -> dict[str, ShapleyEstimate]:
    """Dispatch to exact or Monte Carlo Shapley based on the day's meeting count."""
    n = len(_day_meetings(person, meetings, date))
    if n <= exact_threshold:
        exact = shapley_exact(person, meetings, date)
        return {mid: ShapleyEstimate(value=v, standard_error=0.0) for mid, v in exact.items()}
    return shapley_monte_carlo(person, meetings, date, seed=seed, n_samples=n_samples)


def series_rollup(
    shapley_by_meeting: dict[str, float], series_id_by_meeting: dict[str, str | None]
) -> dict[str, float]:
    """Sum Shapley values across meetings sharing a recurring series id.

    Meetings with no series id are not part of any roll-up (their value
    already stands alone in `shapley_by_meeting`).
    """
    rollup: dict[str, float] = {}
    for meeting_id, phi in shapley_by_meeting.items():
        series_id = series_id_by_meeting.get(meeting_id)
        if series_id is None:
            continue
        rollup[series_id] = rollup.get(series_id, 0.0) + phi
    return rollup

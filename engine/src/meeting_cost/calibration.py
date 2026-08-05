"""Calibration harness for the week-ranking exercise (CLAUDE.md section 2, "Calibration").

c, fatigue_rate and fatigue_threshold are starting values, not measurements.
This grid-searches the parameter space, correlating each candidate's
week-level penalty against self-reported week rankings from real people, and
reports the best correlation found rather than tuning until some target
threshold is hit - a weak correlation is a valid, reportable result.

Week-level aggregation is one of CLAUDE.md section 7's open questions
("How day penalties aggregate into a week-level figure. Undefined."). The
simplest, most literal aggregation - summing daily P across the week - is
used here as a provisional placeholder, same treatment as the other
flagged-but-unblocked defaults in model.py.

The self-report scale's polarity (does rank 1 mean best or worst week?) is
not pinned down by the spec either, so this searches for the parameter
combination that maximises the *magnitude* of the Spearman correlation
rather than assuming a sign, and reports the signed value so a human can
read off which direction it actually points.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as date_
from datetime import timedelta

from meeting_cost.model import day_penalty
from meeting_cost.types import Meeting, Person

DAYS_PER_WEEK = 7


def week_penalty(
    person: Person,
    meetings: Sequence[Meeting],
    week_start: date_,
    reentry_cost: float,
    fatigue_rate: float,
    fatigue_threshold: float,
) -> float:
    """Sum of P across a 7-day week starting at `week_start` (provisional aggregation)."""
    return sum(
        day_penalty(
            person, meetings, week_start + timedelta(days=offset), reentry_cost, fatigue_rate, fatigue_threshold
        ).penalty_minutes
        for offset in range(DAYS_PER_WEEK)
    )


def _rank(values: Sequence[float]) -> list[float]:
    """1-based ranks with ties given the average rank of the tied positions."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman_correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Spearman rank correlation (tie-corrected via Pearson correlation of ranks)."""
    n = len(xs)
    if n != len(ys):
        raise ValueError("xs and ys must be the same length")
    if n < 2:
        raise ValueError("need at least 2 observations to compute a correlation")

    rx, ry = _rank(xs), _rank(ys)
    mean_rx, mean_ry = sum(rx) / n, sum(ry) / n
    cov = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
    var_x = sum((a - mean_rx) ** 2 for a in rx)
    var_y = sum((b - mean_ry) ** 2 for b in ry)
    if var_x == 0 or var_y == 0:
        return 0.0  # no variation in one side; correlation undefined, reported as 0
    return cov / (var_x * var_y) ** 0.5


@dataclass(frozen=True)
class WeekObservation:
    person: Person
    meetings: Sequence[Meeting]
    week_start: date_
    self_reported_rank: float  # relative order only; scale and polarity are the caller's convention


@dataclass(frozen=True)
class ParamGrid:
    reentry_costs: Sequence[float]
    fatigue_rates: Sequence[float]
    fatigue_thresholds: Sequence[float]


@dataclass(frozen=True)
class GridPointResult:
    reentry_cost: float
    fatigue_rate: float
    fatigue_threshold: float
    correlation: float


@dataclass(frozen=True)
class CalibrationResult:
    best: GridPointResult
    all_results: list[GridPointResult]


def spearman_fit(observations: Sequence[WeekObservation], param_grid: ParamGrid) -> CalibrationResult:
    if len(observations) < 2:
        raise ValueError("need at least 2 week observations to compute a rank correlation")

    reported = [o.self_reported_rank for o in observations]
    all_results: list[GridPointResult] = []

    for c in param_grid.reentry_costs:
        for lam in param_grid.fatigue_rates:
            for r_star in param_grid.fatigue_thresholds:
                penalties = [
                    week_penalty(o.person, o.meetings, o.week_start, c, lam, r_star) for o in observations
                ]
                corr = spearman_correlation(penalties, reported)
                all_results.append(
                    GridPointResult(reentry_cost=c, fatigue_rate=lam, fatigue_threshold=r_star, correlation=corr)
                )

    best = max(all_results, key=lambda r: abs(r.correlation))
    return CalibrationResult(best=best, all_results=all_results)

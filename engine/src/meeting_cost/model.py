"""Per-person, per-day cost model (CLAUDE.md section 2).

Symbol mapping: c -> reentry_cost, lambda -> fatigue_rate, r* -> fatigue_threshold.

Provisional defaults for open questions in CLAUDE.md section 7 (flagged, not
resolved): overlapping/double-booked meetings are merged into one block;
a run is broken by a gap of any length greater than zero (touching meetings
stay in the same run); meetings are clipped to the working window, so time
outside W is simply dropped rather than penalised via a kappa multiplier.
A day absent from a person's window_by_weekday is treated as non-working:
P = 0 for that day.

Lunch protection (CLAUDE.md section 7's "whether a lunch interval is
protected") is a POLICY term, not a measurement: mu is a flat, binary
penalty ("no lunch break available today") rather than something
calibrated against self-reported data the way c/lambda/r* are. See
_lunch_protection_penalty.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date as date_
from datetime import datetime, time, timedelta

from meeting_cost.types import Interval, Meeting, Person

DEFAULT_REENTRY_COST = 20.0
DEFAULT_FATIGUE_THRESHOLD = 90.0
# Spec gives a starting range of 0.3-0.5 for lambda, not a point value.
# Midpoint used as the provisional default, pending calibration.
DEFAULT_FATIGUE_RATE = 0.4

# 12:00-14:00 in minutes from midnight.
DEFAULT_LUNCH_WINDOW: tuple[float, float] = (720.0, 840.0)
DEFAULT_LUNCH_MINUTES = 60.0
DEFAULT_LUNCH_PENALTY = 60.0


def _clip_to_window(window: Interval, meetings: Sequence[Interval]) -> list[Interval]:
    clipped = []
    for m in meetings:
        start = max(m.start, window.start)
        end = min(m.end, window.end)
        if end > start:
            clipped.append(Interval(start, end))
    return clipped


def _merge_contiguous(intervals: Sequence[Interval]) -> list[Interval]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda iv: iv.start)
    merged = [ordered[0]]
    for iv in ordered[1:]:
        last = merged[-1]
        if iv.start <= last.end:
            if iv.end > last.end:
                merged[-1] = Interval(last.start, iv.end)
        else:
            merged.append(iv)
    return merged


def compute_runs(meetings: Sequence[Interval]) -> list[Interval]:
    """Maximal contiguous meeting runs: overlapping or touching intervals merged.

    Caller is responsible for restricting `meetings` to the working window and
    the day of interest first (see compute_gaps / day_penalty).
    """
    return _merge_contiguous(meetings)


def compute_gaps(window: Interval, meetings: Sequence[Interval]) -> list[Interval]:
    """Free intervals within `window`, given `meetings` (possibly overlapping
    or extending outside the window)."""
    runs = compute_runs(_clip_to_window(window, meetings))
    gaps: list[Interval] = []
    cursor = window.start
    for run in runs:
        if run.start > cursor:
            gaps.append(Interval(cursor, run.start))
        cursor = run.end
    if window.end > cursor:
        gaps.append(Interval(cursor, window.end))
    return gaps


def gap_yield(gap_minutes: float, reentry_cost: float) -> float:
    return max(0.0, gap_minutes - reentry_cost)


def fatigue(runs: Sequence[Interval], fatigue_threshold: float, fatigue_rate: float) -> float:
    return fatigue_rate * sum(max(0.0, r.minutes - fatigue_threshold) for r in runs)


def _lunch_protection_penalty(
    gaps: Sequence[Interval],
    day: date_,
    lunch_window: tuple[float, float],
    lunch_minutes: float,
    lunch_penalty: float,
) -> float:
    """mu unless some gap has a contiguous stretch of at least
    `lunch_minutes` lying entirely within `lunch_window`.

    Works from the raw gap structure, not gap_yield: the re-entry cost c
    does not apply here (CLAUDE.md) - this asks only whether a lunch
    break exists at all, not how usable it is. A gap's overlap with the
    lunch window is itself the largest such contiguous stretch that gap
    can offer, so checking overlap length is sufficient - no need to
    search for sub-intervals separately.
    """
    midnight = datetime.combine(day, time())
    lunch_start = midnight + timedelta(minutes=lunch_window[0])
    lunch_end = midnight + timedelta(minutes=lunch_window[1])

    for g in gaps:
        overlap_start = max(g.start, lunch_start)
        overlap_end = min(g.end, lunch_end)
        if overlap_end <= overlap_start:
            continue
        overlap_minutes = (overlap_end - overlap_start).total_seconds() / 60
        if overlap_minutes >= lunch_minutes:
            return 0.0
    return lunch_penalty


def usable_focus_time(
    window: Interval,
    meetings: Sequence[Interval],
    reentry_cost: float,
    fatigue_rate: float,
    fatigue_threshold: float,
    lunch_window: tuple[float, float] = DEFAULT_LUNCH_WINDOW,
    lunch_minutes: float = DEFAULT_LUNCH_MINUTES,
    lunch_penalty: float = DEFAULT_LUNCH_PENALTY,
) -> float:
    gaps = compute_gaps(window, meetings)
    runs = compute_runs(_clip_to_window(window, meetings))
    gap_total = sum(gap_yield(g.minutes, reentry_cost) for g in gaps)
    lam = _lunch_protection_penalty(gaps, window.start.date(), lunch_window, lunch_minutes, lunch_penalty)
    return gap_total - fatigue(runs, fatigue_threshold, fatigue_rate) - lam


@dataclass(frozen=True)
class GapDetail:
    interval: Interval
    yield_minutes: float


@dataclass(frozen=True)
class RunDetail:
    interval: Interval
    fatigue_minutes: float


@dataclass(frozen=True)
class DayPenaltyResult:
    person_id: str
    date: date_
    is_working_day: bool
    window_minutes: float
    empty_day_usable_minutes: float  # U(empty)
    usable_focus_minutes: float  # U(M)
    penalty_minutes: float  # P(M)
    fatigue_minutes: float  # Phi(M)
    lunch_penalty_minutes: float = 0.0  # Lambda(M)
    gaps: list[GapDetail] = field(default_factory=list)
    runs: list[RunDetail] = field(default_factory=list)


def day_penalty(
    person: Person,
    meetings: Sequence[Meeting],
    date: date_,
    reentry_cost: float | None = None,
    fatigue_rate: float | None = None,
    fatigue_threshold: float | None = None,
    lunch_window: tuple[float, float] | None = None,
    lunch_minutes: float | None = None,
    lunch_penalty: float | None = None,
) -> DayPenaltyResult:
    """P(M) for `person` on `date`, given any pool of meetings.

    Meetings are filtered to those on `date` where `person.id` is an
    attendee - callers do not need to pre-filter.
    """
    c = reentry_cost if reentry_cost is not None else (
        person.reentry_cost if person.reentry_cost is not None else DEFAULT_REENTRY_COST
    )
    lam = fatigue_rate if fatigue_rate is not None else (
        person.fatigue_rate if person.fatigue_rate is not None else DEFAULT_FATIGUE_RATE
    )
    r_star = fatigue_threshold if fatigue_threshold is not None else (
        person.fatigue_threshold if person.fatigue_threshold is not None else DEFAULT_FATIGUE_THRESHOLD
    )
    lunch_win = lunch_window if lunch_window is not None else (
        person.lunch_window if person.lunch_window is not None else DEFAULT_LUNCH_WINDOW
    )
    lunch_min = lunch_minutes if lunch_minutes is not None else (
        person.lunch_minutes if person.lunch_minutes is not None else DEFAULT_LUNCH_MINUTES
    )
    mu = lunch_penalty if lunch_penalty is not None else (
        person.lunch_penalty if person.lunch_penalty is not None else DEFAULT_LUNCH_PENALTY
    )

    window_times = person.window_by_weekday.get(date.weekday())
    if window_times is None:
        return DayPenaltyResult(
            person_id=person.id,
            date=date,
            is_working_day=False,
            window_minutes=0.0,
            empty_day_usable_minutes=0.0,
            usable_focus_minutes=0.0,
            penalty_minutes=0.0,
            fatigue_minutes=0.0,
            lunch_penalty_minutes=0.0,
        )

    window = Interval(
        datetime.combine(date, window_times[0]),
        datetime.combine(date, window_times[1]),
    )
    day_meetings = [
        m.interval
        for m in meetings
        if m.start.date() == date and person.id in m.attendee_ids
    ]

    empty_usable = window.minutes - c
    gaps = compute_gaps(window, day_meetings)
    runs = compute_runs(_clip_to_window(window, day_meetings))
    phi = fatigue(runs, r_star, lam)
    lunch_lambda = _lunch_protection_penalty(gaps, date, lunch_win, lunch_min, mu)
    usable = sum(gap_yield(g.minutes, c) for g in gaps) - phi - lunch_lambda
    penalty = empty_usable - usable

    return DayPenaltyResult(
        person_id=person.id,
        date=date,
        is_working_day=True,
        window_minutes=window.minutes,
        empty_day_usable_minutes=empty_usable,
        usable_focus_minutes=usable,
        penalty_minutes=penalty,
        fatigue_minutes=phi,
        lunch_penalty_minutes=lunch_lambda,
        gaps=[GapDetail(g, gap_yield(g.minutes, c)) for g in gaps],
        runs=[RunDetail(r, lam * max(0.0, r.minutes - r_star)) for r in runs],
    )

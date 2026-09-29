"""Synthetic calendar generator (CLAUDE.md section 6, "Synthetic calendar generator").

Returns exactly the engine's own input types, so anything that consumes real
data later would consume synthetic data identically.
"""

from __future__ import annotations

import random
from datetime import date as date_
from datetime import datetime, time, timedelta

from meeting_cost.types import Meeting, Person

WEEKDAYS_MON_FRI = (0, 1, 2, 3, 4)

# Meetings snap to a half-hour grid, both in start time and duration, so
# generated calendars read like real ones (nothing starting at :37) and
# line up visually with the candidate slot grid. Durations are drawn from
# exactly these three choices, weighted toward the first (30 min most
# common, 90 min least): `meeting_length_minutes` still bounds which of
# them are eligible for a given call, but no longer produces arbitrary
# in-between values like 47.
MEETING_START_GRID_MINUTES = 30
MEETING_DURATION_CHOICES_MINUTES: tuple[int, ...] = (30, 60, 90)
MEETING_DURATION_WEIGHTS: tuple[int, ...] = (3, 2, 1)


def _sample_duration(
    rng: random.Random,
    meeting_length_minutes: tuple[int, int],
    duration_weights: tuple[float, ...] = MEETING_DURATION_WEIGHTS,
) -> int | None:
    min_len, max_len = meeting_length_minutes
    eligible = [
        d for d in MEETING_DURATION_CHOICES_MINUTES if min_len <= d <= max_len
    ]
    if not eligible:
        return None
    weights = [
        duration_weights[MEETING_DURATION_CHOICES_MINUTES.index(d)]
        for d in eligible
    ]
    return rng.choices(eligible, weights=weights, k=1)[0]


def generate_week(
    person_ids: list[str],
    week_start: date_,
    seed: int,
    meetings_per_day: tuple[int, int],
    meeting_length_minutes: tuple[int, int],
    working_window: tuple[time, time] = (time(9), time(17)),
    other_attendee_probability: float = 0.3,
    max_placement_attempts: int = 20,
    duration_weights: tuple[float, ...] = MEETING_DURATION_WEIGHTS,
) -> tuple[list[Person], list[Meeting]]:
    """Generate a Mon-Fri week of meetings for `person_ids`.

    `week_start` is treated as that week's Monday. Each person gets the same
    `working_window` on every weekday. For each (person, weekday) pair, a
    random number of meetings in `meetings_per_day` is placed. Each
    meeting's duration is drawn from MEETING_DURATION_CHOICES_MINUTES
    (filtered to `meeting_length_minutes`, weighted by `duration_weights` -
    same order as MEETING_DURATION_CHOICES_MINUTES, i.e. (30, 60, 90) -
    see _sample_duration) and its start snapped to the
    MEETING_START_GRID_MINUTES grid, non-overlapping with that same owning
    person's other meetings that day (the owner is always attendee_ids[0]
    on a generated meeting). A meeting whose duration has no eligible
    choice within `meeting_length_minutes`, or that cannot find a free
    grid-aligned slot after max_placement_attempts tries, is skipped
    rather than forced.

    Other attendees are added independently at `other_attendee_probability`
    per candidate; a meeting generated this way is not guaranteed
    conflict-free on those other attendees' own calendars - the model's
    provisional overlap handling covers that case, deliberately exercised
    elsewhere rather than avoided here.

    Determinism: a single `random.Random(seed)` instance is threaded through
    the whole call, so the same seed always produces byte-identical output.
    """
    rng = random.Random(seed)
    people = [
        Person(id=pid, window_by_weekday={d: working_window for d in WEEKDAYS_MON_FRI})
        for pid in person_ids
    ]

    meetings: list[Meeting] = []
    meeting_counter = 0
    min_n, max_n = meetings_per_day

    for weekday in WEEKDAYS_MON_FRI:
        day = week_start + timedelta(days=weekday)
        window_start = datetime.combine(day, working_window[0])
        window_end = datetime.combine(day, working_window[1])
        window_minutes = int((window_end - window_start).total_seconds() // 60)

        for owner_id in person_ids:
            n_meetings = rng.randint(min_n, max_n)
            placed: list[tuple[int, int]] = []

            for _ in range(n_meetings):
                duration = _sample_duration(rng, meeting_length_minutes, duration_weights)
                if duration is None or duration > window_minutes:
                    continue
                max_start_slot = (window_minutes - duration) // MEETING_START_GRID_MINUTES
                for _attempt in range(max_placement_attempts):
                    start_min = rng.randint(0, max_start_slot) * MEETING_START_GRID_MINUTES
                    end_min = start_min + duration
                    if all(end_min <= s or start_min >= e for s, e in placed):
                        placed.append((start_min, end_min))
                        break
                else:
                    continue  # no free grid-aligned slot found; skip

                other_ids = [
                    pid
                    for pid in person_ids
                    if pid != owner_id and rng.random() < other_attendee_probability
                ]
                meeting_counter += 1
                meetings.append(
                    Meeting(
                        id=f"synthetic-{meeting_counter}",
                        start=window_start + timedelta(minutes=start_min),
                        end=window_start + timedelta(minutes=end_min),
                        attendee_ids=tuple([owner_id, *other_ids]),
                    )
                )

    return people, meetings

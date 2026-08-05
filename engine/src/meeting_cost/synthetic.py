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


def generate_week(
    person_ids: list[str],
    week_start: date_,
    seed: int,
    meetings_per_day: tuple[int, int],
    meeting_length_minutes: tuple[int, int],
    working_window: tuple[time, time] = (time(9), time(17)),
    other_attendee_probability: float = 0.3,
    max_placement_attempts: int = 20,
) -> tuple[list[Person], list[Meeting]]:
    """Generate a Mon-Fri week of meetings for `person_ids`.

    `week_start` is treated as that week's Monday. Each person gets the same
    `working_window` on every weekday. For each (person, weekday) pair, a
    random number of meetings in `meetings_per_day` is placed, each with a
    random duration in `meeting_length_minutes`, non-overlapping with that
    same owning person's other meetings that day (the owner is always
    attendee_ids[0] on a generated meeting). Other attendees are added
    independently at `other_attendee_probability` per candidate; a meeting
    generated this way is not guaranteed conflict-free on those other
    attendees' own calendars - the model's provisional overlap handling
    covers that case, deliberately exercised elsewhere rather than avoided
    here.

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
    min_len, max_len = meeting_length_minutes
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
                duration = rng.randint(min_len, max_len)
                if duration > window_minutes:
                    continue
                for _attempt in range(max_placement_attempts):
                    start_min = rng.randint(0, window_minutes - duration)
                    end_min = start_min + duration
                    if all(end_min <= s or start_min >= e for s, e in placed):
                        placed.append((start_min, end_min))
                        break
                else:
                    continue  # no free slot found after max_placement_attempts; skip

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

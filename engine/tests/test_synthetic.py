from datetime import date, time

import pytest

from meeting_cost.synthetic import _sample_duration, generate_week

PERSON_IDS = ["alice", "bob", "carol"]
WEEK_START = date(2026, 1, 5)  # a Monday


def test_generate_week_returns_a_person_per_id_with_mon_fri_windows():
    people, _ = generate_week(
        PERSON_IDS, WEEK_START, seed=1, meetings_per_day=(1, 3), meeting_length_minutes=(15, 60)
    )
    assert [p.id for p in people] == PERSON_IDS
    for p in people:
        assert set(p.window_by_weekday.keys()) == {0, 1, 2, 3, 4}
        assert p.window_by_weekday[0] == (time(9), time(17))


def test_generate_week_meetings_within_window_and_length_bounds():
    _, meetings = generate_week(
        PERSON_IDS, WEEK_START, seed=1, meetings_per_day=(2, 4), meeting_length_minutes=(15, 90)
    )
    assert meetings  # non-trivial scenario actually produced meetings
    for m in meetings:
        assert time(9) <= m.start.time() < time(17)
        assert time(9) < m.end.time() <= time(17)
        assert 15 <= m.minutes <= 90
        assert m.start.weekday() in {0, 1, 2, 3, 4}
        assert m.attendee_ids[0] in PERSON_IDS  # owner convention


def test_generate_week_meetings_snap_to_the_half_hour_grid():
    # Start snapped to :00/:30, duration snapped to one of {30, 60, 90} -
    # both requirements independent of the closed-form cost math, purely
    # about how the synthetic calendar reads.
    _, meetings = generate_week(
        PERSON_IDS, WEEK_START, seed=1, meetings_per_day=(2, 4), meeting_length_minutes=(15, 90)
    )
    assert meetings
    for m in meetings:
        assert m.start.minute in (0, 30)
        assert m.end.minute in (0, 30)
        assert m.minutes in (30, 60, 90)


def test_sample_duration_is_weighted_toward_30_and_filters_by_range():
    import random

    rng = random.Random(0)
    counts = {30: 0, 60: 0, 90: 0}
    for _ in range(2000):
        d = _sample_duration(rng, (30, 90))
        counts[d] += 1

    # Weighted 3:2:1 toward 30 - not asserting exact proportions (that's
    # the RNG's business), just the ordering the weighting is meant to
    # produce, with enough samples that it isn't noise.
    assert counts[30] > counts[60] > counts[90]

    # Range excludes 60 and 90 entirely -> only 30 is ever eligible.
    rng = random.Random(0)
    for _ in range(50):
        assert _sample_duration(rng, (15, 45)) == 30

    # Range excludes all three choices -> no eligible duration.
    rng = random.Random(0)
    assert _sample_duration(rng, (10, 20)) is None


def test_generate_week_ids_are_unique():
    _, meetings = generate_week(
        PERSON_IDS, WEEK_START, seed=1, meetings_per_day=(2, 4), meeting_length_minutes=(15, 60)
    )
    ids = [m.id for m in meetings]
    assert len(ids) == len(set(ids))


def test_generate_week_owner_has_no_self_overlaps():
    # attendee_ids[0] is the owner by construction; a person's own meetings
    # (as owner) on a given day must not overlap each other.
    _, meetings = generate_week(
        PERSON_IDS, WEEK_START, seed=2, meetings_per_day=(3, 6), meeting_length_minutes=(15, 60)
    )
    by_owner_day: dict[tuple[str, object], list] = {}
    for m in meetings:
        key = (m.attendee_ids[0], m.start.date())
        by_owner_day.setdefault(key, []).append(m)

    for group in by_owner_day.values():
        ordered = sorted(group, key=lambda m: m.start)
        for prev, nxt in zip(ordered, ordered[1:]):
            assert prev.end <= nxt.start


def test_generate_week_is_deterministic_given_seed():
    _, meetings_a = generate_week(
        PERSON_IDS, WEEK_START, seed=42, meetings_per_day=(1, 3), meeting_length_minutes=(15, 60)
    )
    _, meetings_b = generate_week(
        PERSON_IDS, WEEK_START, seed=42, meetings_per_day=(1, 3), meeting_length_minutes=(15, 60)
    )
    assert meetings_a == meetings_b


def test_generate_week_different_seeds_differ():
    _, meetings_a = generate_week(
        PERSON_IDS, WEEK_START, seed=1, meetings_per_day=(2, 4), meeting_length_minutes=(15, 60)
    )
    _, meetings_b = generate_week(
        PERSON_IDS, WEEK_START, seed=2, meetings_per_day=(2, 4), meeting_length_minutes=(15, 60)
    )
    assert meetings_a != meetings_b

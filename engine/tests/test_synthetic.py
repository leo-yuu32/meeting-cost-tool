from datetime import date, time

from meeting_cost.synthetic import generate_week

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

import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

# export_lookup.py is a standalone script under engine/scripts/, not part of
# the installed meeting_cost package - import it directly by path.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from export_lookup import (  # noqa: E402
    DEFAULT_DURATION_WEIGHTS,
    DEFAULT_MEETING_LENGTH_MINUTES,
    DEFAULT_MEETINGS_PER_DAY,
    _is_busy,
    _window_union_minutes,
    build_lookup,
    write_lookup,
)

from meeting_cost.marginal import marginal_cost, marginal_cost_for_person
from meeting_cost.synthetic import generate_week
from meeting_cost.types import Meeting, Person

SEED = 1
PERSON_IDS = ["alice", "bob", "carol"]
WEEK_START = date(2026, 1, 5)  # a Monday


def test_build_lookup_shape():
    data = build_lookup(seed=SEED, person_ids=["alice", "bob"], week_start=WEEK_START)

    assert data["seed"] == SEED
    assert data["day"] == WEEK_START.isoformat()
    assert data["durations"] == [30, 45, 60]
    assert isinstance(data["slots"], list) and len(data["slots"]) > 0
    assert all(isinstance(s, int) for s in data["slots"])
    assert data["slots"] == sorted(data["slots"])

    people_ids = {p["id"] for p in data["people"]}
    assert people_ids == {"alice", "bob"}
    assert all(p["display_name"] for p in data["people"])

    slot_keys = {str(s) for s in data["slots"]}
    for person_id in people_ids:
        assert set(data["costs"][person_id].keys()) == slot_keys
        assert set(data["longest_block"][person_id].keys()) == slot_keys
        assert set(data["busy"][person_id].keys()) == slot_keys
        for slot_key in slot_keys:
            assert set(data["costs"][person_id][slot_key].keys()) == {"30", "45", "60"}
            assert set(data["longest_block"][person_id][slot_key].keys()) == {"30", "45", "60"}
            assert set(data["busy"][person_id][slot_key].keys()) == {"30", "45", "60"}
            for duration_key in ("30", "45", "60"):
                assert isinstance(data["costs"][person_id][slot_key][duration_key], (int, float))
                assert isinstance(data["longest_block"][person_id][slot_key][duration_key], (int, float))
                assert isinstance(data["busy"][person_id][slot_key][duration_key], bool)

    assert set(data["meetings"].keys()) == people_ids
    for person_id in people_ids:
        for interval in data["meetings"][person_id]:
            assert set(interval.keys()) == {"id", "start", "end"}
            assert isinstance(interval["id"], str)
            assert isinstance(interval["start"], int)
            assert isinstance(interval["end"], int)
            assert interval["start"] < interval["end"]

    assert set(data["window"].keys()) == {"start", "end"}
    assert isinstance(data["window"]["start"], int)
    assert isinstance(data["window"]["end"], int)
    assert data["window"]["start"] < data["window"]["end"]

    assert set(data["attribution"].keys()) == people_ids
    assert set(data["day_penalty"].keys()) == people_ids
    for person_id in people_ids:
        assert isinstance(data["day_penalty"][person_id], (int, float))
        for meeting_id, value in data["attribution"][person_id].items():
            assert isinstance(meeting_id, str)
            assert isinstance(value, (int, float))

    json.dumps(data)  # must be JSON-serializable, matching what gets written to disk


def test_attribution_meeting_ids_match_the_meetings_table():
    data = build_lookup(seed=SEED, person_ids=PERSON_IDS, week_start=WEEK_START)
    for person_id in [p["id"] for p in data["people"]]:
        attributed_ids = set(data["attribution"][person_id].keys())
        meeting_ids = {m["id"] for m in data["meetings"][person_id]}
        assert attributed_ids == meeting_ids


def test_attribution_sums_to_day_penalty_for_every_person():
    # Efficiency is the whole reason to use Shapley here (CLAUDE.md section
    # 2): attributions across a person-day's meetings must sum exactly to
    # that day's P. If this ever fails, the export's wiring has diverged
    # from shapley.py, not the Shapley math itself (that's covered in
    # test_shapley.py).
    data = build_lookup(seed=SEED, person_ids=PERSON_IDS, week_start=WEEK_START)
    for person_id in [p["id"] for p in data["people"]]:
        total_attribution = sum(data["attribution"][person_id].values())
        assert total_attribution == pytest.approx(data["day_penalty"][person_id])


def test_window_matches_the_working_window_when_everyone_shares_one():
    data = build_lookup(seed=SEED, person_ids=PERSON_IDS, week_start=WEEK_START)
    # generate_week gives every person the same default 09:00-17:00 window,
    # so the union should equal exactly that.
    assert data["window"] == {"start": 9 * 60, "end": 17 * 60}


def test_window_union_minutes_unions_differing_person_windows():
    people = [
        Person(id="a", window_by_weekday={0: (time(9), time(17))}),
        Person(id="b", window_by_weekday={0: (time(8), time(16))}),
        Person(id="c", window_by_weekday={0: (time(9, 30), time(18))}),
    ]
    assert _window_union_minutes(people, 0) == (8 * 60, 18 * 60)


def test_window_union_minutes_skips_people_without_a_window_that_day():
    people = [
        Person(id="a", window_by_weekday={0: (time(9), time(17))}),
        Person(id="b", window_by_weekday={1: (time(9), time(17))}),  # not working weekday 0
    ]
    assert _window_union_minutes(people, 0) == (9 * 60, 17 * 60)


def test_window_union_minutes_raises_when_nobody_works_that_day():
    people = [Person(id="a", window_by_weekday={1: (time(9), time(17))})]
    with pytest.raises(ValueError):
        _window_union_minutes(people, 0)


def test_meetings_export_is_sorted_and_matches_generate_week_directly():
    data = build_lookup(seed=SEED, person_ids=PERSON_IDS, week_start=WEEK_START)

    people, meetings = generate_week(
        PERSON_IDS,
        WEEK_START,
        seed=SEED,
        meetings_per_day=DEFAULT_MEETINGS_PER_DAY,
        meeting_length_minutes=DEFAULT_MEETING_LENGTH_MINUTES,
        duration_weights=DEFAULT_DURATION_WEIGHTS,
    )

    for person in people:
        expected = sorted(
            (
                (m.id, m.start.hour * 60 + m.start.minute, m.end.hour * 60 + m.end.minute)
                for m in meetings
                if person.id in m.attendee_ids and m.start.date() == WEEK_START
            ),
            key=lambda t: t[1],
        )
        actual = [(m["id"], m["start"], m["end"]) for m in data["meetings"][person.id]]
        assert actual == expected

        # sorted ascending by start, as claimed
        starts = [m["start"] for m in data["meetings"][person.id]]
        assert starts == sorted(starts)


def test_busy_table_is_key_aligned_with_costs():
    # Every (person, slot, duration) that busy covers must also exist in
    # costs - the tables are built from the same loop, but this is the
    # invariant the front end actually depends on, so assert it directly
    # rather than trusting the shape test above to catch a divergence.
    data = build_lookup(seed=SEED, person_ids=PERSON_IDS, week_start=WEEK_START)

    assert set(data["busy"].keys()) == set(data["costs"].keys())
    found_busy = False
    for person_id in data["busy"]:
        assert set(data["busy"][person_id].keys()) == set(data["costs"][person_id].keys())
        for slot_key in data["busy"][person_id]:
            assert set(data["busy"][person_id][slot_key].keys()) == set(data["costs"][person_id][slot_key].keys())
            for duration_key, is_busy in data["busy"][person_id][slot_key].items():
                assert duration_key in data["costs"][person_id][slot_key]
                if is_busy:
                    found_busy = True

    assert found_busy, "expected at least one busy (person, slot, duration) in this scenario"


def test_is_busy_hand_built_calendar():
    day = WEEK_START

    def dt(hour: int, minute: int = 0) -> datetime:
        return datetime.combine(day, time(hour, minute))

    existing = [
        Meeting(id="e1", start=dt(10, 0), end=dt(10, 30), attendee_ids=("p",)),
        Meeting(id="e2", start=dt(13, 0), end=dt(14, 0), attendee_ids=("p",)),
    ]

    assert _is_busy(existing, dt(10, 15), dt(10, 45)) is True  # partial overlap
    assert _is_busy(existing, dt(9, 45), dt(10, 45)) is True  # candidate contains a meeting
    assert _is_busy(existing, dt(13, 15), dt(13, 30)) is True  # meeting contains the candidate
    assert _is_busy(existing, dt(9, 30), dt(10, 0)) is False  # ends exactly when e1 starts (touching)
    assert _is_busy(existing, dt(10, 30), dt(11, 0)) is False  # starts exactly when e1 ends (touching)
    assert _is_busy(existing, dt(11, 0), dt(12, 0)) is False  # clean gap between meetings
    assert _is_busy([], dt(10, 0), dt(10, 30)) is False  # no existing meetings at all


def test_busy_true_even_when_marginal_cost_is_near_zero():
    # The reported bug: a candidate fully absorbed inside one large existing
    # meeting costs nothing extra (the merged run is unchanged), but the
    # slot is obviously unbookable. Cost alone can't signal feasibility;
    # busy must be derived from the calendar directly, not inferred from cost.
    person = Person(
        id="p1",
        window_by_weekday={0: (time(9), time(17))},
        reentry_cost=20,
        fatigue_rate=0.4,
        fatigue_threshold=90,
    )
    day = WEEK_START
    existing = [
        Meeting(
            id="all-day",
            start=datetime.combine(day, time(9)),
            end=datetime.combine(day, time(17)),
            attendee_ids=("p1",),
        )
    ]
    candidate_start = datetime.combine(day, time(10))
    candidate_end = datetime.combine(day, time(11))
    candidate = Meeting(id="candidate", start=candidate_start, end=candidate_end, attendee_ids=("p1",))

    result = marginal_cost_for_person(person, existing, candidate, day)
    assert result.cost_minutes == pytest.approx(0.0)
    assert _is_busy(existing, candidate_start, candidate_end) is True


def test_lookup_does_not_precompute_any_fixed_attendee_total():
    data = build_lookup(seed=SEED, person_ids=PERSON_IDS, week_start=WEEK_START)
    assert "total" not in data
    assert "totals" not in data
    # costs are keyed by individual person id only, never by a combination/tuple of ids.
    assert set(data["costs"].keys()) == set(PERSON_IDS)


def test_summing_a_subset_matches_calling_the_engine_directly():
    data = build_lookup(seed=SEED, person_ids=PERSON_IDS, week_start=WEEK_START)

    subset = ["alice", "carol"]
    slot_minutes = data["slots"][3]
    duration = 45

    looked_up_total = sum(data["costs"][pid][str(slot_minutes)][str(duration)] for pid in subset)

    # Recompute independently via the real engine for the same subset/slot/duration.
    people, meetings = generate_week(
        PERSON_IDS,
        WEEK_START,
        seed=SEED,
        meetings_per_day=DEFAULT_MEETINGS_PER_DAY,
        meeting_length_minutes=DEFAULT_MEETING_LENGTH_MINUTES,
        duration_weights=DEFAULT_DURATION_WEIGHTS,
    )
    existing_by_person = {p.id: [m for m in meetings if p.id in m.attendee_ids] for p in people}
    slot_start = datetime.combine(WEEK_START, time(0)) + timedelta(minutes=slot_minutes)
    candidate = Meeting(
        id="check",
        start=slot_start,
        end=slot_start + timedelta(minutes=duration),
        attendee_ids=tuple(subset),
    )
    direct = marginal_cost(people, existing_by_person, candidate)

    assert looked_up_total == pytest.approx(direct.total_cost_minutes)


def test_summing_the_full_attendee_list_also_matches():
    data = build_lookup(seed=SEED, person_ids=PERSON_IDS, week_start=WEEK_START)

    slot_minutes = data["slots"][0]
    duration = 30
    looked_up_total = sum(data["costs"][pid][str(slot_minutes)][str(duration)] for pid in PERSON_IDS)

    people, meetings = generate_week(
        PERSON_IDS,
        WEEK_START,
        seed=SEED,
        meetings_per_day=DEFAULT_MEETINGS_PER_DAY,
        meeting_length_minutes=DEFAULT_MEETING_LENGTH_MINUTES,
        duration_weights=DEFAULT_DURATION_WEIGHTS,
    )
    existing_by_person = {p.id: [m for m in meetings if p.id in m.attendee_ids] for p in people}
    slot_start = datetime.combine(WEEK_START, time(0)) + timedelta(minutes=slot_minutes)
    candidate = Meeting(
        id="check", start=slot_start, end=slot_start + timedelta(minutes=duration), attendee_ids=tuple(PERSON_IDS)
    )
    direct = marginal_cost(people, existing_by_person, candidate)

    assert looked_up_total == pytest.approx(direct.total_cost_minutes)


def test_retention_matches_one_minus_penalty_over_clear_day_yield_for_every_person():
    data = build_lookup(seed=SEED, person_ids=PERSON_IDS, week_start=WEEK_START)
    for person_id in [p["id"] for p in data["people"]]:
        expected = 1.0 - data["day_penalty"][person_id] / data["clear_day_yield"][person_id]
        assert data["retention"][person_id] == pytest.approx(expected)


def test_retention_is_one_for_an_empty_calendar():
    # No meetings at all means P(M) = 0, so retention should be exactly 1.0.
    data = build_lookup(seed=SEED, person_ids=["alice"], week_start=WEEK_START, meetings_per_day=(0, 0))
    assert data["day_penalty"]["alice"] == pytest.approx(0.0)
    assert data["retention"]["alice"] == pytest.approx(1.0)


def test_write_lookup_creates_file_with_matching_content(tmp_path):
    output_path = tmp_path / "scenarios" / "lookup.json"
    written = write_lookup(output_path=output_path, seed=3, person_ids=["alice"], week_start=WEEK_START)

    assert written == output_path
    assert output_path.exists()

    on_disk = json.loads(output_path.read_text())
    expected = build_lookup(seed=3, person_ids=["alice"], week_start=WEEK_START)
    assert on_disk == expected

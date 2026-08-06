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

from export_lookup import _is_busy, build_lookup, write_lookup  # noqa: E402

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

    json.dumps(data)  # must be JSON-serializable, matching what gets written to disk


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
        meetings_per_day=(1, 3),
        meeting_length_minutes=(15, 60),
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
        PERSON_IDS, WEEK_START, seed=SEED, meetings_per_day=(1, 3), meeting_length_minutes=(15, 60)
    )
    existing_by_person = {p.id: [m for m in meetings if p.id in m.attendee_ids] for p in people}
    slot_start = datetime.combine(WEEK_START, time(0)) + timedelta(minutes=slot_minutes)
    candidate = Meeting(
        id="check", start=slot_start, end=slot_start + timedelta(minutes=duration), attendee_ids=tuple(PERSON_IDS)
    )
    direct = marginal_cost(people, existing_by_person, candidate)

    assert looked_up_total == pytest.approx(direct.total_cost_minutes)


def test_write_lookup_creates_file_with_matching_content(tmp_path):
    output_path = tmp_path / "scenarios" / "lookup.json"
    written = write_lookup(output_path=output_path, seed=3, person_ids=["alice"], week_start=WEEK_START)

    assert written == output_path
    assert output_path.exists()

    on_disk = json.loads(output_path.read_text())
    expected = build_lookup(seed=3, person_ids=["alice"], week_start=WEEK_START)
    assert on_disk == expected

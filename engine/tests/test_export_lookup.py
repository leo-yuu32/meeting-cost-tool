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

from export_lookup import build_lookup, write_lookup  # noqa: E402

from meeting_cost.marginal import marginal_cost
from meeting_cost.synthetic import generate_week
from meeting_cost.types import Meeting

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
        for slot_key in slot_keys:
            assert set(data["costs"][person_id][slot_key].keys()) == {"30", "45", "60"}
            assert set(data["longest_block"][person_id][slot_key].keys()) == {"30", "45", "60"}
            for duration_key in ("30", "45", "60"):
                assert isinstance(data["costs"][person_id][slot_key][duration_key], (int, float))
                assert isinstance(data["longest_block"][person_id][slot_key][duration_key], (int, float))

    json.dumps(data)  # must be JSON-serializable, matching what gets written to disk


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

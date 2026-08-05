import json
from datetime import date, datetime, time, timedelta

import pytest

from meeting_cost.api import get_attribution, get_day_penalty, get_sensitivities, get_slot_ranking
from meeting_cost.types import Interval, Meeting, Person

DAY = date(2026, 1, 5)


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(DAY, time(hour, minute))


def person(pid="p1") -> Person:
    return Person(
        id=pid,
        window_by_weekday={0: (time(9), time(17))},
        reentry_cost=20,
        fatigue_rate=0.4,
        fatigue_threshold=90,
    )


def meeting(mid, start, minutes, attendees=("p1",), series_id=None) -> Meeting:
    return Meeting(
        id=mid, start=start, end=start + timedelta(minutes=minutes), attendee_ids=attendees, series_id=series_id
    )


def test_get_day_penalty_matches_worked_example_and_is_json_serializable():
    p = person()
    meetings = [meeting("m1", dt(10, 0), 30), meeting("m2", dt(10, 30), 60)]
    result = get_day_penalty(p, meetings, DAY)

    assert result["penalty_minutes"] == pytest.approx(110)
    assert result["person_id"] == "p1"
    assert result["date"] == DAY.isoformat()
    assert isinstance(result["gaps"], list) and len(result["gaps"]) == 2
    assert isinstance(result["runs"], list) and len(result["runs"]) == 1

    json.dumps(result)  # must not raise


def test_get_slot_ranking_contract_and_json_serializable():
    p = person()
    window = Interval(dt(9, 0), dt(17, 0))
    result = get_slot_ranking(
        people=[p],
        existing_by_person={"p1": []},
        duration_minutes=30,
        attendee_ids=["p1"],
        candidate_window=window,
        grid_minutes=60,
    )
    assert result["duration_minutes"] == 30
    assert result["grid_minutes"] == 60
    assert len(result["slots"]) > 0
    slot = result["slots"][0]
    assert set(slot.keys()) == {"start", "end", "total_cost_minutes", "rank", "per_attendee"}
    attendee = slot["per_attendee"][0]
    assert set(attendee.keys()) == {"person_id", "cost_minutes", "longest_remaining_block_minutes", "day_state"}
    assert "penalty_minutes" in attendee["day_state"]

    json.dumps(result)


def test_get_sensitivities_contract_and_json_serializable():
    p = person()
    result = get_sensitivities(
        people=[p],
        existing_by_person={"p1": []},
        slot_start=dt(11, 0),
        attendee_ids=["p1"],
        duration_minutes=30,
        durations=[15, 30, 60],
    )
    assert len(result["duration_sensitivity"]) == 3
    assert len(result["attendee_sensitivity"]) == 1
    assert result["attendee_sensitivity"][0]["person_id"] == "p1"

    json.dumps(result)


def test_get_attribution_contract_efficiency_and_series_rollup():
    p = person()
    meetings = [
        meeting("m1", dt(9, 0), 30, series_id="standup"),
        meeting("m2", dt(9, 30), 30, series_id="standup"),
        meeting("m3", dt(11, 0), 45),
    ]
    result = get_attribution(p, meetings, DAY, seed=1)

    assert set(result["shapley"].keys()) == {"m1", "m2", "m3"}
    total = sum(v["value"] for v in result["shapley"].values())
    assert total == pytest.approx(get_day_penalty(p, meetings, DAY)["penalty_minutes"])
    assert result["series_rollup"]["standup"] == pytest.approx(
        result["shapley"]["m1"]["value"] + result["shapley"]["m2"]["value"]
    )
    assert "m3" not in result["series_rollup"]

    json.dumps(result)

from datetime import datetime, time

import pytest

from meeting_cost.types import Interval, Meeting, Person


def test_interval_minutes():
    iv = Interval(datetime(2026, 1, 5, 9, 0), datetime(2026, 1, 5, 10, 30))
    assert iv.minutes == 90


def test_interval_rejects_non_positive_duration():
    with pytest.raises(ValueError):
        Interval(datetime(2026, 1, 5, 10, 0), datetime(2026, 1, 5, 9, 0))
    with pytest.raises(ValueError):
        Interval(datetime(2026, 1, 5, 9, 0), datetime(2026, 1, 5, 9, 0))


def test_person_default_window():
    p = Person(id="p1", window_by_weekday={0: (time(9), time(17))})
    assert p.window_by_weekday[0] == (time(9), time(17))
    assert p.reentry_cost is None


def test_person_rejects_bad_weekday_or_window():
    with pytest.raises(ValueError):
        Person(id="p1", window_by_weekday={7: (time(9), time(17))})
    with pytest.raises(ValueError):
        Person(id="p1", window_by_weekday={0: (time(17), time(9))})


def test_meeting_interval_and_minutes():
    m = Meeting(
        id="m1",
        start=datetime(2026, 1, 5, 10, 0),
        end=datetime(2026, 1, 5, 10, 30),
        attendee_ids=("p1", "p2"),
    )
    assert m.minutes == 30
    assert m.interval == Interval(m.start, m.end)


def test_meeting_rejects_non_positive_duration():
    with pytest.raises(ValueError):
        Meeting(
            id="m1",
            start=datetime(2026, 1, 5, 10, 0),
            end=datetime(2026, 1, 5, 9, 0),
            attendee_ids=("p1",),
        )

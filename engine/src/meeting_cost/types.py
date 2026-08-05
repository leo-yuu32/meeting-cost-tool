"""Plain calendar vocabulary shared by every engine module.

No Graph/Outlook/Google types anywhere below this line - real ingestion,
if it is ever built, would translate into these types at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"Interval end ({self.end}) must be after start ({self.start})")

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60


@dataclass(frozen=True)
class Person:
    id: str
    # 0=Monday .. 6=Sunday; a weekday absent from this dict is non-working.
    window_by_weekday: dict[int, tuple[time, time]]
    reentry_cost: float | None = None
    fatigue_rate: float | None = None
    fatigue_threshold: float | None = None

    def __post_init__(self) -> None:
        for weekday, (start, end) in self.window_by_weekday.items():
            if not 0 <= weekday <= 6:
                raise ValueError(f"weekday must be 0-6, got {weekday}")
            if end <= start:
                raise ValueError(f"window end ({end}) must be after start ({start}) for weekday {weekday}")


@dataclass(frozen=True)
class Meeting:
    id: str
    start: datetime
    end: datetime
    attendee_ids: tuple[str, ...]
    series_id: str | None = None

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"Meeting end ({self.end}) must be after start ({self.start})")

    @property
    def interval(self) -> Interval:
        return Interval(self.start, self.end)

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60

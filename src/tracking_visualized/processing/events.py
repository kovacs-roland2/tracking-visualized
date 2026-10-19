from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from tracking_visualized.domain import (
    Event,
    EventType,
    Match,
    PeriodType,
)

_PERIOD_ORDER = {
    PeriodType.FIRST_HALF: 0,
    PeriodType.SECOND_HALF: 1,
}


class EventCatalogError(ValueError):
    """Raised when the unified event collection is inconsistent."""


def _event_sort_key(
    event: Event,
) -> tuple[int, float, int, str]:
    """Return a tuple that can be used to sort events in chronological match order.

    Args:
        event (Event): The event to generate a sort key for.

    Returns:
        tuple[int, float, int, str]: A tuple containing the period order, period seconds,
        frame index, and event ID.
    """
    try:
        period_order = _PERIOD_ORDER[event.time.period]
    except KeyError as exc:
        raise EventCatalogError(f"Unsupported event period '{event.time.period}'.") from exc

    frame_index = event.frame_index if event.frame_index is not None else 2**63 - 1

    return (
        period_order,
        event.time.seconds,
        frame_index,
        event.event_id,
    )


def sort_events(
    events: Iterable[Event],
) -> tuple[Event, ...]:
    """
    Return events in chronological match order.

    Args:
        events (Iterable[Event]): The events to sort.

    Returns:
        tuple[Event, ...]: The sorted events.
    """
    return tuple(
        sorted(
            events,
            key=_event_sort_key,
        )
    )


def filter_shot_events(
    events: Iterable[Event],
) -> tuple[Event, ...]:
    """
    Return all shot events, including goals.

    Args:
        events (Iterable[Event]): The events to filter.

    Returns:
        tuple[Event, ...]: The filtered events.
    """
    return tuple(event for event in sort_events(events) if event.event_type == EventType.SHOT)


def filter_goal_events(
    events: Iterable[Event],
) -> tuple[Event, ...]:
    """
    Return shots whose outcome is a goal.

    Args:
        events (Iterable[Event]): The events to filter.

    Returns:
        tuple[Event, ...]: The filtered events.
    """
    return tuple(event for event in filter_shot_events(events) if event.is_goal)


@dataclass(frozen=True, slots=True)
class EventCatalog:
    """Chronological index of MVP-supported match events."""

    events: tuple[Event, ...]

    _by_id: Mapping[str, Event] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        supported_events = filter_shot_events(self.events)

        by_id: dict[str, Event] = {}

        for event in supported_events:
            if event.event_id in by_id:
                raise EventCatalogError(f"Duplicate event ID '{event.event_id}'.")

            by_id[event.event_id] = event

        object.__setattr__(
            self,
            "events",
            supported_events,
        )

        object.__setattr__(
            self,
            "_by_id",
            MappingProxyType(by_id),
        )

    @classmethod
    def from_match(
        cls,
        match: Match,
    ) -> "EventCatalog":
        return cls(events=tuple(match.events))

    @property
    def shots(self) -> tuple[Event, ...]:
        return self.events

    @property
    def goals(self) -> tuple[Event, ...]:
        return tuple(event for event in self.events if event.is_goal)

    def get_event(
        self,
        event_id: str,
    ) -> Event:
        try:
            return self._by_id[event_id]
        except KeyError as exc:
            raise KeyError(f"Unknown event ID '{event_id}'.") from exc

    def find_event(
        self,
        event_id: str,
    ) -> Event | None:
        return self._by_id.get(event_id)

    def __len__(self) -> int:
        return len(self.events)

    def __contains__(
        self,
        event_id: object,
    ) -> bool:
        return event_id in self._by_id

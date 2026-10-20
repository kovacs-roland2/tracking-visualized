from bisect import bisect_left
from dataclasses import dataclass, replace
from enum import StrEnum
from math import isfinite

from tracking_visualized.domain import (
    Event,
    Frame,
    Match,
    PeriodType,
)


class SynchronizationMethod(StrEnum):
    EXISTING_FRAME = "existing_frame"
    NEAREST_TIMESTAMP = "nearest_timestamp"
    UNMATCHED = "unmatched"


class EventSynchronizationError(ValueError):
    """Raised when event/tracking synchronization cannot be performed."""


@dataclass(frozen=True, slots=True)
class EventSynchronization:
    """
    Represents the synchronization result of a single event with the tracking data.
    """

    event_id: str
    method: SynchronizationMethod

    original_frame_index: int | None
    synchronized_frame_index: int | None

    original_seconds: float
    synchronized_seconds: float | None

    time_difference_seconds: float | None

    note: str | None = None

    @property
    def is_matched(self) -> bool:
        return self.synchronized_frame_index is not None


@dataclass(frozen=True, slots=True)
class SynchronizationReport:
    """
    Represents the overall synchronization report for a set of events."""

    results: tuple[EventSynchronization, ...]

    @property
    def matched(self) -> tuple[EventSynchronization, ...]:
        return tuple(result for result in self.results if result.is_matched)

    @property
    def unmatched(self) -> tuple[EventSynchronization, ...]:
        return tuple(result for result in self.results if not result.is_matched)

    @property
    def is_complete(self) -> bool:
        return not self.unmatched

    def format_text(self) -> str:
        """
        Format the synchronization report as a human-readable text summary.
        Returns:
            str: A formatted string summarizing the synchronization results.
        """
        lines = [(f"Synchronized {len(self.matched)}/{len(self.results)} event(s).")]

        for result in self.results:
            if result.is_matched:
                milliseconds = (result.time_difference_seconds or 0.0) * 1000

                lines.append(
                    f"{result.event_id}: "
                    f"{result.method.value} → "
                    f"frame {result.synchronized_frame_index} "
                    f"({milliseconds:+.1f} ms)"
                )
            else:
                lines.append(
                    f"{result.event_id}: unmatched" + (f" ({result.note})" if result.note else "")
                )

        return "\n".join(lines)


def _frame_time_delta(frame: Frame, seconds: float) -> float:
    return abs(frame.time.seconds - seconds)


def _frame_match_key(frame: Frame, seconds: float) -> tuple[float, bool, int]:
    return (
        _frame_time_delta(frame, seconds),
        frame.time.seconds > seconds,
        frame.frame_index,
    )


class _FrameLookup:
    def __init__(
        self,
        frames: tuple[Frame, ...],
    ) -> None:
        """
        Initialize a lookup structure for frames based on their period and frame index.

        Args:
            frames (tuple[Frame, ...]): A tuple of Frame objects to be indexed."""
        self.by_index: dict[int, Frame] = {}

        frames_by_period: dict[
            PeriodType,
            list[Frame],
        ] = {}

        for frame in frames:
            if frame.frame_index in self.by_index:
                raise EventSynchronizationError(f"Duplicate frame index {frame.frame_index}.")

            self.by_index[frame.frame_index] = frame

            frames_by_period.setdefault(
                frame.time.period,
                [],
            ).append(frame)

        self.frames_by_period: dict[
            PeriodType,
            tuple[Frame, ...],
        ] = {}

        self.times_by_period: dict[
            PeriodType,
            tuple[float, ...],
        ] = {}

        for period, period_frames in frames_by_period.items():
            ordered = tuple(
                sorted(
                    period_frames,
                    key=lambda frame: (
                        frame.time.seconds,
                        frame.frame_index,
                    ),
                )
            )

            self.frames_by_period[period] = ordered

            self.times_by_period[period] = tuple(frame.time.seconds for frame in ordered)

    def nearest_frame(
        self,
        period: PeriodType,
        seconds: float,
    ) -> Frame | None:
        """
        Find the nearest frame to the given period and seconds.

        Args:
            period (PeriodType): The period type for the frame.
            seconds (float): The time in seconds to find the nearest frame for.

        Returns:
            Frame | None: The nearest Frame object if found, otherwise None."""
        frames = self.frames_by_period.get(
            period,
            (),
        )

        times = self.times_by_period.get(
            period,
            (),
        )

        if not frames:
            return None

        index = bisect_left(
            times,
            seconds,
        )

        candidates: list[Frame] = []

        if index > 0:
            candidates.append(frames[index - 1])

        if index < len(frames):
            candidates.append(frames[index])

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda frame: _frame_match_key(frame, seconds),
        )


def _synchronize_event(
    event: Event,
    lookup: _FrameLookup,
    max_time_difference_seconds: float,
) -> tuple[Event, EventSynchronization]:
    """
    Synchronize a single event with the tracking data based on the provided lookup.

    Args:
        event (Event): The event to be synchronized.
        lookup (_FrameLookup): The lookup structure for frames.
        max_time_difference_seconds (float): The maximum allowed time
            difference for synchronization.

    Returns:
        tuple[Event, EventSynchronization]: A tuple containing the synchronized
        event and its synchronization result."""
    original_frame_index = event.frame_index

    # Highest priority:
    # an existing validated frame reference.
    if event.frame_index is not None:
        frame = lookup.by_index.get(event.frame_index)

        if frame is not None and frame.time.period == event.time.period:
            difference = frame.time.seconds - event.time.seconds

            synchronized = replace(
                event,
                time=frame.time,
                frame_index=frame.frame_index,
            )

            return (
                synchronized,
                EventSynchronization(
                    event_id=event.event_id,
                    method=SynchronizationMethod.EXISTING_FRAME,
                    original_frame_index=original_frame_index,
                    synchronized_frame_index=frame.frame_index,
                    original_seconds=event.time.seconds,
                    synchronized_seconds=frame.time.seconds,
                    time_difference_seconds=difference,
                ),
            )

    # Fallback:
    # nearest observed tracking timestamp.
    frame = lookup.nearest_frame(
        event.time.period,
        event.time.seconds,
    )

    if frame is not None:
        difference = frame.time.seconds - event.time.seconds

        if _frame_time_delta(frame, event.time.seconds) <= max_time_difference_seconds:
            synchronized = replace(
                event,
                time=frame.time,
                frame_index=frame.frame_index,
            )

            note = None

            if original_frame_index is not None:
                note = (
                    f"Original frame "
                    f"{original_frame_index} was unusable; "
                    "matched by timestamp instead."
                )

            return (
                synchronized,
                EventSynchronization(
                    event_id=event.event_id,
                    method=SynchronizationMethod.NEAREST_TIMESTAMP,
                    original_frame_index=original_frame_index,
                    synchronized_frame_index=frame.frame_index,
                    original_seconds=event.time.seconds,
                    synchronized_seconds=frame.time.seconds,
                    time_difference_seconds=difference,
                    note=note,
                ),
            )

    # No safe match.
    synchronized = replace(
        event,
        frame_index=None,
    )

    return (
        synchronized,
        EventSynchronization(
            event_id=event.event_id,
            method=SynchronizationMethod.UNMATCHED,
            original_frame_index=(original_frame_index),
            synchronized_frame_index=None,
            original_seconds=(event.time.seconds),
            synchronized_seconds=None,
            time_difference_seconds=None,
            note=(f"No tracking frame found within {max_time_difference_seconds:.3f}s."),
        ),
    )


def synchronize_match_events(
    match: Match,
    *,
    max_time_difference_seconds: float = 0.1,
) -> tuple[Match, SynchronizationReport]:
    """
    Synchronize unified events with tracking frames.

    Args:
        match (Match): The match object containing events and frames.
        max_time_difference_seconds (float): The maximum allowed time
            difference for synchronization.

    Returns:
        tuple[Match, SynchronizationReport]: A tuple containing the
            synchronized match and a synchronization report.
    """

    if not isfinite(max_time_difference_seconds):
        raise EventSynchronizationError("Synchronization tolerance must be finite.")

    if max_time_difference_seconds < 0:
        raise EventSynchronizationError("Synchronization tolerance cannot be negative.")

    lookup = _FrameLookup(tuple(match.frames))

    synchronized_events: list[Event] = []
    results: list[EventSynchronization] = []

    for event in match.events:
        synchronized, result = _synchronize_event(
            event,
            lookup,
            max_time_difference_seconds,
        )

        synchronized_events.append(synchronized)

        results.append(result)

    synchronized_match = replace(
        match,
        events=tuple(synchronized_events),
    )

    return (
        synchronized_match,
        SynchronizationReport(results=tuple(results)),
    )

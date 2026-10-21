from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from math import isfinite

from tracking_visualized.domain import Frame, Match, MatchTime, PeriodType
from tracking_visualized.processing.sequences import (
    EventSequence,
    extract_sequence_by_id,
)


class SequenceSelectionError(ValueError):
    """Raised when a requested sequence selection is invalid."""


@dataclass(frozen=True, slots=True)
class TimeRangeSequence:
    """Tracking sequence selected directly by match time."""

    frames: tuple[Frame, ...]
    start_time: MatchTime
    end_time: MatchTime

    def __post_init__(self) -> None:
        """Validate the integrity of the time range sequence."""
        if not self.frames:
            raise ValueError("Time range sequence must contain at least one frame.")

        if self.start_time.period != self.end_time.period:
            raise ValueError("Sequence start and end must belong to the same period.")

        if self.end_time.seconds <= self.start_time.seconds:
            raise ValueError("Sequence end must be after sequence start.")

        for frame in self.frames:
            if frame.time.period != self.start_time.period:
                raise ValueError("Sequence contains a frame from another period.")

            if not (self.start_time.seconds <= frame.time.seconds <= self.end_time.seconds):
                raise ValueError(f"Frame {frame.frame_index} lies outside the selected time range.")

    @property
    def duration_seconds(self) -> float:
        return self.end_time.seconds - self.start_time.seconds

    @property
    def first_frame(self) -> Frame:
        return self.frames[0]

    @property
    def last_frame(self) -> Frame:
        return self.frames[-1]


type SelectedSequence = EventSequence | TimeRangeSequence


def _validate_seconds(
    value: float,
    name: str,
) -> None:
    """
    Validate that a time value is finite and non-negative.

    Args:
        value (float): The time value to validate.
        name (str): The name of the time value for error messages.
    Raises:
        SequenceSelectionError: If the value is not finite or is negative.
    """
    if not isfinite(value):
        raise SequenceSelectionError(f"{name} must be finite.")

    if value < 0:
        raise SequenceSelectionError(f"{name} cannot be negative.")


def _period_frames(
    match: Match,
    period: PeriodType,
) -> tuple[Frame, ...]:
    """
    Retrieve all tracking frames for a specific match period.

    Args:
        match (Match): The match object containing tracking frames.
        period (PeriodType): The period for which to retrieve frames.

    Returns:
        tuple[Frame, ...]: A tuple of frames corresponding to the specified period."""
    frames = tuple(
        sorted(
            (frame for frame in match.frames if frame.time.period == period),
            key=lambda frame: (
                frame.time.seconds,
                frame.frame_index,
            ),
        )
    )

    if not frames:
        raise SequenceSelectionError(f"No tracking frames available for {period.value}.")

    return frames


def _period_end_seconds(
    match: Match,
    period: PeriodType,
    frames: tuple[Frame, ...],
) -> float:
    """
    Determine the end time of a match period in seconds.

    Args:
        match (Match): The match object containing period information.
        period (PeriodType): The period for which to determine the end time.
        frames (tuple[Frame, ...]): The frames corresponding to the specified period.

    Returns:
        float: The end time of the match period in seconds."""
    for match_period in match.periods:
        if match_period.period == period and match_period.duration_seconds is not None:
            return match_period.duration_seconds

    return frames[-1].time.seconds


def _validate_period_window(
    period: PeriodType,
    start_seconds: float,
    end_seconds: float,
    period_end: float,
) -> None:
    """Validate that the requested range stays within a single period."""
    if start_seconds > period_end:
        raise SequenceSelectionError(
            f"start_seconds ({start_seconds:.3f}) exceeds "
            f"the {period.value} duration "
            f"({period_end:.3f}s)."
        )

    if end_seconds > period_end:
        raise SequenceSelectionError(
            f"end_seconds ({end_seconds:.3f}) exceeds "
            f"the {period.value} duration "
            f"({period_end:.3f}s)."
        )


def select_event_sequence(
    match: Match,
    event_id: str,
    *,
    pre_event_seconds: float,
    post_event_seconds: float,
) -> EventSequence:
    """
    Select a tracking sequence around a match event.

    Args:
        match (Match): The match object containing events and tracking frames.
        event_id (str): The ID of the event to select.
        pre_event_seconds (float): The number of seconds to include before the event.
        post_event_seconds (float): The number of seconds to include after the event.

    Returns:
        EventSequence: The selected event sequence.
    Raises:
        SequenceSelectionError: If the event ID is empty or the selection is invalid."""

    if not event_id.strip():
        raise SequenceSelectionError("Event ID cannot be empty.")

    return extract_sequence_by_id(
        match,
        event_id,
        pre_event_seconds=pre_event_seconds,
        post_event_seconds=post_event_seconds,
    )


def select_time_range(
    match: Match,
    *,
    period: PeriodType,
    start_seconds: float,
    end_seconds: float,
) -> TimeRangeSequence:
    """
    Select tracking frames for an explicit period-relative time range.

    Args:
        match (Match): The match object containing tracking frames.
        period (PeriodType): The period for which to select frames.
        start_seconds (float): The start time in seconds for the selection.
        end_seconds (float): The end time in seconds for the selection.

    Returns:
        TimeRangeSequence: The selected time range sequence.
    Raises:
        SequenceSelectionError: If the selection is invalid or no frames are found."""

    _validate_seconds(
        start_seconds,
        "start_seconds",
    )

    _validate_seconds(
        end_seconds,
        "end_seconds",
    )

    if end_seconds <= start_seconds:
        raise SequenceSelectionError("end_seconds must be greater than start_seconds.")

    frames = _period_frames(
        match,
        period,
    )

    period_end = _period_end_seconds(
        match,
        period,
        frames,
    )

    _validate_period_window(
        period,
        start_seconds,
        end_seconds,
        period_end,
    )

    frame_times = tuple(frame.time.seconds for frame in frames)

    start_index = bisect_left(
        frame_times,
        start_seconds,
    )

    end_index = bisect_right(
        frame_times,
        end_seconds,
    )

    selected_frames = frames[start_index:end_index]

    if not selected_frames:
        raise SequenceSelectionError(
            f"No tracking frames found between "
            f"{start_seconds:.3f}s and "
            f"{end_seconds:.3f}s in {period.value}."
        )

    return TimeRangeSequence(
        frames=selected_frames,
        start_time=MatchTime(
            period=period,
            seconds=start_seconds,
        ),
        end_time=MatchTime(
            period=period,
            seconds=end_seconds,
        ),
    )

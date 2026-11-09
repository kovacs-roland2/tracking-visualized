"""Helpers shared by event-sequence extraction and manual time-range selection."""

from bisect import bisect_left, bisect_right
from math import isfinite
from typing import Protocol

from tracking_visualized.domain import Frame, Match, MatchTime, PeriodType


class TimedFrame(Protocol):
    """Anything with a match time, e.g. a ``Frame`` or a timeline ``FrameTime``."""

    @property
    def time(self) -> MatchTime: ...


def validate_seconds(
    value: float,
    name: str,
    error_cls: type[Exception],
) -> None:
    """Validate that a time value is finite and non-negative.

    Args:
        value: The time value to validate.
        name: The name of the value, used in error messages.
        error_cls: The exception type to raise for an invalid value.
    """
    if not isfinite(value):
        raise error_cls(f"{name} must be finite.")

    if value < 0:
        raise error_cls(f"{name} cannot be negative.")


def period_frames(
    match: Match,
    period: PeriodType,
    error_cls: type[Exception],
) -> tuple[Frame, ...]:
    """Return the tracking frames of one period in chronological order.

    Raises:
        error_cls: If the match has no tracking frames for ``period``.
    """
    frames = tuple(
        sorted(
            (frame for frame in match.frames if frame.time.period == period),
            key=lambda frame: (frame.time.seconds, frame.frame_index),
        )
    )

    if not frames:
        raise error_cls(f"No tracking frames available for {period.value}.")

    return frames


def period_end_seconds(
    match: Match,
    period: PeriodType,
    frames: tuple[Frame, ...],
) -> float:
    """Return the end of a period in seconds.

    Uses the period duration from the match when known, otherwise the time of the
    last tracking frame. ``frames`` must be the non-empty frames of ``period``.
    """
    for match_period in match.periods:
        if match_period.period == period and match_period.duration_seconds is not None:
            return match_period.duration_seconds

    return frames[-1].time.seconds


def frames_in_window[T: TimedFrame](
    frames: tuple[T, ...],
    start_seconds: float,
    end_seconds: float,
) -> tuple[T, ...]:
    """Return the frames whose time lies in ``[start_seconds, end_seconds]``.

    ``frames`` must be ordered by time, as returned by ``period_frames``.
    """
    times = [frame.time.seconds for frame in frames]

    start_index = bisect_left(times, start_seconds)
    end_index = bisect_right(times, end_seconds)

    return frames[start_index:end_index]

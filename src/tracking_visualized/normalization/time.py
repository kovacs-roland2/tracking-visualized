from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from tracking_visualized.domain import (
    MatchTime,
    PeriodType,
)


@dataclass(frozen=True, slots=True)
class SourceFrameTime:
    period: PeriodType
    source_frame_number: int
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.source_frame_number < 0:
            raise ValueError("Source frame number cannot be negative.")

        if self.timestamp.tzinfo is None:
            raise ValueError("Source frame timestamp must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class FrameTime:
    source_frame_number: int
    frame_index: int
    timestamp: datetime
    time: MatchTime


@dataclass(frozen=True, slots=True)
class PeriodTimeline:
    period: PeriodType

    source_start_frame: int
    source_end_frame: int

    global_start_index: int

    start_timestamp: datetime
    end_timestamp: datetime

    frame_rate: float

    frames: tuple[FrameTime, ...]


class MatchTimeline:
    def __init__(
        self,
        periods: tuple[PeriodTimeline, ...],
    ) -> None:
        self.periods = periods

        self._periods_by_type = {period.period: period for period in periods}

        self._frames_by_source = {
            (
                frame.time.period,
                frame.source_frame_number,
            ): frame
            for period in periods
            for frame in period.frames
        }

    @classmethod
    def from_source_frames(
        cls,
        source_frames: list[SourceFrameTime],
    ) -> "MatchTimeline":
        """
        Create a MatchTimeline from a list of SourceFrameTime samples.

        Args:
            source_frames (list[SourceFrameTime]): A list of SourceFrameTime samples.

        Returns:
            MatchTimeline: The constructed MatchTimeline object."""
        if not source_frames:
            raise ValueError("No tracking frames provided.")

        periods: list[PeriodTimeline] = []
        global_start_index = 0

        for period_type in (
            PeriodType.FIRST_HALF,
            PeriodType.SECOND_HALF,
        ):
            period_samples = [frame for frame in source_frames if frame.period == period_type]

            if not period_samples:
                continue

            period_timeline = _build_period_timeline(
                period=period_type,
                samples=period_samples,
                global_start_index=global_start_index,
            )

            periods.append(period_timeline)

            span = period_timeline.source_end_frame - period_timeline.source_start_frame + 1
            global_start_index += span

        if not periods:
            raise ValueError("No tracking frames provided.")

        return cls(
            periods=tuple(periods),
        )

    def normalize_tracking_time(
        self,
        period: PeriodType,
        source_frame_number: int,
        timestamp: datetime,
    ) -> tuple[int, MatchTime]:
        """
        Normalize the tracking time based on the provided period,
        source frame number, and timestamp.

        Args:
            period (PeriodType): The period type for the tracking time.
            source_frame_number (int): The source frame number.
            timestamp (datetime): The timestamp of the tracking time.

        Returns:
            tuple[int, MatchTime]: Tuple containing the normalized frame index and MatchTime object.
        """
        period_timeline = self._periods_by_type[period]

        frame_index = (
            period_timeline.global_start_index
            + source_frame_number
            - period_timeline.source_start_frame
        )

        seconds = (timestamp - period_timeline.start_timestamp).total_seconds()

        if seconds < 0:
            raise ValueError("Tracking timestamp precedes period start.")

        return (
            frame_index,
            MatchTime(
                period=period,
                seconds=seconds,
            ),
        )

    def frame_for_source_number(
        self,
        period: PeriodType,
        source_frame_number: int,
    ) -> FrameTime | None:
        """
        Retrieve the FrameTime for the given period and source frame number.

        Args:
            period (PeriodType): The period type for the frame.
            source_frame_number (int): The source frame number.

        Returns:
            FrameTime | None: The corresponding FrameTime object if found, otherwise None."""
        return self._frames_by_source.get(
            (
                period,
                source_frame_number,
            )
        )

    def nearest_frame(
        self,
        period: PeriodType,
        timestamp: datetime,
        max_difference_seconds: float | None = None,
    ) -> FrameTime | None:
        """
        Find the nearest FrameTime to the given timestamp within the specified period.

        Args:
            period (PeriodType): The period type for the frame.
            timestamp (datetime): The timestamp to find the nearest frame for.
            max_difference_seconds (float | None): Optional maximum allowed difference in seconds.

        Returns:
            FrameTime | None: The nearest FrameTime object if found
            within the allowed difference, otherwise"""
        timeline = self._periods_by_type.get(period)

        if timeline is None:
            return None

        frames = timeline.frames
        timestamps = [frame.timestamp for frame in frames]

        index = bisect_left(
            timestamps,
            timestamp,
        )

        candidates: list[FrameTime] = []

        if index < len(frames):
            candidates.append(frames[index])

        if index > 0:
            candidates.append(frames[index - 1])

        if not candidates:
            return None

        closest = min(
            candidates,
            key=lambda frame: abs((frame.timestamp - timestamp).total_seconds()),
        )

        difference = abs((closest.timestamp - timestamp).total_seconds())

        if max_difference_seconds is not None and difference > max_difference_seconds:
            return None

        return closest


def _estimate_frame_rate(
    samples: list[SourceFrameTime],
) -> float:
    """
    Estimate the frame rate of the source video based on the provided samples.

    Args:
        samples (list[SourceFrameTime]): A list of SourceFrameTime samples.

    Returns:
        float: The estimated frame rate of the source video.
    """
    estimates: list[float] = []

    for previous, current in zip(
        samples,
        samples[1:],
        strict=False,
    ):
        frame_delta = current.source_frame_number - previous.source_frame_number

        time_delta = (current.timestamp - previous.timestamp).total_seconds()

        if frame_delta <= 0 or time_delta <= 0:
            continue

        estimates.append(frame_delta / time_delta)

    if not estimates:
        raise ValueError("Unable to estimate tracking frame rate.")

    return median(estimates)


def _build_period_timeline(
    period: PeriodType,
    samples: list[SourceFrameTime],
    global_start_index: int,
) -> PeriodTimeline:
    """
    Build a PeriodTimeline from the provided samples.

    Args:
        period (PeriodType): The period type for the timeline.
        samples (list[SourceFrameTime]): A list of SourceFrameTime samples.
        global_start_index (int): The global start index for the timeline.

    Returns:
        PeriodTimeline: The constructed PeriodTimeline object.
    """
    if not samples:
        raise ValueError(f"No tracking frames for {period.value}.")

    samples = sorted(
        samples,
        key=lambda sample: sample.source_frame_number,
    )

    source_numbers = [sample.source_frame_number for sample in samples]

    if len(source_numbers) != len(set(source_numbers)):
        raise ValueError(f"Duplicate source frames in {period.value}.")

    source_start = samples[0].source_frame_number
    source_end = samples[-1].source_frame_number

    start_timestamp = samples[0].timestamp

    frames = tuple(
        FrameTime(
            source_frame_number=sample.source_frame_number,
            frame_index=(global_start_index + sample.source_frame_number - source_start),
            timestamp=sample.timestamp,
            time=MatchTime(
                period=period,
                seconds=(sample.timestamp - start_timestamp).total_seconds(),
            ),
        )
        for sample in samples
    )

    return PeriodTimeline(
        period=period,
        source_start_frame=source_start,
        source_end_frame=source_end,
        global_start_index=global_start_index,
        start_timestamp=start_timestamp,
        end_timestamp=samples[-1].timestamp,
        frame_rate=_estimate_frame_rate(samples),
        frames=frames,
    )

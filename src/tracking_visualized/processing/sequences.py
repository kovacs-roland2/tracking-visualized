from dataclasses import dataclass

from tracking_visualized.domain import (
    Event,
    Frame,
    Match,
    MatchTime,
)
from tracking_visualized.processing.events import EventCatalog
from tracking_visualized.processing.frame_windows import (
    frames_in_window,
    period_end_seconds,
    period_frames,
    validate_seconds,
)


class SequenceExtractionError(ValueError):
    """Raised when an event sequence cannot be extracted."""


@dataclass(frozen=True, slots=True)
class EventSequence:
    event: Event
    frames: tuple[Frame, ...]

    requested_pre_seconds: float
    requested_post_seconds: float

    start_time: MatchTime
    end_time: MatchTime

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("Event sequence must contain at least one frame.")

        if self.start_time.period != self.event.time.period:
            raise ValueError("Sequence start must be in the event period.")

        if self.end_time.period != self.event.time.period:
            raise ValueError("Sequence end must be in the event period.")

        if self.start_time.seconds > self.event.time.seconds:
            raise ValueError("Sequence cannot start after the event.")

        if self.end_time.seconds < self.event.time.seconds:
            raise ValueError("Sequence cannot end before the event.")

        if self.end_time.seconds < self.start_time.seconds:
            raise ValueError("Sequence end cannot precede sequence start.")

        for frame in self.frames:
            if frame.time.period != self.event.time.period:
                raise ValueError("Sequence contains a frame from another period.")

            if not (self.start_time.seconds <= frame.time.seconds <= self.end_time.seconds):
                raise ValueError(
                    f"Frame {frame.frame_index} lies outside the sequence time window."
                )

        if self.event.frame_index is not None:
            frame_indices = {frame.frame_index for frame in self.frames}

            if self.event.frame_index not in frame_indices:
                raise ValueError(
                    "The event's referenced tracking frame is not present in the sequence."
                )

    @property
    def requested_duration_seconds(self) -> float:
        return self.requested_pre_seconds + self.requested_post_seconds

    @property
    def duration_seconds(self) -> float:
        return self.end_time.seconds - self.start_time.seconds

    @property
    def effective_pre_seconds(self) -> float:
        return self.event.time.seconds - self.start_time.seconds

    @property
    def effective_post_seconds(self) -> float:
        return self.end_time.seconds - self.event.time.seconds

    @property
    def tracking_span_seconds(self) -> float:
        if len(self.frames) == 1:
            return 0.0

        return self.frames[-1].time.seconds - self.frames[0].time.seconds

    @property
    def is_truncated(self) -> bool:
        return (
            self.effective_pre_seconds < self.requested_pre_seconds
            or self.effective_post_seconds < self.requested_post_seconds
        )

    @property
    def event_frame(self) -> Frame | None:
        if self.event.frame_index is None:
            return None

        for frame in self.frames:
            if frame.frame_index == self.event.frame_index:
                return frame

        return None


def extract_sequence(
    match: Match,
    event: Event,
    *,
    pre_event_seconds: float,
    post_event_seconds: float,
) -> EventSequence:
    """
    Extract tracking frames around a selected event.

    Args:
        match (Match): The match object containing tracking frames.
        event (Event): The event around which to extract the sequence.
        pre_event_seconds (float): The number of seconds to include before the event.
        post_event_seconds (float): The number of seconds to include after the event.

    Returns:
        EventSequence: The extracted sequence of frames around the event.
    """
    validate_seconds(pre_event_seconds, "pre_event_seconds", SequenceExtractionError)
    validate_seconds(post_event_seconds, "post_event_seconds", SequenceExtractionError)

    frames_of_period = period_frames(match, event.time.period, SequenceExtractionError)
    period_end = period_end_seconds(match, event.time.period, frames_of_period)

    if event.time.seconds > period_end:
        raise SequenceExtractionError(
            f"Event '{event.event_id}' occurs at "
            f"{event.time.seconds:.3f}s, beyond the "
            f"{event.time.period.value} boundary "
            f"of {period_end:.3f}s."
        )

    start_seconds = max(
        0.0,
        event.time.seconds - pre_event_seconds,
    )

    end_seconds = min(
        period_end,
        event.time.seconds + post_event_seconds,
    )

    frames = frames_in_window(frames_of_period, start_seconds, end_seconds)

    if not frames:
        raise SequenceExtractionError(
            f"No tracking frames found between "
            f"{start_seconds:.3f}s and "
            f"{end_seconds:.3f}s for event "
            f"'{event.event_id}'."
        )

    return EventSequence(
        event=event,
        frames=frames,
        requested_pre_seconds=pre_event_seconds,
        requested_post_seconds=post_event_seconds,
        start_time=MatchTime(
            period=event.time.period,
            seconds=start_seconds,
        ),
        end_time=MatchTime(
            period=event.time.period,
            seconds=end_seconds,
        ),
    )


def extract_sequence_by_id(
    match: Match,
    event_id: str,
    *,
    pre_event_seconds: float,
    post_event_seconds: float,
) -> EventSequence:
    """
    Extract a sequence around an event selected by ID.

    Args:
        match (Match): The match object containing tracking frames.
        event_id (str): The ID of the event around which to extract the sequence.
        pre_event_seconds (float): The number of seconds to include before the event.
        post_event_seconds (float): The number of seconds to include after the event.

    Returns:
        EventSequence: The extracted sequence of frames around the event.
    """
    catalog = EventCatalog.from_match(match)

    event = catalog.get_event(event_id)

    return extract_sequence(
        match,
        event,
        pre_event_seconds=pre_event_seconds,
        post_event_seconds=post_event_seconds,
    )

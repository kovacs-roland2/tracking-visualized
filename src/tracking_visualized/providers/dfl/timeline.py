from dataclasses import dataclass

from tracking_visualized.domain import PeriodType
from tracking_visualized.domain.models import MatchTime
from tracking_visualized.normalization.time import (
    MatchTimeline,
    SourceFrameTime,
)
from tracking_visualized.providers.dfl.events import (
    ShotEvent,
    to_domain_period,
)
from tracking_visualized.providers.dfl.tracking import (
    BallTrackingSample,
    TrackingPeriod,
)


def _to_domain_period(
    period: TrackingPeriod,
) -> PeriodType:
    """
    Convert a DFL tracking period to a domain period type.

    Args:
        period (TrackingPeriod): The DFL tracking period to convert.

    Returns:
        PeriodType: The corresponding domain period type."""
    if period == TrackingPeriod.FIRST_HALF:
        return PeriodType.FIRST_HALF

    if period == TrackingPeriod.SECOND_HALF:
        return PeriodType.SECOND_HALF

    raise ValueError(f"Unsupported tracking period: {period}")


def build_match_timeline(
    ball_samples: list[BallTrackingSample],
) -> MatchTimeline:
    """
    Build a normalized match timeline from DFL ball tracking.

    Args:
        ball_samples (list[BallTrackingSample]): A list of DFL ball tracking samples.

    Returns:
        MatchTimeline: The constructed MatchTimeline object.
    """

    source_frames: list[SourceFrameTime] = []

    seen_frames: set[tuple[PeriodType, int]] = set()

    for sample in ball_samples:
        period = _to_domain_period(sample.period)

        key = (
            period,
            sample.frame_number,
        )

        if key in seen_frames:
            continue

        seen_frames.add(key)

        source_frames.append(
            SourceFrameTime(
                period=period,
                source_frame_number=sample.frame_number,
                timestamp=sample.timestamp,
            )
        )

    return MatchTimeline.from_source_frames(source_frames)


@dataclass(frozen=True, slots=True)
class NormalizedEventTime:
    time: MatchTime
    frame_index: int | None


def normalize_shot_time(
    shot: ShotEvent,
    timeline: MatchTimeline,
) -> NormalizedEventTime:
    period = to_domain_period(shot.period)

    # Best option: Sportec already calculated the corresponding
    # tracking frame.
    if shot.calculated_frame is not None:
        frame = timeline.frame_for_source_number(
            period,
            shot.calculated_frame,
        )

        if frame is not None:
            return NormalizedEventTime(
                time=frame.time,
                frame_index=frame.frame_index,
            )

    # Fallback: use Sportec's calculated timestamp and find
    # the nearest observed tracking frame.
    if shot.calculated_timestamp is not None:
        frame = timeline.nearest_frame(
            period,
            shot.calculated_timestamp,
            max_difference_seconds=0.1,
        )

        if frame is not None:
            return NormalizedEventTime(
                time=frame.time,
                frame_index=frame.frame_index,
            )

    # Final fallback: preserve event timing even if we cannot
    # associate it with an observed tracking frame.
    return NormalizedEventTime(
        time=MatchTime(
            period=period,
            seconds=shot.period_seconds,
        ),
        frame_index=None,
    )

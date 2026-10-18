from datetime import datetime, timedelta, timezone

import pytest

from tracking_visualized.domain import PeriodType
from tracking_visualized.normalization.time import (
    MatchTimeline,
    SourceFrameTime,
)

START = datetime(
    2023,
    5,
    27,
    13,
    30,
    tzinfo=timezone.utc,
)


def sample(
    period: PeriodType,
    frame: int,
    seconds: float,
) -> SourceFrameTime:
    return SourceFrameTime(
        period=period,
        source_frame_number=frame,
        timestamp=START + timedelta(seconds=seconds),
    )


def test_first_half_normalization():
    timeline = MatchTimeline.from_source_frames(
        [
            sample(
                PeriodType.FIRST_HALF,
                10000,
                0.00,
            ),
            sample(
                PeriodType.FIRST_HALF,
                10001,
                0.04,
            ),
            sample(
                PeriodType.FIRST_HALF,
                10002,
                0.08,
            ),
            sample(
                PeriodType.SECOND_HALF,
                20000,
                3600.00,
            ),
            sample(
                PeriodType.SECOND_HALF,
                20001,
                3600.04,
            ),
        ]
    )

    frame = timeline.frame_for_source_number(
        PeriodType.FIRST_HALF,
        10001,
    )

    assert frame is not None
    assert frame.frame_index == 1
    assert frame.time.seconds == 0.04


def test_second_half_time_resets():
    timeline = MatchTimeline.from_source_frames(
        [
            sample(
                PeriodType.FIRST_HALF,
                100,
                0.00,
            ),
            sample(
                PeriodType.FIRST_HALF,
                101,
                0.04,
            ),
            sample(
                PeriodType.SECOND_HALF,
                500,
                1000.00,
            ),
            sample(
                PeriodType.SECOND_HALF,
                501,
                1000.04,
            ),
        ]
    )

    frame = timeline.frame_for_source_number(
        PeriodType.SECOND_HALF,
        500,
    )

    assert frame is not None
    assert frame.time.seconds == 0.0
    assert frame.frame_index == 2
    assert frame.timestamp == (START + timedelta(seconds=1000))
    assert frame.time.seconds == 0.0
    assert frame.frame_index == 2


def test_missing_frame_gap_is_preserved():
    timeline = MatchTimeline.from_source_frames(
        [
            sample(
                PeriodType.FIRST_HALF,
                100,
                0.00,
            ),
            sample(
                PeriodType.FIRST_HALF,
                101,
                0.04,
            ),
            sample(
                PeriodType.FIRST_HALF,
                103,
                0.12,
            ),
            sample(
                PeriodType.SECOND_HALF,
                500,
                1000.00,
            ),
            sample(
                PeriodType.SECOND_HALF,
                501,
                1000.04,
            ),
        ]
    )

    frame = timeline.frame_for_source_number(
        PeriodType.FIRST_HALF,
        103,
    )

    assert frame is not None
    assert frame.frame_index == 3
    assert frame.time.seconds == 0.12

    missing = timeline.frame_for_source_number(
        PeriodType.FIRST_HALF,
        102,
    )

    assert missing is None


def test_frame_rate_handles_missing_frames():
    timeline = MatchTimeline.from_source_frames(
        [
            sample(
                PeriodType.FIRST_HALF,
                100,
                0.00,
            ),
            sample(
                PeriodType.FIRST_HALF,
                102,
                0.08,
            ),
            sample(
                PeriodType.FIRST_HALF,
                103,
                0.12,
            ),
            sample(
                PeriodType.SECOND_HALF,
                500,
                1000.00,
            ),
            sample(
                PeriodType.SECOND_HALF,
                501,
                1000.04,
            ),
        ]
    )

    period = timeline.periods[0]

    assert period.frame_rate == 25.0


def test_nearest_timestamp_maps_to_frame():
    timeline = MatchTimeline.from_source_frames(
        [
            sample(
                PeriodType.FIRST_HALF,
                100,
                0.00,
            ),
            sample(
                PeriodType.FIRST_HALF,
                101,
                0.04,
            ),
            sample(
                PeriodType.FIRST_HALF,
                102,
                0.08,
            ),
        ]
    )

    result = timeline.nearest_frame(
        PeriodType.FIRST_HALF,
        START
        + timedelta(
            seconds=0.041,
        ),
    )

    assert result is not None
    assert result.source_frame_number == 101


def test_timestamp_outside_tolerance_returns_none():
    timeline = MatchTimeline.from_source_frames(
        [
            sample(
                PeriodType.FIRST_HALF,
                100,
                0.00,
            ),
            sample(
                PeriodType.FIRST_HALF,
                101,
                0.04,
            ),
            sample(
                PeriodType.FIRST_HALF,
                102,
                0.08,
            ),
        ]
    )

    result = timeline.nearest_frame(
        PeriodType.FIRST_HALF,
        START
        + timedelta(
            seconds=10,
        ),
        max_difference_seconds=0.1,
    )

    assert result is None


def test_naive_timestamp_is_rejected():
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        SourceFrameTime(
            period=PeriodType.FIRST_HALF,
            source_frame_number=100,
            timestamp=datetime(
                2023,
                5,
                27,
                13,
                30,
            ),
        )

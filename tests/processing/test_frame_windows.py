import math

import pytest

from tracking_visualized.domain import (
    CoordinateSystem,
    Frame,
    Match,
    MatchMetadata,
    MatchTime,
    Period,
    PeriodType,
    Team,
    TeamSide,
)
from tracking_visualized.processing.frame_windows import (
    frames_in_window,
    period_end_seconds,
    period_frames,
    validate_seconds,
)


def make_frame(index: int, seconds: float, period: PeriodType = PeriodType.FIRST_HALF) -> Frame:
    return Frame(
        frame_index=index,
        time=MatchTime(period=period, seconds=seconds),
        player_positions=(),
        ball_position=None,
    )


def make_match(frames: tuple[Frame, ...], periods: tuple[Period, ...] = ()) -> Match:
    return Match(
        metadata=MatchMetadata(match_id="m1", competition="Liga", season="2026"),
        coordinate_system=CoordinateSystem(pitch_length=105.0, pitch_width=68.0),
        periods=periods,
        teams=(
            Team(team_id="home", name="Home", side=TeamSide.HOME),
            Team(team_id="away", name="Away", side=TeamSide.AWAY),
        ),
        players=(),
        frames=frames,
        events=(),
    )


class CustomError(ValueError):
    pass


@pytest.mark.parametrize("value", [math.nan, math.inf, -1.0])
def test_validate_seconds_rejects_bad_values_with_given_error(value):
    with pytest.raises(CustomError):
        validate_seconds(value, "pre", CustomError)


def test_validate_seconds_accepts_zero_and_positive():
    validate_seconds(0.0, "pre", CustomError)
    validate_seconds(12.5, "pre", CustomError)


def test_period_frames_filters_and_orders_by_time():
    match = make_match(
        (
            make_frame(3, 2.0),
            make_frame(1, 0.0),
            make_frame(2, 1.0),
            make_frame(9, 0.5, PeriodType.SECOND_HALF),
        )
    )

    frames = period_frames(match, PeriodType.FIRST_HALF, CustomError)

    assert [f.frame_index for f in frames] == [1, 2, 3]


def test_period_frames_raises_given_error_when_empty():
    match = make_match((make_frame(1, 0.0),))

    with pytest.raises(CustomError, match="second_half"):
        period_frames(match, PeriodType.SECOND_HALF, CustomError)


def test_period_end_prefers_known_duration_over_last_frame():
    frames = (make_frame(1, 0.0), make_frame(2, 10.0))

    with_duration = make_match(
        frames, (Period(period=PeriodType.FIRST_HALF, duration_seconds=2700.0),)
    )
    without_duration = make_match(frames, (Period(period=PeriodType.FIRST_HALF),))

    assert period_end_seconds(with_duration, PeriodType.FIRST_HALF, frames) == 2700.0
    assert period_end_seconds(without_duration, PeriodType.FIRST_HALF, frames) == 10.0


def test_frames_in_window_is_inclusive_on_both_ends():
    frames = tuple(make_frame(i, float(i)) for i in range(10))

    window = frames_in_window(frames, 2.0, 5.0)

    assert [f.frame_index for f in window] == [2, 3, 4, 5]
    assert frames_in_window(frames, 20.0, 30.0) == ()

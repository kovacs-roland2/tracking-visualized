import pytest

from tracking_visualized.domain import (
    BallPosition,
    Event,
    EventType,
    Frame,
    MatchTime,
    PeriodType,
    PlayerPosition,
    ShotOutcome,
)
from tracking_visualized.processing import (
    EventSequence,
    TrackingGapPolicy,
    TrackingRepairReport,
    repair_sequence_tracking,
)


def _make_sequence(*frames: Frame) -> EventSequence:
    event_time = frames[0].time.seconds
    event = Event(
        event_id="evt-1",
        event_type=EventType.SHOT,
        time=MatchTime(PeriodType.FIRST_HALF, event_time),
        shot_outcome=ShotOutcome.OTHER,
    )

    start_time = MatchTime(PeriodType.FIRST_HALF, min(frame.time.seconds for frame in frames))
    end_time = MatchTime(PeriodType.FIRST_HALF, max(frame.time.seconds for frame in frames))

    return EventSequence(
        event=event,
        frames=frames,
        requested_pre_seconds=0.0,
        requested_post_seconds=0.0,
        start_time=start_time,
        end_time=end_time,
    )


def _frame(
    index: int,
    seconds: float,
    *,
    player_x: float | None = None,
    player_y: float | None = None,
    ball: BallPosition | None = None,
) -> Frame:
    positions = ()
    if player_x is not None or player_y is not None:
        positions = (
            PlayerPosition(
                player_id="player-7",
                x=player_x,
                y=player_y,
            ),
        )

    return Frame(
        frame_index=index,
        time=MatchTime(PeriodType.FIRST_HALF, seconds),
        player_positions=positions,
        ball_position=ball,
    )


def test_repair_sequence_tracking_interpolates_missing_player_and_ball_positions():
    sequence = _make_sequence(
        _frame(100, 10.00, player_x=20.0, player_y=30.0, ball=BallPosition(10.0, 20.0, z=0.0)),
        _frame(101, 10.04, player_x=None, player_y=None, ball=None),
        _frame(102, 10.08, player_x=24.0, player_y=32.0, ball=BallPosition(30.0, 40.0, z=10.0)),
    )

    repaired, report = repair_sequence_tracking(sequence)

    player_position = repaired.frames[1].player_positions[0]
    assert player_position.x == pytest.approx(22.0)
    assert player_position.y == pytest.approx(31.0)

    ball_position = repaired.frames[1].ball_position
    assert ball_position is not None
    assert ball_position.x == pytest.approx(20.0)
    assert ball_position.y == pytest.approx(30.0)
    assert ball_position.z == pytest.approx(5.0)

    assert report.interpolated_player_positions == 1
    assert report.interpolated_ball_positions == 1
    assert report.is_complete is True


def test_repair_sequence_tracking_respects_gap_policy_and_marks_unresolved():
    sequence = _make_sequence(
        _frame(200, 20.00, player_x=10.0, player_y=10.0),
        _frame(201, 20.60, player_x=None, player_y=None),
        _frame(202, 21.00, player_x=10.0, player_y=10.0),
    )

    repaired, report = repair_sequence_tracking(
        sequence,
        policy=TrackingGapPolicy(max_player_gap_seconds=0.2),
    )

    assert report.interpolated_player_positions == 0
    assert report.unresolved_player_positions == 1
    assert repaired.frames[1].player_positions == ()
    assert report.is_complete is False

    repaired, report = repair_sequence_tracking(
        sequence,
        policy=TrackingGapPolicy(interpolate_players=False),
    )

    assert report.interpolated_player_positions == 0
    assert report.unresolved_player_positions == 0
    assert repaired.frames[1].player_positions == ()


def test_repair_sequence_tracking_preserves_known_coordinates_for_partial_observations():
    sequence = _make_sequence(
        _frame(300, 30.0, player_x=10.0, player_y=20.0, ball=BallPosition(40.0, 50.0, z=1.0)),
        _frame(301, 30.1, player_x=12.0, player_y=None, ball=BallPosition(43.0, None, z=1.0)),
        _frame(302, 30.2, player_x=14.0, player_y=24.0, ball=BallPosition(46.0, 55.0, z=1.0)),
    )

    repaired, report = repair_sequence_tracking(sequence)

    player_position = repaired.frames[1].player_positions[0]
    assert player_position.x == pytest.approx(12.0)
    assert player_position.y == pytest.approx(22.0)

    ball_position = repaired.frames[1].ball_position
    assert ball_position is not None
    assert ball_position.x == pytest.approx(43.0)
    assert ball_position.y == pytest.approx(52.5)
    assert ball_position.z == pytest.approx(1.0)

    assert report.interpolated_player_positions == 1
    assert report.interpolated_ball_positions == 1
    assert report.is_complete is True


def test_repair_sequence_tracking_skips_ball_repair_when_disabled():
    sequence = _make_sequence(
        _frame(400, 40.0, ball=BallPosition(0.0, 0.0, z=0.0)),
        _frame(401, 40.04, ball=None),
        _frame(402, 40.08, ball=BallPosition(8.0, 8.0, z=8.0)),
    )

    repaired, report = repair_sequence_tracking(
        sequence,
        policy=TrackingGapPolicy(interpolate_ball=False),
    )

    assert repaired.frames[1].ball_position is None
    assert report.interpolated_ball_positions == 0
    assert report.unresolved_ball_positions == 1
    assert report.is_complete is False


@pytest.mark.parametrize(
    ("kwargs", "error_message"),
    [
        ({"max_player_gap_seconds": float("nan")}, "max_player_gap_seconds"),
        ({"max_player_gap_seconds": -0.1}, "cannot be negative"),
        ({"max_ball_gap_seconds": float("inf")}, "max_ball_gap_seconds"),
    ],
)
def test_tracking_gap_policy_rejects_invalid_values(kwargs, error_message):
    with pytest.raises(ValueError, match=error_message):
        TrackingGapPolicy(**kwargs)


def test_tracking_repair_report_tracks_completion_status():
    repair_report = TrackingRepairReport(
        interpolated_player_positions=2,
        unresolved_player_positions=1,
        interpolated_ball_positions=1,
        unresolved_ball_positions=0,
    )

    assert repair_report.interpolated_positions == 3
    assert repair_report.unresolved_positions == 1
    assert repair_report.is_complete is False

import pytest

from tracking_visualized.cli.sequence_selection import (
    format_sequence_summary,
    select_sequence_from_cli_args,
)
from tracking_visualized.domain import (
    CoordinateSystem,
    Event,
    EventType,
    Frame,
    Match,
    MatchMetadata,
    MatchTime,
    Period,
    PeriodType,
    Player,
    ShotOutcome,
    Team,
    TeamSide,
)
from tracking_visualized.processing import (
    EventSequence,
    TimeRangeSequence,
)


def make_frame(
    frame_index: int,
    seconds: float,
    period: PeriodType,
) -> Frame:
    return Frame(
        frame_index=frame_index,
        time=MatchTime(
            period=period,
            seconds=seconds,
        ),
        player_positions=(),
        ball_position=None,
    )


def build_test_match() -> Match:
    home = Team(
        team_id="home",
        name="Home FC",
        side=TeamSide.HOME,
    )

    away = Team(
        team_id="away",
        name="Away FC",
        side=TeamSide.AWAY,
    )

    player = Player(
        player_id="player-7",
        team_id="home",
        shirt_number=7,
    )

    frames = tuple(
        make_frame(
            frame_index=second,
            seconds=float(second),
            period=PeriodType.FIRST_HALF,
        )
        for second in range(31)
    )

    event = Event(
        event_id="shot-1",
        event_type=EventType.SHOT,
        time=MatchTime(
            period=PeriodType.FIRST_HALF,
            seconds=20.0,
        ),
        team_id="home",
        player_id="player-7",
        frame_index=20,
        shot_outcome=ShotOutcome.GOAL,
    )

    return Match(
        metadata=MatchMetadata(
            match_id="match-1",
            competition="Bundesliga",
            season="2022/2023",
        ),
        coordinate_system=CoordinateSystem(
            pitch_length=105.0,
            pitch_width=68.0,
        ),
        periods=(
            Period(
                period=PeriodType.FIRST_HALF,
                duration_seconds=30.0,
            ),
            Period(
                period=PeriodType.SECOND_HALF,
                duration_seconds=30.0,
            ),
        ),
        teams=(
            home,
            away,
        ),
        players=(player,),
        frames=frames,
        events=(event,),
    )


def test_cli_selects_event():
    match = build_test_match()

    sequence = select_sequence_from_cli_args(
        match,
        [
            "event",
            "--event-id",
            "shot-1",
            "--pre",
            "5",
            "--post",
            "2",
        ],
    )

    assert isinstance(
        sequence,
        EventSequence,
    )

    assert sequence.event.event_id == "shot-1"
    assert sequence.start_time.seconds == 15.0
    assert sequence.end_time.seconds == 22.0


def test_cli_selects_time_range():
    match = build_test_match()

    sequence = select_sequence_from_cli_args(
        match,
        [
            "time",
            "--period",
            "first_half",
            "--start",
            "10",
            "--end",
            "15",
        ],
    )

    assert isinstance(
        sequence,
        TimeRangeSequence,
    )

    assert sequence.start_time.seconds == 10.0
    assert sequence.end_time.seconds == 15.0


def test_cli_event_uses_default_window():
    match = build_test_match()

    sequence = select_sequence_from_cli_args(
        match,
        [
            "event",
            "--event-id",
            "shot-1",
        ],
    )

    assert isinstance(
        sequence,
        EventSequence,
    )

    assert sequence.requested_pre_seconds == 15.0
    assert sequence.requested_post_seconds == 5.0


def test_cli_rejects_negative_time():
    match = build_test_match()

    with pytest.raises(
        SystemExit,
    ):
        select_sequence_from_cli_args(
            match,
            [
                "time",
                "--period",
                "first_half",
                "--start",
                "-1",
                "--end",
                "10",
            ],
        )


def test_event_summary():
    match = build_test_match()

    sequence = select_sequence_from_cli_args(
        match,
        [
            "event",
            "--event-id",
            "shot-1",
            "--pre",
            "5",
            "--post",
            "2",
        ],
    )

    text = format_sequence_summary(sequence)

    assert "shot-1" in text
    assert "Frames:" in text
    assert "Duration:" in text

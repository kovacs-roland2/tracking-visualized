import pytest

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
    SequenceExtractionError,
    extract_sequence,
    extract_sequence_by_id,
)


def make_frame(
    index: int,
    seconds: float,
    period: PeriodType = PeriodType.FIRST_HALF,
) -> Frame:
    return Frame(
        frame_index=index,
        time=MatchTime(
            period=period,
            seconds=seconds,
        ),
        player_positions=(),
        ball_position=None,
    )


def make_event(
    event_id: str,
    seconds: float,
    frame_index: int | None,
    *,
    period: PeriodType = PeriodType.FIRST_HALF,
) -> Event:
    return Event(
        event_id=event_id,
        event_type=EventType.SHOT,
        time=MatchTime(
            period=period,
            seconds=seconds,
        ),
        team_id="home",
        player_id="player-7",
        frame_index=frame_index,
        shot_outcome=ShotOutcome.GOAL,
        x=0.0,
        y=0.0,
        xg=0.5,
    )


def build_test_match(
    *,
    frames: tuple[Frame, ...],
    event_time: float,
    event_id: str = "shot-1",
) -> Match:
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
        name="Player Seven",
        shirt_number=7,
    )
    event = make_event(
        event_id,
        event_time,
        frame_index=int(event_time),
    )

    return Match(
        metadata=MatchMetadata(
            match_id="match-1",
            competition="Test",
            season="2024",
        ),
        coordinate_system=CoordinateSystem(
            pitch_length=105.0,
            pitch_width=68.0,
        ),
        periods=(
            Period(
                period=PeriodType.FIRST_HALF,
                duration_seconds=90.0,
            ),
            Period(
                period=PeriodType.SECOND_HALF,
                duration_seconds=90.0,
            ),
        ),
        teams=(home, away),
        players=(player,),
        frames=frames,
        events=(event,),
    )


def test_extracts_requested_window():
    match = build_test_match(
        frames=tuple(
            make_frame(
                index=second,
                seconds=float(second),
            )
            for second in range(0, 41)
        ),
        event_time=20.0,
    )

    sequence = extract_sequence_by_id(
        match,
        "shot-1",
        pre_event_seconds=15.0,
        post_event_seconds=5.0,
    )

    assert sequence.start_time.seconds == 5.0
    assert sequence.end_time.seconds == 25.0
    assert sequence.duration_seconds == 20.0
    assert sequence.frames[0].time.seconds == 5.0
    assert sequence.frames[-1].time.seconds == 25.0
    assert not sequence.is_truncated


def test_sequence_is_clipped_at_period_start():
    match = build_test_match(
        frames=tuple(
            make_frame(
                index=second,
                seconds=float(second),
            )
            for second in range(0, 31)
        ),
        event_time=5.0,
    )

    sequence = extract_sequence_by_id(
        match,
        "shot-1",
        pre_event_seconds=15.0,
        post_event_seconds=5.0,
    )

    assert sequence.start_time.seconds == 0.0
    assert sequence.end_time.seconds == 10.0
    assert sequence.effective_pre_seconds == 5.0
    assert sequence.effective_post_seconds == 5.0
    assert sequence.is_truncated
    assert all(frame.time.period == PeriodType.FIRST_HALF for frame in sequence.frames)
    assert sequence.frames[0].frame_index == 0
    assert sequence.frames[-1].frame_index == 10
    assert any(frame.frame_index == sequence.event.frame_index for frame in sequence.frames)

    event = match.events[0]

    with pytest.raises(
        SequenceExtractionError,
        match="cannot be negative",
    ):
        extract_sequence(
            match,
            event,
            pre_event_seconds=-1.0,
            post_event_seconds=5.0,
        )

    with pytest.raises(
        KeyError,
        match="Unknown event ID",
    ):
        extract_sequence_by_id(
            match,
            "does-not-exist",
            pre_event_seconds=15.0,
            post_event_seconds=5.0,
        )

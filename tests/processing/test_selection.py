import math

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
    EventSequence,
    SequenceSelectionError,
    TimeRangeSequence,
    select_event_sequence,
    select_time_range,
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
        name="Player Seven",
        shirt_number=7,
    )

    first_half_frames = tuple(
        make_frame(
            frame_index=second,
            seconds=float(second),
            period=PeriodType.FIRST_HALF,
        )
        for second in range(31)
    )

    second_half_frames = tuple(
        make_frame(
            frame_index=100 + second,
            seconds=float(second),
            period=PeriodType.SECOND_HALF,
        )
        for second in range(31)
    )

    shot = Event(
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
        xg=0.25,
    )

    return Match(
        metadata=MatchMetadata(
            match_id="match-1",
            competition="Bundesliga",
            season="2022/2023",
            match_day=34,
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
        frames=(
            *first_half_frames,
            *second_half_frames,
        ),
        events=(shot,),
    )


def test_selects_event_by_id():
    match = build_test_match()

    sequence = select_event_sequence(
        match,
        "shot-1",
        pre_event_seconds=5.0,
        post_event_seconds=3.0,
    )

    assert isinstance(
        sequence,
        EventSequence,
    )

    assert sequence.event.event_id == "shot-1"

    assert sequence.start_time.seconds == 15.0
    assert sequence.end_time.seconds == 23.0

    assert sequence.event_frame is not None
    assert sequence.event_frame.frame_index == 20


def test_selects_manual_time_range():
    match = build_test_match()

    sequence = select_time_range(
        match,
        period=PeriodType.FIRST_HALF,
        start_seconds=10.0,
        end_seconds=15.0,
    )

    assert isinstance(
        sequence,
        TimeRangeSequence,
    )

    assert sequence.start_time.seconds == 10.0
    assert sequence.end_time.seconds == 15.0

    assert sequence.duration_seconds == 5.0

    assert [frame.frame_index for frame in sequence.frames] == [
        10,
        11,
        12,
        13,
        14,
        15,
    ]


def test_manual_selection_uses_requested_period():
    match = build_test_match()

    sequence = select_time_range(
        match,
        period=PeriodType.SECOND_HALF,
        start_seconds=5.0,
        end_seconds=8.0,
    )

    assert all(frame.time.period == PeriodType.SECOND_HALF for frame in sequence.frames)

    assert [frame.frame_index for frame in sequence.frames] == [
        105,
        106,
        107,
        108,
    ]


def test_manual_selection_rejects_reverse_range():
    match = build_test_match()

    with pytest.raises(
        SequenceSelectionError,
        match="greater than",
    ):
        select_time_range(
            match,
            period=PeriodType.FIRST_HALF,
            start_seconds=20.0,
            end_seconds=10.0,
        )


def test_manual_selection_rejects_zero_duration():
    match = build_test_match()

    with pytest.raises(
        SequenceSelectionError,
        match="greater than",
    ):
        select_time_range(
            match,
            period=PeriodType.FIRST_HALF,
            start_seconds=10.0,
            end_seconds=10.0,
        )


def test_manual_selection_rejects_negative_start():
    match = build_test_match()

    with pytest.raises(
        SequenceSelectionError,
        match="cannot be negative",
    ):
        select_time_range(
            match,
            period=PeriodType.FIRST_HALF,
            start_seconds=-1.0,
            end_seconds=10.0,
        )


@pytest.mark.parametrize(
    "value",
    [
        math.nan,
        math.inf,
        -math.inf,
    ],
)
def test_manual_selection_rejects_non_finite_times(
    value: float,
):
    match = build_test_match()

    with pytest.raises(
        SequenceSelectionError,
        match="finite",
    ):
        select_time_range(
            match,
            period=PeriodType.FIRST_HALF,
            start_seconds=value,
            end_seconds=10.0,
        )


def test_manual_selection_rejects_end_beyond_period():
    match = build_test_match()

    with pytest.raises(
        SequenceSelectionError,
        match="exceeds",
    ):
        select_time_range(
            match,
            period=PeriodType.FIRST_HALF,
            start_seconds=20.0,
            end_seconds=31.0,
        )


def test_unknown_event_id_raises():
    match = build_test_match()

    with pytest.raises(
        KeyError,
        match="Unknown event ID",
    ):
        select_event_sequence(
            match,
            "missing-event",
            pre_event_seconds=5.0,
            post_event_seconds=5.0,
        )

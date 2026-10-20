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
    SynchronizationMethod,
    synchronize_match_events,
)


def frame(
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


def event(
    event_id: str,
    seconds: float,
    *,
    frame_index: int | None,
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
    event_frame_index: int | None = None,
    event_period: PeriodType = PeriodType.FIRST_HALF,
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
        events=(
            event(
                event_id,
                event_time,
                frame_index=event_frame_index,
                period=event_period,
            ),
        ),
    )


def test_existing_frame_reference_is_used():
    match = build_test_match(
        frames=(
            frame(100, 10.00),
            frame(101, 10.04),
        ),
        event_time=10.01,
        event_frame_index=101,
    )

    synchronized, report = synchronize_match_events(match)

    event_obj = synchronized.events[0]

    assert event_obj.frame_index == 101
    assert event_obj.time.seconds == 10.04

    result = report.results[0]

    assert result.method == SynchronizationMethod.EXISTING_FRAME
    assert result.time_difference_seconds == pytest.approx(0.03)


def test_event_without_frame_uses_nearest_timestamp():
    match = build_test_match(
        frames=(
            frame(100, 10.00),
            frame(101, 10.04),
            frame(102, 10.08),
        ),
        event_time=10.039,
        event_frame_index=None,
    )

    synchronized, report = synchronize_match_events(match)

    event_obj = synchronized.events[0]

    assert event_obj.frame_index == 101
    assert event_obj.time.seconds == 10.04
    assert report.results[0].method == SynchronizationMethod.NEAREST_TIMESTAMP


def test_event_outside_tolerance_remains_unmatched():
    match = build_test_match(
        frames=(
            frame(100, 10.0),
            frame(101, 10.04),
        ),
        event_time=15.0,
        event_frame_index=None,
    )

    synchronized, report = synchronize_match_events(
        match,
        max_time_difference_seconds=0.1,
    )

    event_obj = synchronized.events[0]

    assert event_obj.frame_index is None
    assert event_obj.time.seconds == 15.0
    assert report.results[0].method == SynchronizationMethod.UNMATCHED
    assert not report.is_complete


def test_invalid_existing_frame_falls_back_to_timestamp():
    match = build_test_match(
        frames=(
            frame(100, 10.00),
            frame(101, 10.04),
        ),
        event_time=10.041,
        event_frame_index=999,
    )

    synchronized, report = synchronize_match_events(match)

    event_obj = synchronized.events[0]

    assert event_obj.frame_index == 101
    assert report.results[0].method == SynchronizationMethod.NEAREST_TIMESTAMP


def test_timestamp_matching_stays_in_same_period():
    match = build_test_match(
        frames=(
            frame(100, 0.00, PeriodType.FIRST_HALF),
            frame(101, 0.04, PeriodType.FIRST_HALF),
            frame(500, 0.00, PeriodType.SECOND_HALF),
            frame(501, 0.04, PeriodType.SECOND_HALF),
        ),
        event_time=0.01,
        event_period=PeriodType.SECOND_HALF,
        event_frame_index=None,
    )

    synchronized, _ = synchronize_match_events(match)

    assert synchronized.events[0].frame_index == 500


def test_missing_frame_tie_prefers_earlier_frame():
    match = build_test_match(
        frames=(
            frame(250, 10.00),
            frame(252, 10.08),
        ),
        event_time=10.04,
        event_frame_index=None,
    )

    synchronized, _ = synchronize_match_events(
        match,
        max_time_difference_seconds=0.05,
    )

    assert synchronized.events[0].frame_index == 250


def test_report_counts_matched_and_unmatched():
    match = Match(
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
            Period(period=PeriodType.FIRST_HALF, duration_seconds=90.0),
            Period(period=PeriodType.SECOND_HALF, duration_seconds=90.0),
        ),
        teams=(
            Team(team_id="home", name="Home FC", side=TeamSide.HOME),
            Team(team_id="away", name="Away FC", side=TeamSide.AWAY),
        ),
        players=(
            Player(player_id="player-7", team_id="home", name="Player Seven", shirt_number=7),
        ),
        frames=(
            frame(100, 10.0),
            frame(101, 10.04),
        ),
        events=(
            event("shot-1", 10.00, frame_index=101),
            event("shot-2", 10.02, frame_index=None),
            event("shot-3", 15.0, frame_index=None),
        ),
    )

    synchronized, report = synchronize_match_events(match, max_time_difference_seconds=0.1)

    assert len(report.matched) == 2
    assert len(report.unmatched) == 1
    assert not report.is_complete

    text = report.format_text()
    assert "Synchronized 2/3" in text

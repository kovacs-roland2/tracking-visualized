import pytest

from tracking_visualized.domain import (
    BallPosition,
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
    PlayerPosition,
    ShotOutcome,
    Team,
    TeamSide,
)
from tracking_visualized.validation import (
    MatchValidationError,
    ValidationSeverity,
    validate_match,
    validate_match_or_raise,
)


def build_valid_match() -> Match:
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

    frame = Frame(
        frame_index=100,
        time=MatchTime(
            period=PeriodType.FIRST_HALF,
            seconds=10.0,
        ),
        player_positions=(
            PlayerPosition(
                player_id="player-7",
                x=50.0,
                y=30.0,
            ),
        ),
        ball_position=BallPosition(
            x=51.0,
            y=30.0,
            z=0.0,
            possession_team_id="home",
            is_in_play=True,
        ),
    )

    shot = Event(
        event_id="shot-1",
        event_type=EventType.SHOT,
        time=MatchTime(
            period=PeriodType.FIRST_HALF,
            seconds=10.0,
        ),
        team_id="home",
        player_id="player-7",
        x=50.0,
        y=30.0,
        frame_index=100,
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
            ),
            Period(
                period=PeriodType.SECOND_HALF,
            ),
        ),
        teams=(home, away),
        players=(player,),
        frames=(frame,),
        events=(shot,),
    )


def test_valid_match_has_no_errors():
    report = validate_match(build_valid_match())

    assert report.is_valid
    assert report.errors == ()


def test_unknown_position_player_is_error():
    match = build_valid_match()

    bad_frame = Frame(
        frame_index=101,
        time=MatchTime(
            period=PeriodType.FIRST_HALF,
            seconds=10.04,
        ),
        player_positions=(
            PlayerPosition(
                player_id="missing-player",
                x=20.0,
                y=20.0,
            ),
        ),
        ball_position=None,
    )

    match = Match(
        metadata=match.metadata,
        coordinate_system=match.coordinate_system,
        periods=match.periods,
        teams=match.teams,
        players=match.players,
        frames=(bad_frame,),
        events=(),
    )

    report = validate_match(match)

    assert not report.is_valid

    assert any(issue.code == "position.unknown_player" for issue in report.errors)


def test_unknown_ball_possession_team_is_error():
    match = build_valid_match()

    frame = Frame(
        frame_index=100,
        time=MatchTime(
            period=PeriodType.FIRST_HALF,
            seconds=10.0,
        ),
        player_positions=(),
        ball_position=BallPosition(
            x=50.0,
            y=34.0,
            possession_team_id="missing-team",
        ),
    )

    match = Match(
        metadata=match.metadata,
        coordinate_system=match.coordinate_system,
        periods=match.periods,
        teams=match.teams,
        players=match.players,
        frames=(frame,),
        events=(),
    )

    report = validate_match(match)

    assert any(issue.code == "ball.unknown_possession_team" for issue in report.errors)


def test_non_monotonic_frame_time_is_error():
    match = build_valid_match()

    frames = (
        Frame(
            frame_index=100,
            time=MatchTime(
                PeriodType.FIRST_HALF,
                10.0,
            ),
            player_positions=(),
            ball_position=None,
        ),
        Frame(
            frame_index=101,
            time=MatchTime(
                PeriodType.FIRST_HALF,
                9.0,
            ),
            player_positions=(),
            ball_position=None,
        ),
    )

    match = Match(
        metadata=match.metadata,
        coordinate_system=match.coordinate_system,
        periods=match.periods,
        teams=match.teams,
        players=match.players,
        frames=frames,
        events=(),
    )

    report = validate_match(match)

    assert any(issue.code == "frame.non_monotonic_time" for issue in report.errors)


def test_missing_frame_indices_are_allowed():
    match = build_valid_match()

    frames = (
        Frame(
            frame_index=100,
            time=MatchTime(
                PeriodType.FIRST_HALF,
                10.0,
            ),
            player_positions=(),
            ball_position=None,
        ),
        Frame(
            frame_index=102,
            time=MatchTime(
                PeriodType.FIRST_HALF,
                10.08,
            ),
            player_positions=(),
            ball_position=None,
        ),
    )

    match = Match(
        metadata=match.metadata,
        coordinate_system=match.coordinate_system,
        periods=match.periods,
        teams=match.teams,
        players=match.players,
        frames=frames,
        events=(),
    )

    report = validate_match(match)

    assert report.is_valid


def test_event_player_team_mismatch_is_error():
    match = build_valid_match()

    event = Event(
        event_id="shot-1",
        event_type=EventType.SHOT,
        time=MatchTime(
            PeriodType.FIRST_HALF,
            10.0,
        ),
        team_id="away",
        player_id="player-7",
        frame_index=100,
        shot_outcome=ShotOutcome.GOAL,
    )

    match = Match(
        metadata=match.metadata,
        coordinate_system=match.coordinate_system,
        periods=match.periods,
        teams=match.teams,
        players=match.players,
        frames=match.frames,
        events=(event,),
    )

    report = validate_match(match)

    assert any(issue.code == "event.player_team_mismatch" for issue in report.errors)


def test_event_missing_frame_is_error():
    match = build_valid_match()

    event = Event(
        event_id="shot-1",
        event_type=EventType.SHOT,
        time=MatchTime(
            PeriodType.FIRST_HALF,
            10.0,
        ),
        team_id="home",
        player_id="player-7",
        frame_index=999999,
        shot_outcome=ShotOutcome.GOAL,
    )

    match = Match(
        metadata=match.metadata,
        coordinate_system=match.coordinate_system,
        periods=match.periods,
        teams=match.teams,
        players=match.players,
        frames=match.frames,
        events=(event,),
    )

    report = validate_match(match)

    assert any(issue.code == "event.unknown_frame" for issue in report.errors)


def test_event_frame_time_mismatch_is_error():
    match = build_valid_match()

    event = Event(
        event_id="shot-1",
        event_type=EventType.SHOT,
        time=MatchTime(
            PeriodType.FIRST_HALF,
            20.0,
        ),
        team_id="home",
        player_id="player-7",
        frame_index=100,
        shot_outcome=ShotOutcome.GOAL,
    )

    match = Match(
        metadata=match.metadata,
        coordinate_system=match.coordinate_system,
        periods=match.periods,
        teams=match.teams,
        players=match.players,
        frames=match.frames,
        events=(event,),
    )

    report = validate_match(match)

    assert any(issue.code == "event.frame_time_mismatch" for issue in report.errors)


def test_partial_position_is_warning_not_error():
    match = build_valid_match()

    frame = Frame(
        frame_index=100,
        time=MatchTime(
            PeriodType.FIRST_HALF,
            10.0,
        ),
        player_positions=(
            PlayerPosition(
                player_id="player-7",
                x=50.0,
                y=None,
            ),
        ),
        ball_position=None,
    )

    match = Match(
        metadata=match.metadata,
        coordinate_system=match.coordinate_system,
        periods=match.periods,
        teams=match.teams,
        players=match.players,
        frames=(frame,),
        events=(),
    )

    report = validate_match(match)

    assert report.is_valid

    assert any(issue.severity == ValidationSeverity.WARNING for issue in report.issues)


def test_validate_match_or_raise():
    match = build_valid_match()

    validate_match_or_raise(match)


def test_validate_match_or_raise_reports_errors():
    match = build_valid_match()

    invalid_event = match.events[0]
    invalid_match = Match(
        metadata=match.metadata,
        coordinate_system=match.coordinate_system,
        periods=match.periods,
        teams=match.teams,
        players=match.players,
        frames=match.frames,
        events=(
            Event(
                event_id=invalid_event.event_id,
                event_type=invalid_event.event_type,
                time=invalid_event.time,
                team_id=invalid_event.team_id,
                player_id=invalid_event.player_id,
                x=invalid_event.x,
                y=invalid_event.y,
                frame_index=999999,
                shot_outcome=invalid_event.shot_outcome,
                xg=invalid_event.xg,
            ),
        ),
    )

    with pytest.raises(MatchValidationError) as exc_info:
        validate_match_or_raise(invalid_match)

    assert "event.unknown_frame" in str(exc_info.value)

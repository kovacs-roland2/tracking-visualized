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


def test_player_position_is_observed():
    position = PlayerPosition(
        player_id="player-7",
        x=50.0,
        y=30.0,
    )

    assert position.is_observed is True


def test_missing_player_position_is_not_observed():
    position = PlayerPosition(
        player_id="player-7",
        x=None,
        y=None,
    )

    assert position.is_observed is False


def test_goal_event():
    event = Event(
        event_id="event-1",
        event_type=EventType.SHOT,
        time=MatchTime(
            period=PeriodType.SECOND_HALF,
            seconds=1200.0,
        ),
        team_id="away",
        player_id="player-10",
        shot_outcome=ShotOutcome.GOAL,
        xg=0.35,
    )

    assert event.is_goal is True


def test_non_goal_shot():
    event = Event(
        event_id="event-1",
        event_type=EventType.SHOT,
        time=MatchTime(
            period=PeriodType.FIRST_HALF,
            seconds=200.0,
        ),
        shot_outcome=ShotOutcome.SAVED,
    )

    assert event.is_goal is False


def test_frame_contains_player_and_ball_positions():
    frame = Frame(
        frame_index=100,
        time=MatchTime(
            period=PeriodType.FIRST_HALF,
            seconds=4.0,
        ),
        player_positions=(
            PlayerPosition(
                player_id="player-7",
                x=20.0,
                y=30.0,
            ),
        ),
        ball_position=BallPosition(
            x=50.0,
            y=34.0,
            z=0.1,
            possession_team_id="home",
            is_in_play=True,
        ),
    )

    assert frame.frame_index == 100
    assert len(frame.player_positions) == 1

    assert frame.ball_position is not None
    assert frame.ball_position.z == 0.1


def test_frame_rejects_duplicate_player_positions():
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        Frame(
            frame_index=100,
            time=MatchTime(
                period=PeriodType.FIRST_HALF,
                seconds=4.0,
            ),
            player_positions=(
                PlayerPosition(
                    player_id="player-7",
                    x=10.0,
                    y=10.0,
                ),
                PlayerPosition(
                    player_id="player-7",
                    x=11.0,
                    y=10.0,
                ),
            ),
            ball_position=None,
        )


def test_match_exposes_relationships():
    home = Team(
        team_id="home",
        name="1. FC Köln",
        side=TeamSide.HOME,
    )

    away = Team(
        team_id="away",
        name="FC Bayern München",
        side=TeamSide.AWAY,
    )

    player = Player(
        player_id="player-7",
        team_id="home",
        name="Example Player",
        shirt_number=7,
    )

    goal = Event(
        event_id="goal-1",
        event_type=EventType.SHOT,
        time=MatchTime(
            period=PeriodType.SECOND_HALF,
            seconds=100.0,
        ),
        team_id="home",
        player_id="player-7",
        shot_outcome=ShotOutcome.GOAL,
    )

    match = Match(
        metadata=MatchMetadata(
            match_id="J03WMX",
            competition="Bundesliga",
            season="2022/2023",
            match_day=34,
        ),
        coordinate_system=CoordinateSystem(
            pitch_length=105.0,
            pitch_width=68.0,
        ),
        periods=(
            Period(PeriodType.FIRST_HALF),
            Period(PeriodType.SECOND_HALF),
        ),
        teams=(home, away),
        players=(player,),
        frames=(),
        events=(goal,),
    )

    assert match.home_team == home
    assert match.away_team == away

    assert match.get_player("player-7") == player

    assert match.players_for_team("home") == (player,)

    assert match.goals == (goal,)


def test_match_rejects_player_with_unknown_team():
    player = Player(
        player_id="player-7",
        team_id="missing-team",
    )

    with pytest.raises(
        ValueError,
        match="unknown team",
    ):
        Match(
            metadata=MatchMetadata(
                match_id="match-1",
                competition="Bundesliga",
                season="2022/2023",
            ),
            coordinate_system=CoordinateSystem(
                pitch_length=105,
                pitch_width=68,
            ),
            periods=(),
            teams=(
                Team(
                    team_id="home",
                    name="Home",
                    side=TeamSide.HOME,
                ),
                Team(
                    team_id="away",
                    name="Away",
                    side=TeamSide.AWAY,
                ),
            ),
            players=(player,),
            frames=(),
            events=(),
        )

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class TeamSide(StrEnum):
    HOME = "home"
    AWAY = "away"


class PeriodType(StrEnum):
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"


class EventType(StrEnum):
    SHOT = "shot"


class ShotOutcome(StrEnum):
    WIDE = "wide"
    SAVED = "saved"
    BLOCKED = "blocked"
    WOODWORK = "woodwork"
    GOAL = "goal"
    OTHER = "other"


class CoordinateOrigin(StrEnum):
    BOTTOM_LEFT = "bottom_left"


@dataclass(frozen=True, slots=True)
class CoordinateSystem:
    pitch_length: float
    pitch_width: float
    origin: CoordinateOrigin = CoordinateOrigin.BOTTOM_LEFT
    unit: str = "meters"

    def __post_init__(self) -> None:
        if self.pitch_length <= 0:
            raise ValueError("Pitch length must be positive.")

        if self.pitch_width <= 0:
            raise ValueError("Pitch width must be positive.")


@dataclass(frozen=True, slots=True)
class MatchTime:
    period: PeriodType
    seconds: float

    def __post_init__(self) -> None:
        if not isfinite(self.seconds):
            raise ValueError("Match time must be finite.")

        if self.seconds < 0:
            raise ValueError("Match time cannot be negative.")


@dataclass(frozen=True, slots=True)
class Period:
    period: PeriodType
    duration_seconds: float | None = None
    playing_duration_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise ValueError("Period duration must be positive.")

        if self.playing_duration_seconds is not None and self.playing_duration_seconds <= 0:
            raise ValueError("Playing duration must be positive.")

        if (
            self.duration_seconds is not None
            and self.playing_duration_seconds is not None
            and self.playing_duration_seconds > self.duration_seconds
        ):
            raise ValueError("Playing duration cannot exceed period duration.")


@dataclass(frozen=True, slots=True)
class MatchMetadata:
    match_id: str
    competition: str
    season: str
    match_day: int | None = None

    def __post_init__(self) -> None:
        if not self.match_id.strip():
            raise ValueError("Match ID cannot be empty.")

        if not self.competition.strip():
            raise ValueError("Competition cannot be empty.")

        if not self.season.strip():
            raise ValueError("Season cannot be empty.")

        if self.match_day is not None and self.match_day <= 0:
            raise ValueError("Match day must be positive.")


@dataclass(frozen=True, slots=True)
class Team:
    team_id: str
    name: str
    side: TeamSide

    def __post_init__(self) -> None:
        if not self.team_id.strip():
            raise ValueError("Team ID cannot be empty.")

        if not self.name.strip():
            raise ValueError("Team name cannot be empty.")


@dataclass(frozen=True, slots=True)
class Player:
    player_id: str
    team_id: str
    name: str | None = None
    shirt_number: int | None = None

    def __post_init__(self) -> None:
        if not self.player_id.strip():
            raise ValueError("Player ID cannot be empty.")

        if not self.team_id.strip():
            raise ValueError("Player team ID cannot be empty.")

        if self.shirt_number is not None and self.shirt_number < 0:
            raise ValueError("Shirt number cannot be negative.")


@dataclass(frozen=True, slots=True)
class PlayerPosition:
    player_id: str
    x: float | None
    y: float | None

    def __post_init__(self) -> None:
        if not self.player_id.strip():
            raise ValueError("Player ID cannot be empty.")

        for coordinate in (self.x, self.y):
            if coordinate is not None and not isfinite(coordinate):
                raise ValueError("Player coordinates must be finite.")

    @property
    def is_observed(self) -> bool:
        return self.x is not None and self.y is not None


@dataclass(frozen=True, slots=True)
class BallPosition:
    x: float | None
    y: float | None
    z: float | None = None

    possession_team_id: str | None = None
    is_in_play: bool | None = None

    def __post_init__(self) -> None:
        for coordinate in (
            self.x,
            self.y,
            self.z,
        ):
            if coordinate is not None and not isfinite(coordinate):
                raise ValueError("Ball coordinates must be finite.")

    @property
    def is_observed(self) -> bool:
        return self.x is not None and self.y is not None


@dataclass(frozen=True, slots=True)
class Frame:
    frame_index: int
    time: MatchTime

    player_positions: tuple[PlayerPosition, ...]
    ball_position: BallPosition | None

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("Frame index cannot be negative.")

        player_ids = [position.player_id for position in self.player_positions]

        if len(player_ids) != len(set(player_ids)):
            raise ValueError("A frame cannot contain duplicate positions for the same player.")


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    event_type: EventType
    time: MatchTime

    team_id: str | None = None
    player_id: str | None = None

    x: float | None = None
    y: float | None = None

    frame_index: int | None = None

    shot_outcome: ShotOutcome | None = None
    xg: float | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("Event ID cannot be empty.")

        if self.frame_index is not None and self.frame_index < 0:
            raise ValueError("Event frame index cannot be negative.")

        for coordinate in (self.x, self.y):
            if coordinate is not None and not isfinite(coordinate):
                raise ValueError("Event coordinates must be finite.")

        if self.xg is not None:
            if not 0 <= self.xg <= 1:
                raise ValueError("xG must be between 0 and 1.")

        if self.event_type == EventType.SHOT and self.shot_outcome is None:
            raise ValueError("Shot events require a shot outcome.")

    @property
    def is_goal(self) -> bool:
        return self.event_type == EventType.SHOT and self.shot_outcome == ShotOutcome.GOAL


@dataclass(frozen=True, slots=True)
class Match:
    metadata: MatchMetadata
    coordinate_system: CoordinateSystem

    periods: tuple[Period, ...]
    teams: tuple[Team, ...]
    players: tuple[Player, ...]

    frames: Sequence[Frame]
    events: Sequence[Event]

    def __post_init__(self) -> None:
        team_ids = [team.team_id for team in self.teams]

        if len(team_ids) != len(set(team_ids)):
            raise ValueError("Match contains duplicate team IDs.")

        player_ids = [player.player_id for player in self.players]

        if len(player_ids) != len(set(player_ids)):
            raise ValueError("Match contains duplicate player IDs.")

        known_team_ids = set(team_ids)

        for player in self.players:
            if player.team_id not in known_team_ids:
                raise ValueError(
                    f"Player '{player.player_id}' references unknown team '{player.team_id}'."
                )

        sides = {team.side for team in self.teams}

        if TeamSide.HOME not in sides:
            raise ValueError("Match must contain a home team.")

        if TeamSide.AWAY not in sides:
            raise ValueError("Match must contain an away team.")

    @property
    def home_team(self) -> Team:
        return next(team for team in self.teams if team.side == TeamSide.HOME)

    @property
    def away_team(self) -> Team:
        return next(team for team in self.teams if team.side == TeamSide.AWAY)

    def get_team(self, team_id: str) -> Team:
        for team in self.teams:
            if team.team_id == team_id:
                return team

        raise KeyError(f"Unknown team ID '{team_id}'.")

    def get_player(self, player_id: str) -> Player:
        for player in self.players:
            if player.player_id == player_id:
                return player

        raise KeyError(f"Unknown player ID '{player_id}'.")

    def players_for_team(
        self,
        team_id: str,
    ) -> tuple[Player, ...]:
        return tuple(player for player in self.players if player.team_id == team_id)

    @property
    def shots(self) -> tuple[Event, ...]:
        return tuple(event for event in self.events if event.event_type == EventType.SHOT)

    @property
    def goals(self) -> tuple[Event, ...]:
        return tuple(event for event in self.events if event.is_goal)

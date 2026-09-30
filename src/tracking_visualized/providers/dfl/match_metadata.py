import xml.etree.ElementTree as ET
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TeamSide(StrEnum):
    HOME = "home"
    AWAY = "away"


class TeamMetadata(BaseModel):
    team_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    side: TeamSide


class CompetitionMetadata(BaseModel):
    competition_id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class SeasonMetadata(BaseModel):
    season_id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class PeriodMetadata(BaseModel):
    number: Literal[1, 2]
    total_duration_seconds: float = Field(gt=0)
    playing_duration_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_playing_time(self) -> "PeriodMetadata":
        if self.playing_duration_seconds > self.total_duration_seconds:
            raise ValueError("Playing duration cannot exceed total period duration.")

        return self


class MatchMetadata(BaseModel):
    match_id: str = Field(
        min_length=1,
        pattern=r"^DFL-MAT-[A-Z0-9]+$",
    )
    competition: CompetitionMetadata
    season: SeasonMetadata
    match_day: int = Field(gt=0)
    home_team: TeamMetadata
    away_team: TeamMetadata
    periods: tuple[PeriodMetadata, PeriodMetadata]

    @model_validator(mode="after")
    def validate_match(self) -> "MatchMetadata":
        if self.home_team.side != TeamSide.HOME:
            raise ValueError("Home team must have side='home'.")

        if self.away_team.side != TeamSide.AWAY:
            raise ValueError("Away team must have side='away'.")

        if self.home_team.team_id == self.away_team.team_id:
            raise ValueError("Home and away teams must be different.")

        if tuple(period.number for period in self.periods) != (1, 2):
            raise ValueError("Periods must contain first and second half.")

        return self


class DflMatchMetadataError(ValueError):
    """Raised when DFL match metadata is missing or inconsistent."""


def _require_element(
    parent: ET.Element,
    tag: str,
) -> ET.Element:
    """
    Requires an XML element with the given tag to exist as a child of the parent.

    Args:
        parent: The parent XML element.
        tag: The tag of the required child element.

    Returns:
        The required child XML element.
    """
    element = parent.find(tag)

    if element is None:
        raise DflMatchMetadataError(f"Missing required XML element <{tag}>.")

    return element


def _require_attribute(
    element: ET.Element,
    attribute: str,
) -> str:
    """
    Requires an XML attribute to exist on the given element.

    Args:
        element: The XML element.
        attribute: The name of the required attribute.

    Returns:
        The value of the required attribute.
    """
    value = element.get(attribute)

    if value is None or not value.strip():
        raise DflMatchMetadataError(f"Missing required attribute '{attribute}' on <{element.tag}>.")

    return value


def _milliseconds_to_seconds(value: str) -> float:
    """
    Converts a string representing milliseconds to seconds.

    Args:
        value: The string representing milliseconds.

    Returns:
        The equivalent duration in seconds.
    """
    try:
        milliseconds = int(value)
    except ValueError as exc:
        raise DflMatchMetadataError(f"Expected duration in milliseconds, got '{value}'.") from exc

    if milliseconds <= 0:
        raise DflMatchMetadataError("Period duration must be positive.")

    return milliseconds / 1000


def _parse_periods(
    game_information: ET.Element,
) -> tuple[PeriodMetadata, PeriodMetadata]:
    """
    Parses the first and second half period metadata from the <OtherGameInformation> XML element.

    Args:
        game_information: The <OtherGameInformation> XML element.

    Returns:
        A tuple containing the first and second half PeriodMetadata.
    """
    first_half = PeriodMetadata(
        number=1,
        total_duration_seconds=_milliseconds_to_seconds(
            _require_attribute(
                game_information,
                "TotalTimeFirstHalf",
            )
        ),
        playing_duration_seconds=_milliseconds_to_seconds(
            _require_attribute(
                game_information,
                "PlayingTimeFirstHalf",
            )
        ),
    )

    second_half = PeriodMetadata(
        number=2,
        total_duration_seconds=_milliseconds_to_seconds(
            _require_attribute(
                game_information,
                "TotalTimeSecondHalf",
            )
        ),
        playing_duration_seconds=_milliseconds_to_seconds(
            _require_attribute(
                game_information,
                "PlayingTimeSecondHalf",
            )
        ),
    )

    return first_half, second_half


def _parse_teams(
    teams_element: ET.Element,
) -> tuple[TeamMetadata, TeamMetadata]:
    """
    Parses the home and away team metadata from the <Teams> XML element.

    Args:
        teams_element: The <Teams> XML element.

    Returns:
        A tuple containing the home and away TeamMetadata.
    """
    team_elements = teams_element.findall("Team")

    if len(team_elements) != 2:
        raise DflMatchMetadataError(f"Expected exactly 2 teams, found {len(team_elements)}.")

    home_team: TeamMetadata | None = None
    away_team: TeamMetadata | None = None

    for team_element in team_elements:
        team_id = _require_attribute(team_element, "TeamId")
        name = _require_attribute(team_element, "TeamName")
        role = _require_attribute(team_element, "Role")

        if role == "home":
            if home_team is not None:
                raise DflMatchMetadataError("Multiple home teams found.")

            home_team = TeamMetadata(
                team_id=team_id,
                name=name,
                side=TeamSide.HOME,
            )

        elif role == "guest":
            if away_team is not None:
                raise DflMatchMetadataError("Multiple guest teams found.")

            away_team = TeamMetadata(
                team_id=team_id,
                name=name,
                side=TeamSide.AWAY,
            )

        else:
            raise DflMatchMetadataError(f"Unknown DFL team role '{role}'.")

    if home_team is None:
        raise DflMatchMetadataError("Home team not found.")

    if away_team is None:
        raise DflMatchMetadataError("Guest team not found.")

    return home_team, away_team


def _validate_team_consistency(
    general: ET.Element,
    home_team: TeamMetadata,
    away_team: TeamMetadata,
) -> None:
    """
    Validates that the team IDs and names in the <General> element match those in the
    <Teams> element.

    Args:
        general: The <General> XML element.
        home_team: The parsed home TeamMetadata.
        away_team: The parsed away TeamMetadata.

    Returns:
        None
    """
    expected_home_id = _require_attribute(
        general,
        "HomeTeamId",
    )
    expected_away_id = _require_attribute(
        general,
        "GuestTeamId",
    )

    expected_home_name = _require_attribute(
        general,
        "HomeTeamName",
    )
    expected_away_name = _require_attribute(
        general,
        "GuestTeamName",
    )

    if home_team.team_id != expected_home_id:
        raise DflMatchMetadataError("Home team ID differs between <General> and <Teams>.")

    if away_team.team_id != expected_away_id:
        raise DflMatchMetadataError("Away team ID differs between <General> and <Teams>.")

    if home_team.name != expected_home_name:
        raise DflMatchMetadataError("Home team name differs between <General> and <Teams>.")

    if away_team.name != expected_away_name:
        raise DflMatchMetadataError("Away team name differs between <General> and <Teams>.")


def load_match_metadata(path: Path) -> MatchMetadata:
    """
    Load DFL match metadata from a match-information XML file.

    Args:
        path: The path to the match-information XML file.

    Returns:
        The parsed match metadata.s
    """
    if not path.is_file():
        raise FileNotFoundError(f"Match metadata file does not exist: {path}")

    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise DflMatchMetadataError(f"Invalid XML in match metadata file: {path}") from exc

    root = tree.getroot()

    match_information = _require_element(
        root,
        "MatchInformation",
    )

    general = _require_element(
        match_information,
        "General",
    )

    teams_element = _require_element(
        match_information,
        "Teams",
    )

    game_information = _require_element(
        match_information,
        "OtherGameInformation",
    )

    home_team, away_team = _parse_teams(teams_element)

    _validate_team_consistency(
        general,
        home_team,
        away_team,
    )

    try:
        match_day = int(
            _require_attribute(
                general,
                "MatchDay",
            )
        )
    except ValueError as exc:
        raise DflMatchMetadataError("MatchDay must be an integer.") from exc

    return MatchMetadata(
        match_id=_require_attribute(
            general,
            "MatchId",
        ),
        competition=CompetitionMetadata(
            competition_id=_require_attribute(
                general,
                "CompetitionId",
            ),
            name=_require_attribute(
                general,
                "CompetitionName",
            ),
        ),
        season=SeasonMetadata(
            season_id=_require_attribute(
                general,
                "SeasonId",
            ),
            name=_require_attribute(
                general,
                "Season",
            ),
        ),
        match_day=match_day,
        home_team=home_team,
        away_team=away_team,
        periods=_parse_periods(game_information),
    )

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Iterator


class TrackingPeriod(StrEnum):
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"


class TrackingTeam(StrEnum):
    HOME = "home"
    AWAY = "away"


@dataclass(frozen=True, slots=True)
class PlayerTrackingSample:
    frame_number: int
    timestamp: datetime
    period: TrackingPeriod

    person_id: str
    team_id: str
    team: TrackingTeam
    shirt_number: int | None

    x: float | None
    y: float | None


@dataclass(frozen=True, slots=True)
class BallTrackingSample:
    frame_number: int
    timestamp: datetime
    period: TrackingPeriod

    x: float | None
    y: float | None
    z: float | None

    possession_team: TrackingTeam | None
    is_alive: bool | None


@dataclass(frozen=True, slots=True)
class PlayerReference:
    person_id: str
    team_id: str
    team: TrackingTeam
    shirt_number: int | None


class DflTrackingError(ValueError):
    """Raised when DFL tracking data is malformed or inconsistent."""


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
        raise DflTrackingError(f"Missing required attribute '{attribute}' on <{element.tag}>.")

    return value


def _optional_float(value: str | None) -> float | None:
    """
    Converts a string to a float, if possible.

    Args:
        value: The string to convert.

    Returns:
        The converted float, or None if the string is empty or not a valid number.
    """
    if value is None or not value.strip():
        return None

    try:
        return float(value)
    except ValueError as exc:
        raise DflTrackingError(f"Invalid numeric value '{value}'.") from exc


def _optional_int(value: str | None) -> int | None:
    """
    Converts a string to an integer, if possible.

    Args:
        value: The string to convert.

    Returns:
        The converted integer, or None if the string is empty or not a valid number.
    """
    if value is None or not value.strip():
        return None

    try:
        return int(value)
    except ValueError as exc:
        raise DflTrackingError(f"Invalid integer value '{value}'.") from exc


def _parse_timestamp(value: str) -> datetime:
    """
    Parses an ISO-8601 timestamp string into a datetime object.

    Args:
        value: The ISO-8601 timestamp string to parse.

    Returns:
        A datetime object representing the parsed timestamp.
    """
    normalized = value.replace("Z", "+00:00")

    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DflTrackingError(f"Invalid ISO-8601 timestamp '{value}'.") from exc

    if timestamp.tzinfo is None:
        raise DflTrackingError(f"Tracking timestamp must include timezone information: '{value}'.")

    return timestamp


def _parse_period(value: str) -> TrackingPeriod:
    """
    Parses a string representing a game period into a TrackingPeriod enum.

    Args:
        value: The string representing the game period.

    Returns:
        The corresponding TrackingPeriod enum value."""
    normalized = value.replace("_", "").replace("-", "").lower()

    if normalized == "firsthalf":
        return TrackingPeriod.FIRST_HALF

    if normalized == "secondhalf":
        return TrackingPeriod.SECOND_HALF

    raise DflTrackingError(f"Unsupported game section '{value}'.")


def _load_player_index(
    metadata_path: Path,
) -> dict[str, PlayerReference]:
    """
    Load a mapping of player person IDs to PlayerReference objects from the match metadata XML.

    Args:
        metadata_path: The path to the match metadata XML file.

    Returns:
        A dictionary mapping player person IDs to PlayerReference objects.
    """
    try:
        tree = ET.parse(metadata_path)
    except ET.ParseError as exc:
        raise DflTrackingError(f"Invalid match metadata XML: {metadata_path}") from exc

    root = tree.getroot()

    match_information = root.find("MatchInformation")

    if match_information is None:
        raise DflTrackingError("Missing <MatchInformation> element.")

    general = match_information.find("General")
    teams = match_information.find("Teams")

    if general is None:
        raise DflTrackingError("Missing <General> element.")

    if teams is None:
        raise DflTrackingError("Missing <Teams> element.")

    home_team_id = _require_attribute(
        general,
        "HomeTeamId",
    )

    away_team_id = general.get("GuestTeamId") or general.get("AwayTeamId")

    if not away_team_id:
        raise DflTrackingError("Missing away/guest team ID.")

    player_index: dict[str, PlayerReference] = {}

    for team_element in teams.findall("Team"):
        team_id = _require_attribute(
            team_element,
            "TeamId",
        )

        if team_id == home_team_id:
            team = TrackingTeam.HOME
        elif team_id == away_team_id:
            team = TrackingTeam.AWAY
        else:
            continue

        players = team_element.find("Players")

        if players is None:
            continue

        for player in players.findall("Player"):
            person_id = _require_attribute(
                player,
                "PersonId",
            )

            shirt_number = _optional_int(player.get("ShirtNumber"))

            player_index[person_id] = PlayerReference(
                person_id=person_id,
                team_id=team_id,
                team=team,
                shirt_number=shirt_number,
            )

    if not player_index:
        raise DflTrackingError("No home or away players found in match metadata.")

    return player_index


def _parse_possession(
    value: str | None,
) -> TrackingTeam | None:
    """
    Parses a string representing ball possession into a TrackingTeam enum.

    Args:
        value: The string representing ball possession.

    Returns:
        The corresponding TrackingTeam enum value, or None if the value is unknown.
    """
    if value is None or not value.strip():
        return None

    if value == "1":
        return TrackingTeam.HOME

    if value == "2":
        return TrackingTeam.AWAY

    raise DflTrackingError(f"Unknown BallPossession value '{value}'.")


def _parse_ball_status(
    value: str | None,
) -> bool | None:
    """
    Parses a string representing ball status into a boolean value.

    Args:
        value: The string representing ball status.

    Returns:
        The corresponding boolean value, or None if the value is unknown.
    """
    if value is None or not value.strip():
        return None

    if value == "0":
        return False

    if value == "1":
        return True

    raise DflTrackingError(f"Unknown BallStatus value '{value}'.")


def _parse_player_frame(
    frame: ET.Element,
    period: TrackingPeriod,
    player: PlayerReference,
) -> PlayerTrackingSample:
    """
    Parses a player tracking frame XML element into a PlayerTrackingSample object.

    Args:
        frame: The XML element representing the player tracking frame.
        period: The game period (first half or second half).
        player: The PlayerReference object for the player being tracked.

    Returns:
        A PlayerTrackingSample object containing the parsed tracking data.
    """
    try:
        frame_number = int(_require_attribute(frame, "N"))
    except DflTrackingError:
        raise
    except ValueError as exc:
        raise DflTrackingError("Tracking frame number must be an integer.") from exc

    timestamp = _parse_timestamp(_require_attribute(frame, "T"))

    return PlayerTrackingSample(
        frame_number=frame_number,
        timestamp=timestamp,
        period=period,
        person_id=player.person_id,
        team_id=player.team_id,
        team=player.team,
        shirt_number=player.shirt_number,
        x=_optional_float(frame.get("X")),
        y=_optional_float(frame.get("Y")),
    )


def _parse_ball_frame(
    frame: ET.Element,
    period: TrackingPeriod,
) -> BallTrackingSample:
    """
    Parses a ball tracking frame XML element into a BallTrackingSample object.

    Args:
        frame: The XML element representing the ball tracking frame.
        period: The game period (first half or second half).

    Returns:
        A BallTrackingSample object containing the parsed tracking data.
    """
    try:
        frame_number = int(_require_attribute(frame, "N"))
    except DflTrackingError:
        raise
    except ValueError as exc:
        raise DflTrackingError("Tracking frame number must be an integer.") from exc

    timestamp = _parse_timestamp(_require_attribute(frame, "T"))

    return BallTrackingSample(
        frame_number=frame_number,
        timestamp=timestamp,
        period=period,
        x=_optional_float(frame.get("X")),
        y=_optional_float(frame.get("Y")),
        z=_optional_float(frame.get("Z")),
        possession_team=_parse_possession(frame.get("BallPossession")),
        is_alive=_parse_ball_status(frame.get("BallStatus")),
    )


TrackingSample = PlayerTrackingSample | BallTrackingSample


def iter_tracking_samples(
    tracking_path: Path,
    metadata_path: Path,
) -> Iterator[TrackingSample]:
    """
    Stream player and ball samples from DFL tracking XML.

    Args:
        tracking_path: The path to the tracking XML file.
        metadata_path: The path to the match metadata XML file.

    Yields:
        PlayerTrackingSample or BallTrackingSample objects for each frame in the tracking data."""

    if not tracking_path.is_file():
        raise FileNotFoundError(f"Tracking file does not exist: {tracking_path}")

    if not metadata_path.is_file():
        raise FileNotFoundError(f"Metadata file does not exist: {metadata_path}")

    player_index = _load_player_index(metadata_path)

    try:
        context = ET.iterparse(
            tracking_path,
            events=("end",),
        )

        for _, frame_set in context:
            if frame_set.tag != "FrameSet":
                continue

            game_section = _require_attribute(
                frame_set,
                "GameSection",
            )

            period = _parse_period(game_section)

            team_id = _require_attribute(
                frame_set,
                "TeamId",
            )

            if team_id.lower() == "ball":
                for frame in frame_set.findall("Frame"):
                    yield _parse_ball_frame(
                        frame,
                        period,
                    )

            else:
                person_id = frame_set.get("PersonId")

                if not person_id:
                    frame_set.clear()
                    continue

                player = player_index.get(person_id)

                # Ignore tracked objects that are not players
                # from either participating team.
                if player is None:
                    frame_set.clear()
                    continue

                for frame in frame_set.findall("Frame"):
                    yield _parse_player_frame(
                        frame,
                        period,
                        player,
                    )

            frame_set.clear()

    except ET.ParseError as exc:
        raise DflTrackingError(f"Invalid tracking XML: {tracking_path}") from exc

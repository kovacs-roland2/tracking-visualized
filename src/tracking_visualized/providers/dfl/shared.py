import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic.dataclasses import dataclass

from tracking_visualized.providers.dfl.match_metadata import TeamSide
from tracking_visualized.providers.dfl.utils import optional_int, require_attribute

if TYPE_CHECKING:
    from tracking_visualized.providers.dfl.tracking import TrackingTeam


@dataclass(frozen=True, slots=True)
class PlayerReference:
    person_id: str
    name: str | None = None
    team_id: str = ""
    team: "TrackingTeam" = ""
    shirt_number: int | None = None


def _load_team_layout(metadata_path: Path) -> tuple[ET.Element, str, str]:
    """
    Parse the match metadata XML and locate its teams.

    Args:
        metadata_path: The path to the match metadata XML file.

    Returns:
        The <Teams> element, the home team ID and the away team ID.
    """
    from tracking_visualized.providers.dfl.tracking import DflTrackingError

    try:
        tree = ET.parse(metadata_path)
    except ET.ParseError as exc:
        raise DflTrackingError(f"Invalid match metadata XML: {metadata_path}") from exc

    match_information = tree.getroot().find("MatchInformation")

    if match_information is None:
        raise DflTrackingError("Missing <MatchInformation> element.")

    general = match_information.find("General")
    teams = match_information.find("Teams")

    if general is None:
        raise DflTrackingError("Missing <General> element.")

    if teams is None:
        raise DflTrackingError("Missing <Teams> element.")

    home_team_id = require_attribute(general, "HomeTeamId", DflTrackingError)
    away_team_id = general.get("GuestTeamId") or general.get("AwayTeamId")

    if not away_team_id:
        raise DflTrackingError("Missing away/guest team ID.")

    return teams, home_team_id, away_team_id


def load_team_side_index(
    metadata_path: Path,
) -> dict[str, TeamSide]:
    """
    Load a mapping of team IDs to TeamSide values from the match metadata XML.

    Args:
        metadata_path: The path to the match metadata XML file.

    Returns:
        A dictionary mapping team IDs to their home/away TeamSide value.
    """
    from tracking_visualized.providers.dfl.tracking import DflTrackingError

    teams, home_team_id, away_team_id = _load_team_layout(metadata_path)

    team_sides: dict[str, TeamSide] = {}

    for team_element in teams.findall("Team"):
        team_id = require_attribute(
            team_element,
            "TeamId",
            DflTrackingError,
        )

        if team_id == home_team_id:
            team_sides[team_id] = TeamSide.HOME
        elif team_id == away_team_id:
            team_sides[team_id] = TeamSide.AWAY

    if not team_sides:
        raise DflTrackingError("No home or away teams found in match metadata.")

    return team_sides


def _player_name(player: ET.Element) -> str | None:
    """Display name of a DFL player, e.g. ``Y. Sommer``.

    DFL metadata has ``Shortname``, ``FirstName`` and ``LastName`` attributes; the short
    name is preferred, then the full name.
    """

    short_name = (player.get("Shortname") or "").strip()

    if short_name:
        return short_name

    full_name = " ".join(
        part.strip() for part in (player.get("FirstName"), player.get("LastName")) if part
    ).strip()

    return full_name or None


def load_player_index(
    metadata_path: Path,
) -> dict[str, PlayerReference]:
    """
    Load a mapping of player person IDs to PlayerReference objects from the match metadata XML.

    Args:
        metadata_path: The path to the match metadata XML file.

    Returns:
        A dictionary mapping player person IDs to PlayerReference objects.
    """
    from tracking_visualized.providers.dfl.tracking import DflTrackingError, TrackingTeam

    teams, home_team_id, away_team_id = _load_team_layout(metadata_path)

    player_index: dict[str, PlayerReference] = {}

    for team_element in teams.findall("Team"):
        team_id = require_attribute(
            team_element,
            "TeamId",
            DflTrackingError,
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
            person_id = require_attribute(
                player,
                "PersonId",
                DflTrackingError,
            )

            shirt_number = optional_int(player.get("ShirtNumber"), DflTrackingError)

            player_index[person_id] = PlayerReference(
                person_id=person_id,
                name=_player_name(player),
                team_id=team_id,
                team=team,
                shirt_number=shirt_number,
            )

    if not player_index:
        raise DflTrackingError("No home or away players found in match metadata.")

    return player_index

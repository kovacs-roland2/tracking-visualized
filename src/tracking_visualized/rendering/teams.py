from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from tracking_visualized.domain import Player, Team, TeamSide
from tracking_visualized.rendering._validation import validate_colors


@dataclass(frozen=True, slots=True)
class TeamStyle:
    """Visual identity of a team's player markers."""

    marker_color: str
    edge_color: str = "#ffffff"
    number_color: str = "#ffffff"
    edge_width: float = 1.5

    def __post_init__(self) -> None:
        validate_colors(self, ("marker_color", "edge_color", "number_color"))

        if self.edge_width < 0:
            raise ValueError("edge_width must not be negative.")


DEFAULT_HOME_STYLE = TeamStyle(marker_color="#d62828")
DEFAULT_AWAY_STYLE = TeamStyle(marker_color="#1d4ed8")


def validate_team_styles(
    players: Iterable[Player],
    team_styles: Mapping[str, "TeamStyle"],
) -> None:
    """Raise ValueError if a player belongs to a team that has no style."""

    for player in players:
        if player.team_id not in team_styles:
            raise ValueError(
                f"No style for team '{player.team_id}' of player '{player.player_id}'."
            )


def resolve_team_styles(
    teams: Iterable[Team],
    *,
    home: TeamStyle | None = None,
    away: TeamStyle | None = None,
) -> dict[str, TeamStyle]:
    """Map each team ID to its style based on home/away side.

    Args:
        teams: Teams taking part in the match.
        home: Style for the home team. Defaults to DEFAULT_HOME_STYLE.
        away: Style for the away team. Defaults to DEFAULT_AWAY_STYLE.

    Returns:
        A mapping of team ID to TeamStyle.
    """

    styles_by_side = {
        TeamSide.HOME: home or DEFAULT_HOME_STYLE,
        TeamSide.AWAY: away or DEFAULT_AWAY_STYLE,
    }

    return {team.team_id: styles_by_side[team.side] for team in teams}


__all__ = [
    "DEFAULT_AWAY_STYLE",
    "DEFAULT_HOME_STYLE",
    "TeamStyle",
    "resolve_team_styles",
    "validate_team_styles",
]

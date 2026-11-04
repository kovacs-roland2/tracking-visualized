from collections.abc import Iterable
from dataclasses import dataclass

from matplotlib.colors import is_color_like

from tracking_visualized.domain import Team, TeamSide


@dataclass(frozen=True, slots=True)
class TeamStyle:
    """Visual identity of a team's player markers."""

    marker_color: str
    edge_color: str = "#ffffff"
    number_color: str = "#ffffff"
    edge_width: float = 1.5

    def __post_init__(self) -> None:
        for name, value in (
            ("marker_color", self.marker_color),
            ("edge_color", self.edge_color),
            ("number_color", self.number_color),
        ):
            if not is_color_like(value):
                raise ValueError(f"{name} is not a valid color: {value!r}.")

        if self.edge_width < 0:
            raise ValueError("edge_width must not be negative.")


DEFAULT_HOME_STYLE = TeamStyle(marker_color="#d62828")
DEFAULT_AWAY_STYLE = TeamStyle(marker_color="#1d4ed8")


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
]

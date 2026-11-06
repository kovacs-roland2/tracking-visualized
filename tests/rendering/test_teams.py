import pytest

from tracking_visualized.domain import Team, TeamSide
from tracking_visualized.rendering.teams import (
    DEFAULT_AWAY_STYLE,
    DEFAULT_HOME_STYLE,
    TeamStyle,
    resolve_team_styles,
)

HOME = Team(team_id="home", name="Home FC", side=TeamSide.HOME)
AWAY = Team(team_id="away", name="Away FC", side=TeamSide.AWAY)


def test_resolve_team_styles_by_side():
    custom_home = TeamStyle(marker_color="yellow")
    styles = resolve_team_styles((AWAY, HOME), home=custom_home)

    assert styles == {"home": custom_home, "away": DEFAULT_AWAY_STYLE}
    assert resolve_team_styles((HOME,))["home"] == DEFAULT_HOME_STYLE


@pytest.mark.parametrize("field", ["marker_color", "edge_color", "number_color"])
def test_invalid_team_style_color_raises(field):
    colors = {
        "marker_color": "red",
        "edge_color": "white",
        "number_color": "white",
    }
    colors[field] = "not-a-color"

    with pytest.raises(ValueError, match=field):
        TeamStyle(**colors)


def test_negative_edge_width_raises():
    with pytest.raises(ValueError, match="edge_width"):
        TeamStyle(marker_color="red", edge_width=-1)


def test_zero_edge_width_is_allowed():
    style = TeamStyle(marker_color="red", edge_width=0)

    assert style.edge_width == 0

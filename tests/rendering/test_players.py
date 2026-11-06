import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402

from tracking_visualized.domain import (  # noqa: E402
    CoordinateSystem,
    Frame,
    Match,
    MatchMetadata,
    MatchTime,
    PeriodType,
    Player,
    PlayerPosition,
    Team,
    TeamSide,
)
from tracking_visualized.rendering import (  # noqa: E402
    DEFAULT_AWAY_STYLE,
    DEFAULT_HOME_STYLE,
    PlayerLayer,
    draw_pitch,
    draw_players,
    resolve_team_styles,
)

HOME = Team(team_id="home", name="Home FC", side=TeamSide.HOME)
AWAY = Team(team_id="away", name="Away FC", side=TeamSide.AWAY)

PLAYERS = (
    Player(player_id="h7", team_id="home", shirt_number=7),
    Player(player_id="h9", team_id="home", shirt_number=9),
    Player(player_id="a1", team_id="away", shirt_number=1),
    Player(player_id="a-nonum", team_id="away", shirt_number=None),
)

STYLES = resolve_team_styles((HOME, AWAY))


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.fixture
def ax():
    return draw_pitch()


def make_frame(frame_index: int, positions: dict[str, tuple[float | None, float | None]]) -> Frame:
    return Frame(
        frame_index=frame_index,
        time=MatchTime(period=PeriodType.FIRST_HALF, seconds=frame_index / 25),
        player_positions=tuple(
            PlayerPosition(player_id=player_id, x=x, y=y) for player_id, (x, y) in positions.items()
        ),
        ball_position=None,
    )


FRAME_1 = make_frame(
    0,
    {"h7": (10.0, 20.0), "h9": (30.0, 40.0), "a1": (95.0, 34.0), "a-nonum": (60.0, 10.0)},
)


def offsets(layer: PlayerLayer, team_id: str) -> list[tuple[float, float]]:
    return [tuple(row) for row in np.asarray(layer.markers[team_id].get_offsets())]


def test_player_without_team_style_raises(ax):
    with pytest.raises(ValueError):
        PlayerLayer(ax, PLAYERS, {"home": DEFAULT_HOME_STYLE})


def test_invalid_marker_size_raises(ax):
    with pytest.raises(ValueError):
        PlayerLayer(ax, PLAYERS, STYLES, marker_size=0)


def test_renders_both_teams_with_their_colors(ax):
    layer = draw_players(ax, FRAME_1, PLAYERS, STYLES)

    assert offsets(layer, "home") == [(10.0, 20.0), (30.0, 40.0)]
    assert offsets(layer, "away") == [(95.0, 34.0), (60.0, 10.0)]

    home_face = layer.markers["home"].get_facecolor()[0]
    away_face = layer.markers["away"].get_facecolor()[0]

    assert tuple(home_face) == to_rgba(DEFAULT_HOME_STYLE.marker_color)
    assert tuple(away_face) == to_rgba(DEFAULT_AWAY_STYLE.marker_color)


def test_renders_shirt_numbers_at_player_positions(ax):
    layer = draw_players(ax, FRAME_1, PLAYERS, STYLES)

    label = layer.labels["h7"]

    assert label.get_text() == "7"
    assert label.get_position() == (10.0, 20.0)
    assert label.get_visible()
    assert layer.labels["a1"].get_text() == "1"


def test_player_without_shirt_number_has_no_label(ax):
    layer = draw_players(ax, FRAME_1, PLAYERS, STYLES)

    assert "a-nonum" not in layer.labels
    assert "a-nonum" in layer.visible_player_ids


def test_update_moves_existing_artists(ax):
    layer = PlayerLayer(ax, PLAYERS, STYLES)
    layer.update(FRAME_1)

    patch_count = len(ax.collections)
    text_count = len(ax.texts)

    layer.update(
        make_frame(
            1,
            {"h7": (11.0, 21.0), "h9": (31.0, 41.0), "a1": (94.0, 33.0), "a-nonum": (61.0, 11.0)},
        )
    )

    assert offsets(layer, "home") == [(11.0, 21.0), (31.0, 41.0)]
    assert layer.labels["h7"].get_position() == (11.0, 21.0)
    assert len(ax.collections) == patch_count
    assert len(ax.texts) == text_count


def test_update_returns_all_artists(ax):
    layer = PlayerLayer(ax, PLAYERS, STYLES)
    artists = layer.update(FRAME_1)

    assert set(artists) == {*layer.markers.values(), *layer.labels.values()}


def test_unobserved_player_is_hidden(ax):
    layer = draw_players(
        ax,
        make_frame(0, {"h7": (None, None), "h9": (30.0, 40.0)}),
        PLAYERS,
        STYLES,
    )

    assert offsets(layer, "home") == [(30.0, 40.0)]
    assert not layer.labels["h7"].get_visible()
    assert "h7" not in layer.visible_player_ids


def test_player_absent_from_frame_is_hidden_and_reappears(ax):
    layer = PlayerLayer(ax, PLAYERS, STYLES)

    layer.update(make_frame(0, {"h9": (30.0, 40.0)}))

    assert offsets(layer, "away") == []
    assert not layer.labels["a1"].get_visible()

    layer.update(FRAME_1)

    assert layer.labels["a1"].get_visible()
    assert offsets(layer, "away") == [(95.0, 34.0), (60.0, 10.0)]


def test_unknown_player_is_skipped(ax):
    layer = draw_players(
        ax,
        make_frame(0, {"h7": (10.0, 20.0), "ghost": (50.0, 50.0)}),
        PLAYERS,
        STYLES,
    )

    assert layer.unknown_player_ids == frozenset({"ghost"})
    assert offsets(layer, "home") == [(10.0, 20.0)]


def test_from_match(ax):
    match = Match(
        metadata=MatchMetadata(match_id="m1", competition="Liga", season="2026"),
        coordinate_system=CoordinateSystem(pitch_length=105.0, pitch_width=68.0),
        periods=(),
        teams=(HOME, AWAY),
        players=PLAYERS,
        frames=(FRAME_1,),
        events=(),
    )

    layer = PlayerLayer.from_match(ax, match, marker_size=12.0)
    layer.update(FRAME_1)

    assert set(layer.markers) == {"home", "away"}
    assert layer.markers["home"].get_sizes()[0] == 144.0
    assert layer.labels["h7"].get_fontsize() == pytest.approx(12.0 * 0.55)

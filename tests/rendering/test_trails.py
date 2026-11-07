import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from matplotlib.animation import FuncAnimation  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402

from tracking_visualized.config import RenderingConfig  # noqa: E402
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
    TrailLayer,
    draw_pitch,
    resolve_team_styles,
)

HOME = Team(team_id="home", name="Home FC", side=TeamSide.HOME)
AWAY = Team(team_id="away", name="Away FC", side=TeamSide.AWAY)

PLAYERS = (
    Player(player_id="h1", team_id="home", shirt_number=1),
    Player(player_id="a1", team_id="away", shirt_number=1),
)

STYLES = resolve_team_styles((HOME, AWAY))

# 10 fps and 1 s duration give a window of 10 frames, which keeps the maths readable.
FPS = 10
DURATION = 1.0


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.fixture
def ax():
    return draw_pitch()


def make_layer(ax, **kwargs) -> TrailLayer:
    kwargs.setdefault("duration_seconds", DURATION)

    return TrailLayer(ax, PLAYERS, STYLES, **kwargs)


def make_frame(
    frame_index: int,
    positions: dict[str, tuple[float | None, float | None]],
    period: PeriodType = PeriodType.FIRST_HALF,
) -> Frame:
    return Frame(
        frame_index=frame_index,
        time=MatchTime(period=period, seconds=frame_index / FPS),
        player_positions=tuple(
            PlayerPosition(player_id=player_id, x=x, y=y) for player_id, (x, y) in positions.items()
        ),
        ball_position=None,
    )


def straight_run(layer: TrailLayer, start: int, stop: int) -> None:
    """Move h1 one meter per frame along y=10 for frames start..stop-1."""

    for index in range(start, stop):
        layer.update(make_frame(index, {"h1": (float(index), 10.0)}))


def segments(layer: TrailLayer, team_id: str) -> list[list[tuple[float, float]]]:
    return [[tuple(point) for point in seg] for seg in layer.lines[team_id].get_segments()]


def alphas(layer: TrailLayer, team_id: str) -> list[float]:
    return [float(color[3]) for color in layer.lines[team_id].get_colors()]


def test_invalid_arguments_raise(ax):
    for kwargs in (
        {"duration_seconds": -1},
        {"line_width": 0},
        {"max_alpha": 0},
        {"max_alpha": 1.5},
        {"max_gap_frames": 0},
    ):
        with pytest.raises(ValueError):
            make_layer(ax, **kwargs)


def test_player_without_team_style_raises(ax):
    with pytest.raises(ValueError):
        TrailLayer(ax, PLAYERS, {"home": DEFAULT_HOME_STYLE})


def test_duration_is_stored_in_source_seconds(ax):
    assert make_layer(ax).duration_seconds == DURATION
    assert make_layer(ax, duration_seconds=0.25).duration_seconds == 0.25


def test_first_frame_has_no_trail(ax):
    layer = make_layer(ax)
    layer.update(make_frame(0, {"h1": (0.0, 10.0)}))

    assert segments(layer, "home") == []


def test_trail_follows_player_movement(ax):
    layer = make_layer(ax)
    straight_run(layer, 0, 4)

    assert segments(layer, "home") == [
        [(0.0, 10.0), (1.0, 10.0)],
        [(1.0, 10.0), (2.0, 10.0)],
        [(2.0, 10.0), (3.0, 10.0)],
    ]


def test_trail_uses_team_colors_and_separate_teams(ax):
    layer = make_layer(ax)

    for index in range(3):
        layer.update(
            make_frame(
                index,
                {"h1": (float(index), 10.0), "a1": (50.0 - index, 30.0)},
            )
        )

    home_rgb = to_rgba(DEFAULT_HOME_STYLE.marker_color)[:3]
    away_rgb = to_rgba(DEFAULT_AWAY_STYLE.marker_color)[:3]

    assert len(segments(layer, "home")) == 2
    assert len(segments(layer, "away")) == 2
    assert tuple(layer.lines["home"].get_colors()[0][:3]) == pytest.approx(home_rgb)
    assert tuple(layer.lines["away"].get_colors()[0][:3]) == pytest.approx(away_rgb)


def test_trail_fades_with_age(ax):
    layer = make_layer(ax, max_alpha=0.5)
    straight_run(layer, 0, 5)

    values = alphas(layer, "home")

    assert values == sorted(values)
    assert values[-1] == pytest.approx(0.5 * (1 - 0 / 10))
    assert values[0] == pytest.approx(0.5 * (1 - 3 / 10))


def test_old_positions_are_dropped_after_duration(ax):
    layer = make_layer(ax)
    straight_run(layer, 0, 30)

    drawn = segments(layer, "home")

    # Window is 10 frames: points for frames 19..29 remain, i.e. 10 segments.
    assert len(drawn) == 10
    assert drawn[0][0] == (19.0, 10.0)
    assert drawn[-1][1] == (29.0, 10.0)


def test_zero_duration_draws_no_trail(ax):
    layer = make_layer(ax, duration_seconds=0)
    straight_run(layer, 0, 5)

    assert segments(layer, "home") == []


def test_same_frame_update_does_not_duplicate_points(ax):
    layer = make_layer(ax)
    straight_run(layer, 0, 3)

    layer.update(make_frame(2, {"h1": (2.0, 10.0)}))
    layer.update(make_frame(2, {"h1": (2.0, 10.0)}))

    assert len(segments(layer, "home")) == 2


def test_short_gap_is_bridged_and_long_gap_breaks_the_trail(ax):
    layer = make_layer(ax, max_gap_frames=2)

    layer.update(make_frame(0, {"h1": (0.0, 10.0)}))
    layer.update(make_frame(1, {"h1": (None, None)}))
    layer.update(make_frame(2, {"h1": (2.0, 10.0)}))

    assert segments(layer, "home") == [[(0.0, 10.0), (2.0, 10.0)]]

    layer.update(make_frame(3, {"h1": (None, None)}))
    layer.update(make_frame(4, {}))
    layer.update(make_frame(5, {"h1": (5.0, 10.0)}))

    assert [(2.0, 10.0), (5.0, 10.0)] not in segments(layer, "home")


def test_unobserved_and_unknown_players_add_nothing(ax):
    layer = make_layer(ax)

    for index in range(3):
        layer.update(make_frame(index, {"h1": (None, None), "ghost": (float(index), 5.0)}))

    assert segments(layer, "home") == []
    assert segments(layer, "away") == []


def test_frames_going_backwards_reset_the_trail(ax):
    layer = make_layer(ax)
    straight_run(layer, 100, 105)

    layer.update(make_frame(0, {"h1": (50.0, 20.0)}))

    assert segments(layer, "home") == []

    layer.update(make_frame(1, {"h1": (51.0, 20.0)}))

    assert segments(layer, "home") == [[(50.0, 20.0), (51.0, 20.0)]]


def test_period_change_resets_trails_even_when_frame_indices_are_consecutive(ax):
    layer = make_layer(ax)
    layer.update(make_frame(100, {"h1": (10.0, 20.0)}))

    layer.update(make_frame(101, {"h1": (80.0, 40.0)}, period=PeriodType.SECOND_HALF))

    assert segments(layer, "home") == []

    layer.update(make_frame(102, {"h1": (81.0, 40.0)}, period=PeriodType.SECOND_HALF))

    assert segments(layer, "home") == [[(80.0, 40.0), (81.0, 40.0)]]


def test_large_forward_jump_does_not_connect_old_points(ax):
    layer = make_layer(ax)
    straight_run(layer, 0, 5)

    layer.update(make_frame(500, {"h1": (80.0, 10.0)}))

    assert segments(layer, "home") == []


def test_explicit_reset_clears_trails(ax):
    layer = make_layer(ax)
    straight_run(layer, 0, 5)

    layer.reset()

    assert segments(layer, "home") == []

    straight_run(layer, 0, 2)

    assert segments(layer, "home") == [[(0.0, 10.0), (1.0, 10.0)]]


def test_update_moves_existing_artists(ax):
    layer = make_layer(ax)
    layer.update(make_frame(0, {"h1": (0.0, 10.0)}))

    collection_count = len(ax.collections)

    straight_run(layer, 1, 6)

    assert len(ax.collections) == collection_count


def test_update_returns_all_artists(ax):
    layer = make_layer(ax)

    assert layer.update(make_frame(0, {"h1": (0.0, 10.0)})) == list(layer.lines.values())


def test_trails_draw_below_player_markers(ax):
    layer = make_layer(ax)

    assert all(collection.get_zorder() < 3.0 for collection in layer.lines.values())


def test_from_match_uses_rendering_config(ax):
    match = Match(
        metadata=MatchMetadata(match_id="m1", competition="Liga", season="2026"),
        coordinate_system=CoordinateSystem(pitch_length=105.0, pitch_width=68.0),
        periods=(),
        teams=(HOME, AWAY),
        players=PLAYERS,
        frames=(),
        events=(),
    )

    layer = TrailLayer.from_match(ax, match, RenderingConfig(trail_duration_seconds=3.0, fps=20))

    assert layer.duration_seconds == 3.0
    assert set(layer.lines) == {"home", "away"}


@pytest.mark.parametrize("output_fps", [20, 50])
def test_from_match_trail_expiry_is_independent_of_rendering_fps(ax, output_fps):
    match = Match(
        metadata=MatchMetadata(match_id="m1", competition="Liga", season="2026"),
        coordinate_system=CoordinateSystem(pitch_length=105.0, pitch_width=68.0),
        periods=(),
        teams=(HOME, AWAY),
        players=PLAYERS,
        frames=(),
        events=(),
    )
    layer = TrailLayer.from_match(ax, match, RenderingConfig(fps=output_fps))

    for index in range(101):
        frame = Frame(
            frame_index=index,
            time=MatchTime(period=PeriodType.FIRST_HALF, seconds=index / 25),
            player_positions=(PlayerPosition(player_id="h1", x=float(index), y=10.0),),
            ball_position=None,
        )
        layer.update(frame)

    drawn = segments(layer, "home")

    assert len(drawn) == 50
    assert drawn[0][0] == (50.0, 10.0)
    assert drawn[-1][1] == (100.0, 10.0)


def test_trail_animation_over_frames(ax, tmp_path):
    layer = make_layer(ax)
    frames = [make_frame(i, {"h1": (float(i), 10.0)}) for i in range(6)]

    animation = FuncAnimation(ax.figure, layer.update, frames=frames, repeat=False)
    animation.save(tmp_path / "trails.gif", writer="pillow", fps=5)

    assert len(segments(layer, "home")) == 5

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from matplotlib.animation import FuncAnimation  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402

from tracking_visualized.domain import (  # noqa: E402
    BallPosition,
    Frame,
    MatchTime,
    PeriodType,
)
from tracking_visualized.rendering import (  # noqa: E402
    BallLayer,
    BallStyle,
    PitchDimensions,
    draw_ball,
    draw_pitch,
)

PITCH = PitchDimensions()


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.fixture
def ax():
    return draw_pitch()


def make_frame(frame_index: int, ball: BallPosition | None) -> Frame:
    return Frame(
        frame_index=frame_index,
        time=MatchTime(period=PeriodType.FIRST_HALF, seconds=frame_index / 25),
        player_positions=(),
        ball_position=ball,
    )


def offsets(layer: BallLayer) -> list[tuple[float, float]]:
    return [tuple(row) for row in np.asarray(layer.marker.get_offsets())]


def test_invalid_style_raises():
    with pytest.raises(ValueError):
        BallStyle(marker_color="not-a-color")

    with pytest.raises(ValueError):
        BallStyle(edge_width=-1)


def test_invalid_layer_arguments_raise(ax):
    with pytest.raises(ValueError):
        BallLayer(ax, marker_size=0)

    with pytest.raises(ValueError):
        BallLayer(ax, out_of_bounds_margin=-1)


def test_renders_ball_with_style_and_size(ax):
    style = BallStyle(marker_color="yellow", edge_color="black")
    layer = draw_ball(ax, make_frame(0, BallPosition(x=52.5, y=34.0)), style, marker_size=6.0)

    assert offsets(layer) == [(52.5, 34.0)]
    assert layer.is_visible
    assert tuple(layer.marker.get_facecolor()[0]) == to_rgba("yellow")
    assert layer.marker.get_sizes()[0] == 36.0


def test_ball_is_drawn_above_players_by_default(ax):
    layer = BallLayer(ax)

    assert layer.marker.get_zorder() > 3.1


def test_update_moves_existing_marker(ax):
    layer = BallLayer(ax)
    layer.update(make_frame(0, BallPosition(x=10.0, y=20.0)))

    collection_count = len(ax.collections)

    layer.update(make_frame(1, BallPosition(x=11.0, y=21.0)))

    assert offsets(layer) == [(11.0, 21.0)]
    assert len(ax.collections) == collection_count


def test_update_returns_artists(ax):
    layer = BallLayer(ax)

    assert layer.update(make_frame(0, BallPosition(x=1.0, y=1.0))) == [layer.marker]


@pytest.mark.parametrize(
    "ball",
    [None, BallPosition(x=None, y=None), BallPosition(x=10.0, y=None)],
)
def test_missing_ball_is_hidden(ax, ball):
    layer = BallLayer(ax)
    layer.update(make_frame(0, ball))

    assert offsets(layer) == []
    assert not layer.is_visible
    assert not layer.is_out_of_bounds


def test_ball_reappears_after_missing_frame(ax):
    layer = BallLayer(ax)

    layer.update(make_frame(0, BallPosition(x=10.0, y=20.0)))
    layer.update(make_frame(1, None))
    assert offsets(layer) == []

    layer.update(make_frame(2, BallPosition(x=12.0, y=22.0)))
    assert offsets(layer) == [(12.0, 22.0)]
    assert layer.is_visible


@pytest.mark.parametrize(
    ("x", "y"),
    [(-6.0, 34.0), (111.0, 34.0), (50.0, -6.0), (50.0, 75.0), (500.0, 500.0)],
)
def test_ball_far_outside_pitch_is_hidden_and_flagged(ax, x, y):
    layer = BallLayer(ax, pitch=PITCH)
    layer.update(make_frame(0, BallPosition(x=x, y=y)))

    assert offsets(layer) == []
    assert not layer.is_visible
    assert layer.is_out_of_bounds


@pytest.mark.parametrize(
    ("x", "y"),
    [(0.0, 0.0), (105.0, 68.0), (-4.0, 34.0), (109.0, 72.0)],
)
def test_ball_on_or_slightly_outside_pitch_is_shown(ax, x, y):
    layer = BallLayer(ax, pitch=PITCH)
    layer.update(make_frame(0, BallPosition(x=x, y=y)))

    assert offsets(layer) == [(x, y)]
    assert layer.is_visible
    assert not layer.is_out_of_bounds


def test_custom_margin(ax):
    layer = BallLayer(ax, pitch=PITCH, out_of_bounds_margin=0.0)
    layer.update(make_frame(0, BallPosition(x=-0.5, y=10.0)))

    assert layer.is_out_of_bounds


def test_no_bounds_check_without_pitch(ax):
    layer = BallLayer(ax)
    layer.update(make_frame(0, BallPosition(x=500.0, y=500.0)))

    assert layer.is_visible


def test_ball_animation_follows_frames(ax, tmp_path):
    frames = [
        make_frame(0, BallPosition(x=10.0, y=10.0)),
        make_frame(1, BallPosition(x=12.0, y=11.0)),
        make_frame(2, None),
        make_frame(3, BallPosition(x=16.0, y=13.0)),
    ]
    layer = BallLayer(ax)
    seen: list[list[tuple[float, float]]] = []

    def step(frame: Frame):
        artists = layer.update(frame)
        seen.append(offsets(layer))
        return artists

    animation = FuncAnimation(ax.figure, step, frames=frames, repeat=False)
    animation.save(tmp_path / "ball.gif", writer="pillow", fps=5)

    # FuncAnimation draws the first frame once more for its initial draw.
    assert seen[-4:] == [[(10.0, 10.0)], [(12.0, 11.0)], [], [(16.0, 13.0)]]

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402

from tracking_visualized.config import RenderingConfig  # noqa: E402
from tracking_visualized.domain import CoordinateSystem  # noqa: E402
from tracking_visualized.rendering import (  # noqa: E402
    PitchDimensions,
    PitchDimensionsError,
    PitchStyle,
    draw_pitch,
)


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def find_artist(ax, gid):
    for artist in [*ax.patches, *ax.lines]:
        if artist.get_gid() == gid:
            return artist

    raise AssertionError(f"No artist with gid {gid!r}")


def test_default_dimensions_follow_ifab():
    dims = PitchDimensions()

    assert dims.length == 105.0
    assert dims.width == 68.0
    assert dims.penalty_area_depth == 16.5
    assert dims.penalty_area_width == 40.32
    assert dims.goal_area_depth == 5.5
    assert dims.goal_area_width == 18.32
    assert dims.center_circle_radius == 9.15
    assert dims.penalty_spot_distance == 11.0
    assert dims.center == (52.5, 34.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"length": 0},
        {"width": -68},
        {"center_circle_radius": float("nan")},
        {"penalty_area_width": 70},
        {"penalty_area_depth": 60},
        {"goal_area_width": 41},
        {"goal_area_depth": 17},
        {"penalty_spot_distance": 20},
        {"width": 15, "penalty_area_width": 14, "goal_area_width": 10},
    ],
)
def test_invalid_dimensions_raise(kwargs):
    with pytest.raises(PitchDimensionsError):
        PitchDimensions(**kwargs)


def test_from_coordinate_system():
    dims = PitchDimensions.from_coordinate_system(
        CoordinateSystem(pitch_length=100.0, pitch_width=64.0)
    )

    assert (dims.length, dims.width) == (100.0, 64.0)


def test_from_rendering_config_maps_width_to_length():
    dims = PitchDimensions.from_rendering_config(
        RenderingConfig(pitch_width=110.0, pitch_height=70.0)
    )

    assert (dims.length, dims.width) == (110.0, 70.0)


def test_invalid_style_raises():
    with pytest.raises(ValueError):
        PitchStyle(line_width=0)


def test_draw_pitch_creates_axes_when_missing():
    ax = draw_pitch()

    assert ax is not None
    assert ax.get_aspect() == 1.0
    assert not ax.axison


def test_draw_pitch_reuses_given_axes():
    _, ax = plt.subplots()

    assert draw_pitch(ax) is ax


def test_axis_limits_include_padding():
    dims = PitchDimensions(length=100.0, width=60.0)
    ax = draw_pitch(dimensions=dims, style=PitchStyle(padding=2.0))

    assert ax.get_xlim() == (-2.0, 102.0)
    assert ax.get_ylim() == (-2.0, 62.0)


def test_boundaries():
    ax = draw_pitch()
    boundary = find_artist(ax, "boundaries")

    assert isinstance(boundary, Rectangle)
    assert boundary.get_xy() == (0, 0)
    assert boundary.get_width() == 105.0
    assert boundary.get_height() == 68.0


def test_halfway_line():
    ax = draw_pitch()
    line = find_artist(ax, "halfway_line")

    assert list(line.get_xdata()) == [52.5, 52.5]
    assert list(line.get_ydata()) == [0, 68.0]


@pytest.mark.parametrize(
    ("name", "depth", "box_width"),
    [("penalty_area", 16.5, 40.32), ("goal_area", 5.5, 18.32)],
)
def test_end_boxes(name, depth, box_width):
    ax = draw_pitch()
    y = (68.0 - box_width) / 2

    left = find_artist(ax, f"{name}_left")
    right = find_artist(ax, f"{name}_right")

    assert left.get_xy() == pytest.approx((0, y))
    assert right.get_xy() == pytest.approx((105.0 - depth, y))

    for box in (left, right):
        assert box.get_width() == depth
        assert box.get_height() == box_width


def test_center_circle_and_spot():
    ax = draw_pitch()
    circle = find_artist(ax, "center_circle")
    spot = find_artist(ax, "center_spot")

    assert isinstance(circle, Circle)
    assert circle.center == (52.5, 34.0)
    assert circle.get_radius() == 9.15
    assert spot.center == (52.5, 34.0)


def test_penalty_spots():
    ax = draw_pitch()

    assert find_artist(ax, "penalty_spot_left").center == (11.0, 34.0)
    assert find_artist(ax, "penalty_spot_right").center == (94.0, 34.0)


def test_custom_dimensions_move_markings():
    dims = PitchDimensions(length=100.0, width=64.0)
    ax = draw_pitch(dimensions=dims)

    assert find_artist(ax, "boundaries").get_width() == 100.0
    assert find_artist(ax, "center_circle").center == (50.0, 32.0)
    assert find_artist(ax, "penalty_spot_right").center == (89.0, 32.0)

from dataclasses import dataclass
from math import isfinite

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import Circle, Rectangle
from matplotlib.transforms import Affine2D, Transform

from tracking_visualized.config import PitchOrientation, RenderingConfig
from tracking_visualized.domain import CoordinateSystem


class PitchDimensionsError(ValueError):
    """Raised when pitch dimensions are invalid or markings do not fit."""


@dataclass(frozen=True, slots=True)
class PitchDimensions:
    """Pitch size and marking dimensions in meters.

    Defaults follow the IFAB Laws of the Game. The pitch is drawn in the
    canonical coordinate system: origin at the bottom-left corner, x along
    the pitch length and y along the pitch width.
    """

    length: float = 105.0
    width: float = 68.0

    penalty_area_depth: float = 16.5
    penalty_area_width: float = 40.32

    goal_area_depth: float = 5.5
    goal_area_width: float = 18.32

    center_circle_radius: float = 9.15
    penalty_spot_distance: float = 11.0

    def __post_init__(self) -> None:
        for name in (
            "length",
            "width",
            "penalty_area_depth",
            "penalty_area_width",
            "goal_area_depth",
            "goal_area_width",
            "center_circle_radius",
            "penalty_spot_distance",
        ):
            value = getattr(self, name)

            if not isfinite(value) or value <= 0:
                raise PitchDimensionsError(f"{name} must be a positive finite number, got {value}.")

        if self.penalty_area_width >= self.width:
            raise PitchDimensionsError("Penalty area must be narrower than the pitch.")

        if self.penalty_area_depth * 2 >= self.length:
            raise PitchDimensionsError("Penalty areas must not overlap.")

        if self.goal_area_width >= self.penalty_area_width:
            raise PitchDimensionsError("Goal area must be narrower than the penalty area.")

        if self.goal_area_depth >= self.penalty_area_depth:
            raise PitchDimensionsError("Goal area must be shallower than the penalty area.")

        if self.penalty_spot_distance >= self.penalty_area_depth:
            raise PitchDimensionsError("Penalty spot must lie inside the penalty area.")

        if self.center_circle_radius * 2 >= min(self.length, self.width):
            raise PitchDimensionsError("Center circle must fit inside the pitch.")

    @property
    def center(self) -> tuple[float, float]:
        return self.length / 2, self.width / 2

    @classmethod
    def from_coordinate_system(cls, coordinate_system: CoordinateSystem) -> "PitchDimensions":
        """Create dimensions matching a match's coordinate system."""

        return cls(
            length=coordinate_system.pitch_length,
            width=coordinate_system.pitch_width,
        )

    @classmethod
    def from_rendering_config(cls, config: RenderingConfig) -> "PitchDimensions":
        """Create dimensions from rendering config.

        RenderingConfig names the long side ``pitch_width`` and the short side
        ``pitch_height``; these map to pitch length and width respectively.
        """

        return cls(
            length=config.pitch_width,
            width=config.pitch_height,
        )


@dataclass(frozen=True, slots=True)
class PitchStyle:
    """Visual style of the pitch."""

    pitch_color: str = "#3a7d44"
    line_color: str = "#ffffff"
    line_width: float = 2.0
    spot_radius: float = 0.25
    padding: float = 3.0
    zorder: float = 1.0

    def __post_init__(self) -> None:
        if self.line_width <= 0:
            raise ValueError("line_width must be positive.")

        if self.spot_radius <= 0:
            raise ValueError("spot_radius must be positive.")

        if not isfinite(self.padding) or self.padding < 0:
            raise ValueError("padding must be a non-negative finite number.")


def _line_kwargs(style: PitchStyle) -> dict:
    return {
        "color": style.line_color,
        "linewidth": style.line_width,
        "zorder": style.zorder,
    }


def _outline_rectangle(
    xy: tuple[float, float],
    width: float,
    height: float,
    style: PitchStyle,
    gid: str,
) -> Rectangle:
    return Rectangle(
        xy,
        width,
        height,
        fill=False,
        edgecolor=style.line_color,
        linewidth=style.line_width,
        zorder=style.zorder,
        gid=gid,
    )


def _spot(center: tuple[float, float], style: PitchStyle, gid: str) -> Circle:
    return Circle(
        center,
        style.spot_radius,
        facecolor=style.line_color,
        edgecolor=style.line_color,
        zorder=style.zorder,
        gid=gid,
    )


def _draw_background(ax: Axes, dims: PitchDimensions, style: PitchStyle) -> None:
    ax.add_patch(
        Rectangle(
            (-style.padding, -style.padding),
            dims.length + 2 * style.padding,
            dims.width + 2 * style.padding,
            facecolor=style.pitch_color,
            edgecolor="none",
            zorder=style.zorder - 0.5,
            gid="pitch_background",
        )
    )


def _draw_boundaries(ax: Axes, dims: PitchDimensions, style: PitchStyle) -> None:
    ax.add_patch(_outline_rectangle((0, 0), dims.length, dims.width, style, "boundaries"))


def _draw_halfway_line(ax: Axes, dims: PitchDimensions, style: PitchStyle) -> None:
    half = dims.length / 2
    ax.plot([half, half], [0, dims.width], gid="halfway_line", **_line_kwargs(style))


def _draw_end_boxes(
    ax: Axes,
    dims: PitchDimensions,
    style: PitchStyle,
    depth: float,
    box_width: float,
    name: str,
) -> None:
    y = (dims.width - box_width) / 2

    ax.add_patch(_outline_rectangle((0, y), depth, box_width, style, f"{name}_left"))
    ax.add_patch(
        _outline_rectangle((dims.length - depth, y), depth, box_width, style, f"{name}_right")
    )


def _draw_penalty_areas(ax: Axes, dims: PitchDimensions, style: PitchStyle) -> None:
    _draw_end_boxes(
        ax, dims, style, dims.penalty_area_depth, dims.penalty_area_width, "penalty_area"
    )


def _draw_goal_areas(ax: Axes, dims: PitchDimensions, style: PitchStyle) -> None:
    _draw_end_boxes(ax, dims, style, dims.goal_area_depth, dims.goal_area_width, "goal_area")


def _draw_center_circle(ax: Axes, dims: PitchDimensions, style: PitchStyle) -> None:
    ax.add_patch(
        Circle(
            dims.center,
            dims.center_circle_radius,
            fill=False,
            edgecolor=style.line_color,
            linewidth=style.line_width,
            zorder=style.zorder,
            gid="center_circle",
        )
    )
    ax.add_patch(_spot(dims.center, style, "center_spot"))


def _draw_penalty_spots(ax: Axes, dims: PitchDimensions, style: PitchStyle) -> None:
    y = dims.width / 2

    ax.add_patch(_spot((dims.penalty_spot_distance, y), style, "penalty_spot_left"))
    ax.add_patch(_spot((dims.length - dims.penalty_spot_distance, y), style, "penalty_spot_right"))


def pitch_view_transform(
    dimensions: PitchDimensions,
    orientation: PitchOrientation = PitchOrientation.HORIZONTAL,
) -> Affine2D:
    """Map canonical pitch coordinates to the coordinates the axes are drawn in.

    Horizontal pitches are unchanged. A vertical pitch is rotated by 90 degrees
    counter-clockwise, so the pitch length runs upwards (x becomes the vertical
    axis) and the left side of the pitch ends up on the left of the screen
    looking up the pitch. It is a rotation, not a mirror image.
    """

    if orientation == PitchOrientation.HORIZONTAL:
        return Affine2D()

    # (x, y) -> (width - y, x)
    return Affine2D.from_values(0.0, 1.0, -1.0, 0.0, dimensions.width, 0.0)


def pitch_data_transform(
    ax: Axes,
    dimensions: PitchDimensions,
    orientation: PitchOrientation = PitchOrientation.HORIZONTAL,
) -> Transform:
    """Transform from canonical pitch coordinates to display coordinates.

    Pass it as ``transform`` to the layers so they can keep working with
    canonical pitch coordinates on a pitch drawn with ``orientation``.
    """

    if orientation == PitchOrientation.HORIZONTAL:
        return ax.transData

    return pitch_view_transform(dimensions, orientation) + ax.transData


def draw_pitch(
    ax: Axes | None = None,
    dimensions: PitchDimensions | None = None,
    style: PitchStyle | None = None,
    orientation: PitchOrientation = PitchOrientation.HORIZONTAL,
) -> Axes:
    """Draw a football pitch onto a Matplotlib Axes.

    Args:
        ax: Axes to draw on. A new figure is created when omitted.
        dimensions: Pitch and marking sizes in meters.
        style: Colors, line width and padding.
        orientation: Whether the pitch length runs along the horizontal or the
            vertical axis of the Axes.

    Returns:
        The Axes containing the pitch, ready for players and ball to be drawn
        on top using canonical pitch coordinates. With a vertical pitch, create
        the layers with ``transform=pitch_data_transform(ax, dimensions, orientation)``.
    """

    dims = dimensions or PitchDimensions()
    style = style or PitchStyle()

    if ax is None:
        _, ax = plt.subplots()

    patch_count = len(ax.patches)
    line_count = len(ax.lines)

    _draw_background(ax, dims, style)
    _draw_boundaries(ax, dims, style)
    _draw_halfway_line(ax, dims, style)
    _draw_penalty_areas(ax, dims, style)
    _draw_goal_areas(ax, dims, style)
    _draw_center_circle(ax, dims, style)
    _draw_penalty_spots(ax, dims, style)

    if orientation == PitchOrientation.VERTICAL:
        data_transform = pitch_data_transform(ax, dims, orientation)

        for artist in [*list(ax.patches)[patch_count:], *list(ax.lines)[line_count:]]:
            artist.set_transform(data_transform)

        ax.set_xlim(-style.padding, dims.width + style.padding)
        ax.set_ylim(-style.padding, dims.length + style.padding)
    else:
        ax.set_xlim(-style.padding, dims.length + style.padding)
        ax.set_ylim(-style.padding, dims.width + style.padding)

    ax.set_aspect("equal")
    ax.set_axis_off()

    return ax


__all__ = [
    "PitchDimensions",
    "PitchDimensionsError",
    "PitchStyle",
    "draw_pitch",
    "pitch_data_transform",
    "pitch_view_transform",
]

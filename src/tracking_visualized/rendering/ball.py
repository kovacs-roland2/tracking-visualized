from dataclasses import dataclass

import numpy as np
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection

from tracking_visualized.domain import BallPosition, Frame
from tracking_visualized.rendering._validation import validate_colors
from tracking_visualized.rendering.pitch import PitchDimensions

DEFAULT_OUT_OF_BOUNDS_MARGIN = 5.0


@dataclass(frozen=True, slots=True)
class BallStyle:
    """Visual style of the ball marker."""

    marker_color: str = "#ffffff"
    edge_color: str = "#111111"
    edge_width: float = 1.0

    def __post_init__(self) -> None:
        validate_colors(self, ("marker_color", "edge_color"))

        if self.edge_width < 0:
            raise ValueError("edge_width must not be negative.")


class BallLayer:
    """Ball marker that can be moved frame by frame.

    The marker is created once; ``update`` only moves or hides it.

    The ball is hidden when a frame has no ball position, when the position is
    not observed, or when it lies further than ``out_of_bounds_margin`` meters
    outside the pitch (when ``pitch`` is given). The ball may legitimately leave
    the pitch for throw-ins, corners and goal kicks, so the margin only filters
    clearly invalid coordinates.
    """

    def __init__(
        self,
        ax: Axes,
        style: BallStyle | None = None,
        *,
        marker_size: float = 5.0,
        pitch: PitchDimensions | None = None,
        out_of_bounds_margin: float = DEFAULT_OUT_OF_BOUNDS_MARGIN,
        zorder: float = 4.0,
    ) -> None:
        if marker_size <= 0:
            raise ValueError("marker_size must be positive.")

        if out_of_bounds_margin < 0:
            raise ValueError("out_of_bounds_margin must not be negative.")

        style = style or BallStyle()

        self._pitch = pitch
        self._margin = out_of_bounds_margin

        self.is_visible: bool = False
        self.is_out_of_bounds: bool = False

        self.marker: PathCollection = ax.scatter(
            [],
            [],
            s=marker_size**2,
            facecolors=style.marker_color,
            edgecolors=style.edge_color,
            linewidths=style.edge_width,
            zorder=zorder,
            gid="ball",
        )

    @property
    def artists(self) -> list[Artist]:
        return [self.marker]

    def _is_out_of_bounds(self, x: float, y: float) -> bool:
        if self._pitch is None:
            return False

        return (
            x < -self._margin
            or x > self._pitch.length + self._margin
            or y < -self._margin
            or y > self._pitch.width + self._margin
        )

    def update(self, frame: Frame) -> list[Artist]:
        """Move the ball marker to the ball position in ``frame``.

        Returns:
            The artists of the layer, as expected by Matplotlib's FuncAnimation.
        """

        return self.update_position(frame.ball_position)

    def update_position(self, position: BallPosition | None) -> list[Artist]:
        """Move the ball marker to ``position``, or hide it when unusable."""

        self.is_visible = False
        self.is_out_of_bounds = False

        if position is not None and position.is_observed:
            if self._is_out_of_bounds(position.x, position.y):
                self.is_out_of_bounds = True
            else:
                self.is_visible = True

        if self.is_visible:
            self.marker.set_offsets(np.array([[position.x, position.y]], dtype=float))
        else:
            self.marker.set_offsets(np.empty((0, 2), dtype=float))

        return self.artists


def draw_ball(
    ax: Axes,
    frame: Frame,
    style: BallStyle | None = None,
    *,
    marker_size: float = 5.0,
    pitch: PitchDimensions | None = None,
) -> BallLayer:
    """Draw the ball for a single frame, e.g. for still images."""

    layer = BallLayer(ax, style, marker_size=marker_size, pitch=pitch)
    layer.update(frame)

    return layer


__all__ = [
    "BallLayer",
    "BallStyle",
    "draw_ball",
]

from dataclasses import dataclass

import numpy as np
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.colors import is_color_like
from matplotlib.text import Text

from tracking_visualized.domain import (
    Event,
    EventType,
    Frame,
    Match,
    MatchTime,
    PeriodType,
    ShotOutcome,
)

PERIOD_LABELS = {
    PeriodType.FIRST_HALF: "1H",
    PeriodType.SECOND_HALF: "2H",
}

GOAL_MARKER_SCALE = 1.4
LABEL_SEPARATOR = "  ·  "


@dataclass(frozen=True, slots=True)
class EventStyle:
    """Visual style of the event indicator."""

    shot_color: str = "#f9c80e"
    goal_color: str = "#ffd700"
    goal_edge_color: str = "#5c4400"
    text_color: str = "#ffffff"
    box_color: str = "#111111"
    box_alpha: float = 0.75
    line_width: float = 2.5
    font_size: float = 12.0

    def __post_init__(self) -> None:
        for name in ("shot_color", "goal_color", "goal_edge_color", "text_color", "box_color"):
            value = getattr(self, name)

            if not is_color_like(value):
                raise ValueError(f"{name} is not a valid color: {value!r}.")

        if not 0 <= self.box_alpha <= 1:
            raise ValueError("box_alpha must be between 0 and 1.")

        if self.line_width <= 0:
            raise ValueError("line_width must be positive.")

        if self.font_size <= 0:
            raise ValueError("font_size must be positive.")


def format_event_time(time: MatchTime) -> str:
    """Format a match time as ``1H 07:49`` (period tag, minutes and seconds)."""

    minutes, seconds = divmod(int(time.seconds), 60)

    return f"{PERIOD_LABELS[time.period]} {minutes:02d}:{seconds:02d}"


def format_event_type(event: Event) -> str:
    """Describe the event type, e.g. ``GOAL`` or ``SHOT · SAVED``."""

    if event.is_goal:
        return "GOAL"

    if event.event_type == EventType.SHOT:
        if event.shot_outcome in (None, ShotOutcome.OTHER):
            return "SHOT"

        return f"SHOT{LABEL_SEPARATOR}{event.shot_outcome.value.upper()}"

    return event.event_type.value.upper()


class EventLayer:
    """Highlights a selected shot or goal while the sequence is near the event.

    The marker sits at the event location and a banner shows the event type,
    shirt number and timestamp. Goals get a gold star and a gold banner border.

    By default the marker is drawn behind the player markers and ball, so it
    works as a halo around the shooter without hiding the shirt number, while
    the banner is drawn on top of everything.

    Artists are created once; ``update`` only shows or hides them. The indicator
    is visible from ``show_before_seconds`` before the event until
    ``show_after_seconds`` after it, measured on the match time of the frame, and
    hidden otherwise (including in a different period).
    """

    def __init__(
        self,
        ax: Axes,
        event: Event,
        *,
        shirt_number: int | None = None,
        style: EventStyle | None = None,
        show_before_seconds: float = 1.0,
        show_after_seconds: float = 3.0,
        marker_size: float = 18.0,
        marker_zorder: float = 2.5,
        label_zorder: float = 6.0,
    ) -> None:
        if show_before_seconds < 0:
            raise ValueError("show_before_seconds must not be negative.")

        if show_after_seconds < 0:
            raise ValueError("show_after_seconds must not be negative.")

        if marker_size <= 0:
            raise ValueError("marker_size must be positive.")

        style = style or EventStyle()

        self.event = event
        self.shirt_number = shirt_number
        self.show_before_seconds = show_before_seconds
        self.show_after_seconds = show_after_seconds

        self.is_visible: bool = False

        has_position = event.x is not None and event.y is not None
        offsets = np.array([[event.x, event.y]], dtype=float) if has_position else None

        if event.is_goal:
            marker_kwargs = {
                "marker": "*",
                "s": (marker_size * GOAL_MARKER_SCALE) ** 2,
                "facecolors": style.goal_color,
                "edgecolors": style.goal_edge_color,
                "linewidths": style.line_width * 0.5,
            }
            box_edge_color = style.goal_color
        else:
            marker_kwargs = {
                "marker": "o",
                "s": marker_size**2,
                "facecolors": "none",
                "edgecolors": style.shot_color,
                "linewidths": style.line_width,
            }
            box_edge_color = style.box_color

        self.marker: PathCollection = ax.scatter(
            [],
            [],
            zorder=marker_zorder,
            visible=False,
            gid="event_marker",
            **marker_kwargs,
        )

        if offsets is not None:
            self.marker.set_offsets(offsets)

        self.label: Text = ax.text(
            0.5,
            0.985,
            self.label_text,
            transform=ax.transAxes,
            ha="center",
            va="top",
            color=style.text_color,
            fontsize=style.font_size,
            fontweight="bold",
            bbox={
                "boxstyle": "round,pad=0.4",
                "facecolor": style.box_color,
                "edgecolor": box_edge_color,
                "linewidth": style.line_width * 0.6,
                "alpha": style.box_alpha,
            },
            zorder=label_zorder,
            visible=False,
            gid="event_label",
        )

    @classmethod
    def from_match(
        cls,
        ax: Axes,
        match: Match,
        event: Event,
        **kwargs: float,
    ) -> "EventLayer":
        """Create a layer, looking up the shirt number of the event's player."""

        shirt_number: int | None = None

        if event.player_id is not None:
            try:
                shirt_number = match.get_player(event.player_id).shirt_number
            except KeyError:
                shirt_number = None

        return cls(ax, event, shirt_number=shirt_number, **kwargs)

    @property
    def label_text(self) -> str:
        parts = [format_event_type(self.event)]

        if self.shirt_number is not None:
            parts.append(f"#{self.shirt_number}")

        parts.append(format_event_time(self.event.time))

        return LABEL_SEPARATOR.join(parts)

    @property
    def artists(self) -> list[Artist]:
        return [self.marker, self.label]

    def is_in_window(self, time: MatchTime) -> bool:
        """Whether a frame at ``time`` falls inside the event window."""

        if time.period != self.event.time.period:
            return False

        offset = time.seconds - self.event.time.seconds

        return -self.show_before_seconds <= offset <= self.show_after_seconds

    def update(self, frame: Frame) -> list[Artist]:
        """Show or hide the indicator depending on the time of ``frame``.

        Returns:
            All artists of the layer, as expected by Matplotlib's FuncAnimation.
        """

        self.is_visible = self.is_in_window(frame.time)

        has_position = len(self.marker.get_offsets()) > 0

        self.marker.set_visible(self.is_visible and has_position)
        self.label.set_visible(self.is_visible)

        return self.artists


def draw_event(
    ax: Axes,
    event: Event,
    frame: Frame,
    *,
    shirt_number: int | None = None,
    style: EventStyle | None = None,
    marker_size: float = 18.0,
    show_before_seconds: float = 1.0,
    show_after_seconds: float = 3.0,
) -> EventLayer:
    """Draw the event indicator for a single frame, e.g. for still images."""

    layer = EventLayer(
        ax,
        event,
        shirt_number=shirt_number,
        style=style,
        marker_size=marker_size,
        show_before_seconds=show_before_seconds,
        show_after_seconds=show_after_seconds,
    )
    layer.update(frame)

    return layer


__all__ = [
    "EventLayer",
    "EventStyle",
    "draw_event",
    "format_event_time",
    "format_event_type",
]

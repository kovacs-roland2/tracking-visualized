from dataclasses import dataclass

from matplotlib.artist import Artist
from matplotlib.figure import Figure
from matplotlib.text import Annotation, Text
from matplotlib.transforms import offset_copy

from tracking_visualized.config import TextPosition, VideoConfig
from tracking_visualized.domain import Event, Frame, Match, Team
from tracking_visualized.rendering._validation import validate_colors
from tracking_visualized.rendering.events import (
    LABEL_SEPARATOR,
    find_event_shirt_number,
    format_event_time,
    format_event_type,
)
from tracking_visualized.rendering.teams import TeamStyle, resolve_team_styles

ELLIPSIS = "…"


@dataclass(frozen=True, slots=True)
class OverlayStyle:
    """Visual style of the event text overlay.

    Font sizes are in points. ``chip_padding`` is relative to the subtitle font size.
    The chip takes the team's marker and number colors when a team style is known,
    otherwise ``chip_color`` and ``chip_text_color``.
    """

    title_color: str = "#ffffff"
    goal_color: str = "#ffd700"
    chip_color: str = "#111111"
    chip_text_color: str = "#ffffff"
    chip_alpha: float = 0.95
    title_font_size: float = 20.0
    subtitle_font_size: float = 13.0
    font_weight: str = "bold"
    chip_padding: float = 0.35
    line_gap: float = 6.0
    max_team_name_chars: int = 24
    zorder: float = 10.0

    def __post_init__(self) -> None:
        validate_colors(self, ("title_color", "goal_color", "chip_color", "chip_text_color"))

        if not 0 <= self.chip_alpha <= 1:
            raise ValueError("chip_alpha must be between 0 and 1.")

        if self.title_font_size <= 0 or self.subtitle_font_size <= 0:
            raise ValueError("Font sizes must be positive.")

        if self.chip_padding < 0:
            raise ValueError("chip_padding must not be negative.")

        if self.line_gap < 0:
            raise ValueError("line_gap must not be negative.")

        if self.max_team_name_chars < 2:
            raise ValueError("max_team_name_chars must be at least 2.")


def shorten_text(text: str, limit: int) -> str:
    """Cut ``text`` to at most ``limit`` characters, ending in an ellipsis if cut."""

    if len(text) <= limit:
        return text

    return text[: limit - 1].rstrip() + ELLIPSIS


@dataclass(frozen=True, slots=True)
class _Line:
    text: str
    font_size: float
    color: str
    chip_color: str | None = None
    padding: float = 0.0

    @property
    def padding_points(self) -> float:
        """How far the chip extends beyond the text."""

        return self.padding * self.font_size if self.chip_color is not None else 0.0


class EventOverlay:
    """Two lines of text describing the event, placed in a margin of the video frame.

    The title shows the event type and match time (``GOAL  ·  1H 07:49``), gold for
    goals. Below or above it, a chip in the team's colors shows the shirt number
    and team name (``#11  ·  Team FC``). Missing details are left out, and the chip
    is omitted when neither is known.

    The text is anchored to a point of the figure and grows away from it, upwards
    for ``TextPosition.TOP`` and downwards for ``TextPosition.BOTTOM``, so that
    in both cases the first line is the one nearest to the pitch. The second line is
    placed relative to the first one's bounding box, which keeps the spacing right
    for any font size.

    The overlay is part of the figure, not of the pitch Axes. Artists are created once
    and the overlay is visible for the whole animation.
    """

    def __init__(
        self,
        fig: Figure,
        event: Event,
        *,
        anchor: tuple[float, float],
        position: TextPosition = TextPosition.TOP,
        team: Team | None = None,
        team_style: TeamStyle | None = None,
        shirt_number: int | None = None,
        style: OverlayStyle | None = None,
    ) -> None:
        style = style or OverlayStyle()

        self.event = event
        self.team = team
        self.shirt_number = shirt_number
        self.is_visible: bool = True

        title = _Line(
            self.title_text,
            style.title_font_size,
            style.goal_color if event.is_goal else style.title_color,
        )
        subtitle_text = self._subtitle_text(style)
        lines = [title]

        if subtitle_text:
            chip_color = team_style.marker_color if team_style else style.chip_color
            chip_text_color = team_style.number_color if team_style else style.chip_text_color
            subtitle = _Line(
                subtitle_text,
                style.subtitle_font_size,
                chip_text_color,
                chip_color=chip_color,
                padding=style.chip_padding,
            )
            # Lines run outward from the anchor, which is next to the pitch: the chip
            # comes first in the top margin, the title first in the bottom margin.
            lines = [subtitle, title] if position == TextPosition.TOP else [title, subtitle]

        direction = 1.0 if position == TextPosition.TOP else -1.0
        vertical_alignment = "bottom" if position == TextPosition.TOP else "top"

        self.title: Text
        self.subtitle: Text | None = None
        self._artists: list[Text] = []

        previous: tuple[Text, _Line] | None = None

        for line in lines:
            kwargs = {
                "color": line.color,
                "fontsize": line.font_size,
                "fontweight": style.font_weight,
                "ha": "center",
                "va": vertical_alignment,
                "zorder": style.zorder,
            }

            if line.chip_color is not None:
                kwargs["bbox"] = {
                    "boxstyle": f"round,pad={line.padding}",
                    "facecolor": line.chip_color,
                    "edgecolor": "none",
                    "alpha": style.chip_alpha,
                }

            if previous is None:
                # Leave room for the chip so that its edge, not its text, touches the anchor.
                transform = offset_copy(
                    fig.transFigure,
                    fig=fig,
                    y=direction * line.padding_points,
                    units="points",
                )
                text = fig.text(*anchor, line.text, transform=transform, **kwargs)
            else:
                previous_text, previous_line = previous
                distance = previous_line.padding_points + style.line_gap + line.padding_points
                text = Annotation(
                    line.text,
                    xy=(0.5, 1.0 if direction > 0 else 0.0),
                    xycoords=previous_text,
                    xytext=(0.0, direction * distance),
                    textcoords="offset points",
                    **kwargs,
                )
                fig.add_artist(text)

            if line is title:
                self.title = text
            else:
                self.subtitle = text

            self._artists.append(text)
            previous = (text, line)

    @classmethod
    def from_match(
        cls,
        fig: Figure,
        match: Match,
        event: Event,
        video_config: VideoConfig,
        *,
        home_style: TeamStyle | None = None,
        away_style: TeamStyle | None = None,
        style: OverlayStyle | None = None,
    ) -> "EventOverlay":
        """Create an overlay, looking up the team and shirt number of the event.

        The anchor and the margin come from ``video_config``.
        """

        team: Team | None = None
        team_style: TeamStyle | None = None

        if event.team_id is not None:
            try:
                team = match.get_team(event.team_id)
            except KeyError:
                team = None

        if team is not None:
            team_style = resolve_team_styles(match.teams, home=home_style, away=away_style)[
                team.team_id
            ]

        return cls(
            fig,
            event,
            anchor=video_config.text_anchor,
            position=video_config.layout.text_position,
            team=team,
            team_style=team_style,
            shirt_number=find_event_shirt_number(match, event),
            style=style,
        )

    @property
    def title_text(self) -> str:
        return LABEL_SEPARATOR.join(
            (format_event_type(self.event), format_event_time(self.event.time))
        )

    def _subtitle_text(self, style: OverlayStyle) -> str:
        parts: list[str] = []

        if self.shirt_number is not None:
            parts.append(f"#{self.shirt_number}")

        if self.team is not None:
            parts.append(shorten_text(self.team.name, style.max_team_name_chars))

        return LABEL_SEPARATOR.join(parts)

    @property
    def artists(self) -> list[Artist]:
        return list(self._artists)

    def update(self, frame: Frame) -> list[Artist]:
        """Return the overlay artists; the text does not change between frames."""

        return self.artists


__all__ = [
    "EventOverlay",
    "OverlayStyle",
    "shorten_text",
]

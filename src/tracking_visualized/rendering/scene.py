from dataclasses import dataclass, replace

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from tracking_visualized.config import PitchOrientation, RenderingConfig, VideoConfig
from tracking_visualized.domain import Match
from tracking_visualized.processing import EventSequence, SelectedSequence
from tracking_visualized.rendering.animation import (
    AnimationSettings,
    FrameLayer,
    SequenceAnimator,
)
from tracking_visualized.rendering.ball import BallLayer, BallStyle
from tracking_visualized.rendering.events import EventLayer, EventStyle
from tracking_visualized.rendering.overlays import EventOverlay, OverlayStyle
from tracking_visualized.rendering.pitch import (
    PitchDimensions,
    PitchStyle,
    draw_pitch,
    pitch_data_transform,
)
from tracking_visualized.rendering.players import PlayerLayer
from tracking_visualized.rendering.teams import TeamStyle
from tracking_visualized.rendering.trails import TrailLayer

EVENT_MARKER_SCALE = 1.5
DEFAULT_FIGSIZE = (10.5, 6.8)


@dataclass(frozen=True, slots=True)
class SequenceScene:
    """A figure with the pitch and all layers needed to draw a sequence."""

    fig: Figure
    ax: Axes
    layers: tuple[FrameLayer, ...]


def build_sequence_scene(
    match: Match,
    sequence: SelectedSequence,
    *,
    config: RenderingConfig | None = None,
    figsize: tuple[float, float] = DEFAULT_FIGSIZE,
    pitch_style: PitchStyle | None = None,
    home_style: TeamStyle | None = None,
    away_style: TeamStyle | None = None,
    ball_style: BallStyle | None = None,
    event_style: EventStyle | None = None,
    show_event_label: bool = True,
    orientation: PitchOrientation = PitchOrientation.HORIZONTAL,
) -> SequenceScene:
    """Create the pitch and layers for a match sequence.

    Layers are returned in drawing order: trails, players, ball and, for an
    event sequence, the event indicator. With a vertical ``orientation`` the pitch
    and all layers are rotated together; frames still hold canonical coordinates.
    ``show_event_label=False`` leaves out the event banner and keeps the marker.
    """

    config = config or RenderingConfig()
    pitch = PitchDimensions.from_coordinate_system(match.coordinate_system)

    fig, ax = plt.subplots(figsize=figsize)
    draw_pitch(ax, pitch, pitch_style, orientation)
    transform = pitch_data_transform(ax, pitch, orientation)

    layers: list[FrameLayer] = [
        TrailLayer.from_match(
            ax,
            match,
            config,
            home_style=home_style,
            away_style=away_style,
            transform=transform,
        ),
        PlayerLayer.from_match(
            ax,
            match,
            home_style=home_style,
            away_style=away_style,
            marker_size=config.player_marker_size,
            transform=transform,
        ),
        BallLayer(
            ax,
            ball_style,
            marker_size=config.ball_marker_size,
            pitch=pitch,
            transform=transform,
        ),
    ]

    if isinstance(sequence, EventSequence):
        layers.append(
            EventLayer.from_match(
                ax,
                match,
                sequence.event,
                style=event_style,
                show_label=show_event_label,
                marker_size=config.player_marker_size * EVENT_MARKER_SCALE,
                transform=transform,
            )
        )

    return SequenceScene(fig=fig, ax=ax, layers=tuple(layers))


def create_sequence_animator(
    match: Match,
    sequence: SelectedSequence,
    *,
    config: RenderingConfig | None = None,
    settings: AnimationSettings | None = None,
    **scene_kwargs,
) -> SequenceAnimator:
    """Build the scene for ``sequence`` and wrap it in a SequenceAnimator.

    Playback settings default to the frame rate from ``config``.
    """

    config = config or RenderingConfig()
    settings = settings or AnimationSettings.from_rendering_config(config)

    scene = build_sequence_scene(match, sequence, config=config, **scene_kwargs)

    return SequenceAnimator(scene.fig, sequence.frames, scene.layers, settings)


def apply_video_layout(
    fig: Figure,
    ax: Axes,
    video_config: VideoConfig,
    pitch_style: PitchStyle | None = None,
) -> None:
    """Fit the pitch Axes into the video frame, inside the layout margins.

    The Axes covers the frame minus ``video_config.layout`` margins. Because the
    pitch keeps its aspect ratio, it is scaled to fit that area and centered in
    it. The rest of the frame is filled with the pitch color.
    """

    pitch_style = pitch_style or PitchStyle()

    fig.set_dpi(video_config.dpi)
    fig.set_facecolor(pitch_style.pitch_color)
    ax.set_position(video_config.pitch_box)


def create_video_animator(
    match: Match,
    sequence: SelectedSequence,
    video_config: VideoConfig | None = None,
    *,
    config: RenderingConfig | None = None,
    pitch_style: PitchStyle | None = None,
    event_style: EventStyle | None = None,
    overlay_style: OverlayStyle | None = None,
    **scene_kwargs,
) -> SequenceAnimator:
    """Build an animator whose figure fills the video frame.

    The figure is sized to ``video_config`` (1080x1920 by default) and the pitch is
    laid out as described by ``video_config.layout``: rotated to run along the tall
    side of the frame, fitted inside the margins and centered. The layout's
    ``marker_scale`` enlarges markers, trails and pitch lines relative to ``config``
    and its ``text_scale`` enlarges the text overlay. For an event sequence the event
    text is shown by an ``EventOverlay`` in the margin chosen by
    ``layout.text_position`` (instead of the banner over the pitch), with event type,
    time, shirt number and team name. Styles passed explicitly (``pitch_style``,
    ``overlay_style``) are used as given, without scaling.

    The frame rate comes from ``video_config``, so the result can be passed
    straight to ``render_video``.
    """

    video_config = video_config or VideoConfig()
    layout = video_config.layout

    config = config or RenderingConfig()
    config = config.model_copy(
        update={
            "player_marker_size": config.player_marker_size * layout.marker_scale,
            "ball_marker_size": config.ball_marker_size * layout.marker_scale,
            "trail_line_width": config.trail_line_width * layout.marker_scale,
        }
    )

    if pitch_style is None:
        default_style = PitchStyle()
        pitch_style = replace(
            default_style, line_width=default_style.line_width * layout.marker_scale
        )

    if overlay_style is None:
        default_overlay_style = OverlayStyle()
        overlay_style = replace(
            default_overlay_style,
            title_font_size=default_overlay_style.title_font_size * layout.text_scale,
            subtitle_font_size=default_overlay_style.subtitle_font_size * layout.text_scale,
            line_gap=default_overlay_style.line_gap * layout.text_scale,
        )

    scene = build_sequence_scene(
        match,
        sequence,
        config=config,
        figsize=video_config.figure_size_inches,
        pitch_style=pitch_style,
        event_style=event_style,
        show_event_label=False,
        orientation=layout.orientation,
        **scene_kwargs,
    )

    apply_video_layout(scene.fig, scene.ax, video_config, pitch_style)

    layers = scene.layers

    if isinstance(sequence, EventSequence):
        overlay = EventOverlay.from_match(
            scene.fig,
            match,
            sequence.event,
            video_config,
            home_style=scene_kwargs.get("home_style"),
            away_style=scene_kwargs.get("away_style"),
            style=overlay_style,
        )
        layers = (*layers, overlay)

    return SequenceAnimator(
        scene.fig,
        sequence.frames,
        layers,
        AnimationSettings(fps=video_config.fps),
    )


__all__ = [
    "SequenceScene",
    "apply_video_layout",
    "build_sequence_scene",
    "create_sequence_animator",
    "create_video_animator",
]

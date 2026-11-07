from dataclasses import dataclass

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from tracking_visualized.config import RenderingConfig
from tracking_visualized.domain import Match
from tracking_visualized.processing import EventSequence, SelectedSequence
from tracking_visualized.rendering.animation import (
    AnimationSettings,
    FrameLayer,
    SequenceAnimator,
)
from tracking_visualized.rendering.ball import BallLayer, BallStyle
from tracking_visualized.rendering.events import EventLayer, EventStyle
from tracking_visualized.rendering.pitch import PitchDimensions, PitchStyle, draw_pitch
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
) -> SequenceScene:
    """Create the pitch and layers for a match sequence.

    Layers are returned in drawing order: trails, players, ball and, for an
    event sequence, the event indicator.
    """

    config = config or RenderingConfig()
    pitch = PitchDimensions.from_coordinate_system(match.coordinate_system)

    fig, ax = plt.subplots(figsize=figsize)
    draw_pitch(ax, pitch, pitch_style)

    layers: list[FrameLayer] = [
        TrailLayer.from_match(ax, match, config, home_style=home_style, away_style=away_style),
        PlayerLayer.from_match(
            ax,
            match,
            home_style=home_style,
            away_style=away_style,
            marker_size=config.player_marker_size,
        ),
        BallLayer(ax, ball_style, marker_size=config.ball_marker_size, pitch=pitch),
    ]

    if isinstance(sequence, EventSequence):
        layers.append(
            EventLayer.from_match(
                ax,
                match,
                sequence.event,
                style=event_style,
                marker_size=config.player_marker_size * EVENT_MARKER_SCALE,
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


__all__ = [
    "SequenceScene",
    "build_sequence_scene",
    "create_sequence_animator",
]

from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import floor, isfinite
from typing import Protocol

from matplotlib.animation import FuncAnimation
from matplotlib.artist import Artist
from matplotlib.figure import Figure

from tracking_visualized.config import RenderingConfig
from tracking_visualized.domain import Frame

MAX_FPS = 120
SCHEDULE_EPSILON = 1e-9


class AnimationError(ValueError):
    """Raised when a sequence cannot be animated."""


class FrameLayer(Protocol):
    """Anything that can draw one tracking frame.

    PlayerLayer, BallLayer, TrailLayer and EventLayer all satisfy this.
    The animation engine only depends on this protocol, so rendering logic
    stays separate from the data model.
    """

    def update(self, frame: Frame) -> Iterable[Artist]: ...


@dataclass(frozen=True, slots=True)
class AnimationSettings:
    """Playback controls.

    Attributes:
        fps: Output frames per second (real-time playback rate and saved video fps).
        speed: Playback speed multiplier. 1.0 is real time, 0.5 is half speed.
        repeat: Loop the animation when shown interactively.
        blit: Only redraw changed artists (faster interactive playback).
    """

    fps: int = 25
    speed: float = 1.0
    repeat: bool = False
    blit: bool = False

    def __post_init__(self) -> None:
        if not 0 < self.fps <= MAX_FPS:
            raise ValueError(f"fps must be between 1 and {MAX_FPS}.")

        if not isfinite(self.speed) or self.speed <= 0:
            raise ValueError("speed must be a positive finite number.")

    @classmethod
    def from_rendering_config(cls, config: RenderingConfig, **kwargs) -> "AnimationSettings":
        """Create settings using the frame rate from ``RenderingConfig``."""

        return cls(fps=config.fps, **kwargs)

    @property
    def interval_ms(self) -> float:
        """Delay between frames for real-time interactive playback."""

        return 1000 / self.fps


@dataclass(frozen=True, slots=True)
class ScheduledFrame:
    """One output frame of the animation and the tracking frame it shows.

    Attributes:
        output_index: Position in the animation, starting at 0.
        target_seconds: Sequence time this output frame stands for, measured
            from the first tracking frame.
        frame_seconds: Time of the tracking frame shown, measured from the
            first tracking frame.
        frame: The tracking frame to draw.
    """

    output_index: int
    target_seconds: float
    frame_seconds: float
    frame: Frame

    @property
    def sync_error_seconds(self) -> float:
        """How far the shown tracking frame is from the intended instant."""

        return abs(self.target_seconds - self.frame_seconds)


def build_playback_schedule(
    frames: Sequence[Frame],
    settings: AnimationSettings | None = None,
) -> tuple[ScheduledFrame, ...]:
    """Map output animation frames to tracking frames by timestamp.

    Output frame ``k`` stands for sequence time ``k * speed / fps``. It shows the
    tracking frame whose timestamp is closest to that instant, so the animation
    follows the tracking clock instead of the frame count:

    - an output fps above the tracking rate repeats frames,
    - an output fps below the tracking rate skips frames,
    - gaps from missing source frames are held on the nearest frame instead of
      speeding the animation up.

    Any sequence duration is supported, including a single frame.

    Raises:
        AnimationError: If ``frames`` is empty, spans several periods, or is not
            ordered by time.
    """

    settings = settings or AnimationSettings()

    if not frames:
        raise AnimationError("Cannot animate an empty sequence.")

    period = frames[0].time.period
    origin = frames[0].time.seconds
    elapsed: list[float] = []

    for frame in frames:
        if frame.time.period != period:
            raise AnimationError("Cannot animate frames from more than one period.")

        if elapsed and frame.time.seconds - origin < elapsed[-1]:
            raise AnimationError("Frames must be ordered by time.")

        elapsed.append(frame.time.seconds - origin)

    step = settings.speed / settings.fps
    count = floor(elapsed[-1] / step + SCHEDULE_EPSILON) + 1

    schedule: list[ScheduledFrame] = []

    for output_index in range(count):
        target = output_index * step
        after = bisect_left(elapsed, target)

        if after == 0:
            chosen = 0
        elif after == len(elapsed):
            chosen = len(elapsed) - 1
        else:
            before_gap = target - elapsed[after - 1]
            after_gap = elapsed[after] - target
            chosen = after - 1 if before_gap <= after_gap else after

        schedule.append(
            ScheduledFrame(
                output_index=output_index,
                target_seconds=target,
                frame_seconds=elapsed[chosen],
                frame=frames[chosen],
            )
        )

    return tuple(schedule)


class SequenceAnimator:
    """Turns a sequence of tracking frames into a Matplotlib animation.

    The animator knows nothing about players, balls or events. It builds a
    timestamp-synchronized schedule and calls ``update(frame)`` on every layer
    for each output frame.

    Layers that keep history (such as TrailLayer) reset themselves when the
    animation loops back to the start, because frame indices go backwards.

    Keep a reference to the object returned by ``build``; Matplotlib stops an
    animation that is garbage collected.
    """

    def __init__(
        self,
        fig: Figure,
        frames: Sequence[Frame],
        layers: Sequence[FrameLayer],
        settings: AnimationSettings | None = None,
    ) -> None:
        self.fig = fig
        self.layers = tuple(layers)
        self.settings = settings or AnimationSettings()
        self.schedule = build_playback_schedule(frames, self.settings)

    @property
    def frame_count(self) -> int:
        return len(self.schedule)

    @property
    def duration_seconds(self) -> float:
        """Playback length in seconds at the configured fps."""

        return (self.frame_count - 1) / self.settings.fps

    def render_frame(self, output_index: int) -> list[Artist]:
        """Draw output frame ``output_index`` and return the artists that changed."""

        if not 0 <= output_index < self.frame_count:
            raise IndexError(f"Output frame {output_index} is outside 0..{self.frame_count - 1}.")

        frame = self.schedule[output_index].frame
        artists: list[Artist] = []

        for layer in self.layers:
            artists.extend(layer.update(frame))

        return artists

    def build(self) -> FuncAnimation:
        """Create the Matplotlib animation (nothing is drawn until shown or saved)."""

        return FuncAnimation(
            self.fig,
            self.render_frame,
            frames=range(self.frame_count),
            interval=self.settings.interval_ms,
            repeat=self.settings.repeat,
            blit=self.settings.blit,
        )


def animate_sequence(
    fig: Figure,
    frames: Sequence[Frame],
    layers: Sequence[FrameLayer],
    settings: AnimationSettings | None = None,
) -> FuncAnimation:
    """Shortcut for ``SequenceAnimator(...).build()``."""

    return SequenceAnimator(fig, frames, layers, settings).build()


__all__ = [
    "AnimationError",
    "AnimationSettings",
    "FrameLayer",
    "ScheduledFrame",
    "SequenceAnimator",
    "animate_sequence",
    "build_playback_schedule",
]

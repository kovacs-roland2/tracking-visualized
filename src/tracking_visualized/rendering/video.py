"""Encode an animation into a validated H.264 MP4 with FFmpeg."""

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import matplotlib
from matplotlib.animation import FFMpegWriter

from tracking_visualized.config import VideoConfig
from tracking_visualized.rendering.animation import SequenceAnimator

FFMPEG_ENV_VAR = "FFMPEG_BINARY"

EXPECTED_CODEC_NAME = "h264"
EXPECTED_PIXEL_FORMAT = "yuv420p"

FPS_TOLERANCE = 1e-3
PROBE_TIMEOUT_SECONDS = 60

INSTALL_HINT = (
    "Install FFmpeg (macOS: `brew install ffmpeg`, Debian/Ubuntu: `sudo apt install ffmpeg`), "
    f"or point to it with VideoConfig.ffmpeg_path or the {FFMPEG_ENV_VAR} environment variable."
)


class VideoRenderError(RuntimeError):
    """Raised when a video cannot be rendered."""


class FFmpegNotFoundError(VideoRenderError):
    """Raised when FFmpeg or FFprobe cannot be located."""


class VideoValidationError(VideoRenderError):
    """Raised when a generated video does not match the requested settings."""


@dataclass(frozen=True, slots=True)
class VideoInfo:
    """Properties of an encoded video file, as reported by FFprobe."""

    path: Path
    codec_name: str
    pixel_format: str
    width: int
    height: int
    fps: float | None
    frame_count: int | None
    duration_seconds: float | None


def _resolve_executable(candidate: str | os.PathLike[str]) -> Path | None:
    """Return the path of an executable given as a file path or a command name."""

    resolved = shutil.which(candidate)

    return Path(resolved) if resolved else None


def find_ffmpeg(config: VideoConfig | None = None) -> Path:
    """Locate the FFmpeg executable.

    Lookup order: ``VideoConfig.ffmpeg_path``, the ``FFMPEG_BINARY`` environment
    variable, then ``PATH``. An explicitly configured path that does not work is an
    error; it is never silently replaced by another FFmpeg.

    Raises:
        FFmpegNotFoundError: If no usable FFmpeg is found.
    """

    if config is not None and config.ffmpeg_path is not None:
        found = _resolve_executable(config.ffmpeg_path)

        if found is None:
            raise FFmpegNotFoundError(
                f"VideoConfig.ffmpeg_path '{config.ffmpeg_path}' is not an executable file."
            )

        return found

    from_env = os.environ.get(FFMPEG_ENV_VAR)

    if from_env:
        found = _resolve_executable(from_env)

        if found is None:
            raise FFmpegNotFoundError(f"{FFMPEG_ENV_VAR} '{from_env}' is not an executable file.")

        return found

    found = _resolve_executable("ffmpeg")

    if found is None:
        raise FFmpegNotFoundError(f"FFmpeg was not found. {INSTALL_HINT}")

    return found


def find_ffprobe(ffmpeg: Path) -> Path:
    """Locate FFprobe, preferring the one installed next to ``ffmpeg``.

    Raises:
        FFmpegNotFoundError: If FFprobe cannot be found.
    """

    beside_ffmpeg = shutil.which("ffprobe", path=str(ffmpeg.parent))
    found = beside_ffmpeg or shutil.which("ffprobe")

    if found is None:
        raise FFmpegNotFoundError(
            f"FFprobe was not found next to '{ffmpeg}' or on PATH; it is needed to validate "
            f"the video and ships with FFmpeg. {INSTALL_HINT}"
        )

    return Path(found)


def encoder_arguments(config: VideoConfig) -> list[str]:
    """Extra FFmpeg output arguments for the H.264 encode."""

    return [
        "-pix_fmt",
        EXPECTED_PIXEL_FORMAT,
        "-crf",
        str(config.crf),
        "-preset",
        config.preset,
        "-movflags",
        "+faststart",
    ]


def _parse_frame_rate(value: str | None) -> float | None:
    if not value:
        return None

    try:
        rate = Fraction(value)
    except (ValueError, ZeroDivisionError):
        return None

    return float(rate) if rate > 0 else None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_probe_output(data: Mapping[str, Any], path: Path) -> VideoInfo:
    """Build a VideoInfo from FFprobe's JSON output.

    Raises:
        VideoValidationError: If the file has no video stream.
    """

    streams = data.get("streams") or []

    if not streams:
        raise VideoValidationError(f"'{path}' contains no video stream.")

    stream = streams[0]
    container = data.get("format") or {}

    duration = _optional_float(stream.get("duration"))

    if duration is None:
        duration = _optional_float(container.get("duration"))

    return VideoInfo(
        path=path,
        codec_name=str(stream.get("codec_name", "")),
        pixel_format=str(stream.get("pix_fmt", "")),
        width=int(stream.get("width", 0)),
        height=int(stream.get("height", 0)),
        fps=_parse_frame_rate(stream.get("avg_frame_rate")),
        frame_count=_optional_int(stream.get("nb_frames")),
        duration_seconds=duration,
    )


def probe_video(path: Path, ffprobe: Path) -> VideoInfo:
    """Read the properties of a video file with FFprobe.

    Raises:
        VideoValidationError: If FFprobe fails or the file has no video stream.
    """

    command = [
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_frames,duration:format=duration",
        "-of",
        "json",
        str(path),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VideoValidationError(f"Could not run FFprobe on '{path}': {exc}") from exc

    if result.returncode != 0:
        raise VideoValidationError(
            f"FFprobe could not read '{path}': {result.stderr.strip() or 'unknown error'}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VideoValidationError(f"FFprobe returned unreadable output for '{path}'.") from exc

    return parse_probe_output(data, path)


def validate_video_info(
    info: VideoInfo,
    config: VideoConfig,
    expected_frames: int,
) -> None:
    """Check that an encoded video matches the requested settings.

    Verifies codec, pixel format, frame size, frame rate, frame count and duration.
    All mismatches are reported together.

    Raises:
        VideoValidationError: If anything differs from what was requested.
    """

    problems: list[str] = []

    if info.codec_name != EXPECTED_CODEC_NAME:
        problems.append(f"codec is '{info.codec_name}', expected '{EXPECTED_CODEC_NAME}'")

    if info.pixel_format != EXPECTED_PIXEL_FORMAT:
        problems.append(
            f"pixel format is '{info.pixel_format}', expected '{EXPECTED_PIXEL_FORMAT}'"
        )

    if (info.width, info.height) != (config.width, config.height):
        problems.append(
            f"size is {info.width}x{info.height}, expected {config.width}x{config.height}"
        )

    if info.fps is None or abs(info.fps - config.fps) > FPS_TOLERANCE:
        shown = "unknown" if info.fps is None else f"{info.fps:g}"
        problems.append(f"frame rate is {shown} fps, expected {config.fps}")

    if info.frame_count is not None and info.frame_count != expected_frames:
        problems.append(f"contains {info.frame_count} frames, expected {expected_frames}")

    expected_duration = expected_frames / config.fps

    # Container timestamps are rounded, so allow up to one frame of slack.
    if info.duration_seconds is None or abs(info.duration_seconds - expected_duration) > (
        1 / config.fps
    ):
        shown = "unknown" if info.duration_seconds is None else f"{info.duration_seconds:.3f}s"
        problems.append(f"duration is {shown}, expected {expected_duration:.3f}s")

    if problems:
        raise VideoValidationError(f"Invalid video '{info.path}': " + "; ".join(problems) + ".")


def render_video(
    animator: SequenceAnimator,
    output_path: str | os.PathLike[str],
    config: VideoConfig | None = None,
) -> VideoInfo:
    """Render ``animator`` to an H.264 MP4 file and validate the result.

    The animator's figure is resized to ``config.width`` x ``config.height``
    pixels. Frames are encoded to a temporary file next to ``output_path``; only
    when FFprobe confirms that the video matches the settings is it moved to
    ``output_path`` (replacing an existing file). A failed encode or a video that
    fails validation therefore never leaves a broken file at the final path.

    Args:
        animator: The animation to encode. Its frame rate must equal ``config.fps``.
        output_path: Destination ``.mp4`` file. Missing folders are created.
        config: Video settings. Defaults to ``VideoConfig()``.

    Returns:
        The validated properties of the written video.

    Raises:
        ValueError: If the animator's frame rate differs from ``config.fps``.
        FFmpegNotFoundError: If FFmpeg or FFprobe is not available.
        VideoRenderError: If FFmpeg fails to encode.
        VideoValidationError: If the encoded video does not match the settings.
    """

    config = config or VideoConfig()
    output = Path(output_path)

    if output.suffix.lower() != f".{config.format}":
        raise ValueError(f"Output file must end with '.{config.format}', got '{output.name}'.")

    if animator.settings.fps != config.fps:
        raise ValueError(
            f"Animator runs at {animator.settings.fps} fps but the video is configured "
            f"for {config.fps} fps; build the animator with AnimationSettings(fps={config.fps})."
        )

    ffmpeg = find_ffmpeg(config)
    ffprobe = find_ffprobe(ffmpeg)

    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f".{output.stem}.{os.urandom(16).hex()}.partial{output.suffix}")

    fig = animator.fig
    fig.set_dpi(config.dpi)
    fig.set_size_inches(*config.figure_size_inches)

    writer = FFMpegWriter(
        fps=config.fps,
        codec=config.codec,
        extra_args=encoder_arguments(config),
    )

    try:
        with matplotlib.rc_context({"animation.ffmpeg_path": str(ffmpeg)}):
            animator.build().save(partial, writer=writer, dpi=config.dpi)

        info = probe_video(partial, ffprobe)
        validate_video_info(info, config, animator.frame_count)

        os.replace(partial, output)
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() if isinstance(exc.stderr, str) else ""

        raise VideoRenderError(
            f"FFmpeg failed to encode '{output.name}'" + (f": {details}" if details else ".")
        ) from exc
    finally:
        partial.unlink(missing_ok=True)

    return VideoInfo(
        path=output,
        codec_name=info.codec_name,
        pixel_format=info.pixel_format,
        width=info.width,
        height=info.height,
        fps=info.fps,
        frame_count=info.frame_count,
        duration_seconds=info.duration_seconds,
    )


__all__ = [
    "FFMPEG_ENV_VAR",
    "FFmpegNotFoundError",
    "VideoInfo",
    "VideoRenderError",
    "VideoValidationError",
    "encoder_arguments",
    "find_ffmpeg",
    "find_ffprobe",
    "parse_probe_output",
    "probe_video",
    "render_video",
    "validate_video_info",
]

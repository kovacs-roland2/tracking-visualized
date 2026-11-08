from math import inf, nextafter
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_DATA_DIR = Path("data")
DEFAULT_RAW_DATA_DIR = Path("data/raw")
DEFAULT_PROCESSED_DATA_DIR = Path("data/processed")
DEFAULT_OUTPUT_DIR = Path("output")


class PathConfig(BaseModel):
    """Paths used by the application."""

    data_dir: Path = DEFAULT_DATA_DIR
    raw_data_dir: Path = DEFAULT_RAW_DATA_DIR
    processed_data_dir: Path = DEFAULT_PROCESSED_DATA_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR


class RenderingConfig(BaseModel):
    """Settings controlling the 2D match visualization."""

    pitch_width: float = Field(default=105.0, gt=0)
    pitch_height: float = Field(default=68.0, gt=0)

    fps: int = Field(default=25, gt=0, le=60)

    player_marker_size: float = Field(default=10.0, gt=0)
    ball_marker_size: float = Field(default=5.0, gt=0)

    trail_duration_seconds: float = Field(
        default=2.0,
        ge=0,
        le=10,
    )


H264_PRESETS = (
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
)


class VideoConfig(BaseModel):
    """Settings controlling generated video.

    Frames are rendered at exactly ``width`` x ``height`` pixels and encoded as
    H.264 in an MP4 container.

    Attributes:
        crf: H.264 constant rate factor. Lower means better quality and larger
            files; 18 is visually lossless for most content, 23 is FFmpeg's default.
        preset: x264 speed/compression trade-off.
        dpi: Dots per inch used to turn pixels into Matplotlib figure inches.
            It changes how large text and lines look relative to the frame.
        ffmpeg_path: Explicit FFmpeg executable. When omitted it is looked up via
            the ``FFMPEG_BINARY`` environment variable and ``PATH``.
    """

    width: int = Field(default=1080, gt=0)
    height: int = Field(default=1920, gt=0)

    fps: int = Field(default=25, gt=0, le=60)

    format: str = "mp4"
    codec: str = "libx264"

    crf: int = Field(default=18, ge=0, le=51)
    preset: str = "medium"

    dpi: int = Field(default=100, gt=0, le=600)

    ffmpeg_path: Path | None = None

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        normalized_value = str(value).strip().lower()

        if normalized_value != "mp4":
            raise ValueError("Only MP4 output is currently supported.")

        return normalized_value

    @field_validator("codec")
    @classmethod
    def validate_codec(cls, value: str) -> str:
        normalized_value = str(value).strip().lower()

        if normalized_value != "libx264":
            raise ValueError("Only H.264 encoding (libx264) is currently supported.")

        return normalized_value

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, value: str) -> str:
        normalized_value = str(value).strip().lower()

        if normalized_value not in H264_PRESETS:
            raise ValueError(f"preset must be one of: {', '.join(H264_PRESETS)}.")

        return normalized_value

    @model_validator(mode="after")
    def validate_even_dimensions(self) -> "VideoConfig":
        # yuv420p stores chroma at half resolution, so H.264 needs even dimensions.
        if self.width % 2 or self.height % 2:
            raise ValueError("Video width and height must be even for H.264 (yuv420p).")

        return self

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height

    @property
    def figure_size_inches(self) -> tuple[float, float]:
        """Figure size that renders to exactly ``width`` x ``height`` pixels at ``dpi``."""

        width_inches = self.width / self.dpi
        height_inches = self.height / self.dpi

        # Matplotlib truncates inch-to-pixel conversions, so only nudge values whose
        # floating-point round trip would otherwise lose a pixel.
        if int(width_inches * self.dpi) < self.width:
            width_inches = nextafter(width_inches, inf)

        if int(height_inches * self.dpi) < self.height:
            height_inches = nextafter(height_inches, inf)

        return width_inches, height_inches


class SequenceConfig(BaseModel):
    """Settings controlling which part of a match is rendered."""

    pre_event_seconds: float = Field(
        default=15.0,
        ge=0,
        le=120,
    )

    post_event_seconds: float = Field(
        default=5.0,
        ge=0,
        le=120,
    )


class SynchronizationConfig(BaseModel):
    max_event_frame_difference_seconds: float = Field(
        default=0.1,
        ge=0,
        le=1,
    )


class TrackingRepairConfig(BaseModel):
    max_player_gap_seconds: float = Field(
        default=0.2,
        ge=0,
        le=2,
    )

    max_ball_gap_seconds: float = Field(
        default=0.2,
        ge=0,
        le=2,
    )


class AppConfig(BaseModel):
    """Application-wide configuration."""

    paths: PathConfig = Field(default_factory=PathConfig)
    rendering: RenderingConfig = Field(default_factory=RenderingConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    sequence: SequenceConfig = Field(default_factory=SequenceConfig)
    synchronization: SynchronizationConfig = Field(default_factory=SynchronizationConfig)
    tracking_repair: TrackingRepairConfig = Field(default_factory=TrackingRepairConfig)


__all__ = [
    "H264_PRESETS",
    "AppConfig",
    "PathConfig",
    "RenderingConfig",
    "SequenceConfig",
    "SynchronizationConfig",
    "TrackingRepairConfig",
    "VideoConfig",
]

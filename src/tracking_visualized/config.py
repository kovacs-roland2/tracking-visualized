from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class PathConfig(BaseModel):
    """Paths used by the application."""

    data_dir: Path = Path("data")
    raw_data_dir: Path = Path("data/raw")
    processed_data_dir: Path = Path("data/processed")
    output_dir: Path = Path("output")


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


class VideoConfig(BaseModel):
    """Settings controlling generated video."""

    width: int = Field(default=1080, gt=0)
    height: int = Field(default=1920, gt=0)

    fps: int = Field(default=25, gt=0, le=60)

    format: str = "mp4"
    codec: str = "libx264"

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        if value.lower() != "mp4":
            raise ValueError("Only MP4 output is currently supported.")
        return value.lower()

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height


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


class AppConfig(BaseModel):
    """Application-wide configuration."""

    paths: PathConfig = Field(default_factory=PathConfig)
    rendering: RenderingConfig = Field(default_factory=RenderingConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    sequence: SequenceConfig = Field(default_factory=SequenceConfig)

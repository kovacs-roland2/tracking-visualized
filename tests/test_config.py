import pytest
from pydantic import ValidationError

from tracking_visualized.config import (
    AppConfig,
    RenderingConfig,
    SequenceConfig,
    VideoConfig,
)


def test_default_configuration():
    config = AppConfig()

    assert config.rendering.pitch_width == 105.0
    assert config.rendering.pitch_height == 68.0

    assert config.rendering.fps == 25

    assert config.video.width == 1080
    assert config.video.height == 1920

    assert config.sequence.pre_event_seconds == 15.0
    assert config.sequence.post_event_seconds == 5.0


def test_video_aspect_ratio():
    config = VideoConfig()

    assert config.aspect_ratio == 0.5625


def test_invalid_pitch_dimensions():
    with pytest.raises(ValidationError):
        RenderingConfig(pitch_width=-105)


def test_invalid_rendering_fps():
    with pytest.raises(ValidationError):
        RenderingConfig(fps=0)


def test_invalid_sequence_duration():
    with pytest.raises(ValidationError):
        SequenceConfig(pre_event_seconds=-1)


def test_invalid_video_format():
    with pytest.raises(ValidationError):
        VideoConfig(format="avi")

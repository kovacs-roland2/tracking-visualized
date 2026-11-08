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


def test_video_defaults_describe_vertical_h264_mp4():
    config = VideoConfig()

    assert (config.width, config.height, config.fps) == (1080, 1920, 25)
    assert (config.format, config.codec) == ("mp4", "libx264")
    assert (config.crf, config.preset, config.dpi) == (18, "medium", 100)
    assert config.ffmpeg_path is None


def test_video_figure_size_matches_pixels_at_dpi():
    assert VideoConfig(width=1080, height=1920, dpi=100).figure_size_inches == (10.8, 19.2)
    assert VideoConfig(width=540, height=960, dpi=50).figure_size_inches == (10.8, 19.2)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width": 1081},
        {"height": 1921},
        {"crf": -1},
        {"crf": 52},
        {"preset": "warp"},
        {"codec": "vp9"},
        {"format": "mkv"},
        {"dpi": 0},
        {"fps": 0},
    ],
)
def test_invalid_video_settings_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        VideoConfig(**kwargs)


def test_video_settings_are_normalized():
    config = VideoConfig(preset="SLOW", codec=" LibX264 ")

    assert (config.preset, config.codec) == ("slow", "libx264")

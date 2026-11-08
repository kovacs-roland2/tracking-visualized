import pytest
from pydantic import ValidationError

from tracking_visualized.config import (
    AppConfig,
    PitchOrientation,
    RenderingConfig,
    SequenceConfig,
    VideoConfig,
    VideoLayoutConfig,
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


def test_default_video_layout_is_a_vertical_pitch_with_tiktok_safe_margins():
    layout = VideoConfig().layout

    assert layout.orientation == PitchOrientation.VERTICAL
    assert (layout.margin_top, layout.margin_bottom) == (160, 320)
    assert (layout.margin_left, layout.margin_right) == (40, 40)
    assert layout.marker_scale > 0
    assert layout.text_scale > 0


def test_pitch_box_is_the_frame_minus_margins_in_figure_fractions():
    left, bottom, width, height = VideoConfig().pitch_box

    assert left == pytest.approx(40 / 1080)
    assert bottom == pytest.approx(320 / 1920)
    assert width == pytest.approx(1000 / 1080)
    assert height == pytest.approx(1440 / 1920)


def test_pitch_box_follows_custom_margins():
    layout = VideoLayoutConfig(margin_top=0, margin_bottom=0, margin_left=0, margin_right=0)

    assert VideoConfig(layout=layout).pitch_box == (0.0, 0.0, 1.0, 1.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"margin_top": -1},
        {"margin_left": -1},
        {"marker_scale": 0},
        {"text_scale": 0},
        {"orientation": "diagonal"},
    ],
)
def test_invalid_layout_settings_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        VideoLayoutConfig(**kwargs)


@pytest.mark.parametrize(
    "layout",
    [
        VideoLayoutConfig(margin_left=540, margin_right=540),
        VideoLayoutConfig(margin_top=960, margin_bottom=960),
        VideoLayoutConfig(margin_top=2000),
    ],
)
def test_margins_must_leave_room_for_the_pitch(layout):
    with pytest.raises(ValidationError, match="margins"):
        VideoConfig(layout=layout)


def test_trail_line_width_must_be_positive():
    assert RenderingConfig().trail_line_width == 2.0

    with pytest.raises(ValidationError):
        RenderingConfig(trail_line_width=0)

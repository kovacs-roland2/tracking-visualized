import matplotlib

matplotlib.use("Agg")

import json  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
from dataclasses import replace  # noqa: E402
from pathlib import Path  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from tracking_visualized.config import VideoConfig  # noqa: E402
from tracking_visualized.domain import Frame, MatchTime, PeriodType  # noqa: E402
from tracking_visualized.rendering import (  # noqa: E402
    AnimationSettings,
    FFmpegNotFoundError,
    SequenceAnimator,
    VideoInfo,
    VideoRenderError,
    VideoValidationError,
    find_ffmpeg,
    find_ffprobe,
    render_video,
    validate_video_info,
)
from tracking_visualized.rendering import video as video_module  # noqa: E402
from tracking_visualized.rendering.video import (  # noqa: E402
    FFMPEG_ENV_VAR,
    encoder_arguments,
    parse_probe_output,
    probe_video,
)

SMALL = VideoConfig(width=64, height=112, fps=10, dpi=50)


def has_x264() -> bool:
    ffmpeg = shutil.which("ffmpeg")

    if ffmpeg is None or shutil.which("ffprobe") is None:
        return False

    encoders = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, check=False
    )

    return "libx264" in encoders.stdout


requires_ffmpeg = pytest.mark.skipif(not has_x264(), reason="FFmpeg with libx264 is not installed")


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """No FFmpeg anywhere: empty PATH and no FFMPEG_BINARY."""

    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.delenv(FFMPEG_ENV_VAR, raising=False)

    return empty


def make_executable(path: Path, body: str = "exit 0") -> Path:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)

    return path


def make_info(**overrides) -> VideoInfo:
    values = {
        "path": Path("clip.mp4"),
        "codec_name": "h264",
        "pixel_format": "yuv420p",
        "width": 64,
        "height": 112,
        "fps": 10.0,
        "frame_count": 20,
        "duration_seconds": 2.0,
    }
    values.update(overrides)

    return VideoInfo(**values)


def probe_json(**stream_overrides) -> dict:
    stream = {
        "codec_name": "h264",
        "width": 64,
        "height": 112,
        "pix_fmt": "yuv420p",
        "avg_frame_rate": "10/1",
        "duration": "2.000000",
        "nb_frames": "20",
    }
    stream.update(stream_overrides)

    return {"streams": [stream], "format": {"duration": "2.000000"}}


def make_animator(frame_count: int = 20, fps: int = 10) -> SequenceAnimator:
    fig = plt.figure()
    frames = [
        Frame(
            frame_index=i,
            time=MatchTime(period=PeriodType.FIRST_HALF, seconds=i / fps),
            player_positions=(),
            ball_position=None,
        )
        for i in range(frame_count)
    ]

    class MovingDot:
        def __init__(self) -> None:
            self.dot = fig.add_axes((0, 0, 1, 1)).plot([], [], "o")[0]

        def update(self, frame: Frame):
            self.dot.set_data([frame.frame_index / 100], [0.5])

            return [self.dot]

    return SequenceAnimator(fig, frames, [MovingDot()], AnimationSettings(fps=fps))


# ---------------------------------------------------------------------------
# Locating FFmpeg
# ---------------------------------------------------------------------------


def test_find_ffmpeg_prefers_configured_path(tmp_path, clean_env, monkeypatch):
    configured = make_executable(tmp_path / "configured-ffmpeg")
    from_env = make_executable(tmp_path / "env-ffmpeg")
    monkeypatch.setenv(FFMPEG_ENV_VAR, str(from_env))

    assert find_ffmpeg(VideoConfig(ffmpeg_path=configured)) == configured


def test_find_ffmpeg_uses_environment_variable_before_path(tmp_path, clean_env, monkeypatch):
    from_env = make_executable(tmp_path / "env-ffmpeg")
    make_executable(clean_env / "ffmpeg")
    monkeypatch.setenv(FFMPEG_ENV_VAR, str(from_env))

    assert find_ffmpeg() == from_env


def test_find_ffmpeg_falls_back_to_path(clean_env):
    on_path = make_executable(clean_env / "ffmpeg")

    assert find_ffmpeg().resolve() == on_path.resolve()


def test_find_ffmpeg_missing_explains_how_to_install(clean_env):
    with pytest.raises(FFmpegNotFoundError, match="brew install ffmpeg"):
        find_ffmpeg()


def test_invalid_configured_path_is_not_silently_replaced(tmp_path, clean_env):
    make_executable(clean_env / "ffmpeg")

    with pytest.raises(FFmpegNotFoundError, match="ffmpeg_path"):
        find_ffmpeg(VideoConfig(ffmpeg_path=tmp_path / "missing"))


def test_invalid_environment_variable_is_reported(clean_env, monkeypatch):
    monkeypatch.setenv(FFMPEG_ENV_VAR, "/nowhere/ffmpeg")

    with pytest.raises(FFmpegNotFoundError, match=FFMPEG_ENV_VAR):
        find_ffmpeg()


def test_find_ffprobe_prefers_the_one_next_to_ffmpeg(tmp_path, clean_env):
    folder = tmp_path / "bin"
    folder.mkdir()
    ffmpeg = make_executable(folder / "ffmpeg")
    beside = make_executable(folder / "ffprobe")
    make_executable(clean_env / "ffprobe")

    assert find_ffprobe(ffmpeg).resolve() == beside.resolve()


def test_find_ffprobe_falls_back_to_path_and_reports_when_missing(tmp_path, clean_env):
    ffmpeg = make_executable(tmp_path / "ffmpeg")

    with pytest.raises(FFmpegNotFoundError, match="FFprobe"):
        find_ffprobe(ffmpeg)

    on_path = make_executable(clean_env / "ffprobe")

    assert find_ffprobe(ffmpeg).resolve() == on_path.resolve()


# ---------------------------------------------------------------------------
# Encoding settings
# ---------------------------------------------------------------------------


def test_encoder_arguments_configure_h264():
    arguments = encoder_arguments(VideoConfig(crf=21, preset="slow"))

    pairs = dict(zip(arguments[::2], arguments[1::2], strict=True))

    assert pairs == {
        "-pix_fmt": "yuv420p",
        "-crf": "21",
        "-preset": "slow",
        "-movflags": "+faststart",
    }


# ---------------------------------------------------------------------------
# Probing and validation
# ---------------------------------------------------------------------------


def test_parse_probe_output():
    info = parse_probe_output(probe_json(), Path("clip.mp4"))

    assert info == make_info()


def test_parse_probe_output_handles_unknown_values():
    data = probe_json(avg_frame_rate="0/0", nb_frames="N/A", duration="N/A")
    info = parse_probe_output(data, Path("clip.mp4"))

    assert info.fps is None
    assert info.frame_count is None
    assert info.duration_seconds == 2.0  # falls back to the container duration


def test_parse_probe_output_without_video_stream():
    with pytest.raises(VideoValidationError, match="no video stream"):
        parse_probe_output({"streams": []}, Path("clip.mp4"))


def test_probe_video_reads_ffprobe_json(tmp_path):
    ffprobe = make_executable(tmp_path / "ffprobe", f"cat <<'EOF'\n{json.dumps(probe_json())}\nEOF")

    info = probe_video(tmp_path / "clip.mp4", ffprobe)

    assert info.codec_name == "h264"
    assert (info.width, info.height) == (64, 112)


def test_probe_video_reports_ffprobe_failure(tmp_path):
    ffprobe = make_executable(tmp_path / "ffprobe", "echo 'moov atom not found' >&2\nexit 1")

    with pytest.raises(VideoValidationError, match="moov atom not found"):
        probe_video(tmp_path / "clip.mp4", ffprobe)


def test_probe_video_reports_unreadable_output(tmp_path):
    ffprobe = make_executable(tmp_path / "ffprobe", "echo not-json")

    with pytest.raises(VideoValidationError, match="unreadable"):
        probe_video(tmp_path / "clip.mp4", ffprobe)


def test_matching_video_passes_validation():
    validate_video_info(make_info(), SMALL, expected_frames=20)


def test_validation_tolerates_container_rounding_and_missing_frame_count():
    validate_video_info(
        make_info(duration_seconds=2.08, frame_count=None), SMALL, expected_frames=20
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"codec_name": "mpeg4"}, "codec is 'mpeg4'"),
        ({"pixel_format": "yuv444p"}, "pixel format is 'yuv444p'"),
        ({"width": 66}, "size is 66x112"),
        ({"height": 100}, "size is 64x100"),
        ({"fps": 25.0}, "frame rate is 25"),
        ({"fps": None}, "frame rate is unknown"),
        ({"frame_count": 19}, "contains 19 frames, expected 20"),
        ({"duration_seconds": 5.0}, "duration is 5.000s"),
        ({"duration_seconds": None}, "duration is unknown"),
    ],
)
def test_each_mismatch_is_reported(overrides, message):
    with pytest.raises(VideoValidationError, match=message):
        validate_video_info(make_info(**overrides), SMALL, expected_frames=20)


def test_all_mismatches_are_reported_together():
    info = make_info(codec_name="vp9", width=10, pixel_format="rgb24")

    with pytest.raises(VideoValidationError) as error:
        validate_video_info(info, SMALL, expected_frames=20)

    message = str(error.value)

    assert "codec" in message
    assert "pixel format" in message
    assert "size" in message


# ---------------------------------------------------------------------------
# render_video
# ---------------------------------------------------------------------------


def test_render_video_requires_the_configured_extension(tmp_path):
    with pytest.raises(ValueError, match=r"\.mp4"):
        render_video(make_animator(), tmp_path / "clip.avi", SMALL)


def test_render_video_requires_matching_frame_rate(tmp_path):
    with pytest.raises(ValueError, match="25 fps"):
        render_video(make_animator(fps=10), tmp_path / "clip.mp4", VideoConfig(fps=25))


def test_render_video_reports_missing_ffmpeg_before_doing_any_work(tmp_path, clean_env):
    with pytest.raises(FFmpegNotFoundError):
        render_video(make_animator(), tmp_path / "out" / "clip.mp4", SMALL)

    assert not (tmp_path / "out").exists()


def test_ffmpeg_failure_is_reported_and_leaves_no_file(tmp_path, monkeypatch):
    class FailingAnimation:
        def save(self, path, **kwargs):
            Path(path).write_bytes(b"half a video")

            raise subprocess.CalledProcessError(1, "ffmpeg", output="", stderr="Unknown encoder")

    animator = make_animator()
    monkeypatch.setattr(animator, "build", lambda: FailingAnimation())
    monkeypatch.setattr(video_module, "find_ffmpeg", lambda config: Path("/fake/ffmpeg"))
    monkeypatch.setattr(video_module, "find_ffprobe", lambda ffmpeg: Path("/fake/ffprobe"))

    output = tmp_path / "clip.mp4"

    with pytest.raises(VideoRenderError, match="Unknown encoder"):
        render_video(animator, output, SMALL)

    assert list(tmp_path.iterdir()) == []


@requires_ffmpeg
def test_render_video_encodes_a_valid_h264_mp4(tmp_path):
    output = tmp_path / "nested" / "clip.mp4"

    info = render_video(make_animator(frame_count=20), output, SMALL)

    assert output.is_file()
    assert (info.codec_name, info.pixel_format) == ("h264", "yuv420p")
    assert (info.width, info.height) == (64, 112)
    assert info.fps == pytest.approx(10.0)
    assert info.frame_count == 20
    assert info.duration_seconds == pytest.approx(2.0, abs=0.1)
    assert [p.name for p in output.parent.iterdir()] == ["clip.mp4"]


@requires_ffmpeg
def test_render_video_encodes_rounding_sensitive_dimensions(tmp_path):
    config = VideoConfig(width=58, height=112, fps=10, dpi=100)

    info = render_video(make_animator(frame_count=2), tmp_path / "clip.mp4", config)

    assert (info.width, info.height) == (58, 112)


@requires_ffmpeg
def test_render_video_resizes_the_figure_to_the_video(tmp_path):
    animator = make_animator(frame_count=5)
    animator.fig.set_size_inches(3, 3)

    render_video(animator, tmp_path / "clip.mp4", SMALL)

    assert tuple(animator.fig.get_size_inches() * animator.fig.dpi) == pytest.approx((64, 112))


@requires_ffmpeg
def test_render_video_replaces_an_existing_file(tmp_path):
    output = tmp_path / "clip.mp4"
    output.write_bytes(b"old")

    render_video(make_animator(frame_count=5), output, SMALL)

    assert output.read_bytes() != b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["clip.mp4"]


@requires_ffmpeg
def test_invalid_video_never_reaches_the_final_path(tmp_path, monkeypatch):
    output = tmp_path / "clip.mp4"
    output.write_bytes(b"previous good video")

    real_probe = video_module.probe_video

    def wrong_codec(path, ffprobe):
        return replace(real_probe(path, ffprobe), codec_name="mpeg4")

    monkeypatch.setattr(video_module, "probe_video", wrong_codec)

    with pytest.raises(VideoValidationError, match="codec"):
        render_video(make_animator(frame_count=5), output, SMALL)

    assert output.read_bytes() == b"previous good video"
    assert [p.name for p in tmp_path.iterdir()] == ["clip.mp4"]

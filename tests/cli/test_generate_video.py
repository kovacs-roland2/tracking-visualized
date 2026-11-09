import shutil
import subprocess
from pathlib import Path

import pytest

from tracking_visualized.cli import generate_video
from tracking_visualized.cli.generate_video import (
    EXIT_ERROR,
    EXIT_OK,
    ProgressReporter,
    build_parser,
    default_output_path,
    format_shot_listing,
    main,
)
from tracking_visualized.config import VideoConfig, VideoLayoutConfig
from tracking_visualized.domain import PeriodType, ShotOutcome
from tracking_visualized.providers.dfl import ShotSummary
from tracking_visualized.rendering import VideoInfo

MATCH_ID = "J03TEST"
GOAL_ID = "E-GOAL"

# A small frame keeps real encodes quick; it still has room for the event text.
SMALL_TIKTOK = VideoConfig(width=540, height=960, dpi=50)


def has_x264() -> bool:
    ffmpeg = shutil.which("ffmpeg")

    if ffmpeg is None or shutil.which("ffprobe") is None:
        return False

    encoders = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, check=False
    )

    return "libx264" in encoders.stdout


requires_ffmpeg = pytest.mark.skipif(not has_x264(), reason="FFmpeg with libx264 is not installed")


@pytest.fixture
def small_format(monkeypatch):
    monkeypatch.setattr(generate_video, "video_config_for_format", lambda name: SMALL_TIKTOK)


def run(dfl_data_dir, *args: str) -> list[str]:
    return ["--match", MATCH_ID, "--data-dir", str(dfl_data_dir), *args]


def fake_video(output: Path, frames: int = 1) -> VideoInfo:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"x" * 2000)

    return VideoInfo(output, "h264", "yuv420p", 540, 960, 25.0, frames, 2.0)


def make_shot(**overrides) -> ShotSummary:
    values = {
        "event_id": "E1",
        "period": PeriodType.FIRST_HALF,
        "period_seconds": 467.9,
        "team_name": "Home FC",
        "shirt_number": 11,
        "player_name": None,
        "outcome": ShotOutcome.GOAL,
        "xg": 0.3,
    }
    values.update(overrides)

    return ShotSummary(**values)


# --- parser --------------------------------------------------------------------------------


def test_parser_defaults():
    args = build_parser().parse_args(["--match", "J03WMX", "--event", "E1"])

    assert (args.match, args.event) == ("J03WMX", "E1")
    assert args.format == "tiktok"
    assert (args.pre, args.post) == (5.0, 3.0)
    assert args.output is None
    assert args.list_events is False
    assert args.verbose is False


def test_parser_reads_all_options():
    args = build_parser().parse_args(
        [
            "--match", "J03WMX", "--event", "E1", "--format", "tiktok", "-o", "clip.mp4",
            "--pre", "7", "--post", "1.5", "--data-dir", "d", "--ffmpeg", "/usr/bin/ffmpeg",
            "--verbose",
        ]
    )  # fmt: skip

    assert args.output == Path("clip.mp4")
    assert (args.pre, args.post) == (7.0, 1.5)
    assert args.data_dir == Path("d")
    assert args.ffmpeg == Path("/usr/bin/ffmpeg")
    assert args.verbose is True


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--event", "E1"],
        ["--match", "M", "--event", "E1", "--format", "vhs"],
        ["--match", "M", "--event", "E1", "--pre", "-1"],
        ["--match", "M", "--event", "E1", "--post", "soon"],
    ],
)
def test_invalid_arguments_exit_with_usage_error(argv, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(argv)

    assert exit_info.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_event_is_required_without_list_events(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--match", MATCH_ID])

    assert exit_info.value.code == 2
    assert "--event is required" in capsys.readouterr().err


def test_an_empty_clip_is_rejected(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--match", MATCH_ID, "--event", "E1", "--pre", "0", "--post", "0"])

    assert exit_info.value.code == 2
    assert "--pre and --post cannot both be 0" in capsys.readouterr().err


# --- helpers -------------------------------------------------------------------------------


def test_default_output_path_is_in_the_output_folder():
    assert default_output_path("J03WMX", "182265", "tiktok") == Path(
        "output/J03WMX_182265_tiktok.mp4"
    )


def test_default_output_path_is_safe_for_odd_event_ids():
    path = default_output_path("J03WMX", "a/b c:d", "tiktok")

    assert path.parent == Path("output")
    assert path.name == "J03WMX_a_b_c_d_tiktok.mp4"


def test_shot_listing_is_a_table():
    listing = format_shot_listing(
        [
            make_shot(),
            make_shot(
                event_id="LONGER-EVENT-ID",
                period=PeriodType.SECOND_HALF,
                period_seconds=61.0,
                team_name="Away United",
                shirt_number=None,
                outcome=ShotOutcome.SAVED,
            ),
        ]
    )
    header, goal, saved = listing.splitlines()

    assert header.split() == ["EVENT", "ID", "TIME", "TEAM", "PLAYER", "OUTCOME"]
    assert goal.split() == ["E1", "1H", "07:47", "Home", "FC", "#11", "GOAL"]
    assert saved.split() == ["LONGER-EVENT-ID", "2H", "01:01", "Away", "United", "-", "saved"]
    # Columns line up.
    assert goal.index("1H") == saved.index("2H")


@pytest.mark.parametrize(
    ("shirt_number", "player_name", "expected"),
    [
        (11, "K. Coman", "#11 K. Coman"),
        (None, "K. Coman", "K. Coman"),
        (11, None, "#11"),
        (None, None, "-"),
    ],
)
def test_shot_listing_shows_the_player_number_and_name(shirt_number, player_name, expected):
    listing = format_shot_listing([make_shot(shirt_number=shirt_number, player_name=player_name)])
    header, row = listing.splitlines()
    player_column = row[header.index("PLAYER") : header.index("OUTCOME")]

    assert player_column.strip() == expected


def test_empty_shot_listing():
    assert format_shot_listing([]) == "No shots or goals found."


def test_progress_is_reported_in_ten_percent_steps():
    lines: list[str] = []
    reporter = ProgressReporter(lines.append)

    for done in range(1, 101):
        reporter(done, 100)

    assert len(lines) == 10
    assert lines[0].startswith("  rendering 10%")
    assert lines[-1].startswith("  rendering 100% (100/100 frames)")


def test_progress_ignores_an_empty_total():
    lines: list[str] = []

    ProgressReporter(lines.append)(0, 0)

    assert lines == []


# --- running the command -------------------------------------------------------------------


def test_list_events_prints_the_shots_without_reading_tracking(dfl_data_dir, capsys):
    next((dfl_data_dir / MATCH_ID).glob("*positions_raw_observed*")).write_text("not xml")

    code = main(run(dfl_data_dir, "--list-events"))
    out = capsys.readouterr().out

    assert code == EXIT_OK
    assert "E-GOAL" in out and "E-WIDE" in out
    assert "Home FC" in out and "GOAL" in out
    assert out.index("E-GOAL") < out.index("E-WIDE")


def test_missing_match_is_a_friendly_error(tmp_path, capsys):
    code = main(["--match", "J00NONE", "--event", "E1", "--data-dir", str(tmp_path)])
    captured = capsys.readouterr()

    assert code == EXIT_ERROR
    assert captured.err.startswith("error: No data found for match 'J00NONE'")
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_unknown_event_is_a_friendly_error(dfl_data_dir, capsys):
    code = main(run(dfl_data_dir, "--event", "NOPE"))
    captured = capsys.readouterr()

    assert code == EXIT_ERROR
    assert "no shot or goal with event ID 'NOPE'" in captured.err
    assert "--list-events" in captured.err
    assert "Traceback" not in captured.err


def test_wrong_output_extension_is_rejected_before_loading(dfl_data_dir, capsys):
    code = main(run(dfl_data_dir, "--event", GOAL_ID, "-o", "clip.avi"))
    captured = capsys.readouterr()

    assert code == EXIT_ERROR
    assert "must end with '.mp4'" in captured.err
    assert "Reading match" not in captured.out


def test_missing_ffmpeg_is_a_friendly_error(dfl_data_dir, small_format, tmp_path, capsys):
    code = main(
        run(
            dfl_data_dir,
            "--event", GOAL_ID,
            "-o", str(tmp_path / "clip.mp4"),
            "--ffmpeg", str(tmp_path / "no-ffmpeg"),
        )
    )  # fmt: skip
    captured = capsys.readouterr()

    assert code == EXIT_ERROR
    assert "ffmpeg_path" in captured.err and "not an executable" in captured.err
    assert not (tmp_path / "clip.mp4").exists()


def test_verbose_shows_the_traceback(dfl_data_dir, capsys):
    code = main(run(dfl_data_dir, "--event", "NOPE", "--verbose"))
    captured = capsys.readouterr()

    assert code == EXIT_ERROR
    assert "Traceback" in captured.err
    assert "error: " in captured.err


def test_a_too_small_text_margin_is_reported(dfl_data_dir, monkeypatch, tmp_path, capsys):
    tight = VideoConfig(
        width=540, height=960, dpi=50, layout=VideoLayoutConfig(margin_top=40, text_gap=0)
    )
    monkeypatch.setattr(generate_video, "video_config_for_format", lambda name: tight)

    code = main(run(dfl_data_dir, "--event", GOAL_ID, "-o", str(tmp_path / "clip.mp4")))

    assert code == EXIT_ERROR
    assert "top margin" in capsys.readouterr().err


def test_main_wires_the_pipeline_together(
    dfl_data_dir, small_format, tmp_path, monkeypatch, capsys
):
    captured: dict = {}

    def fake_render(animator, output, config, *, progress):
        captured.update(frames=animator.frame_count, output=output, config=config)
        progress(1, 2)
        progress(2, 2)

        return fake_video(output, animator.frame_count)

    monkeypatch.setattr(generate_video, "render_video", fake_render)
    output = tmp_path / "out" / "goal.mp4"
    arguments = run(
        dfl_data_dir, "--event", GOAL_ID, "--pre", "2", "--post", "1", "-o", str(output)
    )

    code = main(arguments)
    out = capsys.readouterr().out

    assert code == EXIT_OK
    assert captured["frames"] == 76
    assert captured["output"] == output
    assert captured["config"] == SMALL_TIKTOK

    assert out.splitlines()[0] == "Match J03TEST, event E-GOAL, format tiktok"
    assert "Rendering 76 frames at 540x960, 25 fps" in out
    assert "rendering 50%" in out and "rendering 100%" in out
    assert f"Saved video to {output}" in out
    assert "h264 yuv420p 540x960 at 25 fps, 2.00 s" in out
    assert out.index("Reading match") < out.index("Rendering") < out.index("Saved video")


def test_a_clip_near_the_period_start_is_noted(
    dfl_data_dir, small_format, tmp_path, monkeypatch, capsys
):
    def fake_render(animator, output, config, *, progress):
        return fake_video(output)

    monkeypatch.setattr(generate_video, "render_video", fake_render)
    arguments = run(dfl_data_dir, "--event", GOAL_ID, "--pre", "60", "-o", str(tmp_path / "c.mp4"))

    code = main(arguments)

    assert code == EXIT_OK
    assert "Note: the clip is 11.0 s instead of 63.0 s" in capsys.readouterr().out


@pytest.mark.parametrize(("pre", "post"), [("0", "1"), ("1", "0")])
def test_one_sided_clips_are_rendered(pre, post, dfl_data_dir, small_format, tmp_path, monkeypatch):
    def fake_render(animator, output, config, *, progress):
        return fake_video(output, animator.frame_count)

    monkeypatch.setattr(generate_video, "render_video", fake_render)
    arguments = run(
        dfl_data_dir,
        "--event",
        GOAL_ID,
        "--pre",
        pre,
        "--post",
        post,
        "-o",
        str(tmp_path / "c.mp4"),
    )

    assert main(arguments) == EXIT_OK


def test_list_events_ignores_the_clip_length(dfl_data_dir, capsys):
    code = main(run(dfl_data_dir, "--list-events", "--pre", "0", "--post", "0"))

    assert code == EXIT_OK
    assert GOAL_ID in capsys.readouterr().out


def test_an_untruncated_clip_with_off_grid_seconds_has_no_note(
    dfl_data_dir, small_format, tmp_path, monkeypatch, capsys
):
    def fake_render(animator, output, config, *, progress):
        return fake_video(output)

    monkeypatch.setattr(generate_video, "render_video", fake_render)
    arguments = run(
        dfl_data_dir,
        "--event",
        GOAL_ID,
        "--pre",
        "2.33",
        "--post",
        "2.33",
        "-o",
        str(tmp_path / "c.mp4"),
    )

    code = main(arguments)

    assert code == EXIT_OK
    assert "Note:" not in capsys.readouterr().out


def test_the_ffmpeg_option_reaches_the_video_config(
    dfl_data_dir, small_format, tmp_path, monkeypatch
):
    seen: dict = {}

    def fake_render(animator, output, config, *, progress):
        seen["ffmpeg"] = config.ffmpeg_path

        return fake_video(output)

    monkeypatch.setattr(generate_video, "render_video", fake_render)
    arguments = run(
        dfl_data_dir, "--event", GOAL_ID, "--ffmpeg", "/opt/ffmpeg", "-o", str(tmp_path / "c.mp4")
    )

    main(arguments)

    assert seen["ffmpeg"] == Path("/opt/ffmpeg")


def test_default_output_goes_to_the_output_folder(
    dfl_data_dir, small_format, tmp_path, monkeypatch
):
    seen: dict = {}

    def fake_render(animator, output, config, *, progress):
        seen["output"] = output

        return fake_video(tmp_path / "ignored.mp4")

    monkeypatch.setattr(generate_video, "render_video", fake_render)

    main(run(dfl_data_dir, "--event", GOAL_ID, "--pre", "1", "--post", "1"))

    assert seen["output"] == Path("output/J03TEST_E-GOAL_tiktok.mp4")


@requires_ffmpeg
def test_end_to_end_writes_a_valid_video(dfl_data_dir, small_format, tmp_path, capsys):
    output = tmp_path / "videos" / "goal.mp4"

    code = main(
        run(dfl_data_dir, "--event", GOAL_ID, "--pre", "1", "--post", "1", "-o", str(output))
    )
    out = capsys.readouterr().out

    assert code == EXIT_OK
    assert output.is_file() and output.stat().st_size > 0
    assert "h264 yuv420p 540x960 at 25 fps" in out
    assert "validated with ffprobe" in out
    assert not list(output.parent.glob(".*partial*"))


@requires_ffmpeg
def test_end_to_end_second_half_event(dfl_data_dir, small_format, tmp_path, capsys):
    output = tmp_path / "wide.mp4"

    code = main(
        run(dfl_data_dir, "--event", "E-WIDE", "--pre", "1", "--post", "1", "-o", str(output))
    )

    assert code == EXIT_OK
    assert output.is_file()

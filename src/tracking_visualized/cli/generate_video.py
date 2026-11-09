"""Generate a video of a shot or goal from a match with a single command.

Example:
    generate-video --match J03WMX --event 18226500000041 --format tiktok
"""

import argparse
import re
import sys
import traceback
from collections.abc import Callable, Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from tracking_visualized.cli.arguments import non_negative_float  # noqa: E402
from tracking_visualized.config import (  # noqa: E402
    DEFAULT_VIDEO_FORMAT,
    VideoConfig,
    video_config_for_format,
    video_format_names,
)
from tracking_visualized.domain import MatchTime  # noqa: E402
from tracking_visualized.processing import select_event_sequence  # noqa: E402
from tracking_visualized.providers.dfl import (  # noqa: E402
    DEFAULT_DFL_DIR,
    DflMatchFiles,
    ShotSummary,
    list_shots,
    load_event_match,
)
from tracking_visualized.rendering import (  # noqa: E402
    VideoInfo,
    create_video_animator,
    format_event_time,
    render_video,
)

PROG = "generate-video"

DEFAULT_PRE_SECONDS = 5.0
DEFAULT_POST_SECONDS = 3.0
DEFAULT_OUTPUT_DIR = Path("output")

PROGRESS_STEP_PERCENT = 10

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INTERRUPTED = 130

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser of the video generation command."""

    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Generate a video of a shot or goal from a match.",
        epilog="List the event IDs of a match with: %(prog)s --match MATCH_ID --list-events",
    )

    parser.add_argument(
        "--match",
        required=True,
        metavar="MATCH_ID",
        help="Match to use, e.g. J03WMX. Its files are read from <data-dir>/<MATCH_ID>/.",
    )
    parser.add_argument(
        "--event",
        metavar="EVENT_ID",
        help="ID of the shot or goal to render. Required unless --list-events is used.",
    )
    parser.add_argument(
        "--list-events",
        action="store_true",
        help="List the shots and goals of the match with their IDs and exit.",
    )
    parser.add_argument(
        "--format",
        default=DEFAULT_VIDEO_FORMAT,
        choices=video_format_names(),
        help=f"Output format. Default: {DEFAULT_VIDEO_FORMAT}",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help=(
            "Path of the MP4 file to write; missing folders are created and an existing "
            f"file is replaced. Default: {DEFAULT_OUTPUT_DIR}/<match>_<event>_<format>.mp4"
        ),
    )
    parser.add_argument(
        "--pre",
        type=non_negative_float,
        default=DEFAULT_PRE_SECONDS,
        help=f"Seconds before the event to include. Default: {DEFAULT_PRE_SECONDS:g}",
    )
    parser.add_argument(
        "--post",
        type=non_negative_float,
        default=DEFAULT_POST_SECONDS,
        help=f"Seconds after the event to include. Default: {DEFAULT_POST_SECONDS:g}",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DFL_DIR,
        help=f"Folder that contains the match folders. Default: {DEFAULT_DFL_DIR}",
    )
    parser.add_argument(
        "--ffmpeg",
        type=Path,
        metavar="PATH",
        help="FFmpeg executable to use. Default: $FFMPEG_BINARY, then ffmpeg on PATH.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show the full traceback when something goes wrong.",
    )

    return parser


def default_output_path(match_id: str, event_id: str, video_format: str) -> Path:
    """Default file for a generated video, e.g. ``output/J03WMX_1822_tiktok.mp4``."""

    name = _UNSAFE_FILENAME_CHARS.sub("_", f"{match_id}_{event_id}_{video_format}")

    return DEFAULT_OUTPUT_DIR / f"{name}.mp4"


def format_shot_listing(shots: Sequence[ShotSummary]) -> str:
    """Format shots as a table: event ID, time, team, player and outcome."""

    if not shots:
        return "No shots or goals found."

    rows = [("EVENT ID", "TIME", "TEAM", "PLAYER", "OUTCOME")]

    for shot in shots:
        rows.append(
            (
                shot.event_id,
                format_event_time(MatchTime(shot.period, shot.period_seconds)),
                shot.team_name,
                f"#{shot.shirt_number}" if shot.shirt_number is not None else "-",
                "GOAL" if shot.is_goal else shot.outcome.value,
            )
        )

    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]

    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        for row in rows
    )


class ProgressReporter:
    """Prints rendering progress in steps of ``PROGRESS_STEP_PERCENT`` percent."""

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._last_step = 0

    def __call__(self, done: int, total: int) -> None:
        if total <= 0:
            return

        step = int(done * 100 / total) // PROGRESS_STEP_PERCENT * PROGRESS_STEP_PERCENT

        if step > self._last_step:
            self._last_step = step
            self._emit(f"  rendering {step}% ({done}/{total} frames)")


def _say(message: str) -> None:
    print(message, flush=True)


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr, flush=True)

    return EXIT_ERROR


def _describe_video(info: VideoInfo) -> str:
    size_mb = info.path.stat().st_size / 1_000_000

    return (
        f"{info.codec_name} {info.pixel_format} {info.width}x{info.height} at "
        f"{info.fps:g} fps, {info.duration_seconds:.2f} s, {size_mb:.1f} MB"
    )


def _video_config(args: argparse.Namespace) -> VideoConfig:
    video_config = video_config_for_format(args.format)

    if args.ffmpeg is not None:
        video_config = video_config.model_copy(update={"ffmpeg_path": args.ffmpeg})

    return video_config


def _generate(args: argparse.Namespace) -> int:
    files = DflMatchFiles.discover(args.match, args.data_dir)

    if args.list_events:
        _say(format_shot_listing(list_shots(files)))

        return EXIT_OK

    video_config = _video_config(args)
    output = args.output or default_output_path(files.match_id, args.event, args.format)

    if output.suffix.lower() != f".{video_config.format}":
        return _fail(f"The output file must end with '.{video_config.format}', got '{output}'.")

    _say(f"Match {files.match_id}, event {args.event}, format {args.format}")

    match = load_event_match(
        files,
        args.event,
        pre_event_seconds=args.pre,
        post_event_seconds=args.post,
        on_stage=_say,
    )
    sequence = select_event_sequence(
        match,
        args.event,
        pre_event_seconds=args.pre,
        post_event_seconds=args.post,
    )

    if sequence.is_truncated:
        _say(
            f"Note: the clip is {sequence.duration_seconds:.1f} s instead of "
            f"{sequence.requested_duration_seconds:.1f} s because the event is close to the "
            "start or end of the period."
        )

    animator = create_video_animator(match, sequence, video_config)

    try:
        _say(
            f"Rendering {animator.frame_count} frames at "
            f"{video_config.width}x{video_config.height}, {video_config.fps} fps"
        )
        info = render_video(animator, output, video_config, progress=ProgressReporter(_say))
    finally:
        plt.close(animator.fig)

    _say(f"Saved video to {info.path}")
    _say(f"  {_describe_video(info)} (validated with ffprobe)")

    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command and return the process exit code.

    Problems caused by the input, the data or the environment are reported as one
    ``error:`` line on stderr with exit code 1, plus ``--verbose`` for a traceback.
    Invalid arguments exit with code 2 via argparse.
    """

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.list_events and not args.event:
        parser.error("--event is required (use --list-events to see the available IDs).")

    if not args.list_events and args.pre + args.post <= 0:
        parser.error("--pre and --post cannot both be 0; the clip would be a single frame.")

    try:
        return _generate(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)

        return EXIT_INTERRUPTED
    except (ValueError, OSError, RuntimeError) as exc:
        if args.verbose:
            traceback.print_exc()

        return _fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())

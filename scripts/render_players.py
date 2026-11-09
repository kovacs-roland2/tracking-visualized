"""Render one tracking frame (players, ball, movement trails and optionally a
selected shot/goal event) of the sample match to output/players.png, or with --animate a clip of
the sequence to output/sequence.gif using the animation engine.

Loads the frames with the same DFL loader as ``generate-video``, which scans the whole
tracking file twice (once for the match timeline, once for the selected frames), so it
takes about a minute on the full match.
With --video the same clip is encoded to output/sequence.mp4 (needs FFmpeg) in the 1080x1920
vertical TikTok layout: the pitch is rotated and fitted inside the layout margins, and the
event text (type, time, shirt number, team) is shown above the pitch.
"""

import argparse
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from sample_data import MATCH_ID  # noqa: E402

from tracking_visualized.config import (  # noqa: E402
    PitchOrientation,
    RenderingConfig,
    VideoConfig,
)
from tracking_visualized.domain import Match, PeriodType  # noqa: E402
from tracking_visualized.providers.dfl import (  # noqa: E402
    DflDatasetError,
    DflMatchFiles,
    ShotSummary,
    list_shots,
    load_event_match,
    load_time_window_match,
)
from tracking_visualized.rendering import (  # noqa: E402
    AnimationSettings,
    BallLayer,
    EventLayer,
    EventOverlay,
    FrameLayer,
    OverlayLayoutError,
    OverlayStyle,
    PitchDimensions,
    PitchStyle,
    PlayerLayer,
    SequenceAnimator,
    TrailLayer,
    apply_video_layout,
    draw_pitch,
    pitch_data_transform,
    render_video,
    resolve_team_styles,
)

OUTPUT_FILE = Path("output") / "players.png"
ANIMATION_FILE = Path("output") / "sequence.gif"
VIDEO_FILE = Path("output") / "sequence.mp4"
ANIMATION_DPI = 80

FPS = 25


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seconds",
        type=float,
        default=60.0,
        help="With --event none: seconds after first-half kick-off to render (default: 60).",
    )
    parser.add_argument(
        "--trail-seconds",
        type=float,
        default=RenderingConfig().trail_duration_seconds,
        help="Length of the player movement trails in seconds (default: from RenderingConfig).",
    )
    parser.add_argument(
        "--event",
        default="first-goal",
        help=(
            "Shot to highlight (either half): an event ID or 'first-goal', or 'none' to render "
            "the frame at --seconds without an event (default: first-goal). "
            "The rendered frame is taken relative to the event instead of --seconds."
        ),
    )
    parser.add_argument(
        "--after-event-seconds",
        type=float,
        default=0.5,
        help="With --event: seconds after the event to render (default: 0.5).",
    )
    parser.add_argument(
        "--animate",
        action="store_true",
        help="Render an animated clip (output/sequence.gif) instead of a single frame.",
    )
    parser.add_argument(
        "--video",
        action="store_true",
        help="Encode the clip as an H.264 MP4 (output/sequence.mp4) with FFmpeg.",
    )
    parser.add_argument(
        "--clip-before-seconds",
        type=float,
        default=3.0,
        help="With --animate/--video: seconds before the event (or --seconds) to start the clip.",
    )
    parser.add_argument(
        "--clip-after-seconds",
        type=float,
        default=2.0,
        help="With --animate/--video: seconds after the event (or --seconds) to end the clip.",
    )
    return parser.parse_args()


def select_shot(files: DflMatchFiles, event_arg: str) -> ShotSummary:
    """Pick a shot by event ID, or the first goal of the match."""

    shots = list_shots(files)

    if event_arg == "first-goal":
        goals = [shot for shot in shots if shot.is_goal]

        if not goals:
            raise SystemExit("No goal found.")

        return goals[0]

    for shot in shots:
        if shot.event_id == event_arg:
            return shot

    ids = ", ".join(shot.event_id for shot in shots)

    raise SystemExit(f"No shot with ID '{event_arg}'. Available: {ids}")


def load_frames(args: argparse.Namespace, files: DflMatchFiles, shot: ShotSummary | None) -> Match:
    """Load the frames to render: the clip, or the trail window ending at the rendered frame."""

    clip = args.animate or args.video

    if shot is not None:
        pre = args.clip_before_seconds if clip else args.trail_seconds
        post = args.clip_after_seconds if clip else args.after_event_seconds

        return load_event_match(
            files, shot.event_id, pre_event_seconds=pre, post_event_seconds=post, on_stage=print
        )

    start = args.seconds - (args.clip_before_seconds if clip else args.trail_seconds)
    end = args.seconds + (args.clip_after_seconds if clip else 0.0)

    return load_time_window_match(
        files,
        period=PeriodType.FIRST_HALF,
        start_seconds=max(0.0, start),
        end_seconds=end,
        on_stage=print,
    )


def main() -> None:
    args = parse_args()

    files = DflMatchFiles.discover(MATCH_ID)
    shot = select_shot(files, args.event) if args.event.lower() != "none" else None

    try:
        match = load_frames(args, files, shot)
    except DflDatasetError as error:
        raise SystemExit(str(error)) from error

    coordinate_system = match.coordinate_system
    teams = match.teams
    players = match.players
    event = match.events[0] if match.events else None
    frames = list(match.frames)

    if not (args.animate or args.video):
        # The trails end at the rendered (last) frame and reach back --trail-seconds.
        trail_start = frames[-1].time.seconds - args.trail_seconds
        frames = [frame for frame in frames if frame.time.seconds >= trail_start]

    if not any(frame.player_positions for frame in frames):
        raise SystemExit("No player positions found in the selected frames.")

    first_frame = frames[0].frame_index
    last_frame = frames[-1].frame_index

    pitch = PitchDimensions.from_coordinate_system(coordinate_system)
    config = RenderingConfig()
    team_styles = resolve_team_styles(teams)

    video_config = VideoConfig(fps=FPS)
    layout = video_config.layout

    # The preview and GIF use a landscape figure; the video uses the vertical TikTok layout.
    orientation = layout.orientation if args.video else PitchOrientation.HORIZONTAL
    marker_scale = layout.marker_scale if args.video else 1.6
    pitch_style = PitchStyle(
        line_width=PitchStyle().line_width * (marker_scale if args.video else 1)
    )
    overlay_defaults = OverlayStyle()
    overlay_style = replace(
        overlay_defaults,
        title_font_size=overlay_defaults.title_font_size * layout.text_scale,
        subtitle_font_size=overlay_defaults.subtitle_font_size * layout.text_scale,
        line_gap=overlay_defaults.line_gap * layout.text_scale,
    )

    if args.video:
        fig, ax = plt.subplots(figsize=video_config.figure_size_inches, dpi=video_config.dpi)
        apply_video_layout(fig, ax, video_config, pitch_style)
    else:
        fig, ax = plt.subplots(figsize=(10.5, 6.8))

    draw_pitch(ax, pitch, pitch_style, orientation)
    transform = pitch_data_transform(ax, pitch, orientation)

    layers: list[FrameLayer] = [
        TrailLayer(
            ax,
            players,
            team_styles,
            duration_seconds=args.trail_seconds,
            line_width=config.trail_line_width * marker_scale,
            transform=transform,
        ),
        PlayerLayer(
            ax,
            players,
            team_styles,
            marker_size=config.player_marker_size * marker_scale,
            transform=transform,
        ),
        BallLayer(
            ax,
            marker_size=config.ball_marker_size * marker_scale,
            pitch=pitch,
            transform=transform,
        ),
    ]

    event_layer: EventLayer | None = None

    if event is not None and shot is not None:
        event_layer = EventLayer(
            ax,
            event,
            shirt_number=shot.shirt_number,
            show_label=not args.video,
            marker_size=config.player_marker_size * 1.5 * marker_scale,
            transform=transform,
        )
        layers.append(event_layer)

        if args.video:
            # In the video the event text sits in the top margin instead of over the pitch.
            team = next(team for team in teams if team.team_id == event.team_id)
            overlay = EventOverlay(
                fig,
                event,
                anchor=video_config.text_anchor,
                position=layout.text_position,
                team=team,
                team_style=team_styles[team.team_id],
                shirt_number=shot.shirt_number,
                style=overlay_style,
            )

            try:
                overlay.validate_fit(video_config)
            except OverlayLayoutError as error:
                raise SystemExit(str(error)) from error

            layers.append(overlay)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    if args.animate or args.video:
        animator = SequenceAnimator(fig, frames, layers, AnimationSettings(fps=FPS))

        if args.video:
            info = render_video(animator, VIDEO_FILE, video_config)

            print(f"Encoded {animator.frame_count} frames ({len(frames)} tracking frames).")
            print(
                f"{info.codec_name} {info.pixel_format} {info.width}x{info.height} "
                f"at {info.fps:g} fps, {info.duration_seconds:.2f} s "
                f"(validated with ffprobe)."
            )
            print(f"Saved video to {VIDEO_FILE}")
            return

        animation = animator.build()
        animation.save(ANIMATION_FILE, writer="pillow", fps=FPS, dpi=ANIMATION_DPI)

        worst_sync = max(step.sync_error_seconds for step in animator.schedule)

        print(f"Animated {len(frames)} tracking frames (frames {first_frame}..{last_frame}).")
        print(
            f"{animator.frame_count} output frames at {FPS} fps, "
            f"{animator.duration_seconds:.2f} s long "
            f"(worst timestamp sync error {worst_sync * 1000:.1f} ms)."
        )
        print(f"Saved animation to {ANIMATION_FILE}")
        return

    for frame in frames:
        for layer in layers:
            layer.update(frame)

    fig.savefig(OUTPUT_FILE, dpi=150, bbox_inches="tight")

    if event_layer is not None:
        print(f"Event '{event_layer.event.event_id}': {event_layer.label_text}.")

    print(f"Rendered frame {frames[-1].frame_index} with trails from {len(frames)} frames.")
    print(f"Saved player preview to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

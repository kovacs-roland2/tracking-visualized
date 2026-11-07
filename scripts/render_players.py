"""Render one tracking frame (players, ball, movement trails and optionally a
selected shot/goal event) of the sample match to output/players.png, or with --animate a clip of
the sequence to output/sequence.gif using the animation engine.

Scans the whole tracking file twice (once to find the first-half origin frame,
once to collect positions for the trail window), so it takes about a minute on the full match.
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from sample_data import EVENTS_FILE, METADATA_FILE, TRACKING_FILE  # noqa: E402

from tracking_visualized.config import RenderingConfig  # noqa: E402
from tracking_visualized.domain import (  # noqa: E402
    BallPosition,
    CoordinateSystem,
    Event,
    EventType,
    Frame,
    MatchTime,
    PeriodType,
    Player,
    PlayerPosition,
    ShotOutcome,
    Team,
    TeamSide,
)
from tracking_visualized.providers.dfl import (  # noqa: E402
    BallTrackingSample,
    PlayerTrackingSample,
    ShotEvent,
    TrackingPeriod,
    create_coordinate_system,
    iter_tracking_samples,
    load_match_metadata,
    load_shot_events,
    normalize_event_coordinates,
    normalize_tracking_coordinates,
)
from tracking_visualized.providers.dfl.shared import load_player_index  # noqa: E402
from tracking_visualized.rendering import (  # noqa: E402
    AnimationSettings,
    BallLayer,
    EventLayer,
    FrameLayer,
    PitchDimensions,
    PlayerLayer,
    SequenceAnimator,
    TrailLayer,
    draw_pitch,
    resolve_team_styles,
)

OUTPUT_FILE = Path("output") / "players.png"
ANIMATION_FILE = Path("output") / "sequence.gif"
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
            "First-half shot to highlight: an event ID or 'first-goal', or 'none' to render "
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
        "--clip-before-seconds",
        type=float,
        default=3.0,
        help="With --animate: seconds before the event (or --seconds) to start the clip.",
    )
    parser.add_argument(
        "--clip-after-seconds",
        type=float,
        default=2.0,
        help="With --animate: seconds after the event (or --seconds) to end the clip.",
    )
    return parser.parse_args()


def find_first_half_origin() -> int | None:
    """Return the earliest first-half frame number across all players and the ball.

    iter_tracking_samples yields one FrameSet at a time in XML order, so the
    first sample seen is not necessarily the first frame of the half. Taking
    the minimum over every first-half sample makes the origin independent of
    track order.
    """

    origin: int | None = None

    for sample in iter_tracking_samples(TRACKING_FILE, METADATA_FILE):
        if sample.period != TrackingPeriod.FIRST_HALF:
            continue

        if origin is None or sample.frame_number < origin:
            origin = sample.frame_number

    return origin


def collect_frame_samples(
    first_frame: int, last_frame: int, coordinate_system: CoordinateSystem
) -> dict[int, tuple[list[PlayerPosition], BallPosition | None]]:
    """Collect player and ball positions for first-half frames in ``first_frame..last_frame``."""

    frames: dict[int, tuple[list[PlayerPosition], BallPosition | None]] = {}

    for sample in iter_tracking_samples(TRACKING_FILE, METADATA_FILE):
        if sample.period != TrackingPeriod.FIRST_HALF:
            continue

        if not first_frame <= sample.frame_number <= last_frame:
            continue

        positions, ball = frames.setdefault(sample.frame_number, ([], None))
        x, y = normalize_tracking_coordinates(sample.x, sample.y, coordinate_system)

        if isinstance(sample, PlayerTrackingSample):
            positions.append(PlayerPosition(sample.person_id, x, y))
        elif isinstance(sample, BallTrackingSample):
            frames[sample.frame_number] = (
                positions,
                BallPosition(x=x, y=y, z=sample.z, is_in_play=sample.is_alive),
            )

    return frames


def select_shot(event_arg: str) -> ShotEvent:
    """Pick a first-half shot by event ID, or the first first-half goal."""

    shots = [
        shot
        for shot in load_shot_events(EVENTS_FILE, METADATA_FILE)
        if shot.period.name == "FIRST_HALF"
    ]

    if event_arg == "first-goal":
        goals = [shot for shot in shots if shot.is_goal]

        if not goals:
            raise SystemExit("No first-half goal found.")

        return goals[0]

    for shot in shots:
        if shot.event_id == event_arg:
            return shot

    ids = ", ".join(shot.event_id for shot in shots)

    raise SystemExit(f"No first-half shot with ID '{event_arg}'. Available: {ids}")


def build_event(
    shot: ShotEvent,
    event_frame: int,
    origin_frame: int,
    coordinate_system: CoordinateSystem,
) -> Event:
    x, y = normalize_event_coordinates(shot.x, shot.y, coordinate_system)

    return Event(
        event_id=shot.event_id,
        event_type=EventType.SHOT,
        time=MatchTime(PeriodType.FIRST_HALF, (event_frame - origin_frame) / FPS),
        team_id=shot.team_id,
        player_id=shot.player_id,
        x=x,
        y=y,
        frame_index=event_frame,
        shot_outcome=ShotOutcome(shot.outcome.value),
        xg=shot.xg,
    )


def main() -> None:
    args = parse_args()

    metadata = load_match_metadata(METADATA_FILE)
    coordinate_system = create_coordinate_system(metadata.pitch_length, metadata.pitch_width)

    teams = (
        Team(metadata.home_team.team_id, metadata.home_team.name, TeamSide.HOME),
        Team(metadata.away_team.team_id, metadata.away_team.name, TeamSide.AWAY),
    )
    players = tuple(
        Player(ref.person_id, ref.team_id, ref.name, ref.shirt_number)
        for ref in load_player_index(METADATA_FILE).values()
    )

    origin_frame = find_first_half_origin()

    if origin_frame is None:
        raise SystemExit("No first-half tracking samples found.")

    shot = select_shot(args.event) if args.event.lower() != "none" else None
    event: Event | None = None

    if shot is not None:
        anchor_frame = (
            shot.calculated_frame
            if shot.calculated_frame is not None
            else origin_frame + round(shot.period_seconds * FPS)
        )
        event = build_event(shot, anchor_frame, origin_frame, coordinate_system)
    else:
        anchor_frame = origin_frame + round(args.seconds * FPS)

    if args.animate:
        first_frame = max(origin_frame, anchor_frame - round(args.clip_before_seconds * FPS))
        last_frame = anchor_frame + round(args.clip_after_seconds * FPS)
    else:
        last_frame = anchor_frame + (round(args.after_event_seconds * FPS) if shot else 0)
        first_frame = max(origin_frame, last_frame - round(args.trail_seconds * FPS))

    samples = collect_frame_samples(first_frame, last_frame, coordinate_system)

    if not samples or not any(positions for positions, _ in samples.values()):
        raise SystemExit(f"No player positions found in frames {first_frame}..{last_frame}.")

    frames = [
        Frame(
            frame_index=frame_number,
            time=MatchTime(PeriodType.FIRST_HALF, (frame_number - origin_frame) / FPS),
            player_positions=tuple(positions),
            ball_position=ball,
        )
        for frame_number, (positions, ball) in sorted(samples.items())
    ]

    pitch = PitchDimensions.from_coordinate_system(coordinate_system)
    config = RenderingConfig()
    team_styles = resolve_team_styles(teams)

    fig, ax = plt.subplots(figsize=(10.5, 6.8))
    draw_pitch(ax, pitch)

    layers: list[FrameLayer] = [
        TrailLayer(
            ax,
            players,
            team_styles,
            duration_seconds=args.trail_seconds,
            line_width=config.player_marker_size * 0.3,
        ),
        PlayerLayer(ax, players, team_styles, marker_size=config.player_marker_size * 1.6),
        BallLayer(ax, marker_size=config.ball_marker_size * 1.6, pitch=pitch),
    ]

    event_layer: EventLayer | None = None

    if event is not None and shot is not None:
        event_layer = EventLayer(
            ax,
            event,
            shirt_number=shot.shirt_number,
            marker_size=config.player_marker_size * 2.4,
        )
        layers.append(event_layer)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    if args.animate:
        animator = SequenceAnimator(fig, frames, layers, AnimationSettings(fps=FPS))
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

"""Render one tracking frame (players, ball and movement trails) of the sample match
to output/players.png.

Scans the whole tracking file twice (once to find the first-half origin frame,
once to collect positions for the trail window), so it takes about a minute on the full match.
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from tracking_visualized.config import RenderingConfig  # noqa: E402
from tracking_visualized.domain import (  # noqa: E402
    BallPosition,
    CoordinateSystem,
    Frame,
    MatchTime,
    PeriodType,
    Player,
    PlayerPosition,
    Team,
    TeamSide,
)
from tracking_visualized.providers.dfl import (  # noqa: E402
    BallTrackingSample,
    PlayerTrackingSample,
    TrackingPeriod,
    create_coordinate_system,
    iter_tracking_samples,
    load_match_metadata,
    normalize_tracking_coordinates,
)
from tracking_visualized.providers.dfl.shared import load_player_index  # noqa: E402
from tracking_visualized.rendering import (  # noqa: E402
    PitchDimensions,
    TrailLayer,
    draw_ball,
    draw_pitch,
    draw_players,
    resolve_team_styles,
)

MATCH_ID = "J03WMX"
BASE_DIR = Path("data/raw/dfl") / MATCH_ID
TRACKING_FILE = BASE_DIR / ("DFL_04_03_positions_raw_observed_DFL-COM-000001_DFL-MAT-J03WMX.xml")
METADATA_FILE = BASE_DIR / ("DFL_02_01_matchinformation_DFL-COM-000001_DFL-MAT-J03WMX.xml")
OUTPUT_FILE = Path("output") / "players.png"

FPS = 25


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seconds",
        type=float,
        default=60.0,
        help="Seconds after the first-half kick-off frame to render (default: 60).",
    )
    parser.add_argument(
        "--trail-seconds",
        type=float,
        default=RenderingConfig().trail_duration_seconds,
        help="Length of the player movement trails in seconds (default: from RenderingConfig).",
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

    target_frame = origin_frame + round(args.seconds * FPS)
    trail_frames = round(args.trail_seconds * FPS)
    first_frame = max(origin_frame, target_frame - trail_frames)

    samples = collect_frame_samples(first_frame, target_frame, coordinate_system)

    if target_frame not in samples or not samples[target_frame][0]:
        raise SystemExit(f"No player positions found at frame {target_frame}.")

    frames = [
        Frame(
            frame_index=frame_number,
            time=MatchTime(PeriodType.FIRST_HALF, (frame_number - origin_frame) / FPS),
            player_positions=tuple(positions),
            ball_position=ball,
        )
        for frame_number, (positions, ball) in sorted(samples.items())
    ]
    frame = frames[-1]

    pitch = PitchDimensions.from_coordinate_system(coordinate_system)
    config = RenderingConfig()
    team_styles = resolve_team_styles(teams)

    fig, ax = plt.subplots(figsize=(10.5, 6.8))
    draw_pitch(ax, pitch)

    trails = TrailLayer(
        ax,
        players,
        team_styles,
        duration_seconds=args.trail_seconds,
        fps=FPS,
        line_width=config.player_marker_size * 0.3,
    )

    for trail_frame in frames:
        trails.update(trail_frame)

    layer = draw_players(
        ax,
        frame,
        players,
        team_styles,
        marker_size=config.player_marker_size * 1.6,
    )
    ball_layer = draw_ball(
        ax,
        frame,
        marker_size=config.ball_marker_size * 1.6,
        pitch=pitch,
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_FILE, dpi=150, bbox_inches="tight")

    print(f"Rendered {len(layer.visible_player_ids)} players at frame {target_frame}.")
    print(f"Ball {'shown' if ball_layer.is_visible else 'not shown'} at frame {target_frame}.")
    print(f"Drew trails from {len(frames)} frames ({args.trail_seconds:g} s).")
    print(f"Saved player preview to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

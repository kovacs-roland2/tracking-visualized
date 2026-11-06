"""Render one tracking frame (players and ball) of the sample match to output/players.png.

Scans the whole tracking file twice (once to find the first-half origin frame,
once to collect positions), so it takes about a minute on the full match.
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
    target_frame: int, coordinate_system: CoordinateSystem
) -> tuple[list[PlayerPosition], BallPosition | None]:
    """Collect player and ball positions recorded at ``target_frame`` in the first half."""

    positions: list[PlayerPosition] = []
    ball: BallPosition | None = None

    for sample in iter_tracking_samples(TRACKING_FILE, METADATA_FILE):
        if sample.period != TrackingPeriod.FIRST_HALF or sample.frame_number != target_frame:
            continue

        x, y = normalize_tracking_coordinates(sample.x, sample.y, coordinate_system)

        if isinstance(sample, PlayerTrackingSample):
            positions.append(PlayerPosition(sample.person_id, x, y))
        elif isinstance(sample, BallTrackingSample):
            ball = BallPosition(x=x, y=y, z=sample.z, is_in_play=sample.is_alive)

    return positions, ball


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
    positions, ball = collect_frame_samples(target_frame, coordinate_system)

    if not positions:
        raise SystemExit(f"No player positions found at frame {target_frame}.")

    frame = Frame(
        frame_index=target_frame,
        time=MatchTime(PeriodType.FIRST_HALF, args.seconds),
        player_positions=tuple(positions),
        ball_position=ball,
    )

    fig, ax = plt.subplots(figsize=(10.5, 6.8))
    draw_pitch(ax, PitchDimensions.from_coordinate_system(coordinate_system))
    config = RenderingConfig()
    layer = draw_players(
        ax,
        frame,
        players,
        resolve_team_styles(teams),
        marker_size=config.player_marker_size * 1.6,
    )
    ball_layer = draw_ball(
        ax,
        frame,
        marker_size=config.ball_marker_size * 1.6,
        pitch=PitchDimensions.from_coordinate_system(coordinate_system),
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_FILE, dpi=150, bbox_inches="tight")

    print(f"Rendered {len(layer.visible_player_ids)} players at frame {target_frame}.")
    print(f"Ball {'shown' if ball_layer.is_visible else 'not shown'} at frame {target_frame}.")
    print(f"Saved player preview to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

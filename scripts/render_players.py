"""Render one tracking frame of the sample match to output/players.png.

Scans the whole tracking file, so it takes a while on the full match.
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from tracking_visualized.config import RenderingConfig  # noqa: E402
from tracking_visualized.domain import (  # noqa: E402
    Frame,
    MatchTime,
    PeriodType,
    Player,
    PlayerPosition,
    Team,
    TeamSide,
)
from tracking_visualized.providers.dfl import (  # noqa: E402
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

    target_frame: int | None = None
    positions: list[PlayerPosition] = []

    for sample in iter_tracking_samples(TRACKING_FILE, METADATA_FILE):
        if not isinstance(sample, PlayerTrackingSample):
            continue

        if sample.period != TrackingPeriod.FIRST_HALF:
            continue

        if target_frame is None:
            target_frame = sample.frame_number + round(args.seconds * FPS)

        if sample.frame_number == target_frame:
            x, y = normalize_tracking_coordinates(sample.x, sample.y, coordinate_system)
            positions.append(PlayerPosition(sample.person_id, x, y))

    if target_frame is None:
        raise SystemExit("No first-half player samples found.")

    frame = Frame(
        frame_index=target_frame,
        time=MatchTime(PeriodType.FIRST_HALF, args.seconds),
        player_positions=tuple(positions),
        ball_position=None,
    )

    fig, ax = plt.subplots(figsize=(10.5, 6.8))
    draw_pitch(ax, PitchDimensions.from_coordinate_system(coordinate_system))
    layer = draw_players(
        ax,
        frame,
        players,
        resolve_team_styles(teams),
        marker_size=RenderingConfig().player_marker_size * 1.6,
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_FILE, dpi=150, bbox_inches="tight")

    print(f"Rendered {len(layer.visible_player_ids)} players at frame {target_frame}.")
    print(f"Saved player preview to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

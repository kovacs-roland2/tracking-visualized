from pathlib import Path

from tracking_visualized.providers.dfl import (
    BallTrackingSample,
    build_match_timeline,
    iter_tracking_samples,
    load_shot_events,
    normalize_shot_time,
)

MATCH_ID = "J03WMX"

BASE_DIR = Path("data/raw/dfl") / MATCH_ID

TRACKING_FILE = BASE_DIR / ("DFL_04_03_positions_raw_observed_DFL-COM-000001_DFL-MAT-J03WMX.xml")

METADATA_FILE = BASE_DIR / ("DFL_02_01_matchinformation_DFL-COM-000001_DFL-MAT-J03WMX.xml")

EVENTS_FILE = BASE_DIR / ("DFL_03_02_events_raw_DFL-COM-000001_DFL-MAT-J03WMX.xml")


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Required dataset file does not exist: {path}")


def load_ball_samples() -> list[BallTrackingSample]:
    """Load only ball samples from the DFL tracking stream."""

    ball_samples: list[BallTrackingSample] = []

    for sample in iter_tracking_samples(
        TRACKING_FILE,
        METADATA_FILE,
    ):
        if isinstance(sample, BallTrackingSample):
            ball_samples.append(sample)

    if not ball_samples:
        raise RuntimeError("No ball tracking samples were found.")

    return ball_samples


def print_period_summary(timeline) -> None:
    print("\nTIMELINE")
    print("=" * 72)

    for period in timeline.periods:
        observed_frames = len(period.frames)

        logical_frame_span = period.source_end_frame - period.source_start_frame + 1

        missing_frames = logical_frame_span - observed_frames

        first_frame = period.frames[0]
        last_frame = period.frames[-1]

        print(f"\n{period.period.value.upper()}")
        print(f"  source first frame : {period.source_start_frame}")
        print(f"  source last frame  : {period.source_end_frame}")
        print(f"  observed frames    : {observed_frames}")
        print(f"  logical frame span : {logical_frame_span}")
        print(f"  missing frames     : {missing_frames}")
        print(f"  estimated fps      : {period.frame_rate:.3f}")
        print(f"  global start index : {period.global_start_index}")
        print(f"  global first index : {first_frame.frame_index}")
        print(f"  global last index  : {last_frame.frame_index}")
        print(f"  start timestamp    : {period.start_timestamp.isoformat()}")
        print(f"  end timestamp      : {period.end_timestamp.isoformat()}")
        print(f"  normalized duration: {last_frame.time.seconds:.3f}s")


def print_goal_mappings(timeline) -> None:
    shots = load_shot_events(
        EVENTS_FILE,
        METADATA_FILE,
    )

    goals = [shot for shot in shots if shot.is_goal]

    print("\nGOAL → TRACKING MAPPINGS")
    print("=" * 72)

    if not goals:
        print("No goals found.")
        return

    for goal in goals:
        normalized = normalize_shot_time(
            goal,
            timeline,
        )

        player = goal.player_name or goal.player_id
        shirt_number = f"#{goal.shirt_number}" if goal.shirt_number is not None else "#?"

        calculated_frame = (
            str(goal.calculated_frame) if goal.calculated_frame is not None else "None"
        )

        print(f"\n{shirt_number} {player}")
        print(f"  period             : {normalized.time.period.value}")
        print(f"  event period time  : {goal.period_seconds:.3f}s")
        print(f"  calculated frame   : {calculated_frame}")
        print(
            f"  calculated time    : {goal.calculated_timestamp.isoformat()}"
            if goal.calculated_timestamp is not None
            else "  calculated time    : None"
        )
        print(f"  normalized time    : {normalized.time.seconds:.3f}s")
        print(f"  normalized frame   : {normalized.frame_index}")

        if goal.calculated_frame is not None:
            period = normalized.time.period

            exact_frame = timeline.frame_for_source_number(
                period,
                goal.calculated_frame,
            )

            print(f"  exact frame found   : {exact_frame is not None}")


def main() -> None:
    for path in (
        TRACKING_FILE,
        METADATA_FILE,
        EVENTS_FILE,
    ):
        require_file(path)

    print(f"Inspecting DFL match {MATCH_ID}")
    print(f"Tracking: {TRACKING_FILE}")
    print(f"Metadata: {METADATA_FILE}")
    print(f"Events:   {EVENTS_FILE}")

    print("\nLoading ball tracking samples...")

    ball_samples = load_ball_samples()

    print(f"Loaded {len(ball_samples):,} ball samples.")

    timeline = build_match_timeline(ball_samples)

    print_period_summary(timeline)
    print_goal_mappings(timeline)

    print("\nTimeline inspection complete.")


if __name__ == "__main__":
    main()

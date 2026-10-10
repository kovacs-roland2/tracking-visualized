from pathlib import Path

from tracking_visualized.providers.dfl import (
    load_shot_events,
)

BASE_DIR = Path("data/raw/dfl/J03WMX")

EVENTS_FILE = BASE_DIR / ("DFL_03_02_events_raw_DFL-COM-000001_DFL-MAT-J03WMX.xml")

METADATA_FILE = BASE_DIR / ("DFL_02_01_matchinformation_DFL-COM-000001_DFL-MAT-J03WMX.xml")


def main() -> None:
    shots = load_shot_events(
        EVENTS_FILE,
        METADATA_FILE,
    )

    for shot in shots:
        marker = "GOAL" if shot.is_goal else shot.outcome.value

        print(
            f"{shot.period.value} "
            f"{shot.period_seconds:7.2f}s | "
            f"#{shot.shirt_number} "
            f"{shot.player_name} | "
            f"{marker} | "
            f"xG={shot.xg}"
        )


if __name__ == "__main__":
    main()

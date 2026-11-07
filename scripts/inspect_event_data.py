from sample_data import EVENTS_FILE, METADATA_FILE

from tracking_visualized.providers.dfl import (
    load_shot_events,
)


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

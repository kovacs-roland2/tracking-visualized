from pathlib import Path

import matplotlib.pyplot as plt

from tracking_visualized.domain import CoordinateSystem
from tracking_visualized.providers.dfl import (
    normalize_event_coordinates,
    normalize_tracking_coordinates,
)
from tracking_visualized.rendering import PitchDimensions, draw_pitch

OUTPUT_PATH = Path("output/debug_coordinate_normalization.png")


def main() -> None:
    pitch = CoordinateSystem(
        pitch_length=105.0,
        pitch_width=68.0,
    )

    tracking_points = [
        (-52.5, -34.0),
        (0.0, 0.0),
        (52.5, 34.0),
    ]

    event_points = [
        (0.0, 0.0),
        (52.5, 34.0),
        (105.0, 68.0),
    ]

    normalized_tracking = [
        normalize_tracking_coordinates(
            x,
            y,
            pitch,
        )
        for x, y in tracking_points
    ]

    normalized_events = [
        normalize_event_coordinates(
            x,
            y,
            pitch,
        )
        for x, y in event_points
    ]

    fig, ax = plt.subplots(figsize=(12, 8))

    draw_pitch(ax, PitchDimensions.from_coordinate_system(pitch))

    for index, (x, y) in enumerate(normalized_tracking):
        ax.scatter(
            x,
            y,
            marker="o",
        )

        ax.annotate(
            f"tracking {index}",
            (x, y),
        )

    for index, (x, y) in enumerate(normalized_events):
        ax.scatter(
            x,
            y,
            marker="x",
        )

        ax.annotate(
            f"event {index}",
            (x, y),
        )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fig.savefig(
        OUTPUT_PATH,
        dpi=150,
        bbox_inches="tight",
    )

    plt.close(fig)

    print(f"Saved coordinate debug plot to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

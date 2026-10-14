from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle

from tracking_visualized.domain import CoordinateSystem
from tracking_visualized.providers.dfl import (
    normalize_event_coordinates,
    normalize_tracking_coordinates,
)

OUTPUT_PATH = Path("output/debug_coordinate_normalization.png")


def draw_pitch(
    ax: plt.Axes,
    pitch: CoordinateSystem,
) -> None:
    length = pitch.pitch_length
    width = pitch.pitch_width

    ax.add_patch(
        Rectangle(
            (0, 0),
            length,
            width,
            fill=False,
        )
    )

    ax.plot(
        [length / 2, length / 2],
        [0, width],
    )

    ax.add_patch(
        Circle(
            (length / 2, width / 2),
            radius=9.15,
            fill=False,
        )
    )

    ax.scatter(
        length / 2,
        width / 2,
        marker=".",
    )

    ax.set_xlim(-5, length + 5)
    ax.set_ylim(-5, width + 5)

    ax.set_aspect("equal")

    ax.set_xlabel("x (meters)")
    ax.set_ylabel("y (meters)")


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
        (0.0, 68.0),
        (52.5, 34.0),
        (105.0, 0.0),
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

    draw_pitch(
        ax,
        pitch,
    )

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

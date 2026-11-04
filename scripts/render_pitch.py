from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from tracking_visualized.rendering import draw_pitch  # noqa: E402

OUTPUT_FILE = Path("output") / "pitch.png"


def main() -> None:
    fig, ax = plt.subplots(figsize=(10.5, 6.8))
    draw_pitch(ax)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_FILE, dpi=150, bbox_inches="tight")
    print(f"Saved pitch preview to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

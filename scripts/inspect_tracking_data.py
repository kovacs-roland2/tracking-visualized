from itertools import islice
from pathlib import Path

from tracking_visualized.providers.dfl import (
    iter_tracking_samples,
)

MATCH_ID = "J03WMX"

BASE_DIR = Path("data/raw/dfl") / MATCH_ID

TRACKING_FILE = BASE_DIR / ("DFL_04_03_positions_raw_observed_DFL-COM-000001_DFL-MAT-J03WMX.xml")

METADATA_FILE = BASE_DIR / ("DFL_02_01_matchinformation_DFL-COM-000001_DFL-MAT-J03WMX.xml")


def main() -> None:
    samples = iter_tracking_samples(
        TRACKING_FILE,
        METADATA_FILE,
    )

    for sample in islice(samples, 20):
        print(sample)


if __name__ == "__main__":
    main()

"""Paths of the IDSSE sample match shared by the helper scripts."""

from pathlib import Path

MATCH_ID = "J03WMX"

BASE_DIR = Path("data/raw/dfl") / MATCH_ID

METADATA_FILE = BASE_DIR / "DFL_02_01_matchinformation_DFL-COM-000001_DFL-MAT-J03WMX.xml"
EVENTS_FILE = BASE_DIR / "DFL_03_02_events_raw_DFL-COM-000001_DFL-MAT-J03WMX.xml"
TRACKING_FILE = BASE_DIR / "DFL_04_03_positions_raw_observed_DFL-COM-000001_DFL-MAT-J03WMX.xml"


def require_file(path: Path) -> None:
    """Raise if a dataset file is missing or empty."""

    if not path.is_file():
        raise FileNotFoundError(f"Missing required dataset file: {path}")

    if path.stat().st_size == 0:
        raise ValueError(f"Dataset file is empty: {path}")

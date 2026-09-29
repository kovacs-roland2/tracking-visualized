import xml.etree.ElementTree as ET
from pathlib import Path

MATCH_ID = "J03WMX"

DATA_DIR = Path("data/raw/dfl") / MATCH_ID

MATCH_INFO_FILE = DATA_DIR / "DFL_02_01_matchinformation_DFL-COM-000001_DFL-MAT-J03WMX.xml"

EVENTS_FILE = DATA_DIR / "DFL_03_02_events_raw_DFL-COM-000001_DFL-MAT-J03WMX.xml"

POSITIONS_FILE = DATA_DIR / "DFL_04_03_positions_raw_observed_DFL-COM-000001_DFL-MAT-J03WMX.xml"


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required dataset file: {path}")

    if path.stat().st_size == 0:
        raise ValueError(f"Dataset file is empty: {path}")


def verify_match_information() -> None:
    tree = ET.parse(MATCH_INFO_FILE)
    root = tree.getroot()

    general = root.find(".//General")

    if general is None:
        raise ValueError("Could not find General match metadata")

    assert general.attrib["MatchId"] == "DFL-MAT-J03WMX"

    print(f"Match: {general.attrib['HomeTeamName']} vs {general.attrib['GuestTeamName']}")
    print(f"Result: {general.attrib['Result']}")
    print(f"Competition: {general.attrib['CompetitionName']}")


def verify_events() -> None:
    tree = ET.parse(EVENTS_FILE)
    root = tree.getroot()

    events = root.findall(".//Event")
    shots = root.findall(".//ShotAtGoal")
    goals = root.findall(".//SuccessfulShot")

    if not events:
        raise ValueError("No events found")

    if not shots:
        raise ValueError("No shots found")

    if not goals:
        raise ValueError("No successful shots/goals found")

    print(f"Events: {len(events)}")
    print(f"Shots: {len(shots)}")
    print(f"Successful shots: {len(goals)}")


def main() -> None:
    for path in (MATCH_INFO_FILE, EVENTS_FILE, POSITIONS_FILE):
        require_file(path)
        print(f"OK: {path} ({path.stat().st_size:,} bytes)")

    verify_match_information()
    verify_events()

    print("Sample DFL dataset verification passed.")


if __name__ == "__main__":
    main()

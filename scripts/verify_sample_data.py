import xml.etree.ElementTree as ET

from sample_data import EVENTS_FILE, METADATA_FILE, TRACKING_FILE, require_file


def verify_match_information() -> None:
    tree = ET.parse(METADATA_FILE)
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
    for path in (METADATA_FILE, EVENTS_FILE, TRACKING_FILE):
        require_file(path)
        print(f"OK: {path} ({path.stat().st_size:,} bytes)")

    verify_match_information()
    verify_events()

    print("Sample DFL dataset verification passed.")


if __name__ == "__main__":
    main()

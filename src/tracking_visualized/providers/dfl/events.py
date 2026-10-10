import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from tracking_visualized.providers.dfl.match_metadata import TeamSide
from tracking_visualized.providers.dfl.shared import (
    PlayerReference,
    load_player_index,
    load_team_side_index,
)
from tracking_visualized.providers.dfl.utils import (
    optional_float,
    optional_int,
    parse_timestamp,
    require_attribute,
)


class ShotOutcome(StrEnum):
    WIDE = "wide"
    SAVED = "saved"
    BLOCKED = "blocked"
    WOODWORK = "woodwork"
    GOAL = "goal"
    OTHER = "other"


SHOT_OUTCOMES = {
    "ShotWide": ShotOutcome.WIDE,
    "SavedShot": ShotOutcome.SAVED,
    "BlockedShot": ShotOutcome.BLOCKED,
    "ShotWoodWork": ShotOutcome.WOODWORK,
    "SuccessfulShot": ShotOutcome.GOAL,
    "OtherShot": ShotOutcome.OTHER,
}


class MatchPeriod(StrEnum):
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"


@dataclass(frozen=True, slots=True)
class ShotEvent:
    event_id: str
    match_id: str

    timestamp: datetime
    period: MatchPeriod
    period_seconds: float

    team_id: str
    team_side: TeamSide

    player_id: str
    player_name: str | None
    shirt_number: int | None

    x: float | None
    y: float | None
    xg: float | None

    outcome: ShotOutcome

    calculated_frame: int | None
    calculated_timestamp: datetime | None

    @property
    def is_goal(self) -> bool:
        return self.outcome == ShotOutcome.GOAL


class DflEventError(ValueError):
    """Raised when DFL event data is malformed or inconsistent."""


@dataclass(frozen=True, slots=True)
class PeriodWindow:
    period: MatchPeriod
    start: datetime
    end: datetime


def _parse_period_name(value: str) -> MatchPeriod:
    """
    Parse a DFL period name into a MatchPeriod enum.

    Args:
        value: The period name string from the DFL event XML.

    Returns:
        The corresponding MatchPeriod enum value.S
    """
    if value == "firstHalf":
        return MatchPeriod.FIRST_HALF

    if value == "secondHalf":
        return MatchPeriod.SECOND_HALF

    raise DflEventError(f"Unsupported game section '{value}'.")


def _parse_period_windows(
    root: ET.Element,
) -> list[PeriodWindow]:
    """
    Parse the start and end timestamps of match periods from the DFL event XML.

    ARgs:
        root: The root element of the DFL event XML tree.

    Returns:
        A list of PeriodWindow objects representing the start and end times of each match period.
    """
    starts: dict[MatchPeriod, datetime] = {}
    ends: dict[MatchPeriod, datetime] = {}

    for event in root.findall("Event"):
        event_time = parse_timestamp(
            require_attribute(event, "EventTime", DflEventError),
            DflEventError,
        )

        for child in event:
            if child.tag in {
                "KickOff",
                "Kickoff",
                "KickoffWhistle",
            }:
                section = child.get("GameSection")

                if section:
                    starts[_parse_period_name(section)] = event_time

            elif child.tag == "FinalWhistle":
                section = child.get("GameSection")

                if section:
                    ends[_parse_period_name(section)] = event_time

    windows = []

    for period in (
        MatchPeriod.FIRST_HALF,
        MatchPeriod.SECOND_HALF,
    ):
        if period not in starts:
            raise DflEventError(f"Missing start of {period.value}.")

        if period not in ends:
            raise DflEventError(f"Missing end of {period.value}.")

        windows.append(
            PeriodWindow(
                period=period,
                start=starts[period],
                end=ends[period],
            )
        )

    return windows


def _find_period(
    timestamp: datetime,
    periods: list[PeriodWindow],
) -> PeriodWindow:
    """
    Find the match period that contains the given timestamp.

    Args:
        timestamp: The timestamp to check.
        periods: A list of PeriodWindow objects representing the match periods.

    Returns:
        The PeriodWindow that contains the timestamp.s
    """
    for period in periods:
        if period.start <= timestamp <= period.end:
            return period

    raise DflEventError(
        f"Event timestamp {timestamp.isoformat()} does not fall inside a match period."
    )


def _parse_shot_outcome(
    shot: ET.Element,
) -> ShotOutcome:
    """
    Parse the outcome of a shot event from the DFL event XML.

    Args:
        shot: The XML element representing the shot event.

    Returns:
        The corresponding ShotOutcome enum value.
    """
    outcomes = [SHOT_OUTCOMES[child.tag] for child in shot if child.tag in SHOT_OUTCOMES]

    if len(outcomes) != 1:
        raise DflEventError(
            f"Expected ShotAtGoal to contain exactly one recognized outcome, found {len(outcomes)}."
        )

    return outcomes[0]


def _parse_shot(
    event: ET.Element,
    shot: ET.Element,
    periods: list[PeriodWindow],
    player_index: dict[str, PlayerReference],
    team_sides: dict[str, TeamSide],
) -> ShotEvent:
    """
    Parse a shot event from the DFL event XML.

    Args:
        event: The XML element representing the shot event.
        shot: The XML element representing the shot details.
        periods: A list of PeriodWindow objects representing the match periods.
        player_index: A dictionary mapping player IDs to PlayerReference objects.
        team_sides: A dictionary mapping team IDs to TeamSide enums.

    Returns:
        The corresponding ShotEvent object.
    """
    event_id = require_attribute(
        event,
        "EventId",
        DflEventError,
    )

    match_id = require_attribute(
        event,
        "MatchId",
        DflEventError,
    )

    timestamp = parse_timestamp(
        require_attribute(
            event,
            "EventTime",
            DflEventError,
        ),
        DflEventError,
    )

    period = _find_period(
        timestamp,
        periods,
    )

    player_id = require_attribute(
        shot,
        "Player",
        DflEventError,
    )

    team_id = require_attribute(
        shot,
        "Team",
        DflEventError,
    )

    player = player_index.get(player_id)

    if player is None:
        raise DflEventError(f"Unknown shot player '{player_id}'.")

    team_side = team_sides.get(team_id)

    if team_side is None:
        raise DflEventError(f"Unknown shot team '{team_id}'.")

    if player.team_id != team_id:
        raise DflEventError(f"Player '{player_id}' does not belong to team '{team_id}'.")

    calculated_timestamp_value = event.get("CalculatedTimestamp")

    return ShotEvent(
        event_id=event_id,
        match_id=match_id,
        timestamp=timestamp,
        period=period.period,
        period_seconds=(timestamp - period.start).total_seconds(),
        team_id=team_id,
        team_side=team_side,
        player_id=player_id,
        player_name=player.name,
        shirt_number=player.shirt_number,
        x=optional_float(event.get("X-Position"), DflEventError),
        y=optional_float(event.get("Y-Position"), DflEventError),
        xg=optional_float(shot.get("xG"), DflEventError),
        outcome=_parse_shot_outcome(shot),
        calculated_frame=optional_int(event.get("CalculatedFrame"), DflEventError),
        calculated_timestamp=(
            parse_timestamp(calculated_timestamp_value, DflEventError)
            if calculated_timestamp_value
            else None
        ),
    )


def load_shot_events(
    events_path: Path,
    metadata_path: Path,
) -> list[ShotEvent]:
    """
    Load shot and goal events from DFL event XML.

    Args:
        events_path: Path to the DFL event XML file.
        metadata_path: Path to the DFL match metadata XML file.

    Returns:
        A list of ShotEvent objects representing the shot and goal events in the match.
    """

    if not events_path.is_file():
        raise FileNotFoundError(f"Event file does not exist: {events_path}")

    if not metadata_path.is_file():
        raise FileNotFoundError(f"Metadata file does not exist: {metadata_path}")

    try:
        tree = ET.parse(events_path)
    except ET.ParseError as exc:
        raise DflEventError(f"Invalid event XML: {events_path}") from exc

    root = tree.getroot()

    periods = _parse_period_windows(root)

    player_index = load_player_index(metadata_path)

    team_sides = load_team_side_index(metadata_path)

    shots: list[ShotEvent] = []

    for event in root.findall("Event"):
        shot = event.find(".//ShotAtGoal")

        if shot is None:
            continue

        shots.append(
            _parse_shot(
                event=event,
                shot=shot,
                periods=periods,
                player_index=player_index,
                team_sides=team_sides,
            )
        )

    return sorted(
        shots,
        key=lambda shot: shot.timestamp,
    )

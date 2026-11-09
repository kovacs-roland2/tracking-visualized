"""Load the part of a DFL match needed to render one event.

A full match has well over 100,000 tracking frames, so the loader only builds the
frames of a window around the selected shot. Tracking XML is streamed twice: once
for the ball, which defines the match timeline, and once for the players and ball
inside the window.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tracking_visualized.domain import (
    BallPosition,
    CoordinateSystem,
    Event,
    EventType,
    Frame,
    Match,
    MatchMetadata,
    Period,
    PeriodType,
    Player,
    PlayerPosition,
    ShotOutcome,
    Team,
    TeamSide,
)
from tracking_visualized.normalization.time import FrameTime, MatchTimeline, PeriodTimeline
from tracking_visualized.processing.frame_windows import frames_in_window
from tracking_visualized.providers.dfl.coordinates import (
    create_coordinate_system,
    normalize_tracking_coordinates,
    validate_event_coordinates,
)
from tracking_visualized.providers.dfl.events import (
    ShotEvent,
    load_shot_events,
    to_domain_period,
)
from tracking_visualized.providers.dfl.match_metadata import MatchMetadata as DflMatchMetadata
from tracking_visualized.providers.dfl.match_metadata import load_match_metadata
from tracking_visualized.providers.dfl.shared import load_player_index
from tracking_visualized.providers.dfl.timeline import (
    build_match_timeline,
    normalize_shot_time,
)
from tracking_visualized.providers.dfl.tracking import (
    BallTrackingSample,
    PlayerTrackingSample,
    TrackingPeriod,
    iter_tracking_samples,
)

DEFAULT_DFL_DIR = Path("data/raw/dfl")
MATCH_ID_PREFIX = "DFL-MAT-"

METADATA_PATTERN = "*matchinformation*.xml"
EVENTS_PATTERN = "*events_raw*.xml"
TRACKING_PATTERN = "*positions_raw_observed*.xml"

DOWNLOAD_HINT = "See 'Downloading the Sample Data' in the README for how to get the files."

MAX_LISTED_EVENT_IDS = 10

_MATCH_ID_PATTERN = re.compile(r"[A-Za-z0-9]+")

type StageCallback = Callable[[str], None]


class DflDatasetError(ValueError):
    """Raised when DFL files are missing or do not contain the requested event."""


class DflEventNotFoundError(DflDatasetError):
    """Raised when a shot event ID does not exist in the match."""


def normalize_match_id(match_id: str) -> str:
    """Return the short match ID used for the data folder, e.g. ``J03WMX``.

    Accepts the short form and the full ``DFL-MAT-J03WMX`` form.

    Raises:
        DflDatasetError: If the ID is empty or contains characters other than letters
            and digits.
    """

    short = match_id.strip().removeprefix(MATCH_ID_PREFIX)

    if not _MATCH_ID_PATTERN.fullmatch(short):
        raise DflDatasetError(
            f"'{match_id}' is not a valid match ID. Use the ID of a folder in the data "
            f"directory, e.g. J03WMX or {MATCH_ID_PREFIX}J03WMX."
        )

    return short


@dataclass(frozen=True, slots=True)
class DflMatchFiles:
    """The three DFL files of one match."""

    match_id: str
    metadata: Path
    events: Path
    tracking: Path

    @classmethod
    def discover(cls, match_id: str, data_dir: Path = DEFAULT_DFL_DIR) -> "DflMatchFiles":
        """Find the match files in ``data_dir / <match ID>``.

        Raises:
            DflDatasetError: If the match folder or one of its files is missing, or a file
                kind is ambiguous.
        """

        short_id = normalize_match_id(match_id)
        match_dir = Path(data_dir) / short_id

        if not match_dir.is_dir():
            raise DflDatasetError(
                f"No data found for match '{short_id}': the folder '{match_dir}' does not "
                f"exist. {DOWNLOAD_HINT}"
            )

        return cls(
            match_id=short_id,
            metadata=_find_file(match_dir, METADATA_PATTERN, "match information"),
            events=_find_file(match_dir, EVENTS_PATTERN, "event"),
            tracking=_find_file(match_dir, TRACKING_PATTERN, "tracking"),
        )


def _find_file(match_dir: Path, pattern: str, description: str) -> Path:
    candidates = sorted(path for path in match_dir.glob(pattern) if path.is_file())

    if not candidates:
        raise DflDatasetError(
            f"No {description} file ('{pattern}') in '{match_dir}'. {DOWNLOAD_HINT}"
        )

    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)

        raise DflDatasetError(f"Found several {description} files in '{match_dir}': {names}.")

    if candidates[0].stat().st_size == 0:
        raise DflDatasetError(f"The {description} file '{candidates[0]}' is empty.")

    return candidates[0]


@dataclass(frozen=True, slots=True)
class ShotSummary:
    """A shot of the match, as listed for event selection."""

    event_id: str
    period: PeriodType
    period_seconds: float
    team_name: str
    shirt_number: int | None
    player_name: str | None
    outcome: ShotOutcome
    xg: float | None

    @property
    def is_goal(self) -> bool:
        return self.outcome == ShotOutcome.GOAL


def list_shots(files: DflMatchFiles) -> list[ShotSummary]:
    """List the shots and goals of a match in chronological order.

    Reads only the metadata and event files, not the large tracking file.
    """

    metadata = load_match_metadata(files.metadata)
    team_names = {
        metadata.home_team.team_id: metadata.home_team.name,
        metadata.away_team.team_id: metadata.away_team.name,
    }

    shots = [
        ShotSummary(
            event_id=shot.event_id,
            period=to_domain_period(shot.period),
            period_seconds=shot.period_seconds,
            team_name=team_names.get(shot.team_id, shot.team_id),
            shirt_number=shot.shirt_number,
            player_name=shot.player_name,
            outcome=ShotOutcome(shot.outcome.value),
            xg=shot.xg,
        )
        for shot in load_shot_events(files.events, files.metadata)
    ]

    period_order = {PeriodType.FIRST_HALF: 0, PeriodType.SECOND_HALF: 1}

    return sorted(shots, key=lambda shot: (period_order[shot.period], shot.period_seconds))


def _find_shot(files: DflMatchFiles, event_id: str) -> ShotEvent:
    shots = load_shot_events(files.events, files.metadata)

    for shot in shots:
        if shot.event_id == event_id:
            return shot

    listed = ", ".join(shot.event_id for shot in shots[:MAX_LISTED_EVENT_IDS])
    more = ", ..." if len(shots) > MAX_LISTED_EVENT_IDS else ""

    raise DflEventNotFoundError(
        f"Match '{files.match_id}' has no shot or goal with event ID '{event_id}'. "
        f"Available IDs: {listed}{more}. List them all with --list-events."
    )


def _known_periods(period: PeriodType, frames: tuple[FrameTime, ...]) -> tuple[Period, ...]:
    """The event's period with its length from the full timeline.

    Only a window of frames is loaded, so without this the sequence selection would
    take the last loaded frame as the end of the period and report clips as cut short.
    """

    duration = frames[-1].time.seconds if frames else 0.0

    return (Period(period, duration_seconds=duration),) if duration > 0 else ()


def _to_tracking_period(period: PeriodType) -> TrackingPeriod:
    return (
        TrackingPeriod.FIRST_HALF if period == PeriodType.FIRST_HALF else TrackingPeriod.SECOND_HALF
    )


def _stage_reporter(on_stage: StageCallback | None) -> StageCallback:
    def stage(message: str) -> None:
        if on_stage is not None:
            on_stage(message)

    return stage


def _read_timeline(files: DflMatchFiles, stage: StageCallback) -> MatchTimeline:
    """First pass over the tracking file: build the match timeline from the ball."""

    stage("Scanning tracking data for the match timeline (1/2)")

    ball_samples = [
        sample
        for sample in iter_tracking_samples(files.tracking, files.metadata, ball_only=True)
        if isinstance(sample, BallTrackingSample)
    ]

    if not ball_samples:
        raise DflDatasetError(f"The tracking file '{files.tracking}' contains no ball tracking.")

    return build_match_timeline(ball_samples)


def _period_timeline(timeline: MatchTimeline, period: PeriodType) -> PeriodTimeline:
    period_timeline = next((item for item in timeline.periods if item.period == period), None)

    if period_timeline is None:
        raise DflDatasetError(f"The tracking data has no frames for the {period.value}.")

    return period_timeline


def _build_match(
    files: DflMatchFiles,
    metadata: DflMatchMetadata,
    period_timeline: PeriodTimeline,
    window: tuple[FrameTime, ...],
    events: tuple[Event, ...],
    stage: StageCallback,
) -> Match:
    """Second pass over the tracking file: build a ``Match`` with the frames of ``window``."""

    period = period_timeline.period
    coordinate_system = create_coordinate_system(metadata.pitch_length, metadata.pitch_width)

    stage(f"Reading {len(window)} tracking frames (2/2)")

    frames = _collect_frames(files, window, period, coordinate_system)

    team_sides = {
        metadata.home_team.team_id: TeamSide.HOME,
        metadata.away_team.team_id: TeamSide.AWAY,
    }
    teams = (
        Team(metadata.home_team.team_id, metadata.home_team.name, TeamSide.HOME),
        Team(metadata.away_team.team_id, metadata.away_team.name, TeamSide.AWAY),
    )
    players = tuple(
        Player(reference.person_id, reference.team_id, reference.name, reference.shirt_number)
        for reference in load_player_index(files.metadata).values()
        if reference.team_id in team_sides
    )

    return Match(
        metadata=MatchMetadata(
            match_id=metadata.match_id,
            competition=metadata.competition.name,
            season=metadata.season.name,
            match_day=metadata.match_day,
        ),
        coordinate_system=coordinate_system,
        periods=_known_periods(period, period_timeline.frames),
        teams=teams,
        players=players,
        frames=tuple(frames),
        events=events,
    )


def load_event_match(
    files: DflMatchFiles,
    event_id: str,
    *,
    pre_event_seconds: float,
    post_event_seconds: float,
    on_stage: StageCallback | None = None,
) -> Match:
    """Load a ``Match`` holding the selected shot and the frames around it.

    The match contains the shot as its only event and only the tracking frames from
    ``pre_event_seconds`` before to ``post_event_seconds`` after it, with frame
    indices and times from the normalized match timeline. That is enough for
    ``select_event_sequence`` and for rendering.

    Args:
        files: The match's DFL files.
        event_id: ID of a shot or goal event.
        pre_event_seconds: Seconds of tracking to load before the shot.
        post_event_seconds: Seconds of tracking to load after the shot.
        on_stage: Called with a short message when a loading stage starts.

    Raises:
        DflEventNotFoundError: If the event ID is not a shot of this match.
        DflDatasetError: If no tracking frames exist around the shot.
    """

    stage = _stage_reporter(on_stage)
    stage("Reading match information and events")

    metadata = load_match_metadata(files.metadata)
    shot = _find_shot(files, event_id)

    timeline = _read_timeline(files, stage)
    normalized = normalize_shot_time(shot, timeline)
    period_timeline = _period_timeline(timeline, normalized.time.period)

    window = frames_in_window(
        period_timeline.frames,
        normalized.time.seconds - pre_event_seconds,
        normalized.time.seconds + post_event_seconds,
    )

    if not window:
        raise DflDatasetError(
            f"No tracking frames around event '{event_id}' "
            f"({normalized.time.period.value}, {normalized.time.seconds:.1f} s)."
        )

    x, y = validate_event_coordinates(shot.x, shot.y)
    event = Event(
        event_id=shot.event_id,
        event_type=EventType.SHOT,
        time=normalized.time,
        team_id=shot.team_id,
        player_id=shot.player_id,
        x=x,
        y=y,
        frame_index=normalized.frame_index,
        shot_outcome=ShotOutcome(shot.outcome.value),
        xg=shot.xg,
    )

    return _build_match(files, metadata, period_timeline, window, (event,), stage)


def load_time_window_match(
    files: DflMatchFiles,
    *,
    period: PeriodType,
    start_seconds: float,
    end_seconds: float,
    on_stage: StageCallback | None = None,
) -> Match:
    """Load a ``Match`` with the tracking frames of a period-relative time range.

    Like ``load_event_match`` but without an event: the match has no events and the
    frames from ``start_seconds`` to ``end_seconds`` of ``period``.

    Raises:
        DflDatasetError: If the range is empty or holds no tracking frames.
    """

    if end_seconds < start_seconds:
        raise DflDatasetError(
            f"The end of the time range ({end_seconds:g} s) is before its start "
            f"({start_seconds:g} s)."
        )

    stage = _stage_reporter(on_stage)
    stage("Reading match information")

    metadata = load_match_metadata(files.metadata)
    period_timeline = _period_timeline(_read_timeline(files, stage), period)
    window = frames_in_window(period_timeline.frames, start_seconds, end_seconds)

    if not window:
        raise DflDatasetError(
            f"No tracking frames between {start_seconds:.1f} s and {end_seconds:.1f} s "
            f"of the {period.value}."
        )

    return _build_match(files, metadata, period_timeline, window, (), stage)


def _collect_frames(
    files: DflMatchFiles,
    window: tuple[FrameTime, ...],
    period: PeriodType,
    coordinate_system: CoordinateSystem,
) -> list[Frame]:
    """Stream the tracking file and build a ``Frame`` for each timeline frame in ``window``."""

    tracking_period = _to_tracking_period(period)
    wanted = {frame.source_frame_number: frame for frame in window}

    players: dict[int, dict[str, PlayerPosition]] = {number: {} for number in wanted}
    balls: dict[int, BallPosition] = {}

    for sample in iter_tracking_samples(files.tracking, files.metadata):
        if sample.period != tracking_period or sample.frame_number not in wanted:
            continue

        x, y = normalize_tracking_coordinates(sample.x, sample.y, coordinate_system)

        if isinstance(sample, PlayerTrackingSample):
            players[sample.frame_number][sample.person_id] = PlayerPosition(sample.person_id, x, y)
        elif isinstance(sample, BallTrackingSample):
            balls[sample.frame_number] = BallPosition(
                x=x, y=y, z=sample.z, is_in_play=sample.is_alive
            )

    return [
        Frame(
            frame_index=frame.frame_index,
            time=frame.time,
            player_positions=tuple(players[frame.source_frame_number].values()),
            ball_position=balls.get(frame.source_frame_number),
        )
        for frame in window
    ]


__all__ = [
    "DEFAULT_DFL_DIR",
    "DflDatasetError",
    "DflEventNotFoundError",
    "DflMatchFiles",
    "ShotSummary",
    "list_shots",
    "load_event_match",
    "load_time_window_match",
    "normalize_match_id",
]

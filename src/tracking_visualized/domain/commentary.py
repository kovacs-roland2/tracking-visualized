from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from tracking_visualized.domain.models import MatchTime, PeriodType

COMMENTARY_SCRIPT_VERSION = 1

MAX_PAUSE_SECONDS = 10.0
MIN_ZONE_POINTS = 3


class HighlightRole(StrEnum):
    """What a highlighted player does in the play; the renderer styles by role."""

    SHOOTER = "shooter"
    ASSIST = "assist"
    PASSER = "passer"
    RECEIVER = "receiver"
    DEFENDER = "defender"
    GOALKEEPER = "goalkeeper"
    ATTACKER = "attacker"
    OTHER = "other"


class AnnotationType(StrEnum):
    ARROW = "arrow"
    PASSING_LANE = "passing_lane"
    DISTANCE_LINE = "distance_line"
    ZONE = "zone"


def _require_text(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty.")


def _require_non_negative(value: float, name: str) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite number that is not negative, got {value}.")


@dataclass(frozen=True, slots=True)
class PlayerTarget:
    """An annotation end point that follows a player."""

    player_id: str

    def __post_init__(self) -> None:
        _require_text(self.player_id, "Player ID")


@dataclass(frozen=True, slots=True)
class PointTarget:
    """A fixed point on the pitch, in canonical coordinates (meters, bottom-left origin)."""

    x: float
    y: float

    def __post_init__(self) -> None:
        for name, value in (("x", self.x), ("y", self.y)):
            if not isfinite(value):
                raise ValueError(f"Point {name} coordinate must be finite, got {value}.")


type AnnotationTarget = PlayerTarget | PointTarget


@dataclass(frozen=True, slots=True)
class Highlight:
    """A player to spotlight during a beat."""

    player_id: str
    role: HighlightRole

    def __post_init__(self) -> None:
        _require_text(self.player_id, "Player ID")


def _require_distinct_ends(start: AnnotationTarget, end: AnnotationTarget, kind: str) -> None:
    if start == end:
        raise ValueError(f"A {kind} needs two different end points.")


@dataclass(frozen=True, slots=True)
class ArrowAnnotation:
    """An arrow between two players or points."""

    start: AnnotationTarget
    end: AnnotationTarget
    label: str | None = None

    type = AnnotationType.ARROW

    def __post_init__(self) -> None:
        _require_distinct_ends(self.start, self.end, "arrow")


@dataclass(frozen=True, slots=True)
class PassingLaneAnnotation:
    """The passing lane between two players."""

    from_player_id: str
    to_player_id: str
    label: str | None = None

    type = AnnotationType.PASSING_LANE

    def __post_init__(self) -> None:
        _require_text(self.from_player_id, "Player ID")
        _require_text(self.to_player_id, "Player ID")

        if self.from_player_id == self.to_player_id:
            raise ValueError("A passing lane needs two different players.")


@dataclass(frozen=True, slots=True)
class DistanceLineAnnotation:
    """A line between two players or points; the renderer shows its length in meters."""

    start: AnnotationTarget
    end: AnnotationTarget
    label: str | None = None

    type = AnnotationType.DISTANCE_LINE

    def __post_init__(self) -> None:
        _require_distinct_ends(self.start, self.end, "distance line")


@dataclass(frozen=True, slots=True)
class ZoneAnnotation:
    """A shaded pitch zone, given as the corners of a polygon."""

    points: tuple[PointTarget, ...]
    label: str | None = None

    type = AnnotationType.ZONE

    def __post_init__(self) -> None:
        if len(self.points) < MIN_ZONE_POINTS:
            raise ValueError(f"A zone needs at least {MIN_ZONE_POINTS} points.")

        if len(set(self.points)) != len(self.points):
            raise ValueError("A zone cannot repeat a point.")


type Annotation = ArrowAnnotation | PassingLaneAnnotation | DistanceLineAnnotation | ZoneAnnotation


@dataclass(frozen=True, slots=True)
class Beat:
    """One step of the commentary.

    Attributes:
        start_seconds: When the beat starts, in seconds of match time within the script's
            period (the same clock as ``MatchTime.seconds``).
        text: The subtitle / narration line.
        pause_seconds: Length of a freeze-frame hold at ``start_seconds``. It is
            output time: it adds to the length of the video, not to match time.
        duration_seconds: How long the beat stays active in match time. Without it, the
            beat lasts until the next beat starts, or until the clip ends.
        highlights: Players to spotlight.
        annotations: Arrows, lanes, distance lines and zones to draw.
    """

    start_seconds: float
    text: str
    pause_seconds: float = 0.0
    duration_seconds: float | None = None
    highlights: tuple[Highlight, ...] = ()
    annotations: tuple[Annotation, ...] = ()

    def __post_init__(self) -> None:
        _require_non_negative(self.start_seconds, "Beat start")
        _require_text(self.text, "Beat text")
        _require_non_negative(self.pause_seconds, "Beat pause")

        if self.pause_seconds > MAX_PAUSE_SECONDS:
            raise ValueError(
                f"A pause can be at most {MAX_PAUSE_SECONDS:g} seconds, got {self.pause_seconds:g}."
            )

        if self.duration_seconds is not None:
            _require_non_negative(self.duration_seconds, "Beat duration")

            if self.duration_seconds == 0:
                raise ValueError("Beat duration must be greater than zero.")

        player_ids = [highlight.player_id for highlight in self.highlights]
        duplicates = sorted({player for player in player_ids if player_ids.count(player) > 1})

        if duplicates:
            raise ValueError(
                f"A beat cannot highlight the same player twice: {', '.join(duplicates)}."
            )

    @property
    def end_seconds(self) -> float | None:
        """End of the beat in match time, or ``None`` if it lasts until the next beat."""

        if self.duration_seconds is None:
            return None

        return self.start_seconds + self.duration_seconds

    @property
    def has_pause(self) -> bool:
        return self.pause_seconds > 0


@dataclass(frozen=True, slots=True)
class CommentaryScript:
    """The commentary for one event sequence.

    Attributes:
        match_id: Full ID of the match, e.g. ``DFL-MAT-J03WMX``.
        event_id: ID of the event the clip is built around.
        period: Match period of the clip; all beat times are in this period.
        beats: The beats in order of time; at least one.
        language: Language of the beat texts, e.g. ``en``.
        generator: Optional note on what produced the script, e.g. the model name.
        version: Format version of the script, see ``COMMENTARY_SCRIPT_VERSION``.
    """

    match_id: str
    event_id: str
    period: PeriodType
    beats: tuple[Beat, ...]
    language: str = "en"
    generator: str | None = None
    version: int = COMMENTARY_SCRIPT_VERSION

    def __post_init__(self) -> None:
        _require_text(self.match_id, "Match ID")
        _require_text(self.event_id, "Event ID")
        _require_text(self.language, "Language")

        if not self.beats:
            raise ValueError("A commentary script needs at least one beat.")

        if self.version != COMMENTARY_SCRIPT_VERSION:
            raise ValueError(
                f"Unsupported script version {self.version}; "
                f"this release supports version {COMMENTARY_SCRIPT_VERSION}."
            )

    def start_time(self, beat: Beat) -> MatchTime:
        """Start of ``beat`` as a ``MatchTime`` in the script's period."""

        return MatchTime(period=self.period, seconds=beat.start_seconds)

    @property
    def total_pause_seconds(self) -> float:
        """Combined length of all freeze-frame holds."""

        return sum(beat.pause_seconds for beat in self.beats)


__all__ = [
    "COMMENTARY_SCRIPT_VERSION",
    "MAX_PAUSE_SECONDS",
    "MIN_ZONE_POINTS",
    "Annotation",
    "AnnotationTarget",
    "AnnotationType",
    "ArrowAnnotation",
    "Beat",
    "CommentaryScript",
    "DistanceLineAnnotation",
    "Highlight",
    "HighlightRole",
    "PassingLaneAnnotation",
    "PlayerTarget",
    "PointTarget",
    "ZoneAnnotation",
]

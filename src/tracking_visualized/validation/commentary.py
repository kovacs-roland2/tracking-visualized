from collections.abc import Iterable

from tracking_visualized.commentary.io import short_match_id
from tracking_visualized.domain import (
    AnnotationTarget,
    ArrowAnnotation,
    Beat,
    CommentaryScript,
    DistanceLineAnnotation,
    Match,
    PassingLaneAnnotation,
    PlayerTarget,
    PointTarget,
    ZoneAnnotation,
)
from tracking_visualized.processing import EventSequence, SelectedSequence
from tracking_visualized.validation.match import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)

DEFAULT_MAX_ISSUES = 50
# Beat times are written by an LLM or by hand, usually to two decimals, while clip
# edges come from float arithmetic. Times this close count as equal (well under a frame).
TIME_TOLERANCE_SECONDS = 0.01


class CommentaryScriptValidationError(ValueError):
    """Raised when a commentary script does not fit its match and clip."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report

        super().__init__(report.format_text())


class _Issues:
    def __init__(self, max_issues: int) -> None:
        self._max_issues = max_issues
        self.items: list[ValidationIssue] = []
        self.truncated = False

    def add(self, severity: ValidationSeverity, code: str, message: str) -> None:
        if len(self.items) >= self._max_issues:
            self.truncated = True
            return

        self.items.append(ValidationIssue(severity=severity, code=code, message=message))

    def error(self, code: str, message: str) -> None:
        self.add(ValidationSeverity.ERROR, code, message)

    def warning(self, code: str, message: str) -> None:
        self.add(ValidationSeverity.WARNING, code, message)


def _beat_name(index: int, beat: Beat) -> str:
    return f"Beat {index + 1} (at {beat.start_seconds:g} s)"


def _player_ids_of(beat: Beat) -> Iterable[str]:
    for highlight in beat.highlights:
        yield highlight.player_id

    for annotation in beat.annotations:
        match annotation:
            case PassingLaneAnnotation():
                yield annotation.from_player_id
                yield annotation.to_player_id
            case ArrowAnnotation() | DistanceLineAnnotation():
                for target in (annotation.start, annotation.end):
                    if isinstance(target, PlayerTarget):
                        yield target.player_id


def _points_of(beat: Beat) -> Iterable[PointTarget]:
    def point_targets(targets: Iterable[AnnotationTarget]) -> Iterable[PointTarget]:
        return (target for target in targets if isinstance(target, PointTarget))

    for annotation in beat.annotations:
        match annotation:
            case ArrowAnnotation() | DistanceLineAnnotation():
                yield from point_targets((annotation.start, annotation.end))
            case ZoneAnnotation():
                yield from annotation.points


def _check_identity(
    script: CommentaryScript, match: Match, sequence: EventSequence, issues: _Issues
) -> None:
    # J03WMX and DFL-MAT-J03WMX name the same match.
    if short_match_id(script.match_id) != short_match_id(match.metadata.match_id):
        issues.error(
            "commentary_match_mismatch",
            f"The script is for match '{script.match_id}', not '{match.metadata.match_id}'.",
        )

    if script.event_id != sequence.event.event_id:
        issues.error(
            "commentary_event_mismatch",
            f"The script is for event '{script.event_id}', not '{sequence.event.event_id}'.",
        )

    if script.period != sequence.event.time.period:
        issues.error(
            "commentary_period_mismatch",
            f"The script is for the {script.period.value}, but the event is in the "
            f"{sequence.event.time.period.value}.",
        )


def _check_times(script: CommentaryScript, sequence: EventSequence, issues: _Issues) -> None:
    clip_start = sequence.start_time.seconds
    clip_end = sequence.end_time.seconds

    for index, beat in enumerate(script.beats):
        name = _beat_name(index, beat)

        if not (
            clip_start - TIME_TOLERANCE_SECONDS
            <= beat.start_seconds
            <= clip_end + TIME_TOLERANCE_SECONDS
        ):
            issues.error(
                "commentary_beat_outside_clip",
                f"{name} starts outside the clip, which runs from {clip_start:.2f} s "
                f"to {clip_end:.2f} s.",
            )

        end = beat.end_seconds

        if end is not None and end > clip_end + TIME_TOLERANCE_SECONDS:
            issues.error(
                "commentary_beat_outside_clip",
                f"{name} lasts until {end:.2f} s, after the clip ends at {clip_end:.2f} s.",
            )

    for index, (previous, current) in enumerate(zip(script.beats, script.beats[1:], strict=False)):
        if current.start_seconds <= previous.start_seconds:
            issues.error(
                "commentary_beats_unsorted",
                f"Beat {index + 2} (at {current.start_seconds:g} s) does not start after "
                f"beat {index + 1} (at {previous.start_seconds:g} s); beats must be in "
                "strictly increasing order of time.",
            )
            continue

        end = previous.end_seconds

        if end is not None and end > current.start_seconds + TIME_TOLERANCE_SECONDS:
            issues.error(
                "commentary_beats_overlap",
                f"Beat {index + 1} (at {previous.start_seconds:g} s) lasts until {end:.2f} s, "
                f"but beat {index + 2} starts at {current.start_seconds:g} s.",
            )


def _check_players(
    script: CommentaryScript, match: Match, sequence: SelectedSequence, issues: _Issues
) -> None:
    known = {player.player_id for player in match.players}
    in_clip = {
        position.player_id
        for frame in sequence.frames
        for position in frame.player_positions
        if position.is_observed
    }

    for index, beat in enumerate(script.beats):
        for player_id in dict.fromkeys(_player_ids_of(beat)):
            if player_id not in known:
                issues.error(
                    "commentary_unknown_player",
                    f"{_beat_name(index, beat)} refers to unknown player '{player_id}'.",
                )
            elif player_id not in in_clip:
                issues.warning(
                    "commentary_player_not_in_clip",
                    f"{_beat_name(index, beat)} refers to player '{player_id}', who has no "
                    "tracked position in the clip.",
                )


def _check_points(script: CommentaryScript, match: Match, issues: _Issues) -> None:
    length = match.coordinate_system.pitch_length
    width = match.coordinate_system.pitch_width

    for index, beat in enumerate(script.beats):
        for point in _points_of(beat):
            if not (0 <= point.x <= length and 0 <= point.y <= width):
                issues.error(
                    "commentary_point_outside_pitch",
                    f"{_beat_name(index, beat)} uses the point ({point.x:g}, {point.y:g}), "
                    f"which is outside the {length:g} x {width:g} m pitch.",
                )


def validate_commentary_script(
    script: CommentaryScript,
    match: Match,
    sequence: SelectedSequence,
    *,
    max_issues: int = DEFAULT_MAX_ISSUES,
) -> ValidationReport:
    """Check a script against the match and the clip it is meant for.

    Errors are problems that make the script unusable for this clip:

    - the script is for another match, event or period (or the clip is not an event
      sequence at all),
    - a beat starts or ends outside the clip,
    - beats are not in strictly increasing order of time, or a beat's duration runs
      into the next beat,
    - a highlight or annotation refers to a player who is not in the match,
    - an annotation point lies outside the pitch.

    A player who is in the match but has no tracked position in the clip is a warning.
    All problems are reported together.

    Args:
        script: The script to check.
        match: The match the script is for.
        sequence: The clip the script is for.
        max_issues: Report at most this many issues; the report is then marked truncated.
    """

    if max_issues <= 0:
        raise ValueError("max_issues must be positive.")

    issues = _Issues(max_issues)

    if not isinstance(sequence, EventSequence):
        issues.error(
            "commentary_sequence_not_event",
            "A commentary script belongs to an event sequence, but the clip was selected "
            "by time range.",
        )
    else:
        _check_identity(script, match, sequence, issues)
        _check_times(script, sequence, issues)

    _check_players(script, match, sequence, issues)
    _check_points(script, match, issues)

    return ValidationReport(issues=tuple(issues.items), truncated=issues.truncated)


def validate_commentary_script_or_raise(
    script: CommentaryScript,
    match: Match,
    sequence: SelectedSequence,
) -> ValidationReport:
    """Like ``validate_commentary_script``, but raise if there are errors.

    Returns:
        The report, which may still hold warnings.

    Raises:
        CommentaryScriptValidationError: If the script has errors. The message lists
            every problem, and ``error.report`` holds the full report.
    """

    report = validate_commentary_script(script, match, sequence)

    if not report.is_valid:
        raise CommentaryScriptValidationError(report)

    return report


__all__ = [
    "CommentaryScriptValidationError",
    "validate_commentary_script",
    "validate_commentary_script_or_raise",
]

from dataclasses import dataclass
from enum import StrEnum

from tracking_visualized.domain import (
    EventType,
    Match,
)


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: ValidationSeverity
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]
    truncated: bool = False

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == ValidationSeverity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == ValidationSeverity.WARNING)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def format_text(self) -> str:
        """
        Format the validation report as a human-readable string.

        Returns:
            str: The formatted validation report.
        """
        if not self.issues:
            return "Match validation passed."

        lines = [
            (
                f"Match validation found "
                f"{len(self.errors)} error(s) and "
                f"{len(self.warnings)} warning(s)."
            )
        ]

        for issue in self.issues:
            lines.append(f"[{issue.severity.value.upper()}] {issue.code}: {issue.message}")

        if self.truncated:
            lines.append("Additional validation issues were omitted.")

        return "\n".join(lines)


class MatchValidationError(ValueError):
    """Raised when unified match validation fails."""

    def __init__(
        self,
        report: ValidationReport,
    ) -> None:
        self.report = report

        super().__init__(report.format_text())


class _IssueCollector:
    def __init__(
        self,
        max_issues: int,
    ) -> None:
        if max_issues <= 0:
            raise ValueError("max_issues must be positive.")

        self.max_issues = max_issues
        self.issues: list[ValidationIssue] = []
        self.truncated = False

    @property
    def full(self) -> bool:
        return len(self.issues) >= self.max_issues

    def add(
        self,
        severity: ValidationSeverity,
        code: str,
        message: str,
    ) -> None:
        """
        Add a validation issue to the collector.

        Args:
            severity: The severity of the issue.
            code: The code of the issue.
            message: The message of the issue.
        Raises:
            ValueError: If the collector is full and cannot accept more issues."""
        if self.full:
            self.truncated = True
            return

        self.issues.append(
            ValidationIssue(
                severity=severity,
                code=code,
                message=message,
            )
        )


def _validate_teams_and_players(
    match: Match,
    collector: _IssueCollector,
) -> None:
    """
    Validate the teams and players in the match.

    Args:
        match: The Match object to validate.
        collector: The _IssueCollector to collect validation issues.
    """
    team_ids = {team.team_id for team in match.teams}

    player_ids = {player.player_id for player in match.players}

    home_teams = [team for team in match.teams if team.side.value == "home"]

    away_teams = [team for team in match.teams if team.side.value == "away"]

    if len(home_teams) != 1:
        collector.add(
            ValidationSeverity.ERROR,
            "team.home_count",
            (f"Match must contain exactly one home team; found {len(home_teams)}."),
        )

    if len(away_teams) != 1:
        collector.add(
            ValidationSeverity.ERROR,
            "team.away_count",
            (f"Match must contain exactly one away team; found {len(away_teams)}."),
        )

    for player in match.players:
        if player.team_id not in team_ids:
            collector.add(
                ValidationSeverity.ERROR,
                "player.unknown_team",
                (f"Player '{player.player_id}' references unknown team '{player.team_id}'."),
            )

    if len(player_ids) != len(match.players):
        collector.add(
            ValidationSeverity.ERROR,
            "player.duplicate_id",
            "Match contains duplicate player IDs.",
        )


def _validate_player_positions(
    match: Match,
    collector: _IssueCollector,
) -> None:
    """
    Validate the player positions in the match frames.

    Args:
        match: The Match object to validate.
        collector: The _IssueCollector to collect validation issues.
    """
    known_players = {player.player_id for player in match.players}

    for frame in match.frames:
        if collector.full:
            return

        seen_players: set[str] = set()

        for position in frame.player_positions:
            if position.player_id in seen_players:
                collector.add(
                    ValidationSeverity.ERROR,
                    "position.duplicate_player",
                    (
                        f"Frame {frame.frame_index} contains "
                        f"multiple positions for player "
                        f"'{position.player_id}'."
                    ),
                )

            seen_players.add(position.player_id)

            if position.player_id not in known_players:
                collector.add(
                    ValidationSeverity.ERROR,
                    "position.unknown_player",
                    (
                        f"Frame {frame.frame_index} references "
                        f"unknown player '{position.player_id}'."
                    ),
                )

            if (position.x is None and position.y is not None) or (
                position.x is not None and position.y is None
            ):
                collector.add(
                    ValidationSeverity.WARNING,
                    "position.partial_coordinate",
                    (
                        f"Player '{position.player_id}' in frame "
                        f"{frame.frame_index} has only one "
                        "coordinate."
                    ),
                )


def _validate_ball_positions(
    match: Match,
    collector: _IssueCollector,
) -> None:
    """
    Validate the ball positions in the match frames.

    Args:
        match: The Match object to validate.
        collector: The _IssueCollector to collect validation issues.
    """
    known_teams = {team.team_id for team in match.teams}

    for frame in match.frames:
        if collector.full:
            return

        ball = frame.ball_position

        if ball is None:
            continue

        if (ball.x is None and ball.y is not None) or (ball.x is not None and ball.y is None):
            collector.add(
                ValidationSeverity.WARNING,
                "ball.partial_coordinate",
                (f"Ball in frame {frame.frame_index} has only one planar coordinate."),
            )

        if ball.possession_team_id is not None and ball.possession_team_id not in known_teams:
            collector.add(
                ValidationSeverity.ERROR,
                "ball.unknown_possession_team",
                (
                    f"Ball in frame {frame.frame_index} "
                    "references unknown possession team "
                    f"'{ball.possession_team_id}'."
                ),
            )

        if ball.z is not None and ball.z < 0:
            collector.add(
                ValidationSeverity.WARNING,
                "ball.negative_height",
                (f"Ball in frame {frame.frame_index} has negative height {ball.z}."),
            )


def _validate_timeline(
    match: Match,
    collector: _IssueCollector,
) -> None:
    """
    Validate the match timeline, ensuring that frames are consistent and ordered.

    Args:
        match: The Match object to validate.
        collector: The _IssueCollector to collect validation issues.
    """
    known_periods = {period.period for period in match.periods}

    seen_frame_indices: set[int] = set()

    previous_by_period = {}

    for frame in match.frames:
        if collector.full:
            return

        if frame.frame_index in seen_frame_indices:
            collector.add(
                ValidationSeverity.ERROR,
                "frame.duplicate_index",
                (f"Duplicate frame index {frame.frame_index}."),
            )

        seen_frame_indices.add(frame.frame_index)

        if frame.time.period not in known_periods:
            collector.add(
                ValidationSeverity.ERROR,
                "frame.unknown_period",
                (f"Frame {frame.frame_index} references unknown period '{frame.time.period}'."),
            )

        previous = previous_by_period.get(frame.time.period)

        if previous is not None:
            if frame.time.seconds <= previous.time.seconds:
                collector.add(
                    ValidationSeverity.ERROR,
                    "frame.non_monotonic_time",
                    (
                        f"Frame {frame.frame_index} has time "
                        f"{frame.time.seconds:.3f}s after frame "
                        f"{previous.frame_index} at "
                        f"{previous.time.seconds:.3f}s in the "
                        f"same period."
                    ),
                )

            if frame.frame_index <= previous.frame_index:
                collector.add(
                    ValidationSeverity.ERROR,
                    "frame.non_monotonic_index",
                    (f"Frame index {frame.frame_index} does not follow {previous.frame_index}."),
                )

        previous_by_period[frame.time.period] = frame

        first_frame_by_period = {}

        for frame in match.frames:
            first_frame_by_period.setdefault(
                frame.time.period,
                frame,
            )

        for period_type, frame in first_frame_by_period.items():
            if abs(frame.time.seconds) > 1e-6:
                collector.add(
                    ValidationSeverity.WARNING,
                    "period.nonzero_start",
                    (f"{period_type.value} begins at {frame.time.seconds:.6f}s instead of 0."),
                )


def _validate_events(
    match: Match,
    collector: _IssueCollector,
) -> None:
    """
    Validate the events in the match, ensuring that they reference known periods, teams, and players
    and that there are no duplicate event IDs.

    Args:
        match: The Match object to validate.
        collector: The _IssueCollector to collect validation issues.
    """
    teams = {team.team_id: team for team in match.teams}

    players = {player.player_id: player for player in match.players}

    frames = {frame.frame_index: frame for frame in match.frames}

    periods = {period.period for period in match.periods}

    seen_event_ids: set[str] = set()

    for event in match.events:
        if collector.full:
            return

        if event.event_id in seen_event_ids:
            collector.add(
                ValidationSeverity.ERROR,
                "event.duplicate_id",
                (f"Duplicate event ID '{event.event_id}'."),
            )

        seen_event_ids.add(event.event_id)

        if event.time.period not in periods:
            collector.add(
                ValidationSeverity.ERROR,
                "event.unknown_period",
                (f"Event '{event.event_id}' references unknown period '{event.time.period}'."),
            )

        if event.team_id is not None and event.team_id not in teams:
            collector.add(
                ValidationSeverity.ERROR,
                "event.unknown_team",
                (f"Event '{event.event_id}' references unknown team '{event.team_id}'."),
            )

        if event.player_id is not None and event.player_id not in players:
            collector.add(
                ValidationSeverity.ERROR,
                "event.unknown_player",
                (f"Event '{event.event_id}' references unknown player '{event.player_id}'."),
            )

        if event.player_id is not None and event.team_id is not None and event.player_id in players:
            player = players[event.player_id]

            if player.team_id != event.team_id:
                collector.add(
                    ValidationSeverity.ERROR,
                    "event.player_team_mismatch",
                    (
                        f"Event '{event.event_id}' assigns "
                        f"player '{event.player_id}' to team "
                        f"'{event.team_id}', but the player "
                        f"belongs to '{player.team_id}'."
                    ),
                )

        if event.event_type == EventType.SHOT:
            if event.player_id is None:
                collector.add(
                    ValidationSeverity.ERROR,
                    "event.shot_missing_player",
                    (f"Shot event '{event.event_id}' has no player."),
                )

            if event.team_id is None:
                collector.add(
                    ValidationSeverity.ERROR,
                    "event.shot_missing_team",
                    (f"Shot event '{event.event_id}' has no team."),
                )

        if event.frame_index is not None:
            frame = frames.get(event.frame_index)

            if frame is None:
                collector.add(
                    ValidationSeverity.ERROR,
                    "event.unknown_frame",
                    (f"Event '{event.event_id}' references missing frame {event.frame_index}."),
                )

                continue

            if frame.time.period != event.time.period:
                collector.add(
                    ValidationSeverity.ERROR,
                    "event.frame_period_mismatch",
                    (
                        f"Event '{event.event_id}' is in "
                        f"{event.time.period.value}, but frame "
                        f"{event.frame_index} is in "
                        f"{frame.time.period.value}."
                    ),
                )

            difference = abs(frame.time.seconds - event.time.seconds)

            if difference > 1e-6:
                collector.add(
                    ValidationSeverity.ERROR,
                    "event.frame_time_mismatch",
                    (
                        f"Event '{event.event_id}' has time "
                        f"{event.time.seconds:.6f}s but its "
                        f"referenced frame {event.frame_index} "
                        f"has time "
                        f"{frame.time.seconds:.6f}s."
                    ),
                )

        if (event.x is None and event.y is not None) or (event.x is not None and event.y is None):
            collector.add(
                ValidationSeverity.WARNING,
                "event.partial_coordinate",
                (f"Event '{event.event_id}' has only one coordinate."),
            )


def validate_match(
    match: Match,
    *,
    max_issues: int = 500,
) -> ValidationReport:
    """
    Validate cross-object consistency of a unified match.

    Args:
        match: The Match object to validate.
        max_issues: The maximum number of issues to collect before truncating the report.

    Returns:
        ValidationReport: A report containing the validation issues found in the match.
    """

    collector = _IssueCollector(max_issues=max_issues)

    _validate_teams_and_players(
        match,
        collector,
    )

    _validate_player_positions(
        match,
        collector,
    )

    _validate_ball_positions(
        match,
        collector,
    )

    _validate_timeline(
        match,
        collector,
    )

    _validate_events(
        match,
        collector,
    )

    return ValidationReport(
        issues=tuple(collector.issues),
        truncated=collector.truncated,
    )


def validate_match_or_raise(
    match: Match,
    *,
    max_issues: int = 500,
) -> ValidationReport:
    """
    Validate a match and raise an exception if validation fails.

    Args:
        match: The Match object to validate.
        max_issues: The maximum number of issues to collect before truncating the report.

    Returns:
        ValidationReport: A report containing the validation issues found in the match.

    Raises:
        MatchValidationError: If the match fails validation.
    """
    report = validate_match(
        match,
        max_issues=max_issues,
    )

    if not report.is_valid:
        raise MatchValidationError(report)

    return report

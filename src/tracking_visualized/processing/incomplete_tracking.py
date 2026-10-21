from dataclasses import dataclass, replace
from math import isfinite

from tracking_visualized.domain import (
    BallPosition,
    Frame,
    PlayerPosition,
)
from tracking_visualized.processing.sequences import EventSequence


class IncompleteTrackingError(ValueError):
    """Raised when incomplete tracking data cannot be processed safely."""


def _validate_gap_seconds(name: str, value: float) -> None:
    """Validate a time gap threshold used by tracking repair logic."""
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")

    if value < 0:
        raise ValueError(f"{name} cannot be negative.")


@dataclass(frozen=True, slots=True)
class TrackingGapPolicy:
    """Policy for handling gaps in tracking data."""

    max_player_gap_seconds: float = 0.2
    max_ball_gap_seconds: float = 0.2

    interpolate_players: bool = True
    interpolate_ball: bool = True

    def __post_init__(self) -> None:
        """Validate the tracking gap policy parameters."""
        _validate_gap_seconds("max_player_gap_seconds", self.max_player_gap_seconds)
        _validate_gap_seconds("max_ball_gap_seconds", self.max_ball_gap_seconds)


@dataclass(frozen=True, slots=True)
class TrackingRepairReport:
    """Report on the repair of tracking data."""

    interpolated_player_positions: int
    unresolved_player_positions: int

    interpolated_ball_positions: int
    unresolved_ball_positions: int

    @property
    def interpolated_positions(self) -> int:
        return self.interpolated_player_positions + self.interpolated_ball_positions

    @property
    def unresolved_positions(self) -> int:
        return self.unresolved_player_positions + self.unresolved_ball_positions

    @property
    def is_complete(self) -> bool:
        return self.unresolved_positions == 0


def _player_is_observed(
    position: PlayerPosition | None,
) -> bool:
    """Check if a player position is observed (i.e., has valid coordinates).

    Args:
        position (PlayerPosition | None): The player position to check.

    Returns:
        bool: True if the player position is observed, False otherwise.
    """
    return position is not None and position.x is not None and position.y is not None


def _ball_is_observed(
    position: BallPosition | None,
) -> bool:
    """
    Check if a ball position is observed (i.e., has valid coordinates).

    Args:
        position (BallPosition | None): The ball position to check.

    Returns:
        bool: True if the ball position is observed, False otherwise.
    """
    return position is not None and position.x is not None and position.y is not None


def _interpolate(
    start: float,
    end: float,
    alpha: float,
) -> float:
    """
    Linearly interpolate between two values.

    Args:
        start (float): The starting value.
        end (float): The ending value.
        alpha (float): The interpolation factor (0.0 to 1.0).

    Returns:
        float: The interpolated value.
    """
    return start + (end - start) * alpha


def _player_position(
    frame: Frame,
    player_id: str,
) -> PlayerPosition | None:
    """
    Retrieve the position of a player in a given frame.

    Args:
        frame (Frame): The frame containing player positions.
        player_id (str): The ID of the player whose position is to be retrieved.

    Returns:
        PlayerPosition | None: The position of the player if observed, otherwise None.
    """
    for position in frame.player_positions:
        if position.player_id == player_id:
            return position

    return None


def _with_player_position(
    frame: Frame,
    position: PlayerPosition,
) -> Frame:
    """
    Return a new frame with the specified player position updated or added.

    Args:
        frame (Frame): The original frame.
        position (PlayerPosition): The player position to update or add.

    Returns:
        Frame: A new frame with the updated player position.
    """
    positions = list(frame.player_positions)

    for index, existing in enumerate(positions):
        if existing.player_id == position.player_id:
            positions[index] = position

            return replace(
                frame,
                player_positions=tuple(positions),
            )

    positions.append(position)

    return replace(
        frame,
        player_positions=tuple(positions),
    )


def _sequence_player_ids(
    frames: tuple[Frame, ...],
) -> tuple[str, ...]:
    """
    Extract the unique player IDs from a sequence of frames.

    Args:
        frames (tuple[Frame, ...]): A tuple of Frame objects representing the sequence.

    Returns:
        tuple[str, ...]: A tuple of unique player IDs present in the frames.
    """
    player_ids = {position.player_id for frame in frames for position in frame.player_positions}

    return tuple(sorted(player_ids))


def _ensure_strictly_ordered(
    left_frame: Frame,
    right_frame: Frame,
) -> float:
    """Return the duration between two frames, validating the ordering."""
    duration = right_frame.time.seconds - left_frame.time.seconds

    if duration <= 0:
        raise IncompleteTrackingError("Tracking frames are not strictly ordered.")

    return duration


def _repair_player(
    frames: list[Frame],
    player_id: str,
    max_gap_seconds: float,
) -> tuple[int, int]:
    """
    Repair the tracking data for a specific player by interpolating missing positions.

    Args:
        frames (list[Frame]): A list of Frame objects representing the tracking data.
        player_id (str): The ID of the player to repair.
        max_gap_seconds (float): The maximum allowed gap in seconds for interpolation.

    Returns:
        tuple[int, int]: A tuple containing the number of interpolated positions
            and the number of unresolved positions.
    """
    observed_indices = [
        index
        for index, frame in enumerate(frames)
        if _player_is_observed(
            _player_position(
                frame,
                player_id,
            )
        )
    ]

    interpolated = 0
    unresolved = 0

    if len(observed_indices) < 2:
        return interpolated, unresolved

    for left_index, right_index in zip(
        observed_indices,
        observed_indices[1:],
        strict=False,
    ):
        if right_index == left_index + 1:
            continue

        left_frame = frames[left_index]
        right_frame = frames[right_index]

        left = _player_position(
            left_frame,
            player_id,
        )

        right = _player_position(
            right_frame,
            player_id,
        )

        assert left is not None
        assert right is not None
        assert left.x is not None
        assert left.y is not None
        assert right.x is not None
        assert right.y is not None

        duration = _ensure_strictly_ordered(left_frame, right_frame)

        missing_indices = range(
            left_index + 1,
            right_index,
        )

        if duration > max_gap_seconds:
            unresolved += sum(
                1
                for index in missing_indices
                if not _player_is_observed(
                    _player_position(
                        frames[index],
                        player_id,
                    )
                )
            )

            continue

        for index in missing_indices:
            frame = frames[index]

            existing = _player_position(
                frame,
                player_id,
            )

            if _player_is_observed(existing):
                continue

            alpha = (frame.time.seconds - left_frame.time.seconds) / duration

            interpolated_x = _interpolate(
                left.x,
                right.x,
                alpha,
            )

            interpolated_y = _interpolate(
                left.y,
                right.y,
                alpha,
            )

            # Preserve a known coordinate if only one
            # component was missing.
            x = existing.x if existing is not None and existing.x is not None else interpolated_x

            y = existing.y if existing is not None and existing.y is not None else interpolated_y

            frames[index] = _with_player_position(
                frame,
                PlayerPosition(
                    player_id=player_id,
                    x=x,
                    y=y,
                ),
            )

            interpolated += 1

    return interpolated, unresolved


def _shared_value(
    left,
    right,
):
    """
    Return the shared value if both inputs are equal, otherwise return None.

    Args:
        left: The first value to compare.
        right: The second value to compare.

    Returns:
        The shared value if both inputs are equal, otherwise None.
    """
    if left == right:
        return left

    return None


def _interpolated_ball(
    left: BallPosition,
    right: BallPosition,
    alpha: float,
    current: BallPosition | None,
) -> BallPosition:
    """
    Interpolate the ball position between two known positions.

    Args:
        left (BallPosition): The ball position at the start of the interval.
        right (BallPosition): The ball position at the end of the interval.
        alpha (float): The interpolation factor (0.0 to 1.0).
        current (BallPosition | None): The current ball position, if available.

    Returns:
        BallPosition: The interpolated ball position."""
    assert left.x is not None
    assert left.y is not None
    assert right.x is not None
    assert right.y is not None

    x = (
        current.x
        if current is not None and current.x is not None
        else _interpolate(
            left.x,
            right.x,
            alpha,
        )
    )

    y = (
        current.y
        if current is not None and current.y is not None
        else _interpolate(
            left.y,
            right.y,
            alpha,
        )
    )

    if current is not None and current.z is not None:
        z = current.z

    elif left.z is not None and right.z is not None:
        z = _interpolate(
            left.z,
            right.z,
            alpha,
        )

    else:
        z = None

    possession_team_id = (
        current.possession_team_id
        if current is not None and current.possession_team_id is not None
        else _shared_value(
            left.possession_team_id,
            right.possession_team_id,
        )
    )

    is_in_play = (
        current.is_in_play
        if current is not None and current.is_in_play is not None
        else _shared_value(
            left.is_in_play,
            right.is_in_play,
        )
    )

    return BallPosition(
        x=x,
        y=y,
        z=z,
        possession_team_id=possession_team_id,
        is_in_play=is_in_play,
    )


def _repair_ball(
    frames: list[Frame],
    max_gap_seconds: float,
) -> tuple[int, int]:
    """
    Repair the tracking data for the ball by interpolating missing positions.

    Args:
        frames (list[Frame]): A list of Frame objects representing the tracking data.
        max_gap_seconds (float): The maximum allowed gap in seconds for interpolation.

    Returns:
        tuple[int, int]: A tuple containing the number of interpolated positions
            and the number of unresolved positions."""
    observed_indices = [
        index for index, frame in enumerate(frames) if _ball_is_observed(frame.ball_position)
    ]

    interpolated = 0

    if not observed_indices:
        return 0, len(frames)

    if len(observed_indices) == 1:
        unresolved = sum(1 for frame in frames if not _ball_is_observed(frame.ball_position))

        return 0, unresolved

    for left_index, right_index in zip(
        observed_indices,
        observed_indices[1:],
        strict=False,
    ):
        if right_index == left_index + 1:
            continue

        left_frame = frames[left_index]
        right_frame = frames[right_index]

        left = left_frame.ball_position
        right = right_frame.ball_position

        assert left is not None
        assert right is not None

        duration = _ensure_strictly_ordered(left_frame, right_frame)

        if duration > max_gap_seconds:
            continue

        for index in range(
            left_index + 1,
            right_index,
        ):
            frame = frames[index]

            if _ball_is_observed(frame.ball_position):
                continue

            alpha = (frame.time.seconds - left_frame.time.seconds) / duration

            ball = _interpolated_ball(
                left,
                right,
                alpha,
                frame.ball_position,
            )

            frames[index] = replace(
                frame,
                ball_position=ball,
            )

            interpolated += 1

    unresolved = sum(1 for frame in frames if not _ball_is_observed(frame.ball_position))

    return interpolated, unresolved


def repair_sequence_tracking(
    sequence: EventSequence,
    *,
    policy: TrackingGapPolicy | None = None,
) -> tuple[EventSequence, TrackingRepairReport]:
    """
    Repair short gaps in an extracted tracking sequence.

    Args:
        sequence (EventSequence): The extracted tracking sequence to repair.
        policy (TrackingGapPolicy | None): The policy for handling gaps in tracking data.

    Returns:
        tuple[EventSequence, TrackingRepairReport]: A tuple containing the repaired
            tracking sequence and a report on the repair process."""

    if policy is None:
        policy = TrackingGapPolicy()

    frames = list(sequence.frames)

    player_interpolated = 0
    player_unresolved = 0

    if policy.interpolate_players:
        for player_id in _sequence_player_ids(sequence.frames):
            interpolated, unresolved = _repair_player(
                frames,
                player_id,
                policy.max_player_gap_seconds,
            )

            player_interpolated += interpolated
            player_unresolved += unresolved

    ball_interpolated = 0
    ball_unresolved = 0

    if policy.interpolate_ball:
        (
            ball_interpolated,
            ball_unresolved,
        ) = _repair_ball(
            frames,
            policy.max_ball_gap_seconds,
        )

    else:
        ball_unresolved = sum(1 for frame in frames if not _ball_is_observed(frame.ball_position))

    repaired = replace(
        sequence,
        frames=tuple(frames),
    )

    return (
        repaired,
        TrackingRepairReport(
            interpolated_player_positions=(player_interpolated),
            unresolved_player_positions=(player_unresolved),
            interpolated_ball_positions=(ball_interpolated),
            unresolved_ball_positions=(ball_unresolved),
        ),
    )

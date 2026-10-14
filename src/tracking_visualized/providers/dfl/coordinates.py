from math import isfinite

from tracking_visualized.domain import CoordinateSystem


class DflCoordinateError(ValueError):
    """Raised when a DFL coordinate cannot be normalized."""


def _validate_coordinate_value(
    value: float | None,
    name: str,
) -> None:
    """
    Validates that a coordinate value is either None or a finite float.

    Args:
        value: The coordinate value to validate.
        name: The name of the coordinate (for error messages).
    """
    if value is None:
        return

    if not isfinite(value):
        raise DflCoordinateError(f"{name} coordinate must be finite, got {value}.")


def normalize_tracking_coordinates(
    x: float | None,
    y: float | None,
    coordinate_system: CoordinateSystem,
) -> tuple[float | None, float | None]:
    """
    Convert Sportec tracking coordinates to canonical coordinates.

    Args:
        x: The x-coordinate in Sportec format.
        y: The y-coordinate in Sportec format.
        coordinate_system: The coordinate system of the pitch.

    Returns:
        A tuple of normalized (x, y) coordinates in canonical format.
    """

    _validate_coordinate_value(x, "x")
    _validate_coordinate_value(y, "y")

    normalized_x = x + coordinate_system.pitch_length / 2 if x is not None else None

    normalized_y = y + coordinate_system.pitch_width / 2 if y is not None else None

    return normalized_x, normalized_y


def normalize_event_coordinates(
    x: float | None,
    y: float | None,
    coordinate_system: CoordinateSystem,
) -> tuple[float | None, float | None]:
    """
    Convert Sportec event coordinates to canonical coordinates.

    Args:
        x: The x-coordinate in Sportec format.
        y: The y-coordinate in Sportec format.
        coordinate_system: The coordinate system of the pitch.

    Returns:
        A tuple of normalized (x, y) coordinates in canonical format.
    """

    _validate_coordinate_value(x, "x")
    _validate_coordinate_value(y, "y")

    normalized_x = x

    normalized_y = coordinate_system.pitch_width - y if y is not None else None

    return normalized_x, normalized_y


def is_on_pitch(
    x: float | None,
    y: float | None,
    coordinate_system: CoordinateSystem,
) -> bool:
    """
    Check if the given coordinates are within the bounds of the pitch.

    Args:
        x: The x-coordinate to check.
        y: The y-coordinate to check.
        coordinate_system: The coordinate system of the pitch.

    Returns:
        True if the coordinates are within the bounds of the pitch, False otherwise.
    """
    if x is None or y is None:
        return False

    return 0 <= x <= coordinate_system.pitch_length and 0 <= y <= coordinate_system.pitch_width


def create_coordinate_system(
    pitch_length: float,
    pitch_width: float,
) -> CoordinateSystem:
    """
    Create a CoordinateSystem object for the pitch.

    Args:
        pitch_length: The length of the pitch in meters.
        pitch_width: The width of the pitch in meters.

    Returns:
        A CoordinateSystem object for the pitch.
    """
    return CoordinateSystem(
        pitch_length=pitch_length,
        pitch_width=pitch_width,
    )

import datetime
import xml.etree.ElementTree as ET


def require_element(
    parent: ET.Element,
    tag: str,
    error_cls: type[Exception],
) -> ET.Element:
    """Requires a child element to exist on the parent and raises error_cls if absent."""
    element = parent.find(tag)

    if element is None:
        raise error_cls(f"Missing required XML element <{tag}>.")

    return element


def require_attribute(
    element: ET.Element,
    attribute: str,
    error_cls: type[Exception],
) -> str:
    """Requires an XML attribute and raises error_cls if it is missing or blank."""
    value = element.get(attribute)

    if value is None or not value.strip():
        raise error_cls(f"Missing required attribute '{attribute}' on <{element.tag}>.")

    return value


def optional_float(
    value: str | None,
    error_cls: type[Exception],
) -> float | None:
    """Converts a string to a float if present, otherwise returns None."""
    if value is None or not value.strip():
        return None

    try:
        return float(value)
    except ValueError as exc:
        raise error_cls(f"Invalid numeric value '{value}'.") from exc


def optional_int(
    value: str | None,
    error_cls: type[Exception],
) -> int | None:
    """Converts a string to an integer if present, otherwise returns None."""
    if value is None or not value.strip():
        return None

    try:
        return int(value)
    except ValueError as exc:
        raise error_cls(f"Invalid integer value '{value}'.") from exc


def milliseconds_to_seconds(
    value: str,
    error_cls: type[Exception],
) -> float:
    """Converts a millisecond string to seconds."""
    try:
        milliseconds = int(value)
    except ValueError as exc:
        raise error_cls(f"Expected duration in milliseconds, got '{value}'.") from exc

    if milliseconds <= 0:
        raise error_cls("Period duration must be positive.")

    return milliseconds / 1000


def parse_timestamp(value: str, error_cls: type[Exception]) -> datetime:
    """
    Parses an ISO-8601 timestamp string into a datetime object.

    Args:
        value: The ISO-8601 timestamp string to parse.

    Returns:
        A datetime object representing the parsed timestamp.
    """
    normalized = value.replace("Z", "+00:00")

    try:
        timestamp = datetime.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise error_cls(f"Invalid ISO-8601 timestamp '{value}'.") from exc

    if timestamp.tzinfo is None:
        raise error_cls(f"Tracking timestamp must include timezone information: '{value}'.")

    return timestamp

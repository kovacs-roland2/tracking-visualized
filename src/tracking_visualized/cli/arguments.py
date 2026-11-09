import argparse


def non_negative_float(value: str) -> float:
    """Argparse type for a non-negative number of seconds.

    Args:
        value: The string to validate.

    Returns:
        The parsed non-negative float.

    Raises:
        argparse.ArgumentTypeError: If the value is not a number or is negative.
    """

    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected a number, got '{value}'.") from exc

    if parsed < 0:
        raise argparse.ArgumentTypeError("Value cannot be negative.")

    return parsed


__all__ = [
    "non_negative_float",
]

import argparse
from collections.abc import Sequence

from tracking_visualized.config import SequenceConfig
from tracking_visualized.domain import Match, PeriodType
from tracking_visualized.processing import (
    EventSequence,
    SelectedSequence,
    SequenceSelectionError,
    TimeRangeSequence,
    select_event_sequence,
    select_time_range,
)


def _non_negative_float(
    value: str,
) -> float:
    """
    Validate that a string represents a non-negative float.

    Args:
        value (str): The string to validate.

    Returns:
        float: The parsed non-negative float."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected a number, got '{value}'.") from exc

    if parsed < 0:
        raise argparse.ArgumentTypeError("Value cannot be negative.")

    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Build the sequence-selection CLI parser."""

    sequence_defaults = SequenceConfig()

    parser = argparse.ArgumentParser(
        prog="football-replay select-sequence",
        description=("Select a tracking sequence by event ID or by an explicit match time range."),
    )

    commands = parser.add_subparsers(
        dest="selection_mode",
        required=True,
    )

    event_parser = commands.add_parser(
        "event",
        help="Select a sequence around an event.",
    )

    event_parser.add_argument(
        "--event-id",
        required=True,
        help="ID of the event to render.",
    )

    event_parser.add_argument(
        "--pre",
        type=_non_negative_float,
        default=sequence_defaults.pre_event_seconds,
        help=(
            f"Seconds before the event to include. Default: {sequence_defaults.pre_event_seconds:g}"
        ),
    )

    event_parser.add_argument(
        "--post",
        type=_non_negative_float,
        default=sequence_defaults.post_event_seconds,
        help=(
            f"Seconds after the event to include. Default: {sequence_defaults.post_event_seconds:g}"
        ),
    )

    time_parser = commands.add_parser(
        "time",
        help="Select an explicit time range.",
    )

    time_parser.add_argument(
        "--period",
        required=True,
        choices=[period.value for period in PeriodType],
        help="Match period containing the requested range.",
    )

    time_parser.add_argument(
        "--start",
        required=True,
        type=_non_negative_float,
        help="Period-relative start time in seconds.",
    )

    time_parser.add_argument(
        "--end",
        required=True,
        type=_non_negative_float,
        help="Period-relative end time in seconds.",
    )

    return parser


def _select_from_namespace(
    match: Match,
    args: argparse.Namespace,
) -> SelectedSequence:
    """
    Select a sequence based on parsed CLI arguments.

    Args:
        match (Match): The match object containing events and tracking frames.
        args (argparse.Namespace): Parsed CLI arguments.

    Returns:
        SelectedSequence: The selected sequence based on the provided arguments."""
    if args.selection_mode == "event":
        return select_event_sequence(
            match,
            args.event_id,
            pre_event_seconds=args.pre,
            post_event_seconds=args.post,
        )

    if args.selection_mode == "time":
        return select_time_range(
            match,
            period=PeriodType(args.period),
            start_seconds=args.start,
            end_seconds=args.end,
        )

    raise SequenceSelectionError(f"Unknown selection mode '{args.selection_mode}'.")


def _parse_cli_args(
    argv: Sequence[str] | None,
) -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    """Build the parser and parse the given argv, if any."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return parser, args


def select_sequence_from_cli_args(
    match: Match,
    argv: Sequence[str] | None = None,
) -> SelectedSequence:
    """
    Parse CLI arguments and return the requested sequence.

    Args:
        match (Match): The match object containing events and tracking frames.
        argv (Sequence[str] | None): Optional list of command-line arguments.
            If None, uses sys.argv.

    Returns:
        SelectedSequence: The selected sequence based on the provided CLI arguments."""

    _, args = _parse_cli_args(argv)

    return _select_from_namespace(
        match,
        args,
    )


def format_sequence_summary(
    sequence: SelectedSequence,
) -> str:
    """
    Create a human-readable CLI summary.

    Args:
        sequence (SelectedSequence): The selected sequence to summarize.

    Returns:
        str: A formatted summary of the selected sequence."""

    if isinstance(
        sequence,
        EventSequence,
    ):
        return "\n".join(
            [
                "Selected event sequence",
                f"Event ID: {sequence.event.event_id}",
                (f"Period: {sequence.event.time.period.value}"),
                (f"Event time: {sequence.event.time.seconds:.3f}s"),
                (f"Window: {sequence.start_time.seconds:.3f}s → {sequence.end_time.seconds:.3f}s"),
                (f"Frames: {len(sequence.frames)}"),
                (f"Duration: {sequence.duration_seconds:.3f}s"),
            ]
        )

    if isinstance(
        sequence,
        TimeRangeSequence,
    ):
        return "\n".join(
            [
                "Selected manual time range",
                (f"Period: {sequence.start_time.period.value}"),
                (f"Window: {sequence.start_time.seconds:.3f}s → {sequence.end_time.seconds:.3f}s"),
                (f"Frames: {len(sequence.frames)}"),
                (f"First frame: {sequence.first_frame.frame_index}"),
                (f"Last frame: {sequence.last_frame.frame_index}"),
                (f"Duration: {sequence.duration_seconds:.3f}s"),
            ]
        )

    raise TypeError(f"Unsupported sequence type: {type(sequence).__name__}")


def run_sequence_selection_cli(
    match: Match,
    argv: Sequence[str] | None = None,
) -> SelectedSequence:
    """
    Run CLI sequence selection against an already loaded match.

    Args:
        match (Match): The match object containing events and tracking frames.
        argv (Sequence[str] | None): Optional list of command-line arguments.
            If None, uses sys.argv.

    Returns:
        SelectedSequence: The selected sequence based on the provided CLI arguments.
    """

    parser, args = _parse_cli_args(argv)

    try:
        sequence = _select_from_namespace(
            match,
            args,
        )
    except (
        KeyError,
        SequenceSelectionError,
    ) as exc:
        parser.error(str(exc))

    print(format_sequence_summary(sequence))

    return sequence

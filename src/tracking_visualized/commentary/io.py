import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from tracking_visualized.commentary.schema import (
    CommentaryScriptModel,
    script_from_domain,
    script_to_domain,
)
from tracking_visualized.config import DEFAULT_OUTPUT_DIR
from tracking_visualized.domain import COMMENTARY_SCRIPT_VERSION, CommentaryScript

MATCH_ID_PREFIX = "DFL-MAT-"
MAX_REPORTED_ERRORS = 10

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class CommentaryScriptError(ValueError):
    """Raised when a script file cannot be read, parsed or understood."""


def short_match_id(match_id: str) -> str:
    """The match ID without the ``DFL-MAT-`` prefix, e.g. ``J03WMX``.

    Scripts may name the match either way; compare IDs in this form.
    """

    return match_id.strip().removeprefix(MATCH_ID_PREFIX)


def default_script_path(
    match_id: str,
    event_id: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    """Default file of a script: ``output/<match>_<event>_commentary.json``.

    The match may be given as ``J03WMX`` or ``DFL-MAT-J03WMX``; both name the same file.
    """

    name = _UNSAFE_FILENAME_CHARS.sub(
        "_", f"{short_match_id(match_id)}_{event_id.strip()}_commentary"
    )

    return Path(output_dir) / f"{name}.json"


def _format_location(location: tuple[int | str, ...]) -> str:
    text = ""

    for part in location:
        text += f"[{part}]" if isinstance(part, int) else f".{part}" if text else str(part)

    return text or "script"


def _describe(source: str) -> str:
    """``Invalid commentary script 'file.json'`` or, without a source, just the prefix."""

    return f"commentary script {source}".rstrip()


def _format_validation_error(source: str, error: ValidationError) -> str:
    problems = [f"  {_format_location(item['loc'])}: {item['msg']}" for item in error.errors()]
    shown = problems[:MAX_REPORTED_ERRORS]

    if len(problems) > MAX_REPORTED_ERRORS:
        shown.append(f"  ... and {len(problems) - MAX_REPORTED_ERRORS} more")

    return f"Invalid {_describe(source)}:\n" + "\n".join(shown)


def _check_version(data: dict[str, Any], source: str) -> None:
    version = data.get("version")

    if version is None:
        raise CommentaryScriptError(
            f"Invalid {_describe(source)}: missing 'version' "
            f"(this release reads version {COMMENTARY_SCRIPT_VERSION})."
        )

    if version != COMMENTARY_SCRIPT_VERSION or isinstance(version, bool):
        raise CommentaryScriptError(
            f"Unsupported {_describe(source)} version {version!r}; "
            f"this release reads version {COMMENTARY_SCRIPT_VERSION}."
        )


def parse_script(text: str | bytes, source: str = "") -> CommentaryScript:
    """Parse a script from JSON text.

    Args:
        text: The JSON document.
        source: Name used in error messages, e.g. the file path.

    Raises:
        CommentaryScriptError: If the text is not valid JSON, has an unsupported
            version or does not match the script format. The message lists the
            problems field by field.
    """

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CommentaryScriptError(
            f"Invalid {_describe(source)}: not valid JSON "
            f"({exc.msg} at line {exc.lineno}, column {exc.colno})."
        ) from exc

    if not isinstance(data, dict):
        raise CommentaryScriptError(
            f"Invalid {_describe(source)}: expected a JSON object at the top level."
        )

    _check_version(data, source)

    try:
        model = CommentaryScriptModel.model_validate(data)
    except ValidationError as exc:
        raise CommentaryScriptError(_format_validation_error(source, exc)) from exc

    try:
        return script_to_domain(model)
    except ValueError as exc:
        raise CommentaryScriptError(f"Invalid {_describe(source)}: {exc}") from exc


def script_to_json(script: CommentaryScript) -> str:
    """Serialize a script to indented JSON, leaving out unset optional fields."""

    model = script_from_domain(script)
    data = model.model_dump(mode="json", exclude_none=True)

    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def load_script(path: str | os.PathLike[str]) -> CommentaryScript:
    """Load a script from a JSON file.

    Raises:
        CommentaryScriptError: If the file is missing, unreadable or not a valid script.
    """

    file = Path(path)

    try:
        text = file.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CommentaryScriptError(f"Commentary script '{file}' does not exist.") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise CommentaryScriptError(f"Could not read commentary script '{file}': {exc}") from exc

    return parse_script(text, f"'{file}'")


def save_script(script: CommentaryScript, path: str | os.PathLike[str]) -> Path:
    """Write a script to a JSON file and return its path.

    Missing folders are created and an existing file is replaced. The file is written
    to a temporary name first, so a failed write never leaves a half-written script.
    """

    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)

    partial = file.with_name(f".{file.name}.{os.urandom(8).hex()}.partial")

    try:
        partial.write_text(script_to_json(script), encoding="utf-8")
        os.replace(partial, file)
    finally:
        partial.unlink(missing_ok=True)

    return file


__all__ = [
    "CommentaryScriptError",
    "default_script_path",
    "load_script",
    "parse_script",
    "save_script",
    "script_to_json",
    "short_match_id",
]

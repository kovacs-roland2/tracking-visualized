"""Commentary scripts: the contract between the LLM and the renderer."""

from tracking_visualized.commentary.io import (
    CommentaryScriptError,
    default_script_path,
    load_script,
    parse_script,
    save_script,
    script_to_json,
    short_match_id,
)
from tracking_visualized.commentary.schema import (
    CommentaryScriptModel,
    commentary_script_json_schema,
    script_from_domain,
    script_to_domain,
)

__all__ = [
    "CommentaryScriptError",
    "CommentaryScriptModel",
    "commentary_script_json_schema",
    "default_script_path",
    "load_script",
    "parse_script",
    "save_script",
    "script_from_domain",
    "script_to_domain",
    "script_to_json",
    "short_match_id",
]

import json
from pathlib import Path

import pytest

from tracking_visualized.commentary import (
    CommentaryScriptError,
    default_script_path,
    load_script,
    parse_script,
    save_script,
    script_to_json,
)
from tracking_visualized.domain import (
    ArrowAnnotation,
    Beat,
    CommentaryScript,
    Highlight,
    HighlightRole,
    PeriodType,
    PlayerTarget,
    PointTarget,
)


def make_script() -> CommentaryScript:
    return CommentaryScript(
        match_id="DFL-MAT-J03WMX",
        event_id="E1",
        period=PeriodType.FIRST_HALF,
        beats=(
            Beat(
                5.0,
                "Köln drängen — schöner Ball!",
                pause_seconds=1.0,
                highlights=(Highlight("p1", HighlightRole.SHOOTER),),
                annotations=(ArrowAnnotation(PlayerTarget("p1"), PointTarget(105.0, 34.0)),),
            ),
            Beat(8.0, "Goal"),
        ),
    )


def valid_data(**overrides) -> dict:
    data = {
        "version": 1,
        "match_id": "m",
        "event_id": "e",
        "period": "first_half",
        "beats": [{"start_seconds": 1.0, "text": "Hello"}],
    }
    data.update(overrides)

    return data


# --- paths -------------------------------------------------------------------------------


def test_default_path_is_in_the_output_folder():
    assert default_script_path("J03WMX", "E1") == Path("output/J03WMX_E1_commentary.json")


def test_default_path_accepts_the_full_match_id():
    assert default_script_path("DFL-MAT-J03WMX", "E1") == default_script_path("J03WMX", "E1")


def test_default_path_is_safe_for_odd_ids_and_honours_the_folder(tmp_path):
    path = default_script_path("J03WMX", "a/b c:d", tmp_path)

    assert path == tmp_path / "J03WMX_a_b_c_d_commentary.json"


# --- serialization -----------------------------------------------------------------------


def test_json_is_readable_and_leaves_out_unset_optional_fields():
    text = script_to_json(make_script())
    data = json.loads(text)

    assert text.endswith("}\n")
    assert '\n  "beats": [\n' in text
    assert "Köln drängen — schöner Ball!" in text  # not escaped
    assert "generator" not in data
    assert "duration_seconds" not in data["beats"][0]
    assert "label" not in data["beats"][0]["annotations"][0]
    assert list(data)[:4] == ["version", "match_id", "event_id", "period"]


def test_save_and_load_round_trip(tmp_path):
    script = make_script()
    path = tmp_path / "nested" / "script.json"

    assert save_script(script, path) == path
    assert load_script(path) == script


def test_save_replaces_an_existing_file_and_leaves_no_temporary_files(tmp_path):
    path = tmp_path / "script.json"
    path.write_text("old")

    save_script(make_script(), path)

    assert load_script(path) == make_script()
    assert [item.name for item in tmp_path.iterdir()] == ["script.json"]


def test_a_failed_save_keeps_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / "script.json"
    path.write_text("old")

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("tracking_visualized.commentary.io.os.replace", fail)

    with pytest.raises(OSError, match="disk full"):
        save_script(make_script(), path)

    assert path.read_text() == "old"
    assert [item.name for item in tmp_path.iterdir()] == ["script.json"]


def test_hand_edited_json_can_be_loaded():
    script = parse_script(
        """
        {
          "version": 1, "match_id": "DFL-MAT-X", "event_id": "E9", "period": "second_half",
          "beats": [
            {"start_seconds": 3, "text": "Edited by hand",
             "highlights": [{"player_id": "p7", "role": "goalkeeper"}]}
          ]
        }
        """
    )

    assert script.period == PeriodType.SECOND_HALF
    assert script.beats[0].start_seconds == 3.0
    assert script.beats[0].highlights == (Highlight("p7", HighlightRole.GOALKEEPER),)


# --- loading errors ----------------------------------------------------------------------


def test_missing_file():
    with pytest.raises(CommentaryScriptError, match="does not exist"):
        load_script("nowhere/script.json")


def test_unreadable_file(tmp_path):
    with pytest.raises(CommentaryScriptError, match="Could not read"):
        load_script(tmp_path)  # a folder


def test_file_that_is_not_text(tmp_path):
    path = tmp_path / "script.json"
    path.write_bytes(b"\xff\xfe\x00bad")

    with pytest.raises(CommentaryScriptError, match="Could not read"):
        load_script(path)


def test_invalid_json_reports_the_position(tmp_path):
    path = tmp_path / "script.json"
    path.write_text('{\n  "version": 1,\n  "beats": [\n')

    with pytest.raises(CommentaryScriptError, match=r"not valid JSON .* line 4") as error:
        load_script(path)

    assert str(path) in str(error.value)


@pytest.mark.parametrize("text", ["[]", '"text"', "3", "null"])
def test_json_that_is_not_an_object(text):
    with pytest.raises(CommentaryScriptError, match="expected a JSON object"):
        parse_script(text)


def test_missing_version():
    data = valid_data()
    del data["version"]

    with pytest.raises(CommentaryScriptError, match="missing 'version'"):
        parse_script(json.dumps(data))


@pytest.mark.parametrize("version", [0, 2, "1", True, 1.5])
def test_unsupported_version(version):
    with pytest.raises(CommentaryScriptError, match="Unsupported .*version .*reads version 1"):
        parse_script(json.dumps(valid_data(version=version)))


def test_field_errors_are_listed_with_their_location():
    data = valid_data(
        beats=[
            {"start_seconds": 1.0, "text": "ok"},
            {
                "start_seconds": -2,
                "text": "",
                "highlights": [{"player_id": "p1", "role": "mascot"}],
            },
        ]
    )

    with pytest.raises(CommentaryScriptError) as error:
        parse_script(json.dumps(data), "'x.json'")

    message = str(error.value)

    assert message.startswith("Invalid commentary script 'x.json':")
    assert "beats[1].start_seconds" in message
    assert "beats[1].text" in message
    assert "beats[1].highlights[0].role" in message


def test_unknown_fields_are_reported_so_typos_are_caught():
    with pytest.raises(CommentaryScriptError, match="beats\\[0\\].pause_secs: Extra inputs"):
        parse_script(
            json.dumps(valid_data(beats=[{"start_seconds": 1, "text": "x", "pause_secs": 1}]))
        )


def test_many_errors_are_cut_off():
    beats = [{"start_seconds": -1, "text": ""} for _ in range(20)]

    with pytest.raises(CommentaryScriptError, match=r"\.\.\. and \d+ more"):
        parse_script(json.dumps(valid_data(beats=beats)))


def test_domain_rules_are_reported_as_script_errors():
    beats = [
        {
            "start_seconds": 1,
            "text": "x",
            "annotations": [{"type": "passing_lane", "from_player_id": "p1", "to_player_id": "p1"}],
        }
    ]

    with pytest.raises(CommentaryScriptError, match="two different players"):
        parse_script(json.dumps(valid_data(beats=beats)))

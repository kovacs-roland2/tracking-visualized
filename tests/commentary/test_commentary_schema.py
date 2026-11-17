import pytest
from pydantic import ValidationError

from tracking_visualized.commentary import (
    CommentaryScriptModel,
    commentary_script_json_schema,
    script_from_domain,
    script_to_domain,
)
from tracking_visualized.domain import (
    COMMENTARY_SCRIPT_VERSION,
    ArrowAnnotation,
    Beat,
    CommentaryScript,
    DistanceLineAnnotation,
    Highlight,
    HighlightRole,
    PassingLaneAnnotation,
    PeriodType,
    PlayerTarget,
    PointTarget,
    ZoneAnnotation,
)


def full_script() -> CommentaryScript:
    return CommentaryScript(
        match_id="DFL-MAT-J03WMX",
        event_id="E1",
        period=PeriodType.SECOND_HALF,
        language="de",
        generator="fake-model",
        beats=(
            Beat(
                start_seconds=610.25,
                text="Das Zuspiel in die Tiefe.",
                pause_seconds=1.5,
                duration_seconds=2.0,
                highlights=(
                    Highlight("p1", HighlightRole.ASSIST),
                    Highlight("p2", HighlightRole.SHOOTER),
                ),
                annotations=(
                    PassingLaneAnnotation("p1", "p2", "Pass"),
                    ArrowAnnotation(PlayerTarget("p2"), PointTarget(105.0, 34.0)),
                    DistanceLineAnnotation(PlayerTarget("p2"), PlayerTarget("gk"), "Distance"),
                    ZoneAnnotation(
                        (PointTarget(88.5, 13.8), PointTarget(105, 13.8), PointTarget(105, 54.2)),
                        "Box",
                    ),
                ),
            ),
            Beat(start_seconds=613.0, text="Und drin!"),
        ),
    )


def test_domain_script_survives_a_round_trip_through_the_wire_model():
    script = full_script()

    assert script_to_domain(script_from_domain(script)) == script


def test_round_trip_through_json_data():
    script = full_script()
    data = script_from_domain(script).model_dump(mode="json")
    parsed = script_to_domain(CommentaryScriptModel.model_validate(data))

    assert parsed == script
    assert data["period"] == "second_half"
    assert data["beats"][0]["highlights"][0] == {"player_id": "p1", "role": "assist"}


def test_annotation_wire_form_has_a_type_and_targets():
    data = script_from_domain(full_script()).model_dump(mode="json")
    lane, arrow, line, zone = data["beats"][0]["annotations"]

    assert lane == {
        "type": "passing_lane",
        "from_player_id": "p1",
        "to_player_id": "p2",
        "label": "Pass",
    }
    assert arrow["type"] == "arrow"
    assert arrow["start"] == {"player_id": "p2"}
    assert arrow["end"] == {"x": 105.0, "y": 34.0}
    assert line["type"] == "distance_line"
    assert zone["type"] == "zone" and len(zone["points"]) == 3


def minimal(**overrides) -> dict:
    data = {
        "version": 1,
        "match_id": "m",
        "event_id": "e",
        "period": "first_half",
        "beats": [{"start_seconds": 1.0, "text": "Hello"}],
    }
    data.update(overrides)

    return data


def test_optional_fields_have_defaults():
    script = script_to_domain(CommentaryScriptModel.model_validate(minimal()))
    beat = script.beats[0]

    assert (script.language, script.generator) == ("en", None)
    assert (beat.pause_seconds, beat.duration_seconds) == (0.0, None)
    assert beat.highlights == () and beat.annotations == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"unknown": 1},
        {"beats": []},
        {"period": "extra_time"},
        {"match_id": ""},
        {"beats": [{"start_seconds": 1.0, "text": "x", "colour": "red"}]},
        {"beats": [{"start_seconds": -1.0, "text": "x"}]},
        {"beats": [{"start_seconds": 1.0, "text": ""}]},
        {"beats": [{"start_seconds": 1.0, "text": "x", "pause_seconds": 11}]},
        {"beats": [{"start_seconds": 1.0, "text": "x", "duration_seconds": 0}]},
        {"beats": [{"start_seconds": float("nan"), "text": "x"}]},
        {"beats": [{"start_seconds": 1.0, "text": "x", "highlights": [{"player_id": "p"}]}]},
        {
            "beats": [
                {
                    "start_seconds": 1.0,
                    "text": "x",
                    "highlights": [{"player_id": "p", "role": "mascot"}],
                }
            ]
        },
        {"beats": [{"start_seconds": 1.0, "text": "x", "annotations": [{"type": "circle"}]}]},
        {
            "beats": [
                {
                    "start_seconds": 1.0,
                    "text": "x",
                    "annotations": [{"type": "zone", "points": [{"x": 0, "y": 0}]}],
                }
            ]
        },
        {
            "beats": [
                {
                    "start_seconds": 1.0,
                    "text": "x",
                    "annotations": [
                        {"type": "arrow", "start": {"x": 1}, "end": {"player_id": "p"}}
                    ],
                }
            ]
        },
        {
            "beats": [
                {
                    "start_seconds": 1.0,
                    "text": "x",
                    "annotations": [
                        {
                            "type": "arrow",
                            "start": {"player_id": "p", "x": 1, "y": 2},
                            "end": {"x": 1, "y": 1},
                        }
                    ],
                }
            ]
        },
    ],
)
def test_invalid_wire_data_is_rejected(overrides):
    with pytest.raises(ValidationError):
        CommentaryScriptModel.model_validate(minimal(**overrides))


def test_domain_rules_apply_after_parsing():
    data = minimal(
        beats=[
            {
                "start_seconds": 1.0,
                "text": "x",
                "annotations": [
                    {"type": "arrow", "start": {"player_id": "p"}, "end": {"player_id": "p"}}
                ],
            }
        ]
    )
    model = CommentaryScriptModel.model_validate(data)

    with pytest.raises(ValueError, match="two different end points"):
        script_to_domain(model)


def test_json_schema_describes_the_script_for_the_llm():
    schema = commentary_script_json_schema()
    definitions = schema["$defs"]

    assert schema["title"] == "CommentaryScriptModel"
    assert set(schema["required"]) == {"version", "match_id", "event_id", "period", "beats"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["beats"]["minItems"] == 1
    assert schema["properties"]["version"]["const"] == COMMENTARY_SCRIPT_VERSION

    beat = definitions["BeatModel"]["properties"]
    assert beat["start_seconds"]["minimum"] == 0
    assert beat["pause_seconds"]["maximum"] == 10.0
    assert "freeze-frame" in beat["pause_seconds"]["description"].lower()

    annotation = beat["annotations"]["items"]
    assert annotation["discriminator"]["propertyName"] == "type"
    assert set(annotation["discriminator"]["mapping"]) == {
        "arrow",
        "passing_lane",
        "distance_line",
        "zone",
    }
    assert set(definitions["HighlightRole"]["enum"]) >= {
        "shooter",
        "assist",
        "defender",
        "goalkeeper",
    }


def test_json_schema_is_plain_json():
    import json

    assert json.loads(json.dumps(commentary_script_json_schema()))

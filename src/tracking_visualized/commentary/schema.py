from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag

from tracking_visualized.domain import (
    COMMENTARY_SCRIPT_VERSION,
    MAX_PAUSE_SECONDS,
    MIN_ZONE_POINTS,
    Annotation,
    AnnotationTarget,
    AnnotationType,
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

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class _StrictModel(BaseModel):
    """Rejects unknown fields, so a typo in a hand-edited script is an error."""

    model_config = ConfigDict(extra="forbid")


class PlayerTargetModel(_StrictModel):
    """An end point that follows a player."""

    player_id: str = Field(min_length=1, description="ID of the player.")


class PointTargetModel(_StrictModel):
    """A fixed point on the pitch."""

    x: FiniteFloat = Field(description="Meters along the pitch length, 0 at the left goal line.")
    y: FiniteFloat = Field(description="Meters along the pitch width, 0 at the bottom touchline.")


def _target_kind(value: Any) -> str:
    """Pick the target form from the keys, so errors name the form that was meant."""

    if isinstance(value, dict):
        return "player" if "player_id" in value else "point"

    return "player" if isinstance(value, PlayerTargetModel) else "point"


TargetModel = Annotated[
    Annotated[PlayerTargetModel, Tag("player")] | Annotated[PointTargetModel, Tag("point")],
    Discriminator(_target_kind),
]


class HighlightModel(_StrictModel):
    """A player to spotlight."""

    player_id: str = Field(min_length=1, description="ID of the player to highlight.")
    role: HighlightRole = Field(description="What the player does in the play.")


class ArrowModel(_StrictModel):
    type: Literal["arrow"]
    start: TargetModel = Field(description="Where the arrow starts: a player or a point.")
    end: TargetModel = Field(description="Where the arrow points to: a player or a point.")
    label: str | None = Field(default=None, description="Optional short caption.")


class PassingLaneModel(_StrictModel):
    type: Literal["passing_lane"]
    from_player_id: str = Field(min_length=1, description="The player passing the ball.")
    to_player_id: str = Field(min_length=1, description="The player the pass is meant for.")
    label: str | None = Field(default=None, description="Optional short caption.")


class DistanceLineModel(_StrictModel):
    type: Literal["distance_line"]
    start: TargetModel = Field(description="One end of the line: a player or a point.")
    end: TargetModel = Field(description="The other end of the line: a player or a point.")
    label: str | None = Field(
        default=None, description="Optional caption; the length in meters is added when drawn."
    )


class ZoneModel(_StrictModel):
    type: Literal["zone"]
    points: list[PointTargetModel] = Field(
        min_length=MIN_ZONE_POINTS,
        description="Corners of the shaded area, in order around its edge.",
    )
    label: str | None = Field(default=None, description="Optional short caption.")


AnnotationModel = Annotated[
    ArrowModel | PassingLaneModel | DistanceLineModel | ZoneModel,
    Field(discriminator="type"),
]


class BeatModel(_StrictModel):
    """One step of the commentary."""

    start_seconds: FiniteFloat = Field(
        ge=0,
        description="When the beat starts, in seconds of match time within the script's period.",
    )
    text: str = Field(min_length=1, description="The subtitle / narration line. Keep it short.")
    pause_seconds: FiniteFloat = Field(
        default=0.0,
        ge=0,
        le=MAX_PAUSE_SECONDS,
        description="Freeze-frame hold at the start of the beat, in seconds. 0 for no pause.",
    )
    duration_seconds: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description=(
            "How long the beat stays active in match time. "
            "Omit it to last until the next beat or the end of the clip."
        ),
    )
    highlights: list[HighlightModel] = Field(
        default_factory=list, description="Players to spotlight during the beat."
    )
    annotations: list[AnnotationModel] = Field(
        default_factory=list, description="Arrows, lanes, distance lines and zones to draw."
    )


class CommentaryScriptModel(_StrictModel):
    """The commentary for one event sequence."""

    version: int = Field(description=f"Script format version; always {COMMENTARY_SCRIPT_VERSION}.")
    match_id: str = Field(min_length=1, description="Full match ID, e.g. DFL-MAT-J03WMX.")
    event_id: str = Field(min_length=1, description="ID of the event the clip is built around.")
    period: PeriodType = Field(description="Match period of the clip; beat times are in it.")
    language: str = Field(default="en", min_length=1, description="Language of the beat texts.")
    generator: str | None = Field(
        default=None, description="Optional note on what produced the script, e.g. a model name."
    )
    beats: list[BeatModel] = Field(
        min_length=1, description="The beats in order of time; at least one."
    )


def _target_to_domain(target: TargetModel) -> AnnotationTarget:
    if isinstance(target, PlayerTargetModel):
        return PlayerTarget(target.player_id)

    return PointTarget(target.x, target.y)


def _target_from_domain(target: AnnotationTarget) -> TargetModel:
    if isinstance(target, PlayerTarget):
        return PlayerTargetModel(player_id=target.player_id)

    return PointTargetModel(x=target.x, y=target.y)


def _annotation_to_domain(annotation: Any) -> Annotation:
    match annotation:
        case ArrowModel():
            return ArrowAnnotation(
                _target_to_domain(annotation.start),
                _target_to_domain(annotation.end),
                annotation.label,
            )
        case PassingLaneModel():
            return PassingLaneAnnotation(
                annotation.from_player_id, annotation.to_player_id, annotation.label
            )
        case DistanceLineModel():
            return DistanceLineAnnotation(
                _target_to_domain(annotation.start),
                _target_to_domain(annotation.end),
                annotation.label,
            )
        case ZoneModel():
            return ZoneAnnotation(
                tuple(PointTarget(point.x, point.y) for point in annotation.points),
                annotation.label,
            )

    raise TypeError(f"Unsupported annotation model: {type(annotation).__name__}")


def _annotation_from_domain(annotation: Annotation) -> Any:
    match annotation:
        case ArrowAnnotation():
            return ArrowModel(
                type=AnnotationType.ARROW.value,
                start=_target_from_domain(annotation.start),
                end=_target_from_domain(annotation.end),
                label=annotation.label,
            )
        case PassingLaneAnnotation():
            return PassingLaneModel(
                type=AnnotationType.PASSING_LANE.value,
                from_player_id=annotation.from_player_id,
                to_player_id=annotation.to_player_id,
                label=annotation.label,
            )
        case DistanceLineAnnotation():
            return DistanceLineModel(
                type=AnnotationType.DISTANCE_LINE.value,
                start=_target_from_domain(annotation.start),
                end=_target_from_domain(annotation.end),
                label=annotation.label,
            )
        case ZoneAnnotation():
            return ZoneModel(
                type=AnnotationType.ZONE.value,
                points=[PointTargetModel(x=point.x, y=point.y) for point in annotation.points],
                label=annotation.label,
            )

    raise TypeError(f"Unsupported annotation: {type(annotation).__name__}")


def script_to_domain(model: CommentaryScriptModel) -> CommentaryScript:
    """Convert a parsed script to the domain model.

    Raises:
        ValueError: If the domain model rejects the content, e.g. an arrow whose two
            ends are the same, or the same player highlighted twice in a beat.
    """

    beats = tuple(
        Beat(
            start_seconds=beat.start_seconds,
            text=beat.text,
            pause_seconds=beat.pause_seconds,
            duration_seconds=beat.duration_seconds,
            highlights=tuple(Highlight(item.player_id, item.role) for item in beat.highlights),
            annotations=tuple(_annotation_to_domain(item) for item in beat.annotations),
        )
        for beat in model.beats
    )

    return CommentaryScript(
        match_id=model.match_id,
        event_id=model.event_id,
        period=model.period,
        beats=beats,
        language=model.language,
        generator=model.generator,
        version=model.version,
    )


def script_from_domain(script: CommentaryScript) -> CommentaryScriptModel:
    """Convert a domain script to its JSON form."""

    return CommentaryScriptModel(
        version=script.version,
        match_id=script.match_id,
        event_id=script.event_id,
        period=script.period,
        language=script.language,
        generator=script.generator,
        beats=[
            BeatModel(
                start_seconds=beat.start_seconds,
                text=beat.text,
                pause_seconds=beat.pause_seconds,
                duration_seconds=beat.duration_seconds,
                highlights=[
                    HighlightModel(player_id=item.player_id, role=item.role)
                    for item in beat.highlights
                ],
                annotations=[_annotation_from_domain(item) for item in beat.annotations],
            )
            for beat in script.beats
        ],
    )


def commentary_script_json_schema() -> dict[str, Any]:
    """JSON schema of a commentary script, e.g. for structured LLM output."""

    return CommentaryScriptModel.model_json_schema()


__all__ = [
    "ArrowModel",
    "BeatModel",
    "CommentaryScriptModel",
    "DistanceLineModel",
    "HighlightModel",
    "PassingLaneModel",
    "PlayerTargetModel",
    "PointTargetModel",
    "ZoneModel",
    "commentary_script_json_schema",
    "script_from_domain",
    "script_to_domain",
]

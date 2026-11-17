import pytest

from tracking_visualized.domain import (
    COMMENTARY_SCRIPT_VERSION,
    MAX_PAUSE_SECONDS,
    AnnotationType,
    ArrowAnnotation,
    Beat,
    CommentaryScript,
    DistanceLineAnnotation,
    Highlight,
    HighlightRole,
    MatchTime,
    PassingLaneAnnotation,
    PeriodType,
    PlayerTarget,
    PointTarget,
    ZoneAnnotation,
)

P1 = PlayerTarget("p1")
P2 = PlayerTarget("p2")


def make_script(*beats: Beat, **kwargs) -> CommentaryScript:
    return CommentaryScript(
        match_id=kwargs.pop("match_id", "DFL-MAT-X"),
        event_id=kwargs.pop("event_id", "E1"),
        period=kwargs.pop("period", PeriodType.FIRST_HALF),
        beats=beats or (Beat(1.0, "Kick-off"),),
        **kwargs,
    )


# --- targets and highlights --------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "   "])
def test_player_target_needs_an_id(value):
    with pytest.raises(ValueError, match="Player ID cannot be empty"):
        PlayerTarget(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_point_target_must_be_finite(value):
    with pytest.raises(ValueError, match="must be finite"):
        PointTarget(value, 1.0)

    with pytest.raises(ValueError, match="must be finite"):
        PointTarget(1.0, value)


def test_highlight_needs_a_player_id():
    with pytest.raises(ValueError, match="Player ID cannot be empty"):
        Highlight(" ", HighlightRole.SHOOTER)


def test_highlight_roles_cover_the_ticket_examples():
    assert {"shooter", "assist", "defender", "goalkeeper"} <= {role.value for role in HighlightRole}


# --- annotations -------------------------------------------------------------------------


def test_annotations_know_their_type():
    assert ArrowAnnotation(P1, PointTarget(1, 2)).type == AnnotationType.ARROW
    assert PassingLaneAnnotation("a", "b").type == AnnotationType.PASSING_LANE
    assert DistanceLineAnnotation(P1, P2).type == AnnotationType.DISTANCE_LINE
    assert ZoneAnnotation((PointTarget(0, 0), PointTarget(1, 0), PointTarget(1, 1))).type == (
        AnnotationType.ZONE
    )


def test_arrow_and_distance_line_may_mix_players_and_points():
    arrow = ArrowAnnotation(P1, PointTarget(105.0, 34.0), label="Run")
    line = DistanceLineAnnotation(PointTarget(0, 0), P2)

    assert arrow.end == PointTarget(105.0, 34.0)
    assert line.start == PointTarget(0, 0)


@pytest.mark.parametrize("annotation", [ArrowAnnotation, DistanceLineAnnotation])
@pytest.mark.parametrize("target", [P1, PointTarget(3.0, 4.0)])
def test_two_end_annotations_need_different_ends(annotation, target):
    with pytest.raises(ValueError, match="two different end points"):
        annotation(target, target)


def test_passing_lane_needs_two_different_players():
    with pytest.raises(ValueError, match="two different players"):
        PassingLaneAnnotation("p1", "p1")

    with pytest.raises(ValueError, match="Player ID cannot be empty"):
        PassingLaneAnnotation("", "p1")


def test_zone_needs_three_distinct_points():
    corners = (PointTarget(0, 0), PointTarget(1, 0), PointTarget(1, 1))

    assert ZoneAnnotation(corners).points == corners

    with pytest.raises(ValueError, match="at least 3 points"):
        ZoneAnnotation(corners[:2])

    with pytest.raises(ValueError, match="repeat a point"):
        ZoneAnnotation((*corners, corners[0]))


# --- beats -------------------------------------------------------------------------------


def test_beat_defaults():
    beat = Beat(12.5, "Great pass")

    assert (beat.pause_seconds, beat.duration_seconds) == (0.0, None)
    assert beat.highlights == () and beat.annotations == ()
    assert beat.end_seconds is None
    assert not beat.has_pause


def test_beat_end_and_pause():
    beat = Beat(10.0, "Shot", pause_seconds=1.5, duration_seconds=2.5)

    assert beat.end_seconds == 12.5
    assert beat.has_pause


@pytest.mark.parametrize("seconds", [-0.1, float("nan"), float("inf")])
def test_beat_start_must_be_a_non_negative_number(seconds):
    with pytest.raises(ValueError, match="Beat start"):
        Beat(seconds, "text")


@pytest.mark.parametrize("text", ["", "   \n"])
def test_beat_text_cannot_be_blank(text):
    with pytest.raises(ValueError, match="Beat text cannot be empty"):
        Beat(1.0, text)


def test_pause_must_be_non_negative_and_bounded():
    assert Beat(1.0, "x", pause_seconds=MAX_PAUSE_SECONDS).pause_seconds == MAX_PAUSE_SECONDS

    with pytest.raises(ValueError, match="Beat pause"):
        Beat(1.0, "x", pause_seconds=-1.0)

    with pytest.raises(ValueError, match="at most 10 seconds"):
        Beat(1.0, "x", pause_seconds=MAX_PAUSE_SECONDS + 0.1)


@pytest.mark.parametrize("duration", [0.0, -1.0, float("nan")])
def test_beat_duration_must_be_positive(duration):
    with pytest.raises(ValueError, match="Beat duration"):
        Beat(1.0, "x", duration_seconds=duration)


def test_beat_cannot_highlight_a_player_twice():
    highlights = (
        Highlight("p1", HighlightRole.SHOOTER),
        Highlight("p2", HighlightRole.ASSIST),
        Highlight("p1", HighlightRole.ATTACKER),
    )

    with pytest.raises(ValueError, match="same player twice: p1"):
        Beat(1.0, "x", highlights=highlights)


# --- script ------------------------------------------------------------------------------


def test_script_defaults():
    script = make_script()

    assert script.version == COMMENTARY_SCRIPT_VERSION == 1
    assert script.language == "en"
    assert script.generator is None


def test_script_needs_at_least_one_beat():
    with pytest.raises(ValueError, match="at least one beat"):
        CommentaryScript("m", "e", PeriodType.FIRST_HALF, ())


@pytest.mark.parametrize("field", ["match_id", "event_id", "language"])
def test_script_text_fields_cannot_be_blank(field):
    with pytest.raises(ValueError, match="cannot be empty"):
        make_script(**{field: " "})


def test_script_rejects_unknown_versions():
    with pytest.raises(ValueError, match="Unsupported script version 2"):
        make_script(version=2)


def test_script_start_time_uses_the_script_period():
    script = make_script(Beat(7.5, "x"), period=PeriodType.SECOND_HALF)

    assert script.start_time(script.beats[0]) == MatchTime(PeriodType.SECOND_HALF, 7.5)


def test_total_pause_adds_up_all_holds():
    script = make_script(
        Beat(1.0, "a", pause_seconds=1.0),
        Beat(2.0, "b"),
        Beat(3.0, "c", pause_seconds=2.5),
    )

    assert script.total_pause_seconds == 3.5


def test_models_are_immutable():
    beat = Beat(1.0, "x")

    with pytest.raises(AttributeError):
        beat.text = "changed"

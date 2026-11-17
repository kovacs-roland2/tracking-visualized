import pytest

from tracking_visualized.domain import (
    ArrowAnnotation,
    Beat,
    CommentaryScript,
    CoordinateSystem,
    DistanceLineAnnotation,
    Event,
    EventType,
    Frame,
    Highlight,
    HighlightRole,
    Match,
    MatchMetadata,
    MatchTime,
    PassingLaneAnnotation,
    PeriodType,
    Player,
    PlayerPosition,
    PlayerTarget,
    PointTarget,
    ShotOutcome,
    Team,
    TeamSide,
    ZoneAnnotation,
)
from tracking_visualized.processing import (
    EventSequence,
    TimeRangeSequence,
    select_event_sequence,
)
from tracking_visualized.validation import (
    CommentaryScriptValidationError,
    ValidationSeverity,
    validate_commentary_script,
    validate_commentary_script_or_raise,
)

MATCH_ID = "DFL-MAT-TEST"
EVENT_ID = "goal-1"

HOME = Team("home", "Home FC", TeamSide.HOME)
AWAY = Team("away", "Away FC", TeamSide.AWAY)
PLAYERS = (
    Player("h9", "home", "Nine", 9),
    Player("h10", "home", "Ten", 10),
    Player("a1", "away", "Keeper", 1),
    Player("bench", "home", "Substitute", 20),
)

FPS = 10


def make_match() -> Match:
    # A 20 s clip of the first half: event at 10 s, frames from 0 s to 20 s.
    frames = tuple(
        Frame(
            frame_index=i,
            time=MatchTime(PeriodType.FIRST_HALF, i / FPS),
            player_positions=(
                PlayerPosition("h9", 50.0 + i * 0.1, 30.0),
                PlayerPosition("h10", 40.0, 34.0),
                PlayerPosition("a1", 100.0, None),
            ),
            ball_position=None,
        )
        for i in range(0, 201)
    )
    event = Event(
        event_id=EVENT_ID,
        event_type=EventType.SHOT,
        time=MatchTime(PeriodType.FIRST_HALF, 10.0),
        team_id="home",
        player_id="h9",
        x=90.0,
        y=32.0,
        frame_index=100,
        shot_outcome=ShotOutcome.GOAL,
    )

    return Match(
        metadata=MatchMetadata(match_id=MATCH_ID, competition="Liga", season="2026"),
        coordinate_system=CoordinateSystem(pitch_length=105.0, pitch_width=68.0),
        periods=(),
        teams=(HOME, AWAY),
        players=PLAYERS,
        frames=frames,
        events=(event,),
    )


@pytest.fixture
def match() -> Match:
    return make_match()


@pytest.fixture
def sequence(match) -> EventSequence:
    return select_event_sequence(match, EVENT_ID, pre_event_seconds=8.0, post_event_seconds=5.0)


def make_script(*beats: Beat, **kwargs) -> CommentaryScript:
    return CommentaryScript(
        match_id=kwargs.pop("match_id", MATCH_ID),
        event_id=kwargs.pop("event_id", EVENT_ID),
        period=kwargs.pop("period", PeriodType.FIRST_HALF),
        beats=beats,
        **kwargs,
    )


def codes(report, severity=ValidationSeverity.ERROR) -> list[str]:
    return [issue.code for issue in report.issues if issue.severity == severity]


def valid_script() -> CommentaryScript:
    return make_script(
        Beat(
            3.0,
            "Build-up",
            duration_seconds=2.0,
            highlights=(Highlight("h10", HighlightRole.PASSER),),
            annotations=(
                PassingLaneAnnotation("h10", "h9"),
                ArrowAnnotation(PlayerTarget("h9"), PointTarget(105.0, 34.0)),
                DistanceLineAnnotation(PlayerTarget("h9"), PlayerTarget("h10")),
                ZoneAnnotation(
                    (PointTarget(88.5, 13.84), PointTarget(105, 13.84), PointTarget(105, 54.16))
                ),
            ),
        ),
        Beat(5.0, "Pause here", pause_seconds=2.0),
        Beat(10.0, "Shot", highlights=(Highlight("h9", HighlightRole.SHOOTER),)),
    )


# --- valid scripts -----------------------------------------------------------------------


def test_a_valid_script_has_no_issues(match, sequence):
    report = validate_commentary_script(valid_script(), match, sequence)

    assert report.is_valid
    assert report.issues == ()


def test_the_or_raise_variant_returns_the_report(match, sequence):
    assert validate_commentary_script_or_raise(valid_script(), match, sequence).is_valid


def test_beats_exactly_at_the_clip_edges_are_fine(match, sequence):
    script = make_script(
        Beat(2.0, "First frame"), Beat(14.9, "Until the end", duration_seconds=0.1)
    )

    assert validate_commentary_script(script, match, sequence).is_valid


def test_pauses_do_not_count_as_match_time(match, sequence):
    # A 10 s pause on beat 1 does not overlap beat 2, which starts 1 s later in match time.
    script = make_script(
        Beat(3.0, "Long hold", pause_seconds=10.0, duration_seconds=1.0), Beat(4.0, "Next")
    )

    assert validate_commentary_script(script, match, sequence).is_valid


# --- identity ----------------------------------------------------------------------------


def test_other_match_event_and_period_are_errors(match, sequence):
    script = make_script(
        Beat(3.0, "x"), match_id="DFL-MAT-OTHER", event_id="other", period=PeriodType.SECOND_HALF
    )

    report = validate_commentary_script(script, match, sequence)

    assert codes(report) == [
        "commentary_match_mismatch",
        "commentary_event_mismatch",
        "commentary_period_mismatch",
    ]
    assert "'DFL-MAT-OTHER'" in report.issues[0].message


def test_a_time_range_clip_is_rejected(match):
    frames = match.frames[:30]
    sequence = TimeRangeSequence(
        frames=tuple(frames),
        start_time=frames[0].time,
        end_time=frames[-1].time,
    )

    report = validate_commentary_script(make_script(Beat(1.0, "x")), match, sequence)

    assert codes(report) == ["commentary_sequence_not_event"]


# --- times -------------------------------------------------------------------------------


def test_beat_before_the_clip_starts(match, sequence):
    report = validate_commentary_script(make_script(Beat(1.0, "Too early")), match, sequence)

    assert codes(report) == ["commentary_beat_outside_clip"]
    assert "Beat 1 (at 1 s) starts outside the clip" in report.issues[0].message
    assert "2.00 s to 15.00 s" in report.issues[0].message


def test_beat_after_the_clip_ends(match, sequence):
    report = validate_commentary_script(make_script(Beat(15.5, "Too late")), match, sequence)

    assert codes(report) == ["commentary_beat_outside_clip"]


def test_beat_that_lasts_past_the_clip_end(match, sequence):
    script = make_script(Beat(14.0, "Runs out", duration_seconds=2.0))

    report = validate_commentary_script(script, match, sequence)

    assert codes(report) == ["commentary_beat_outside_clip"]
    assert "lasts until 16.00 s" in report.issues[0].message


def test_beats_must_be_sorted(match, sequence):
    script = make_script(Beat(8.0, "b"), Beat(5.0, "a"), Beat(9.0, "c"))

    report = validate_commentary_script(script, match, sequence)

    assert codes(report) == ["commentary_beats_unsorted"]
    assert "Beat 2 (at 5 s) does not start after beat 1 (at 8 s)" in report.issues[0].message


def test_beats_cannot_start_at_the_same_time(match, sequence):
    script = make_script(Beat(5.0, "a"), Beat(5.0, "b"))

    assert codes(validate_commentary_script(script, match, sequence)) == [
        "commentary_beats_unsorted"
    ]


def test_a_duration_running_into_the_next_beat_is_an_overlap(match, sequence):
    script = make_script(Beat(5.0, "a", duration_seconds=3.0), Beat(7.5, "b"))

    report = validate_commentary_script(script, match, sequence)

    assert codes(report) == ["commentary_beats_overlap"]
    assert "lasts until 8.00 s, but beat 2 starts at 7.5 s" in report.issues[0].message


def test_a_duration_ending_exactly_at_the_next_beat_is_fine(match, sequence):
    script = make_script(Beat(5.0, "a", duration_seconds=2.5), Beat(7.5, "b"))

    assert validate_commentary_script(script, match, sequence).is_valid


def test_beats_without_a_duration_never_overlap(match, sequence):
    script = make_script(Beat(5.0, "a"), Beat(5.01, "b"))

    assert validate_commentary_script(script, match, sequence).is_valid


# --- players -----------------------------------------------------------------------------


def test_unknown_players_are_found_in_highlights_and_annotations(match, sequence):
    script = make_script(
        Beat(
            3.0,
            "x",
            highlights=(Highlight("ghost1", HighlightRole.OTHER),),
            annotations=(
                PassingLaneAnnotation("h9", "ghost2"),
                ArrowAnnotation(PlayerTarget("ghost3"), PointTarget(1, 1)),
                DistanceLineAnnotation(PointTarget(2, 2), PlayerTarget("ghost4")),
            ),
        )
    )

    report = validate_commentary_script(script, match, sequence)

    assert codes(report) == ["commentary_unknown_player"] * 4
    assert [issue.message.split("'")[1] for issue in report.issues] == [
        "ghost1",
        "ghost2",
        "ghost3",
        "ghost4",
    ]


def test_an_unknown_player_is_reported_once_per_beat(match, sequence):
    script = make_script(
        Beat(
            3.0,
            "x",
            highlights=(Highlight("ghost", HighlightRole.OTHER),),
            annotations=(PassingLaneAnnotation("ghost", "h9"),),
        )
    )

    assert codes(validate_commentary_script(script, match, sequence)) == [
        "commentary_unknown_player"
    ]


def test_a_player_without_tracking_in_the_clip_is_only_a_warning(match, sequence):
    script = make_script(Beat(3.0, "x", highlights=(Highlight("bench", HighlightRole.OTHER),)))

    report = validate_commentary_script(script, match, sequence)

    assert report.is_valid
    assert codes(report, ValidationSeverity.WARNING) == ["commentary_player_not_in_clip"]
    assert validate_commentary_script_or_raise(script, match, sequence).warnings


def test_a_player_with_a_partial_position_counts_as_not_tracked(match, sequence):
    # "a1" has x but no y in every frame, so there is no observed position.
    script = make_script(Beat(3.0, "x", highlights=(Highlight("a1", HighlightRole.GOALKEEPER),)))

    report = validate_commentary_script(script, match, sequence)

    assert codes(report, ValidationSeverity.WARNING) == ["commentary_player_not_in_clip"]


# --- pitch points ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "point", [(-0.1, 10), (105.1, 10), (50, -1), (50, 68.5)], ids=["left", "right", "bottom", "top"]
)
def test_points_outside_the_pitch(match, sequence, point):
    script = make_script(
        Beat(3.0, "x", annotations=(ArrowAnnotation(PlayerTarget("h9"), PointTarget(*point)),))
    )

    report = validate_commentary_script(script, match, sequence)

    assert codes(report) == ["commentary_point_outside_pitch"]
    assert "outside the 105 x 68 m pitch" in report.issues[0].message


def test_points_on_the_pitch_edge_are_fine(match, sequence):
    zone = ZoneAnnotation((PointTarget(0, 0), PointTarget(105, 0), PointTarget(105, 68)))

    assert validate_commentary_script(
        make_script(Beat(3.0, "x", annotations=(zone,))), match, sequence
    ).is_valid


def test_zone_corners_are_checked_too(match, sequence):
    zone = ZoneAnnotation((PointTarget(0, 0), PointTarget(50, 0), PointTarget(50, 80)))

    report = validate_commentary_script(
        make_script(Beat(3.0, "x", annotations=(zone,))), match, sequence
    )

    assert codes(report) == ["commentary_point_outside_pitch"]


# --- reporting ---------------------------------------------------------------------------


def test_all_problems_are_reported_together(match, sequence):
    script = make_script(
        Beat(20.0, "late", highlights=(Highlight("ghost", HighlightRole.OTHER),)),
        Beat(1.0, "early and unsorted"),
        match_id="other",
    )

    report = validate_commentary_script(script, match, sequence)

    assert set(codes(report)) == {
        "commentary_match_mismatch",
        "commentary_beat_outside_clip",
        "commentary_beats_unsorted",
        "commentary_unknown_player",
    }


def test_or_raise_lists_every_problem_and_carries_the_report(match, sequence):
    script = make_script(Beat(1.0, "early"), Beat(0.5, "earlier"))

    with pytest.raises(CommentaryScriptValidationError) as error:
        validate_commentary_script_or_raise(script, match, sequence)

    assert not error.value.report.is_valid
    message = str(error.value)

    assert "commentary_beat_outside_clip" in message
    assert "commentary_beats_unsorted" in message
    assert message.startswith("Match validation found 3 error(s)")


def test_the_report_is_truncated_at_max_issues(match, sequence):
    beats = tuple(Beat(0.1 * i, f"beat {i}") for i in range(1, 11))  # all before the clip

    report = validate_commentary_script(make_script(*beats), match, sequence, max_issues=3)

    assert len(report.issues) == 3
    assert report.truncated


def test_max_issues_must_be_positive(match, sequence):
    with pytest.raises(ValueError, match="max_issues"):
        validate_commentary_script(valid_script(), match, sequence, max_issues=0)

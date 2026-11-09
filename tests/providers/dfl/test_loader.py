import pytest

from tracking_visualized.domain import EventType, PeriodType, ShotOutcome, TeamSide
from tracking_visualized.processing import select_event_sequence
from tracking_visualized.providers.dfl import (
    DflDatasetError,
    DflEventNotFoundError,
    DflMatchFiles,
    list_shots,
    load_event_match,
    normalize_match_id,
)

MATCH_ID = "J03TEST"
GOAL_ID = "E-GOAL"
WIDE_ID = "E-WIDE"


@pytest.fixture
def files(dfl_data_dir) -> DflMatchFiles:
    return DflMatchFiles.discover(MATCH_ID, dfl_data_dir)


@pytest.mark.parametrize("value", ["J03TEST", "DFL-MAT-J03TEST", "  J03TEST  "])
def test_match_id_is_normalized_to_the_folder_name(value):
    assert normalize_match_id(value) == "J03TEST"


@pytest.mark.parametrize("value", ["", "   ", "../secret", "a/b", "J03 TEST", "DFL-MAT-"])
def test_invalid_match_ids_are_rejected(value):
    with pytest.raises(DflDatasetError, match="not a valid match ID"):
        normalize_match_id(value)


def test_discover_finds_the_three_files(dfl_data_dir):
    files = DflMatchFiles.discover("DFL-MAT-J03TEST", dfl_data_dir)

    assert files.match_id == "J03TEST"
    assert "matchinformation" in files.metadata.name
    assert "events_raw" in files.events.name
    assert "positions_raw_observed" in files.tracking.name


def test_discover_reports_a_missing_match_folder(dfl_data_dir):
    with pytest.raises(DflDatasetError, match="No data found for match 'J00NONE'") as error:
        DflMatchFiles.discover("J00NONE", dfl_data_dir)

    assert "README" in str(error.value)


def test_discover_reports_a_missing_file(dfl_data_dir):
    next((dfl_data_dir / MATCH_ID).glob("*events_raw*")).unlink()

    with pytest.raises(DflDatasetError, match="No event file"):
        DflMatchFiles.discover(MATCH_ID, dfl_data_dir)


def test_discover_reports_ambiguous_files(dfl_data_dir):
    match_dir = dfl_data_dir / MATCH_ID
    original = next(match_dir.glob("*positions_raw_observed*"))
    (match_dir / "copy_positions_raw_observed.xml").write_text(original.read_text())

    with pytest.raises(DflDatasetError, match="several tracking files"):
        DflMatchFiles.discover(MATCH_ID, dfl_data_dir)


def test_discover_reports_an_empty_file(dfl_data_dir):
    next((dfl_data_dir / MATCH_ID).glob("*matchinformation*")).write_text("")

    with pytest.raises(DflDatasetError, match="is empty"):
        DflMatchFiles.discover(MATCH_ID, dfl_data_dir)


def test_list_shots_is_chronological_with_team_names(files):
    goal, wide = list_shots(files)

    assert (goal.event_id, goal.period, goal.period_seconds) == (
        GOAL_ID,
        PeriodType.FIRST_HALF,
        8.0,
    )
    assert goal.is_goal
    assert (goal.team_name, goal.shirt_number) == ("Home FC", 9)
    assert (wide.event_id, wide.period) == (WIDE_ID, PeriodType.SECOND_HALF)
    assert wide.outcome == ShotOutcome.WIDE
    assert not wide.is_goal


def test_loaded_match_holds_the_event_and_only_the_window(files):
    match = load_event_match(files, GOAL_ID, pre_event_seconds=2, post_event_seconds=1)

    # 3 s at 25 fps, both ends included.
    assert len(match.frames) == 76
    assert match.frames[0].time.seconds == pytest.approx(6.0)
    assert match.frames[-1].time.seconds == pytest.approx(9.0)

    (event,) = match.events

    assert event.event_id == GOAL_ID
    assert event.event_type == EventType.SHOT
    assert event.is_goal
    assert event.time.seconds == pytest.approx(8.0)
    assert (event.x, event.y) == (95.0, 32.0)
    assert event.xg == pytest.approx(0.4)
    assert event.frame_index in {frame.frame_index for frame in match.frames}


def test_loaded_match_has_teams_players_and_metadata(files):
    match = load_event_match(files, GOAL_ID, pre_event_seconds=1, post_event_seconds=1)

    assert match.metadata.match_id == "DFL-MAT-J03TEST"
    assert (match.metadata.competition, match.metadata.season) == ("Testliga", "2022/2023")
    assert match.coordinate_system.pitch_length == 105.0
    assert [(team.name, team.side) for team in match.teams] == [
        ("Home FC", TeamSide.HOME),
        ("Away United", TeamSide.AWAY),
    ]
    assert {(player.team_id, player.shirt_number) for player in match.players} == {
        ("DFL-CLU-HOME", 9),
        ("DFL-CLU-AWAY", 10),
    }


def test_frames_hold_normalized_positions_and_ball(files):
    match = load_event_match(files, GOAL_ID, pre_event_seconds=1, post_event_seconds=0)
    first = match.frames[0]
    positions = {position.player_id: position for position in first.player_positions}

    # Frame 175 of the half: home x = -10 + 175 * 0.05; tracking is centred on the pitch.
    home = positions["DFL-OBJ-HOME-1"]
    away = positions["DFL-OBJ-AWAY-1"]

    assert home.x == pytest.approx(-10 + 175 * 0.05 + 52.5)
    assert home.y == pytest.approx(4.0 + 34.0)
    assert (away.x, away.y) == pytest.approx((12.0 + 52.5, -3.0 + 34.0))
    assert first.ball_position.x == pytest.approx(175 * 0.1 + 52.5)
    assert first.ball_position.z == pytest.approx(0.2)
    assert first.ball_position.is_in_play is True


def test_frame_indices_follow_the_match_timeline(files):
    match = load_event_match(files, GOAL_ID, pre_event_seconds=1, post_event_seconds=1)
    indices = [frame.frame_index for frame in match.frames]

    assert indices == list(range(indices[0], indices[0] + len(indices)))
    assert indices[0] == 175


def test_second_half_events_continue_the_frame_numbering(files):
    match = load_event_match(files, WIDE_ID, pre_event_seconds=1, post_event_seconds=1)

    assert match.events[0].time.period == PeriodType.SECOND_HALF
    assert match.events[0].time.seconds == pytest.approx(4.0)
    # The first half has 401 frames, so the second half starts at frame index 401.
    assert match.frames[0].frame_index == 401 + 75
    assert all(frame.time.period == PeriodType.SECOND_HALF for frame in match.frames)


def test_window_is_clipped_at_the_start_of_the_period(files):
    match = load_event_match(files, GOAL_ID, pre_event_seconds=60, post_event_seconds=0)

    assert match.frames[0].time.seconds == 0.0
    assert match.frames[-1].time.seconds == pytest.approx(8.0)


def test_loaded_match_works_with_sequence_selection(files):
    match = load_event_match(files, GOAL_ID, pre_event_seconds=2, post_event_seconds=1)
    sequence = select_event_sequence(match, GOAL_ID, pre_event_seconds=2, post_event_seconds=1)

    assert len(sequence.frames) == 76
    assert sequence.event_frame is not None
    assert not sequence.is_truncated


def test_loaded_match_knows_the_length_of_the_event_period(files):
    match = load_event_match(files, GOAL_ID, pre_event_seconds=1, post_event_seconds=1)

    assert len(match.periods) == 1
    assert match.periods[0].period == PeriodType.FIRST_HALF
    assert match.periods[0].duration_seconds == pytest.approx(16.0)


def test_off_grid_window_is_not_reported_as_truncated(files):
    match = load_event_match(files, GOAL_ID, pre_event_seconds=2.33, post_event_seconds=2.33)
    sequence = select_event_sequence(
        match, GOAL_ID, pre_event_seconds=2.33, post_event_seconds=2.33
    )

    assert not sequence.is_truncated


def test_window_past_the_end_of_the_period_is_truncated(files):
    match = load_event_match(files, WIDE_ID, pre_event_seconds=1, post_event_seconds=10)
    sequence = select_event_sequence(match, WIDE_ID, pre_event_seconds=1, post_event_seconds=10)

    assert sequence.is_truncated
    assert sequence.effective_post_seconds == pytest.approx(4.0)


def test_stage_messages_are_reported_in_order(files):
    stages: list[str] = []

    load_event_match(
        files, GOAL_ID, pre_event_seconds=1, post_event_seconds=1, on_stage=stages.append
    )

    assert len(stages) == 3
    assert "events" in stages[0]
    assert "(1/2)" in stages[1]
    assert "51 tracking frames" in stages[2] and "(2/2)" in stages[2]


def test_unknown_event_lists_available_ids(files):
    with pytest.raises(DflEventNotFoundError, match="'NOPE'") as error:
        load_event_match(files, "NOPE", pre_event_seconds=1, post_event_seconds=1)

    message = str(error.value)

    assert GOAL_ID in message and WIDE_ID in message
    assert "--list-events" in message


def test_event_without_tracking_in_its_period_is_reported(dfl_data_dir, files):
    tracking = files.tracking
    text = tracking.read_text()
    # Keep only the first half, so the second-half shot has no tracking.
    head, _, _ = text.partition('<FrameSet GameSection="SecondHalf"')
    tracking.write_text(head + "</Positions>\n")

    with pytest.raises(DflDatasetError, match="second_half"):
        load_event_match(files, WIDE_ID, pre_event_seconds=1, post_event_seconds=1)

from pathlib import Path

import pytest

from tracking_visualized.providers.dfl import DflEventError, MatchPeriod, ShotOutcome
from tracking_visualized.providers.dfl.events import load_shot_events

MATCH_METADATA_XML = """\
<PutDataRequest>
    <MatchInformation>
        <General
            HomeTeamId="DFL-CLU-HOME"
            GuestTeamId="DFL-CLU-AWAY"
        />
        <Teams>
            <Team
                TeamId="DFL-CLU-HOME"
                TeamName="Home FC"
            >
                <Players>
                    <Player
                        PersonId="DFL-OBJ-HOME-1"
                        ShirtNumber="7"
                    />
                </Players>
            </Team>

            <Team
                TeamId="DFL-CLU-AWAY"
                TeamName="Away FC"
            >
                <Players>
                    <Player
                        PersonId="DFL-OBJ-AWAY-1"
                        ShirtNumber="10"
                    />
                </Players>
            </Team>
        </Teams>
    </MatchInformation>
</PutDataRequest>
"""


EVENTS_XML = """\
<PutDataRequest>
    <Event
        MatchId="DFL-MAT-J03TEST"
        EventId="1"
        EventTime="2023-05-27T15:30:00.000+02:00"
        X-Position="80.0"
        Y-Position="30.0"
    >
        <KickOff GameSection="firstHalf" />
    </Event>

    <Event
        MatchId="DFL-MAT-J03TEST"
        EventId="2"
        EventTime="2023-05-27T15:35:00.000+02:00"
        CalculatedFrame="7500"
        CalculatedTimestamp="2023-05-27T15:34:59.960+02:00"
        X-Position="95.0"
        Y-Position="32.0"
    >
        <ShotAtGoal
            Team="DFL-CLU-HOME"
            Player="DFL-OBJ-HOME-1"
            xG="0.25"
        >
            <SuccessfulShot CurrentResult="1:0" />
        </ShotAtGoal>
    </Event>

    <Event
        MatchId="DFL-MAT-J03TEST"
        EventId="3"
        EventTime="2023-05-27T16:17:00.000+02:00"
    >
        <FinalWhistle GameSection="firstHalf" />
    </Event>

    <Event
        MatchId="DFL-MAT-J03TEST"
        EventId="4"
        EventTime="2023-05-27T16:35:00.000+02:00"
    >
        <KickOff GameSection="secondHalf" />
    </Event>

    <Event
        MatchId="DFL-MAT-J03TEST"
        EventId="5"
        EventTime="2023-05-27T16:40:00.000+02:00"
        X-Position="90.0"
        Y-Position="40.0"
    >
        <ShotAtGoal
            Team="DFL-CLU-AWAY"
            Player="DFL-OBJ-AWAY-1"
            xG="0.08"
        >
            <ShotWide />
        </ShotAtGoal>
    </Event>

    <Event
        MatchId="DFL-MAT-J03TEST"
        EventId="6"
        EventTime="2023-05-27T17:25:00.000+02:00"
    >
        <FinalWhistle GameSection="secondHalf" />
    </Event>
</PutDataRequest>
"""


def write_event_files(
    tmp_path: Path,
    xml: str = EVENTS_XML,
) -> tuple[Path, Path]:
    events_path = tmp_path / "events.xml"
    metadata_path = tmp_path / "metadata.xml"

    events_path.write_text(xml, encoding="utf-8")
    metadata_path.write_text(MATCH_METADATA_XML, encoding="utf-8")

    return events_path, metadata_path


def test_parses_goal(
    tmp_path: Path,
):
    events_path, metadata_path = write_event_files(tmp_path)

    shots = load_shot_events(events_path, metadata_path)

    goal = shots[0]

    assert goal.event_id == "2"
    assert goal.player_id == "DFL-OBJ-HOME-1"
    assert goal.shirt_number == 7
    assert goal.x == 95.0
    assert goal.y == 32.0
    assert goal.xg == 0.25
    assert goal.outcome == ShotOutcome.GOAL
    assert goal.is_goal is True


def test_parses_wide_shot(
    tmp_path: Path,
):
    events_path, metadata_path = write_event_files(tmp_path)

    shots = load_shot_events(events_path, metadata_path)

    shot = shots[1]

    assert shot.outcome == ShotOutcome.WIDE
    assert shot.is_goal is False


def test_calculates_period_seconds(
    tmp_path: Path,
):
    events_path, metadata_path = write_event_files(tmp_path)

    shots = load_shot_events(events_path, metadata_path)

    assert shots[0].period == MatchPeriod.FIRST_HALF
    assert shots[0].period_seconds == 300.0
    assert shots[1].period == MatchPeriod.SECOND_HALF
    assert shots[1].period_seconds == 300.0


def test_preserves_calculated_tracking_data(
    tmp_path: Path,
):
    events_path, metadata_path = write_event_files(tmp_path)

    shots = load_shot_events(events_path, metadata_path)

    goal = shots[0]

    assert goal.calculated_frame == 7500
    assert goal.calculated_timestamp is not None
    assert goal.calculated_timestamp.tzinfo is not None


def test_finds_nested_penalty_shot(
    tmp_path: Path,
):
    xml = """\
    <PutDataRequest>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="10"
            EventTime="2023-05-27T15:40:00.000+02:00"
        >
            <KickOff GameSection="firstHalf" />
            <Penalty>
                <ShotAtGoal
                    Team="DFL-CLU-HOME"
                    Player="DFL-OBJ-HOME-1"
                    xG="0.62"
                >
                    <SuccessfulShot />
                </ShotAtGoal>
            </Penalty>
        </Event>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="11"
            EventTime="2023-05-27T16:15:00.000+02:00"
        >
            <FinalWhistle GameSection="firstHalf" />
        </Event>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="12"
            EventTime="2023-05-27T16:35:00.000+02:00"
        >
            <KickOff GameSection="secondHalf" />
        </Event>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="13"
            EventTime="2023-05-27T17:25:00.000+02:00"
        >
            <FinalWhistle GameSection="secondHalf" />
        </Event>
    </PutDataRequest>
    """

    events_path, metadata_path = write_event_files(tmp_path, xml)

    shots = load_shot_events(events_path, metadata_path)

    assert len(shots) == 1
    assert shots[0].event_id == "10"
    assert shots[0].outcome == ShotOutcome.GOAL


def test_invalid_outcomes(tmp_path: Path):
    xml = """\
    <PutDataRequest>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="20"
            EventTime="2023-05-27T15:40:00.000+02:00"
        >
            <KickOff GameSection="firstHalf" />
            <ShotAtGoal
                Team="DFL-CLU-HOME"
                Player="DFL-OBJ-HOME-1"
            >
                <SuccessfulShot />
                <ShotWide />
            </ShotAtGoal>
        </Event>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="21"
            EventTime="2023-05-27T16:15:00.000+02:00"
        >
            <FinalWhistle GameSection="firstHalf" />
        </Event>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="22"
            EventTime="2023-05-27T16:35:00.000+02:00"
        >
            <KickOff GameSection="secondHalf" />
        </Event>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="23"
            EventTime="2023-05-27T17:25:00.000+02:00"
        >
            <FinalWhistle GameSection="secondHalf" />
        </Event>
    </PutDataRequest>
    """

    events_path, metadata_path = write_event_files(tmp_path, xml)

    with pytest.raises(DflEventError, match="exactly one recognized outcome"):
        load_shot_events(events_path, metadata_path)


def test_unknown_player_raises_error(tmp_path: Path):
    xml = """\
    <PutDataRequest>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="30"
            EventTime="2023-05-27T15:40:00.000+02:00"
        >
            <KickOff GameSection="firstHalf" />
            <ShotAtGoal
                Team="DFL-CLU-HOME"
                Player="DFL-OBJ-UNKNOWN"
            >
                <SuccessfulShot />
            </ShotAtGoal>
        </Event>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="31"
            EventTime="2023-05-27T16:15:00.000+02:00"
        >
            <FinalWhistle GameSection="firstHalf" />
        </Event>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="32"
            EventTime="2023-05-27T16:35:00.000+02:00"
        >
            <KickOff GameSection="secondHalf" />
        </Event>
        <Event
            MatchId="DFL-MAT-J03TEST"
            EventId="33"
            EventTime="2023-05-27T17:25:00.000+02:00"
        >
            <FinalWhistle GameSection="secondHalf" />
        </Event>
    </PutDataRequest>
    """

    events_path, metadata_path = write_event_files(tmp_path, xml)

    with pytest.raises(DflEventError, match="Unknown shot player"):
        load_shot_events(events_path, metadata_path)

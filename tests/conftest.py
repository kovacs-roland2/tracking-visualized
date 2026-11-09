"""Shared fixtures: a tiny synthetic DFL dataset written to a temporary folder."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

TEST_MATCH_ID = "J03TEST"

HOME_TEAM_ID = "DFL-CLU-HOME"
AWAY_TEAM_ID = "DFL-CLU-AWAY"
HOME_PLAYER_ID = "DFL-OBJ-HOME-1"
AWAY_PLAYER_ID = "DFL-OBJ-AWAY-1"

GOAL_EVENT_ID = "E-GOAL"
WIDE_EVENT_ID = "E-WIDE"

SOURCE_FPS = 25
TIMEZONE = timezone(timedelta(hours=2))

# (first source frame, number of frames, kickoff) of each half. The first half lasts
# 16 s with the goal 8 s in; the second half lasts 8 s with the wide shot 4 s in.
FIRST_HALF = (1000, 401, datetime(2023, 5, 27, 15, 30, 0, tzinfo=TIMEZONE))
SECOND_HALF = (5000, 201, datetime(2023, 5, 27, 16, 35, 0, tzinfo=TIMEZONE))

METADATA_XML = f"""\
<PutDataRequest>
  <MatchInformation>
    <General CompetitionId="DFL-COM-TEST" CompetitionName="Testliga" SeasonId="DFL-SEA-TEST"
      Season="2022/2023" MatchDay="34" MatchId="DFL-MAT-{TEST_MATCH_ID}"
      HomeTeamId="{HOME_TEAM_ID}" HomeTeamName="Home FC"
      GuestTeamId="{AWAY_TEAM_ID}" GuestTeamName="Away United" />
    <Environment PitchX="105.00" PitchY="68.00" />
    <Teams>
      <Team TeamId="{HOME_TEAM_ID}" TeamName="Home FC" Role="home">
        <Players>
          <Player PersonId="{HOME_PLAYER_ID}" ShirtNumber="9" />
        </Players>
      </Team>
      <Team TeamId="{AWAY_TEAM_ID}" TeamName="Away United" Role="guest">
        <Players>
          <Player PersonId="{AWAY_PLAYER_ID}" ShirtNumber="10" />
        </Players>
      </Team>
    </Teams>
    <OtherGameInformation TotalTimeFirstHalf="17000" TotalTimeSecondHalf="9000"
      PlayingTimeFirstHalf="16000" PlayingTimeSecondHalf="8000" />
  </MatchInformation>
</PutDataRequest>
"""


def _timestamp(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds")


def _event_xml(event_id: str, moment: datetime, body: str, attributes: str = "") -> str:
    return (
        f'<Event MatchId="DFL-MAT-{TEST_MATCH_ID}" EventId="{event_id}" '
        f'EventTime="{_timestamp(moment)}" {attributes}>{body}</Event>'
    )


def _events_xml() -> str:
    first_start = FIRST_HALF[2]
    second_start = SECOND_HALF[2]

    goal_frame = FIRST_HALF[0] + 8 * SOURCE_FPS
    wide_frame = SECOND_HALF[0] + 4 * SOURCE_FPS

    events = [
        _event_xml("K1", first_start, '<KickOff GameSection="firstHalf" />'),
        _event_xml(
            GOAL_EVENT_ID,
            first_start + timedelta(seconds=8),
            f'<ShotAtGoal Team="{HOME_TEAM_ID}" Player="{HOME_PLAYER_ID}" xG="0.4">'
            "<SuccessfulShot /></ShotAtGoal>",
            f'CalculatedFrame="{goal_frame}" X-Position="95.0" Y-Position="32.0"',
        ),
        _event_xml(
            "W1",
            first_start + timedelta(seconds=16),
            '<FinalWhistle GameSection="firstHalf" />',
        ),
        _event_xml("K2", second_start, '<KickOff GameSection="secondHalf" />'),
        _event_xml(
            WIDE_EVENT_ID,
            second_start + timedelta(seconds=4),
            f'<ShotAtGoal Team="{AWAY_TEAM_ID}" Player="{AWAY_PLAYER_ID}">'
            "<ShotWide /></ShotAtGoal>",
            f'CalculatedFrame="{wide_frame}" X-Position="10.0" Y-Position="30.0"',
        ),
        _event_xml(
            "W2",
            second_start + timedelta(seconds=8),
            '<FinalWhistle GameSection="secondHalf" />',
        ),
    ]

    return "<PutDataRequest>\n" + "\n".join(events) + "\n</PutDataRequest>\n"


def _frame_set(section: str, team_id: str, person_id: str, frames: list[str]) -> str:
    return (
        f'<FrameSet GameSection="{section}" TeamId="{team_id}" PersonId="{person_id}">'
        + "".join(frames)
        + "</FrameSet>"
    )


def _tracking_xml() -> str:
    sets: list[str] = []

    for section, (first_frame, count, kickoff) in (
        ("FirstHalf", FIRST_HALF),
        ("SecondHalf", SECOND_HALF),
    ):
        home, away, ball = [], [], []

        for i in range(count):
            number = first_frame + i
            stamp = _timestamp(kickoff + timedelta(seconds=i / SOURCE_FPS))

            home.append(f'<Frame N="{number}" T="{stamp}" X="{-10 + i * 0.05:.2f}" Y="4.00" />')
            away.append(f'<Frame N="{number}" T="{stamp}" X="12.00" Y="-3.00" />')
            ball.append(
                f'<Frame N="{number}" T="{stamp}" X="{i * 0.1:.2f}" Y="1.00" Z="0.20" '
                'BallPossession="1" BallStatus="1" />'
            )

        sets.append(_frame_set(section, HOME_TEAM_ID, HOME_PLAYER_ID, home))
        sets.append(_frame_set(section, AWAY_TEAM_ID, AWAY_PLAYER_ID, away))
        sets.append(_frame_set(section, "BALL", "DFL-OBJ-BALL", ball))

    return "<Positions>\n" + "\n".join(sets) + "\n</Positions>\n"


def write_dfl_match(data_dir: Path, match_id: str = TEST_MATCH_ID) -> Path:
    """Write a small DFL match to ``data_dir / match_id`` and return that folder."""

    match_dir = data_dir / match_id
    match_dir.mkdir(parents=True)

    suffix = f"DFL-COM-TEST_DFL-MAT-{match_id}.xml"

    (match_dir / f"DFL_02_01_matchinformation_{suffix}").write_text(METADATA_XML, encoding="utf-8")
    (match_dir / f"DFL_03_02_events_raw_{suffix}").write_text(_events_xml(), encoding="utf-8")
    (match_dir / f"DFL_04_03_positions_raw_observed_{suffix}").write_text(
        _tracking_xml(), encoding="utf-8"
    )

    return match_dir


@pytest.fixture
def dfl_data_dir(tmp_path: Path) -> Path:
    """A data folder holding the synthetic match ``J03TEST``."""

    data_dir = tmp_path / "dfl"
    write_dfl_match(data_dir)

    return data_dir

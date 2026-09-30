from pathlib import Path

import pytest

from tracking_visualized.providers.dfl import (
    BallTrackingSample,
    DflTrackingError,
    PlayerTrackingSample,
    TrackingPeriod,
    TrackingTeam,
    iter_tracking_samples,
)

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

TRACKING_XML = """\
<Positions>
    <FrameSet
        GameSection="FirstHalf"
        TeamId="DFL-CLU-HOME"
        PersonId="DFL-OBJ-HOME-1"
    >
        <Frame
            N="100"
            T="2023-05-27T15:30:00.000+02:00"
            X="-10.5"
            Y="4.25"
        />
        <Frame
            N="101"
            T="2023-05-27T15:30:00.040+02:00"
            X="-10.3"
            Y="4.30"
        />
    </FrameSet>

    <FrameSet
        GameSection="FirstHalf"
        TeamId="DFL-CLU-AWAY"
        PersonId="DFL-OBJ-AWAY-1"
    >
        <Frame
            N="100"
            T="2023-05-27T15:30:00.000+02:00"
            X="12.0"
            Y="-3.0"
        />
    </FrameSet>

    <FrameSet
        GameSection="FirstHalf"
        TeamId="BALL"
        PersonId="DFL-OBJ-BALL"
    >
        <Frame
            N="100"
            T="2023-05-27T15:30:00.000+02:00"
            X="0.5"
            Y="1.25"
            Z="0.15"
            BallPossession="1"
            BallStatus="1"
        />
    </FrameSet>
</Positions>
"""


def write_files(
    tmp_path: Path,
) -> tuple[Path, Path]:
    metadata_path = tmp_path / "metadata.xml"
    tracking_path = tmp_path / "tracking.xml"

    metadata_path.write_text(
        MATCH_METADATA_XML,
        encoding="utf-8",
    )

    tracking_path.write_text(
        TRACKING_XML,
        encoding="utf-8",
    )

    return tracking_path, metadata_path


def test_parses_player_tracking(
    tmp_path: Path,
):
    tracking_path, metadata_path = write_files(tmp_path)

    samples = list(
        iter_tracking_samples(
            tracking_path,
            metadata_path,
        )
    )

    player_samples = [sample for sample in samples if isinstance(sample, PlayerTrackingSample)]

    assert len(player_samples) == 3

    first = player_samples[0]

    assert first.frame_number == 100
    assert first.period == TrackingPeriod.FIRST_HALF
    assert first.person_id == "DFL-OBJ-HOME-1"

    assert first.team_id == "DFL-CLU-HOME"
    assert first.team == TrackingTeam.HOME
    assert first.shirt_number == 7

    assert first.x == -10.5
    assert first.y == 4.25


def test_parses_timestamp(
    tmp_path: Path,
):
    tracking_path, metadata_path = write_files(tmp_path)

    samples = list(
        iter_tracking_samples(
            tracking_path,
            metadata_path,
        )
    )

    first = samples[0]

    assert first.timestamp.year == 2023
    assert first.timestamp.month == 5
    assert first.timestamp.day == 27

    assert first.timestamp.tzinfo is not None


def test_consecutive_frames_are_40ms_apart(
    tmp_path: Path,
):
    tracking_path, metadata_path = write_files(tmp_path)

    players = [
        sample
        for sample in iter_tracking_samples(
            tracking_path,
            metadata_path,
        )
        if isinstance(sample, PlayerTrackingSample) and sample.person_id == "DFL-OBJ-HOME-1"
    ]

    delta = players[1].timestamp - players[0].timestamp

    assert delta.total_seconds() == 0.04


def test_parses_ball_tracking(
    tmp_path: Path,
):
    tracking_path, metadata_path = write_files(tmp_path)

    ball_samples = [
        sample
        for sample in iter_tracking_samples(
            tracking_path,
            metadata_path,
        )
        if isinstance(sample, BallTrackingSample)
    ]

    assert len(ball_samples) == 1

    ball = ball_samples[0]

    assert ball.frame_number == 100

    assert ball.x == 0.5
    assert ball.y == 1.25
    assert ball.z == 0.15

    assert ball.possession_team == TrackingTeam.HOME
    assert ball.is_alive is True


def test_missing_coordinates_become_none(
    tmp_path: Path,
):
    tracking_xml = """\
    <Positions>
        <FrameSet
            GameSection="FirstHalf"
            TeamId="BALL"
        >
            <Frame
                N="100"
                T="2023-05-27T15:30:00.000+02:00"
                BallPossession="1"
                BallStatus="1"
            />
        </FrameSet>
    </Positions>
    """

    metadata_path = tmp_path / "metadata.xml"
    tracking_path = tmp_path / "tracking.xml"

    metadata_path.write_text(
        MATCH_METADATA_XML,
        encoding="utf-8",
    )

    tracking_path.write_text(
        tracking_xml,
        encoding="utf-8",
    )

    samples = list(
        iter_tracking_samples(
            tracking_path,
            metadata_path,
        )
    )

    ball = samples[0]

    assert isinstance(ball, BallTrackingSample)

    assert ball.x is None
    assert ball.y is None
    assert ball.z is None


def test_missing_frame_number_raises_error(
    tmp_path: Path,
):
    tracking_xml = """\
    <Positions>
        <FrameSet
            GameSection="FirstHalf"
            TeamId="BALL"
        >
            <Frame
                T="2023-05-27T15:30:00.000+02:00"
                X="0"
                Y="0"
            />
        </FrameSet>
    </Positions>
    """

    metadata_path = tmp_path / "metadata.xml"
    tracking_path = tmp_path / "tracking.xml"

    metadata_path.write_text(
        MATCH_METADATA_XML,
        encoding="utf-8",
    )

    tracking_path.write_text(
        tracking_xml,
        encoding="utf-8",
    )

    with pytest.raises(
        DflTrackingError,
        match="N",
    ):
        list(
            iter_tracking_samples(
                tracking_path,
                metadata_path,
            )
        )

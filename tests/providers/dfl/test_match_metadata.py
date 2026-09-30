from pathlib import Path

import pytest

from tracking_visualized.providers.dfl import (
    DflMatchMetadataError,
    TeamSide,
    load_match_metadata,
)

VALID_MATCH_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<PutDataRequest>
    <MatchInformation>
        <General
            CompetitionName="Bundesliga"
            CompetitionId="DFL-COM-000001"
            MatchDay="34"
            Season="2022/2023"
            SeasonId="DFL-SEA-0001K6"
            MatchId="DFL-MAT-J03TEST"
            HomeTeamName="Home FC"
            HomeTeamId="DFL-CLU-HOME"
            GuestTeamName="Away FC"
            GuestTeamId="DFL-CLU-AWAY"
        />
        <Teams>
            <Team
                TeamId="DFL-CLU-AWAY"
                TeamName="Away FC"
                Role="guest"
            />
            <Team
                TeamId="DFL-CLU-HOME"
                TeamName="Home FC"
                Role="home"
            />
        </Teams>
        <OtherGameInformation
            TotalTimeFirstHalf="2828280"
            TotalTimeSecondHalf="3010320"
            PlayingTimeFirstHalf="1888960"
            PlayingTimeSecondHalf="1525720"
        />
    </MatchInformation>
</PutDataRequest>
"""


def write_xml(
    tmp_path: Path,
    content: str = VALID_MATCH_XML,
) -> Path:
    path = tmp_path / "match_information.xml"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_match_metadata(tmp_path: Path):
    path = write_xml(tmp_path)

    metadata = load_match_metadata(path)

    assert metadata.match_id == "DFL-MAT-J03TEST"

    assert metadata.competition.competition_id == "DFL-COM-000001"
    assert metadata.competition.name == "Bundesliga"

    assert metadata.season.season_id == "DFL-SEA-0001K6"
    assert metadata.season.name == "2022/2023"

    assert metadata.match_day == 34

    assert metadata.home_team.team_id == "DFL-CLU-HOME"
    assert metadata.home_team.name == "Home FC"
    assert metadata.home_team.side == TeamSide.HOME

    assert metadata.away_team.team_id == "DFL-CLU-AWAY"
    assert metadata.away_team.name == "Away FC"
    assert metadata.away_team.side == TeamSide.AWAY

    assert metadata.periods[0].number == 1
    assert metadata.periods[0].total_duration_seconds == 2828.28
    assert metadata.periods[0].playing_duration_seconds == 1888.96

    assert metadata.periods[1].number == 2
    assert metadata.periods[1].total_duration_seconds == 3010.32
    assert metadata.periods[1].playing_duration_seconds == 1525.72


def test_missing_general_element_raises_error(
    tmp_path: Path,
):
    xml = """\
    <PutDataRequest>
        <MatchInformation>
            <Teams />
            <OtherGameInformation />
        </MatchInformation>
    </PutDataRequest>
    """

    path = write_xml(tmp_path, xml)

    with pytest.raises(
        DflMatchMetadataError,
        match="General",
    ):
        load_match_metadata(path)


def test_invalid_xml_raises_error(
    tmp_path: Path,
):
    path = write_xml(
        tmp_path,
        "<not-valid-xml>",
    )

    with pytest.raises(
        DflMatchMetadataError,
        match="Invalid XML",
    ):
        load_match_metadata(path)


def test_mismatched_team_id_raises_error(
    tmp_path: Path,
):
    xml = VALID_MATCH_XML.replace(
        'HomeTeamId="DFL-CLU-HOME"',
        'HomeTeamId="DFL-CLU-DIFFERENT"',
    )

    path = write_xml(tmp_path, xml)

    with pytest.raises(
        DflMatchMetadataError,
        match="Home team ID differs",
    ):
        load_match_metadata(path)


def test_playing_time_cannot_exceed_total_time(
    tmp_path: Path,
):
    xml = VALID_MATCH_XML.replace(
        'PlayingTimeFirstHalf="1888960"',
        'PlayingTimeFirstHalf="9999999"',
    )

    path = write_xml(tmp_path, xml)

    with pytest.raises(
        ValueError,
        match="Playing duration cannot exceed",
    ):
        load_match_metadata(path)

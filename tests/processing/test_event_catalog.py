import pytest

from tracking_visualized.domain import (
    Event,
    EventType,
    MatchTime,
    PeriodType,
    ShotOutcome,
)
from tracking_visualized.processing import (
    EventCatalog,
    EventCatalogError,
    filter_goal_events,
    filter_shot_events,
    sort_events,
)


def shot(
    event_id: str,
    period: PeriodType,
    seconds: float,
    outcome: ShotOutcome,
    frame_index: int | None = None,
) -> Event:
    return Event(
        event_id=event_id,
        event_type=EventType.SHOT,
        time=MatchTime(
            period=period,
            seconds=seconds,
        ),
        team_id="home",
        player_id="player-7",
        frame_index=frame_index,
        shot_outcome=outcome,
    )


def test_filters_shots():
    events = (
        shot(
            "shot-1",
            PeriodType.FIRST_HALF,
            100.0,
            ShotOutcome.SAVED,
        ),
        shot(
            "goal-1",
            PeriodType.FIRST_HALF,
            200.0,
            ShotOutcome.GOAL,
        ),
    )

    shots = filter_shot_events(events)

    assert len(shots) == 2


def test_filters_goals():
    events = (
        shot(
            "shot-1",
            PeriodType.FIRST_HALF,
            100.0,
            ShotOutcome.SAVED,
        ),
        shot(
            "goal-1",
            PeriodType.FIRST_HALF,
            200.0,
            ShotOutcome.GOAL,
        ),
        shot(
            "shot-2",
            PeriodType.SECOND_HALF,
            100.0,
            ShotOutcome.WIDE,
        ),
    )

    goals = filter_goal_events(events)

    assert len(goals) == 1
    assert goals[0].event_id == "goal-1"


def test_sorts_events_chronologically():
    events = (
        shot(
            "second-half",
            PeriodType.SECOND_HALF,
            60.0,
            ShotOutcome.WIDE,
        ),
        shot(
            "first-half-late",
            PeriodType.FIRST_HALF,
            2500.0,
            ShotOutcome.SAVED,
        ),
        shot(
            "first-half-early",
            PeriodType.FIRST_HALF,
            300.0,
            ShotOutcome.BLOCKED,
        ),
    )

    result = sort_events(events)

    assert [event.event_id for event in result] == [
        "first-half-early",
        "first-half-late",
        "second-half",
    ]


def test_catalog_sorts_events():
    catalog = EventCatalog(
        events=(
            shot(
                "event-2",
                PeriodType.SECOND_HALF,
                10.0,
                ShotOutcome.GOAL,
            ),
            shot(
                "event-1",
                PeriodType.FIRST_HALF,
                100.0,
                ShotOutcome.SAVED,
            ),
        )
    )

    assert [event.event_id for event in catalog.events] == [
        "event-1",
        "event-2",
    ]


def test_event_lookup():
    event = shot(
        "goal-42",
        PeriodType.SECOND_HALF,
        500.0,
        ShotOutcome.GOAL,
    )

    catalog = EventCatalog(events=(event,))

    result = catalog.get_event("goal-42")

    assert result is event


def test_unknown_event_lookup_raises():
    catalog = EventCatalog(events=())

    with pytest.raises(
        KeyError,
        match="Unknown event ID",
    ):
        catalog.get_event("does-not-exist")


def test_find_unknown_event_returns_none():
    catalog = EventCatalog(events=())

    assert catalog.find_event("does-not-exist") is None


def test_duplicate_event_ids_are_rejected():
    events = (
        shot(
            "duplicate",
            PeriodType.FIRST_HALF,
            100.0,
            ShotOutcome.SAVED,
        ),
        shot(
            "duplicate",
            PeriodType.FIRST_HALF,
            200.0,
            ShotOutcome.GOAL,
        ),
    )

    with pytest.raises(
        EventCatalogError,
        match="Duplicate event ID",
    ):
        EventCatalog(events=events)

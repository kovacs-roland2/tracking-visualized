import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from matplotlib.animation import FuncAnimation  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402

from tracking_visualized.domain import (  # noqa: E402
    CoordinateSystem,
    Event,
    EventType,
    Frame,
    Match,
    MatchMetadata,
    MatchTime,
    PeriodType,
    Player,
    ShotOutcome,
    Team,
    TeamSide,
)
from tracking_visualized.rendering import (  # noqa: E402
    EventLayer,
    EventStyle,
    draw_event,
    draw_pitch,
    format_event_time,
    format_event_type,
)

EVENT_TIME = MatchTime(period=PeriodType.FIRST_HALF, seconds=469.77)


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.fixture
def ax():
    return draw_pitch()


def make_event(
    outcome: ShotOutcome = ShotOutcome.SAVED,
    *,
    x: float | None = 90.0,
    y: float | None = 30.0,
    time: MatchTime = EVENT_TIME,
    player_id: str | None = "p11",
) -> Event:
    return Event(
        event_id="e1",
        event_type=EventType.SHOT,
        time=time,
        team_id="home",
        player_id=player_id,
        x=x,
        y=y,
        shot_outcome=outcome,
    )


def make_frame(
    seconds: float,
    period: PeriodType = PeriodType.FIRST_HALF,
    frame_index: int = 0,
) -> Frame:
    return Frame(
        frame_index=frame_index,
        time=MatchTime(period=period, seconds=seconds),
        player_positions=(),
        ball_position=None,
    )


def marker_offsets(layer: EventLayer) -> list[tuple[float, float]]:
    return [tuple(row) for row in np.asarray(layer.marker.get_offsets())]


@pytest.mark.parametrize(
    ("period", "seconds", "expected"),
    [
        (PeriodType.FIRST_HALF, 469.77, "1H 07:49"),
        (PeriodType.FIRST_HALF, 0.0, "1H 00:00"),
        (PeriodType.SECOND_HALF, 2104.57, "2H 35:04"),
        (PeriodType.SECOND_HALF, 3600.0, "2H 60:00"),
    ],
)
def test_format_event_time(period, seconds, expected):
    assert format_event_time(MatchTime(period=period, seconds=seconds)) == expected


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (ShotOutcome.GOAL, "GOAL"),
        (ShotOutcome.SAVED, "SHOT  ·  SAVED"),
        (ShotOutcome.WOODWORK, "SHOT  ·  WOODWORK"),
        (ShotOutcome.OTHER, "SHOT"),
    ],
)
def test_format_event_type(outcome, expected):
    assert format_event_type(make_event(outcome)) == expected


def test_invalid_style_raises():
    for kwargs in (
        {"shot_color": "not-a-color"},
        {"box_alpha": 1.5},
        {"line_width": 0},
        {"font_size": 0},
    ):
        with pytest.raises(ValueError):
            EventStyle(**kwargs)


def test_invalid_layer_arguments_raise(ax):
    for kwargs in (
        {"show_before_seconds": -1},
        {"show_after_seconds": -1},
        {"marker_size": 0},
    ):
        with pytest.raises(ValueError):
            EventLayer(ax, make_event(), **kwargs)


def test_label_shows_type_number_and_timestamp(ax):
    layer = EventLayer(ax, make_event(ShotOutcome.SAVED), shirt_number=11)

    assert layer.label.get_text() == "SHOT  ·  SAVED  ·  #11  ·  1H 07:49"


def test_label_is_positioned_above_the_pitch(ax):
    layer = EventLayer(ax, make_event())

    assert layer.label.get_position() == (0.5, 1.05)
    assert layer.label.get_verticalalignment() == "top"


def test_label_without_shirt_number_omits_it(ax):
    layer = EventLayer(ax, make_event(ShotOutcome.WIDE))

    assert layer.label.get_text() == "SHOT  ·  WIDE  ·  1H 07:49"


def test_marker_is_placed_at_event_location(ax):
    layer = draw_event(ax, make_event(), make_frame(469.77))

    assert marker_offsets(layer) == [(90.0, 30.0)]
    assert layer.marker.get_visible()


def test_shot_marker_is_a_ring_in_shot_color(ax):
    style = EventStyle(shot_color="cyan")
    layer = EventLayer(ax, make_event(ShotOutcome.BLOCKED), style=style, marker_size=20.0)

    assert layer.marker.get_sizes()[0] == 400.0
    assert len(layer.marker.get_facecolor()) == 0 or layer.marker.get_facecolor()[0][3] == 0
    assert tuple(layer.marker.get_edgecolor()[0]) == to_rgba("cyan")


def test_goal_is_highlighted(ax):
    style = EventStyle(goal_color="gold")
    goal = EventLayer(ax, make_event(ShotOutcome.GOAL), style=style, marker_size=20.0)
    shot = EventLayer(ax, make_event(ShotOutcome.SAVED), style=style, marker_size=20.0)

    assert goal.marker.get_sizes()[0] > shot.marker.get_sizes()[0]
    assert tuple(goal.marker.get_facecolor()[0]) == to_rgba("gold")
    assert goal.label.get_bbox_patch().get_edgecolor()[:3] == to_rgba("gold")[:3]
    assert shot.label.get_bbox_patch().get_edgecolor()[:3] != to_rgba("gold")[:3]


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (467.0, False),
        (468.5, True),
        (469.77, True),
        (472.5, True),
        (473.5, False),
        (3000.0, False),
    ],
)
def test_visibility_follows_event_window(ax, seconds, expected):
    layer = EventLayer(ax, make_event(), show_before_seconds=1.5, show_after_seconds=3.0)
    layer.update(make_frame(seconds))

    assert layer.is_visible is expected
    assert layer.marker.get_visible() is expected
    assert layer.label.get_visible() is expected


def test_hidden_in_other_period(ax):
    layer = EventLayer(ax, make_event())
    layer.update(make_frame(469.77, period=PeriodType.SECOND_HALF))

    assert not layer.is_visible
    assert not layer.label.get_visible()


def test_event_without_location_shows_label_but_no_marker(ax):
    layer = EventLayer(ax, make_event(x=None, y=None))
    layer.update(make_frame(469.77))

    assert marker_offsets(layer) == []
    assert layer.label.get_visible()
    assert not layer.marker.get_visible()


def test_update_returns_all_artists(ax):
    layer = EventLayer(ax, make_event())

    assert layer.update(make_frame(469.77)) == [layer.marker, layer.label]


def test_update_does_not_create_new_artists(ax):
    layer = EventLayer(ax, make_event())
    collection_count = len(ax.collections)
    text_count = len(ax.texts)

    for seconds in (460.0, 469.77, 480.0):
        layer.update(make_frame(seconds))

    assert len(ax.collections) == collection_count
    assert len(ax.texts) == text_count


def test_from_match_looks_up_shirt_number(ax):
    home = Team(team_id="home", name="Home FC", side=TeamSide.HOME)
    away = Team(team_id="away", name="Away FC", side=TeamSide.AWAY)
    match = Match(
        metadata=MatchMetadata(match_id="m1", competition="Liga", season="2026"),
        coordinate_system=CoordinateSystem(pitch_length=105.0, pitch_width=68.0),
        periods=(),
        teams=(home, away),
        players=(Player(player_id="p11", team_id="home", shirt_number=11),),
        frames=(),
        events=(),
    )

    known = EventLayer.from_match(ax, match, make_event(player_id="p11"))
    unknown = EventLayer.from_match(ax, match, make_event(player_id="ghost"))
    no_player = EventLayer.from_match(ax, match, make_event(player_id=None))

    assert known.shirt_number == 11
    assert unknown.shirt_number is None
    assert no_player.shirt_number is None


def test_event_indicator_animation(ax, tmp_path):
    layer = EventLayer(ax, make_event(), show_before_seconds=0.5, show_after_seconds=0.5)
    seconds = [468.0, 469.5, 469.77, 470.0, 472.0]
    frames = [make_frame(s, frame_index=i) for i, s in enumerate(seconds)]
    seen: list[bool] = []

    def step(frame: Frame):
        artists = layer.update(frame)
        seen.append(layer.is_visible)
        return artists

    animation = FuncAnimation(ax.figure, step, frames=frames, repeat=False)
    animation.save(tmp_path / "event.gif", writer="pillow", fps=5)

    # FuncAnimation draws the first frame once more for its initial draw.
    assert seen[-5:] == [False, True, True, True, False]


def test_marker_is_behind_players_and_label_is_on_top(ax):
    layer = EventLayer(ax, make_event(ShotOutcome.GOAL))

    # Players are drawn at zorder 3, the ball at 4.
    assert layer.marker.get_zorder() < 3.0
    assert layer.label.get_zorder() > 4.0

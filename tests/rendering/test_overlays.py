import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402

from tracking_visualized.config import (  # noqa: E402
    TextPosition,
    VideoConfig,
    VideoLayoutConfig,
)
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
    DEFAULT_AWAY_STYLE,
    DEFAULT_HOME_STYLE,
    EventOverlay,
    OverlayLayoutError,
    OverlayStyle,
    TeamStyle,
    shorten_text,
)

HOME = Team(team_id="home", name="Home FC", side=TeamSide.HOME)
AWAY = Team(team_id="away", name="Away United", side=TeamSide.AWAY)
PLAYERS = (Player(player_id="p11", team_id="away", shirt_number=11),)

EVENT_TIME = MatchTime(period=PeriodType.FIRST_HALF, seconds=469.77)
ANCHOR = (0.5, 0.8)
FIGSIZE = (5.4, 9.6)


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.fixture
def fig():
    return plt.figure(figsize=FIGSIZE, dpi=100)


def make_event(
    outcome: ShotOutcome = ShotOutcome.GOAL,
    *,
    team_id: str | None = "away",
    player_id: str | None = "p11",
) -> Event:
    return Event(
        event_id="e1",
        event_type=EventType.SHOT,
        time=EVENT_TIME,
        team_id=team_id,
        player_id=player_id,
        x=90.0,
        y=30.0,
        shot_outcome=outcome,
    )


def make_match(players=PLAYERS) -> Match:
    return Match(
        metadata=MatchMetadata(match_id="m1", competition="Liga", season="2026"),
        coordinate_system=CoordinateSystem(pitch_length=105.0, pitch_width=68.0),
        periods=(),
        teams=(HOME, AWAY),
        players=players,
        frames=(),
        events=(),
    )


def make_overlay(fig, event=None, **kwargs) -> EventOverlay:
    kwargs.setdefault("anchor", ANCHOR)
    kwargs.setdefault("team", AWAY)
    kwargs.setdefault("team_style", DEFAULT_AWAY_STYLE)
    kwargs.setdefault("shirt_number", 11)

    return EventOverlay(fig, event or make_event(), **kwargs)


def extent(fig, text):
    fig.canvas.draw()

    return text.get_window_extent()


def test_title_shows_event_type_and_time(fig):
    overlay = make_overlay(fig)

    assert overlay.title.get_text() == "GOAL  ·  1H 07:49"


def test_title_for_a_saved_shot(fig):
    overlay = make_overlay(fig, make_event(ShotOutcome.SAVED))

    assert overlay.title.get_text() == "SHOT  ·  SAVED  ·  1H 07:49"


def test_subtitle_shows_shirt_number_and_team_name(fig):
    overlay = make_overlay(fig)

    assert overlay.subtitle.get_text() == "#11  ·  Away United"


def test_subtitle_without_shirt_number_shows_only_the_team(fig):
    overlay = make_overlay(fig, shirt_number=None)

    assert overlay.subtitle.get_text() == "Away United"


def test_subtitle_without_team_shows_only_the_shirt_number(fig):
    overlay = make_overlay(fig, team=None, team_style=None)

    assert overlay.subtitle.get_text() == "#11"


def test_there_is_no_subtitle_without_number_and_team(fig):
    overlay = make_overlay(fig, team=None, team_style=None, shirt_number=None)

    assert overlay.subtitle is None
    assert overlay.artists == [overlay.title]


def test_long_team_names_are_shortened(fig):
    long_team = Team(
        team_id="away", name="Association Sportive de Longue Distance", side=TeamSide.AWAY
    )
    overlay = make_overlay(fig, team=long_team, style=OverlayStyle(max_team_name_chars=12))

    assert overlay.subtitle.get_text() == "#11  ·  Association…"


def test_shorten_text():
    assert shorten_text("Short", 10) == "Short"
    assert shorten_text("Exactly10!", 10) == "Exactly10!"
    assert shorten_text("A longer name", 8) == "A longe…"


def test_goal_title_is_gold_and_other_shots_are_white(fig):
    style = OverlayStyle()

    goal = make_overlay(fig)
    saved = make_overlay(fig, make_event(ShotOutcome.SAVED))

    assert goal.title.get_color() == style.goal_color
    assert saved.title.get_color() == style.title_color


def test_chip_uses_the_team_colors(fig):
    overlay = make_overlay(fig, team_style=DEFAULT_HOME_STYLE)
    chip = overlay.subtitle.get_bbox_patch()

    assert chip.get_facecolor()[:3] == to_rgba(DEFAULT_HOME_STYLE.marker_color)[:3]
    assert overlay.subtitle.get_color() == DEFAULT_HOME_STYLE.number_color


def test_chip_falls_back_to_the_style_colors_without_team_style(fig):
    style = OverlayStyle(chip_color="#336699", chip_text_color="#ffeecc")
    overlay = make_overlay(fig, team_style=None, style=style)

    assert overlay.subtitle.get_bbox_patch().get_facecolor()[:3] == to_rgba("#336699")[:3]
    assert overlay.subtitle.get_color() == "#ffeecc"


def test_font_sizes_come_from_the_style(fig):
    style = OverlayStyle(title_font_size=33.0, subtitle_font_size=17.0)
    overlay = make_overlay(fig, style=style)

    assert overlay.title.get_fontsize() == 33.0
    assert overlay.subtitle.get_fontsize() == 17.0


def test_top_position_stacks_the_title_above_the_chip_above_the_anchor(fig):
    overlay = make_overlay(fig, position=TextPosition.TOP)
    title, chip = extent(fig, overlay.title), extent(fig, overlay.subtitle)
    chip_box = overlay.subtitle.get_bbox_patch().get_window_extent()
    anchor_y = ANCHOR[1] * fig.bbox.height

    assert title.y0 > chip.y1
    # The chip, not its text, touches the anchor.
    assert chip_box.y0 == pytest.approx(anchor_y, abs=2.0)


def test_bottom_position_stacks_the_chip_below_the_title_below_the_anchor(fig):
    overlay = make_overlay(fig, position=TextPosition.BOTTOM)
    title, chip = extent(fig, overlay.title), extent(fig, overlay.subtitle)
    chip_box = overlay.subtitle.get_bbox_patch().get_window_extent()
    anchor_y = ANCHOR[1] * fig.bbox.height

    assert chip.y1 < title.y0
    assert title.y1 == pytest.approx(anchor_y, abs=4.0)
    assert chip_box.y1 < title.y0


def test_lines_are_centered_on_the_anchor(fig):
    overlay = make_overlay(fig)
    middle = ANCHOR[0] * fig.bbox.width

    for text in (overlay.title, overlay.subtitle):
        box = extent(fig, text)

        assert (box.x0 + box.x1) / 2 == pytest.approx(middle, abs=1.0)


def test_lines_do_not_overlap_for_any_font_size(fig):
    for size in (8.0, 20.0, 40.0):
        style = OverlayStyle(title_font_size=size, subtitle_font_size=size / 2)
        overlay = make_overlay(fig, style=style)
        title = extent(fig, overlay.title)
        chip_box = overlay.subtitle.get_bbox_patch().get_window_extent()

        assert chip_box.y1 <= title.y0 + 1e-6


def test_overlay_is_always_visible_and_returns_no_changed_artists(fig):
    overlay = make_overlay(fig)
    frame = Frame(
        frame_index=0,
        time=MatchTime(period=PeriodType.SECOND_HALF, seconds=5.0),
        player_positions=(),
        ball_position=None,
    )

    assert overlay.update(frame) == []
    assert all(artist.get_visible() for artist in overlay.artists)


def test_overlay_text_is_part_of_the_figure(fig):
    overlay = make_overlay(fig)
    fig.canvas.draw()

    assert all(artist.figure is fig for artist in overlay.artists)


def test_from_match_looks_up_team_style_and_shirt_number(fig):
    config = VideoConfig(width=540, height=960, dpi=50)
    overlay = EventOverlay.from_match(fig, make_match(), make_event(), config)

    assert overlay.subtitle.get_text() == "#11  ·  Away United"
    assert (
        overlay.subtitle.get_bbox_patch().get_facecolor()[:3]
        == (to_rgba(DEFAULT_AWAY_STYLE.marker_color)[:3])
    )


def test_from_match_uses_custom_team_styles(fig):
    config = VideoConfig(width=540, height=960, dpi=50)
    overlay = EventOverlay.from_match(
        fig,
        make_match(),
        make_event(),
        config,
        away_style=TeamStyle(marker_color="#00ff00"),
    )

    assert overlay.subtitle.get_bbox_patch().get_facecolor()[:3] == to_rgba("#00ff00")[:3]


def test_from_match_tolerates_unknown_team_and_player(fig):
    config = VideoConfig(width=540, height=960, dpi=50)
    event = make_event(team_id="ghost", player_id="nobody")
    overlay = EventOverlay.from_match(fig, make_match(), event, config)

    assert overlay.subtitle is None

    event = make_event(team_id=None, player_id=None)
    overlay = EventOverlay.from_match(fig, make_match(), event, config)

    assert overlay.subtitle is None


def test_from_match_places_the_overlay_in_the_configured_margin(fig):
    layout = VideoLayoutConfig(
        margin_top=100, margin_bottom=300, margin_left=20, margin_right=20, text_gap=10
    )
    config = VideoConfig(width=540, height=960, dpi=50, layout=layout)
    fig = plt.figure(figsize=config.figure_size_inches, dpi=config.dpi)

    top = EventOverlay.from_match(fig, make_match(), make_event(), config)
    box = extent(fig, top.title)

    # The top margin is 100 px tall; the whole card must stay inside it.
    assert box.y1 <= 960 - 0
    assert box.y0 >= 960 - 100

    bottom_layout = layout.model_copy(update={"text_position": TextPosition.BOTTOM})
    bottom_config = config.model_copy(update={"layout": bottom_layout})
    fig2 = plt.figure(figsize=bottom_config.figure_size_inches, dpi=bottom_config.dpi)
    bottom = EventOverlay.from_match(fig2, make_match(), make_event(), bottom_config)
    box = extent(fig2, bottom.subtitle)

    assert box.y1 <= 300
    assert box.y0 >= 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"title_color": "not-a-color"},
        {"chip_alpha": 1.5},
        {"title_font_size": 0},
        {"subtitle_font_size": -1},
        {"chip_padding": -0.1},
        {"line_gap": -1},
        {"max_team_name_chars": 1},
    ],
)
def test_invalid_overlay_styles_are_rejected(kwargs):
    with pytest.raises(ValueError):
        OverlayStyle(**kwargs)


# --- fit check --------------------------------------------------------------------------------


def video_figure(config: VideoConfig):
    return plt.figure(figsize=config.figure_size_inches, dpi=config.dpi)


def layout_config(width=1080, height=1920, dpi=100, **layout) -> VideoConfig:
    layout.setdefault("margin_left", 0)
    layout.setdefault("margin_right", 0)

    return VideoConfig(width=width, height=height, dpi=dpi, layout=VideoLayoutConfig(**layout))


def test_card_that_fits_the_margin_is_accepted():
    config = layout_config(margin_top=320, margin_bottom=320, text_gap=16)
    fig = video_figure(config)

    overlay = EventOverlay.from_match(fig, make_match(), make_event(), config)

    assert overlay.window_extent().y1 <= config.height


def test_card_in_a_too_small_top_margin_is_rejected():
    config = layout_config(margin_top=16, margin_bottom=320, text_gap=16)
    fig = video_figure(config)

    with pytest.raises(OverlayLayoutError, match="top margin"):
        EventOverlay.from_match(fig, make_match(), make_event(), config)


def test_card_in_a_too_small_bottom_margin_is_rejected():
    config = layout_config(
        margin_top=320, margin_bottom=16, text_gap=16, text_position=TextPosition.BOTTOM
    )
    fig = video_figure(config)

    with pytest.raises(OverlayLayoutError, match="bottom margin"):
        EventOverlay.from_match(fig, make_match(), make_event(), config)


def test_error_reports_needed_and_free_space():
    config = layout_config(margin_top=60, margin_bottom=320, text_gap=10)
    fig = video_figure(config)

    with pytest.raises(OverlayLayoutError) as error:
        EventOverlay.from_match(fig, make_match(), make_event(), config)

    assert "50 px are free" in str(error.value)
    assert "60 px margin minus a 10 px gap" in str(error.value)


def test_rejected_overlay_is_removed_from_the_figure():
    config = layout_config(margin_top=16, margin_bottom=320, text_gap=16)
    fig = video_figure(config)

    with pytest.raises(OverlayLayoutError):
        EventOverlay.from_match(fig, make_match(), make_event(), config)

    assert fig.texts == []
    assert fig.artists == []


def test_the_gap_counts_against_the_margin():
    needed = (
        EventOverlay.from_match(
            video_figure(layout_config(margin_top=400, text_gap=0)),
            make_match(),
            make_event(),
            layout_config(margin_top=400, text_gap=0),
        )
        .window_extent()
        .height
    )
    margin = int(needed) + 4

    fits = layout_config(margin_top=margin, text_gap=0)
    EventOverlay.from_match(video_figure(fits), make_match(), make_event(), fits)

    too_tight = layout_config(margin_top=margin, text_gap=8)

    with pytest.raises(OverlayLayoutError):
        EventOverlay.from_match(video_figure(too_tight), make_match(), make_event(), too_tight)


def test_fit_depends_on_the_dpi():
    # The same pixel margin: points shrink at a lower DPI, so the card needs fewer pixels.
    tight = {"margin_top": 110, "margin_bottom": 110, "text_gap": 10}
    style = OverlayStyle(title_font_size=40.0, subtitle_font_size=26.0, line_gap=12.0)

    high = layout_config(dpi=100, **tight)

    with pytest.raises(OverlayLayoutError):
        EventOverlay.from_match(video_figure(high), make_match(), make_event(), high, style=style)

    low = layout_config(width=540, height=960, dpi=50, **tight)
    EventOverlay.from_match(video_figure(low), make_match(), make_event(), low, style=style)


def test_text_wider_than_the_frame_is_rejected():
    config = layout_config(width=540, height=960, dpi=50, margin_top=300, margin_bottom=300)
    style = OverlayStyle(title_font_size=90.0)

    with pytest.raises(OverlayLayoutError, match="wide"):
        EventOverlay.from_match(
            video_figure(config), make_match(), make_event(), config, style=style
        )


def test_window_extent_covers_title_and_chip(fig):
    overlay = make_overlay(fig)
    box = overlay.window_extent()
    chip = overlay.subtitle.get_bbox_patch().get_window_extent()

    assert box.y0 <= chip.y0 and box.y1 >= extent(fig, overlay.title).y1
    assert box.x0 <= chip.x0 and box.x1 >= chip.x1

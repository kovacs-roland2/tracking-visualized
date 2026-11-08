import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

from tracking_visualized.config import (  # noqa: E402
    PitchOrientation,
    RenderingConfig,
    VideoConfig,
    VideoLayoutConfig,
)
from tracking_visualized.domain import (  # noqa: E402
    BallPosition,
    CoordinateSystem,
    Event,
    EventType,
    Frame,
    Match,
    MatchMetadata,
    MatchTime,
    PeriodType,
    Player,
    PlayerPosition,
    ShotOutcome,
    Team,
    TeamSide,
)
from tracking_visualized.processing import EventSequence  # noqa: E402
from tracking_visualized.rendering import (  # noqa: E402
    BallLayer,
    EventLayer,
    EventStyle,
    PitchDimensions,
    PitchStyle,
    PlayerLayer,
    TrailLayer,
    build_sequence_scene,
    create_video_animator,
    draw_pitch,
    pitch_data_transform,
    pitch_view_transform,
    resolve_team_styles,
)

HOME = Team(team_id="home", name="Home FC", side=TeamSide.HOME)
AWAY = Team(team_id="away", name="Away FC", side=TeamSide.AWAY)
PLAYERS = (
    Player(player_id="h9", team_id="home", shirt_number=9),
    Player(player_id="a1", team_id="away", shirt_number=1),
)
STYLES = resolve_team_styles((HOME, AWAY))

PITCH = PitchDimensions(length=100.0, width=64.0)
PADDING = PitchStyle().padding


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def make_frame(index: int, x: float, y: float) -> Frame:
    return Frame(
        frame_index=index,
        time=MatchTime(period=PeriodType.FIRST_HALF, seconds=index / 25),
        player_positions=(
            PlayerPosition(player_id="h9", x=x, y=y),
            PlayerPosition(player_id="a1", x=50.0, y=32.0),
        ),
        ball_position=BallPosition(x=x, y=y),
    )


def make_match(frames: tuple[Frame, ...]) -> Match:
    return Match(
        metadata=MatchMetadata(match_id="m1", competition="Liga", season="2026"),
        coordinate_system=CoordinateSystem(pitch_length=PITCH.length, pitch_width=PITCH.width),
        periods=(),
        teams=(HOME, AWAY),
        players=PLAYERS,
        frames=frames,
        events=(),
    )


def make_event_sequence(frames: tuple[Frame, ...]) -> EventSequence:
    event = Event(
        event_id="e1",
        event_type=EventType.SHOT,
        time=frames[0].time,
        team_id="home",
        player_id="h9",
        x=90.0,
        y=10.0,
        frame_index=frames[0].frame_index,
        shot_outcome=ShotOutcome.GOAL,
    )

    return EventSequence(
        event=event,
        frames=frames,
        requested_pre_seconds=1.0,
        requested_post_seconds=1.0,
        start_time=frames[0].time,
        end_time=frames[-1].time,
    )


def vertical_axes():
    fig, ax = plt.subplots()
    draw_pitch(ax, PITCH, orientation=PitchOrientation.VERTICAL)
    transform = pitch_data_transform(ax, PITCH, PitchOrientation.VERTICAL)
    fig.canvas.draw()

    return ax, transform


def screen(transform, point: tuple[float, float]) -> np.ndarray:
    return transform.transform(point)


def test_horizontal_view_transform_changes_nothing():
    transform = pitch_view_transform(PITCH, PitchOrientation.HORIZONTAL)

    assert transform.transform((12.0, 34.0)).tolist() == [12.0, 34.0]


def test_vertical_view_transform_rotates_the_pitch_by_90_degrees():
    transform = pitch_view_transform(PITCH, PitchOrientation.VERTICAL)

    # x runs up the screen, y runs to the left: a rotation, not a mirror image.
    assert transform.transform((0.0, 0.0)).tolist() == [PITCH.width, 0.0]
    assert transform.transform((PITCH.length, 0.0)).tolist() == [PITCH.width, PITCH.length]
    assert transform.transform((0.0, PITCH.width)).tolist() == [0.0, 0.0]
    assert transform.transform((PITCH.length, PITCH.width)).tolist() == [0.0, PITCH.length]


def test_vertical_pitch_swaps_axes_limits():
    ax = draw_pitch(dimensions=PITCH, orientation=PitchOrientation.VERTICAL)

    assert ax.get_xlim() == (-PADDING, PITCH.width + PADDING)
    assert ax.get_ylim() == (-PADDING, PITCH.length + PADDING)


def test_vertical_pitch_is_taller_than_wide_on_screen():
    ax, _ = vertical_axes()
    boundary = next(p for p in ax.patches if p.get_gid() == "boundaries")
    box = boundary.get_window_extent()

    assert box.height / box.width == pytest.approx(PITCH.length / PITCH.width)


def test_vertical_pitch_markings_are_rotated_with_the_pitch():
    ax, _ = vertical_axes()
    halfway = next(line for line in ax.lines if line.get_gid() == "halfway_line")
    penalty_left = next(p for p in ax.patches if p.get_gid() == "penalty_area_left")
    penalty_right = next(p for p in ax.patches if p.get_gid() == "penalty_area_right")
    to_data = ax.transData.inverted()

    # The halfway line is horizontal on screen, the left penalty area at the bottom.
    (x0, y0), (x1, y1) = to_data.transform(halfway.get_transform().transform(halfway.get_xydata()))
    assert y0 == pytest.approx(y1)

    assert (
        to_data.transform(penalty_left.get_window_extent().get_points()).mean(axis=0)[1]
        < to_data.transform(penalty_right.get_window_extent().get_points()).mean(axis=0)[1]
    )


def test_players_follow_the_rotation_but_keep_canonical_frames():
    ax, transform = vertical_axes()
    layer = PlayerLayer(ax, PLAYERS, STYLES, transform=transform)

    layer.update(make_frame(0, x=100.0, y=0.0))

    marker = layer.markers["home"]

    # Canonical offsets are untouched; only the transform rotates them.
    assert marker.get_offsets().tolist() == [[100.0, 0.0]]
    assert screen(marker.get_offset_transform(), (100.0, 0.0)) == pytest.approx(
        screen(ax.transData, (PITCH.width, PITCH.length))
    )
    assert screen(layer.labels["h9"].get_transform(), layer.labels["h9"].get_position()) == (
        pytest.approx(screen(ax.transData, (PITCH.width, PITCH.length)))
    )


def test_ball_follows_the_rotation():
    ax, transform = vertical_axes()
    layer = BallLayer(ax, pitch=PITCH, transform=transform)

    layer.update(make_frame(0, x=100.0, y=64.0))

    assert layer.is_visible
    assert screen(layer.marker.get_offset_transform(), (100.0, 64.0)) == pytest.approx(
        screen(ax.transData, (0.0, PITCH.length))
    )


def test_trails_follow_the_rotation():
    ax, transform = vertical_axes()
    layer = TrailLayer(ax, PLAYERS, STYLES, duration_seconds=1.0, transform=transform)

    layer.update(make_frame(0, x=10.0, y=10.0))
    layer.update(make_frame(1, x=20.0, y=10.0))

    collection = layer.lines["home"]
    start, end = collection.get_segments()[0]

    assert screen(collection.get_transform(), start) == pytest.approx(
        screen(ax.transData, (PITCH.width - 10.0, 10.0))
    )
    assert screen(collection.get_transform(), end) == pytest.approx(
        screen(ax.transData, (PITCH.width - 10.0, 20.0))
    )


def test_event_marker_rotates_but_the_banner_stays_upright():
    ax, transform = vertical_axes()
    frames = (make_frame(0, x=50.0, y=32.0),)
    event = make_event_sequence(frames).event
    layer = EventLayer(ax, event, shirt_number=9, transform=transform)

    layer.update(frames[0])

    assert screen(layer.marker.get_offset_transform(), (90.0, 10.0)) == pytest.approx(
        screen(ax.transData, (PITCH.width - 10.0, 90.0))
    )
    assert layer.label.get_transform() == ax.transAxes
    assert layer.label.get_rotation() == 0


def test_layers_default_to_axes_data_coordinates():
    ax = draw_pitch(dimensions=PITCH)
    layer = PlayerLayer(ax, PLAYERS, STYLES)

    assert layer.markers["home"].get_offset_transform() == ax.transData


def test_scene_orientation_rotates_the_whole_scene():
    frames = (make_frame(0, x=100.0, y=0.0), make_frame(1, x=100.0, y=0.0))
    scene = build_sequence_scene(
        make_match(frames),
        make_event_sequence(frames),
        orientation=PitchOrientation.VERTICAL,
    )
    scene.fig.canvas.draw()

    assert scene.ax.get_ylim() == (-PADDING, PITCH.length + PADDING)

    for layer in scene.layers:
        layer.update(frames[0])

    trails, players, ball, event = scene.layers
    corner = screen(scene.ax.transData, (PITCH.width, PITCH.length))

    assert screen(players.markers["home"].get_offset_transform(), (100.0, 0.0)) == (
        pytest.approx(corner)
    )
    assert screen(ball.marker.get_offset_transform(), (100.0, 0.0)) == pytest.approx(corner)
    assert event.marker.get_offset_transform() != scene.ax.transData


def test_trail_line_width_comes_from_rendering_config():
    frames = (make_frame(0, x=50.0, y=32.0),)
    scene = build_sequence_scene(
        make_match(frames),
        make_event_sequence(frames),
        config=RenderingConfig(trail_line_width=4.0),
    )
    trails = scene.layers[0]

    assert trails.lines["home"].get_linewidth()[0] == 4.0


# --- video layout -----------------------------------------------------------------------------

LAYOUT = VideoLayoutConfig(
    margin_top=80, margin_bottom=160, margin_left=20, margin_right=20, marker_scale=2.0
)
VIDEO = VideoConfig(width=540, height=960, dpi=50, layout=LAYOUT)


def test_video_animator_is_vertical_by_default():
    frames = (make_frame(0, x=50.0, y=32.0), make_frame(1, x=51.0, y=32.0))
    animator = create_video_animator(make_match(frames), make_event_sequence(frames), VIDEO)
    ax = animator.fig.axes[0]

    assert ax.get_ylim() == (-PADDING, PITCH.length + PADDING)


def test_video_animator_places_the_pitch_inside_the_margins_and_centers_it():
    frames = (make_frame(0, x=50.0, y=32.0), make_frame(1, x=51.0, y=32.0))
    animator = create_video_animator(make_match(frames), make_event_sequence(frames), VIDEO)
    fig = animator.fig
    ax = fig.axes[0]
    fig.canvas.draw()

    # The configured box is 500 x 720 px of the 540 x 960 px frame.
    left, bottom, width, height = ax.get_position(original=True).bounds

    assert (left, bottom) == pytest.approx((20 / 540, 160 / 960))
    assert (width, height) == pytest.approx((500 / 540, 720 / 960))

    # The 70 x 106 m padded pitch is height-limited: 720 px tall, ~475 px wide, centered.
    active = ax.get_position()
    active_px = active.width * 540, active.height * 960
    view_width, view_height = PITCH.width + 2 * PADDING, PITCH.length + 2 * PADDING

    assert active_px[1] == pytest.approx(720)
    assert active_px[0] == pytest.approx(720 * view_width / view_height)
    assert active.x0 * 540 == pytest.approx((540 - active_px[0]) / 2)
    assert active.y0 * 960 == pytest.approx(160)


def test_video_pitch_never_enters_the_margins():
    frames = (make_frame(0, x=50.0, y=32.0), make_frame(1, x=51.0, y=32.0))
    animator = create_video_animator(make_match(frames), make_event_sequence(frames), VIDEO)
    animator.fig.canvas.draw()

    background = next(p for p in animator.fig.axes[0].patches if p.get_gid() == "pitch_background")
    box = background.get_window_extent()

    assert box.x0 >= 20 - 1e-6
    assert box.x1 <= 540 - 20 + 1e-6
    assert box.y0 >= 160 - 1e-6
    assert box.y1 <= 960 - 80 + 1e-6


def test_horizontal_video_layout_is_supported():
    layout = LAYOUT.model_copy(update={"orientation": PitchOrientation.HORIZONTAL})
    video = VIDEO.model_copy(update={"layout": layout})
    frames = (make_frame(0, x=50.0, y=32.0), make_frame(1, x=51.0, y=32.0))
    animator = create_video_animator(make_match(frames), make_event_sequence(frames), video)

    assert animator.fig.axes[0].get_xlim() == (-PADDING, PITCH.length + PADDING)


def test_marker_scale_enlarges_markers_trails_and_pitch_lines():
    frames = (make_frame(0, x=50.0, y=32.0), make_frame(1, x=51.0, y=32.0))
    base = RenderingConfig()
    animator = create_video_animator(
        make_match(frames), make_event_sequence(frames), VIDEO, config=base
    )
    trails, players, ball, event = animator.layers
    boundary = next(p for p in animator.fig.axes[0].patches if p.get_gid() == "boundaries")
    scale = LAYOUT.marker_scale

    assert players.markers["home"].get_sizes()[0] == pytest.approx(
        (base.player_marker_size * scale) ** 2
    )
    assert ball.marker.get_sizes()[0] == pytest.approx((base.ball_marker_size * scale) ** 2)
    assert trails.lines["home"].get_linewidth()[0] == pytest.approx(base.trail_line_width * scale)
    assert boundary.get_linewidth() == pytest.approx(PitchStyle().line_width * scale)
    assert event.marker.get_sizes()[0] > players.markers["home"].get_sizes()[0]


def test_text_scale_enlarges_the_event_banner():
    frames = (make_frame(0, x=50.0, y=32.0), make_frame(1, x=51.0, y=32.0))
    layout = LAYOUT.model_copy(update={"text_scale": 1.5})
    video = VIDEO.model_copy(update={"layout": layout})
    animator = create_video_animator(make_match(frames), make_event_sequence(frames), video)
    event = animator.layers[-1]

    assert event.label.get_fontsize() == pytest.approx(EventStyle().font_size * 1.5)


def test_explicit_styles_are_not_scaled():
    frames = (make_frame(0, x=50.0, y=32.0), make_frame(1, x=51.0, y=32.0))
    animator = create_video_animator(
        make_match(frames),
        make_event_sequence(frames),
        VIDEO,
        pitch_style=PitchStyle(line_width=1.0),
        event_style=EventStyle(font_size=9.0),
    )
    boundary = next(p for p in animator.fig.axes[0].patches if p.get_gid() == "boundaries")

    assert boundary.get_linewidth() == 1.0
    assert animator.layers[-1].label.get_fontsize() == 9.0

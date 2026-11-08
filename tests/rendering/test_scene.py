import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from tracking_visualized.config import RenderingConfig, VideoConfig  # noqa: E402
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
from tracking_visualized.processing import EventSequence, TimeRangeSequence  # noqa: E402
from tracking_visualized.rendering import (  # noqa: E402
    AnimationSettings,
    BallLayer,
    EventLayer,
    PlayerLayer,
    SequenceAnimator,
    TrailLayer,
    build_sequence_scene,
    create_sequence_animator,
    create_video_animator,
)

HOME = Team(team_id="home", name="Home FC", side=TeamSide.HOME)
AWAY = Team(team_id="away", name="Away FC", side=TeamSide.AWAY)
PLAYERS = (
    Player(player_id="h9", team_id="home", shirt_number=9),
    Player(player_id="a1", team_id="away", shirt_number=1),
)


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def make_frames(count: int = 51) -> tuple[Frame, ...]:
    return tuple(
        Frame(
            frame_index=100 + i,
            time=MatchTime(period=PeriodType.FIRST_HALF, seconds=10.0 + i / 25),
            player_positions=(
                PlayerPosition(player_id="h9", x=50.0 + i * 0.1, y=30.0),
                PlayerPosition(player_id="a1", x=60.0, y=34.0 - i * 0.1),
            ),
            ball_position=BallPosition(x=50.0 + i * 0.1, y=30.0),
        )
        for i in range(count)
    )


def make_match(frames: tuple[Frame, ...], events: tuple[Event, ...] = ()) -> Match:
    return Match(
        metadata=MatchMetadata(match_id="m1", competition="Liga", season="2026"),
        coordinate_system=CoordinateSystem(pitch_length=100.0, pitch_width=64.0),
        periods=(),
        teams=(HOME, AWAY),
        players=PLAYERS,
        frames=frames,
        events=events,
    )


def make_event_sequence(frames: tuple[Frame, ...]) -> EventSequence:
    event = Event(
        event_id="e1",
        event_type=EventType.SHOT,
        time=frames[25].time,
        team_id="home",
        player_id="h9",
        x=52.5,
        y=30.0,
        frame_index=frames[25].frame_index,
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


def make_range_sequence(frames: tuple[Frame, ...]) -> TimeRangeSequence:
    return TimeRangeSequence(frames=frames, start_time=frames[0].time, end_time=frames[-1].time)


def test_event_sequence_scene_has_all_layers_in_drawing_order():
    frames = make_frames()
    scene = build_sequence_scene(make_match(frames), make_event_sequence(frames))

    assert [type(layer) for layer in scene.layers] == [
        TrailLayer,
        PlayerLayer,
        BallLayer,
        EventLayer,
    ]


def test_time_range_scene_has_no_event_layer():
    frames = make_frames()
    scene = build_sequence_scene(make_match(frames), make_range_sequence(frames))

    assert [type(layer) for layer in scene.layers] == [TrailLayer, PlayerLayer, BallLayer]


def test_scene_uses_match_pitch_size():
    frames = make_frames()
    scene = build_sequence_scene(make_match(frames), make_range_sequence(frames))

    # Default padding is 3 m on each side.
    assert scene.ax.get_xlim() == (-3.0, 103.0)
    assert scene.ax.get_ylim() == (-3.0, 67.0)


def test_scene_uses_rendering_config_sizes():
    frames = make_frames()
    config = RenderingConfig(player_marker_size=12.0, ball_marker_size=6.0)
    scene = build_sequence_scene(make_match(frames), make_range_sequence(frames), config=config)
    trails, players, ball = scene.layers

    assert players.markers["home"].get_sizes()[0] == 144.0
    assert ball.marker.get_sizes()[0] == 36.0
    assert trails.duration_seconds == config.trail_duration_seconds


def test_create_animator_uses_config_fps_by_default():
    frames = make_frames()
    animator = create_sequence_animator(
        make_match(frames),
        make_range_sequence(frames),
        config=RenderingConfig(fps=20),
    )

    assert isinstance(animator, SequenceAnimator)
    assert animator.settings.fps == 20
    assert animator.frame_count == 41  # 2 s of tracking at 20 fps


def test_create_animator_accepts_explicit_settings():
    frames = make_frames()
    animator = create_sequence_animator(
        make_match(frames),
        make_range_sequence(frames),
        settings=AnimationSettings(fps=25, speed=2.0),
    )

    assert animator.frame_count == 26


def test_event_sequence_animation_end_to_end(tmp_path):
    frames = make_frames()
    animator = create_sequence_animator(make_match(frames), make_event_sequence(frames))
    *_, event_layer = animator.layers
    visible_at: list[bool] = []

    for index in range(animator.frame_count):
        animator.render_frame(index)
        visible_at.append(event_layer.is_visible)

    # Event at 1 s: shown from 1 s before to 3 s after (whole sequence), hidden never here.
    assert all(visible_at)

    animation = animator.build()
    animation.save(tmp_path / "scene.gif", writer="pillow", fps=animator.settings.fps)

    assert (tmp_path / "scene.gif").stat().st_size > 0


def test_video_animator_uses_a_full_size_figure():
    frames = make_frames()
    video = VideoConfig(width=540, height=960, fps=20, dpi=50)

    animator = create_video_animator(
        make_match(frames), make_range_sequence(frames), video, config=RenderingConfig(fps=25)
    )
    fig = animator.fig

    assert tuple(fig.get_size_inches() * fig.get_dpi()) == (540, 960)
    # The frame rate comes from the video config, not from RenderingConfig.
    assert animator.settings.fps == 20
    assert animator.frame_count == 41  # 2 s of tracking at 20 fps
    assert fig.get_facecolor()[:3] == pytest.approx((0x3A / 255, 0x7D / 255, 0x44 / 255))


def test_video_animator_default_canvas_is_1080_by_1920():
    frames = make_frames()
    animator = create_video_animator(make_match(frames), make_range_sequence(frames))
    animator.fig.canvas.draw()

    assert tuple(animator.fig.canvas.get_width_height()) == (1080, 1920)


def test_video_animator_includes_the_event_layer_for_event_sequences():
    frames = make_frames()
    animator = create_video_animator(make_match(frames), make_event_sequence(frames))

    assert [type(layer) for layer in animator.layers][-1] is EventLayer

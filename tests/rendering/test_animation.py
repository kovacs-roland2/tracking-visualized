import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from matplotlib.animation import FuncAnimation  # noqa: E402

from tracking_visualized.config import RenderingConfig  # noqa: E402
from tracking_visualized.domain import (  # noqa: E402
    BallPosition,
    Frame,
    MatchTime,
    PeriodType,
    Player,
    PlayerPosition,
    Team,
    TeamSide,
)
from tracking_visualized.rendering import (  # noqa: E402
    AnimationError,
    AnimationSettings,
    BallLayer,
    SequenceAnimator,
    TrailLayer,
    animate_sequence,
    build_playback_schedule,
    draw_pitch,
    resolve_team_styles,
)

TRACKING_FPS = 25


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def make_frame(
    index: int,
    seconds: float,
    period: PeriodType = PeriodType.FIRST_HALF,
    x: float | None = None,
) -> Frame:
    return Frame(
        frame_index=index,
        time=MatchTime(period=period, seconds=seconds),
        player_positions=((PlayerPosition(player_id="h1", x=x, y=10.0),) if x is not None else ()),
        ball_position=BallPosition(x=x, y=20.0) if x is not None else None,
    )


def tracking_frames(count: int, *, start_seconds: float = 0.0, start_index: int = 0) -> list[Frame]:
    """Frames at 25 Hz; the ball and player x position equals the frame offset."""

    return [
        make_frame(
            start_index + i,
            start_seconds + i / TRACKING_FPS,
            x=float(i),
        )
        for i in range(count)
    ]


class RecordingLayer:
    def __init__(self) -> None:
        self.frames: list[Frame] = []

    def update(self, frame: Frame):
        self.frames.append(frame)

        return []


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_default_settings():
    settings = AnimationSettings()

    assert (settings.fps, settings.speed) == (25, 1.0)
    assert not settings.repeat
    assert not settings.blit
    assert settings.interval_ms == 40


@pytest.mark.parametrize(
    "kwargs",
    [{"fps": 0}, {"fps": 121}, {"speed": 0}, {"speed": -1.0}, {"speed": float("inf")}],
)
def test_invalid_settings_raise(kwargs):
    with pytest.raises(ValueError):
        AnimationSettings(**kwargs)


def test_settings_from_rendering_config():
    settings = AnimationSettings.from_rendering_config(RenderingConfig(fps=30), repeat=True)

    assert settings.fps == 30
    assert settings.repeat


# ---------------------------------------------------------------------------
# Playback schedule
# ---------------------------------------------------------------------------


def test_empty_sequence_raises():
    with pytest.raises(AnimationError):
        build_playback_schedule([])


def test_multiple_periods_raise():
    frames = [
        make_frame(0, 0.0),
        make_frame(1, 0.04, period=PeriodType.SECOND_HALF),
    ]

    with pytest.raises(AnimationError):
        build_playback_schedule(frames)


def test_unordered_frames_raise():
    with pytest.raises(AnimationError):
        build_playback_schedule([make_frame(0, 1.0), make_frame(1, 0.5)])


def test_single_frame_gives_single_output_frame():
    schedule = build_playback_schedule([make_frame(7, 123.4)])

    assert len(schedule) == 1
    assert schedule[0].frame.frame_index == 7
    assert schedule[0].sync_error_seconds == 0


def test_matching_fps_shows_every_frame_once():
    frames = tracking_frames(26)
    schedule = build_playback_schedule(frames, AnimationSettings(fps=25))

    assert [s.frame.frame_index for s in schedule] == list(range(26))
    assert [s.output_index for s in schedule] == list(range(26))


def test_schedule_is_relative_to_first_frame_time():
    frames = tracking_frames(26, start_seconds=500.0, start_index=12_000)
    schedule = build_playback_schedule(frames)

    assert len(schedule) == 26
    assert schedule[0].target_seconds == 0.0
    assert schedule[-1].frame.frame_index == 12_025


def test_higher_output_fps_repeats_frames():
    frames = tracking_frames(26)  # exactly 1 second
    schedule = build_playback_schedule(frames, AnimationSettings(fps=50))

    assert len(schedule) == 51
    assert max(s.sync_error_seconds for s in schedule) <= 0.02 + 1e-9

    shown = [s.frame.frame_index for s in schedule]

    assert shown == sorted(shown)
    assert set(shown) == set(range(26))


def test_lower_output_fps_skips_frames():
    frames = tracking_frames(26)
    schedule = build_playback_schedule(frames, AnimationSettings(fps=10))

    assert len(schedule) == 11
    assert max(s.sync_error_seconds for s in schedule) <= 0.02 + 1e-9
    assert schedule[-1].frame.frame_index == 25


def test_slow_motion_stretches_playback():
    frames = tracking_frames(26)
    half_speed = build_playback_schedule(frames, AnimationSettings(fps=25, speed=0.5))

    assert len(half_speed) == 51
    assert half_speed[-1].frame.frame_index == 25
    assert [s.frame.frame_index for s in half_speed][:4] == [0, 0, 1, 1]


def test_fast_forward_shortens_playback():
    frames = tracking_frames(26)
    double_speed = build_playback_schedule(frames, AnimationSettings(fps=25, speed=2.0))

    # 1 s of tracking at 0.08 s per output frame: 0.00, 0.08, ... 0.96 s.
    assert len(double_speed) == 13
    assert [s.frame.frame_index for s in double_speed][:4] == [0, 2, 4, 6]


def test_gaps_in_tracking_are_held_not_skipped():
    frames = [
        make_frame(0, 0.00),
        make_frame(1, 0.04),
        make_frame(10, 0.40),  # frames 2..9 missing in the source
    ]
    schedule = build_playback_schedule(frames, AnimationSettings(fps=25))

    # The animation keeps its real duration: 0.4 s at 25 fps -> 11 output frames.
    assert len(schedule) == 11
    assert [s.frame.frame_index for s in schedule[:4]] == [0, 1, 1, 1]
    assert schedule[-1].frame.frame_index == 10
    assert schedule[-1].sync_error_seconds == 0


def test_long_sequences_are_supported():
    frames = tracking_frames(25 * 600 + 1)  # ten minutes
    schedule = build_playback_schedule(frames)

    assert len(schedule) == len(frames)


def test_scheduled_frames_never_run_backwards():
    frames = tracking_frames(60)

    for fps in (7, 24, 25, 30, 60):
        schedule = build_playback_schedule(frames, AnimationSettings(fps=fps))
        indices = [s.frame.frame_index for s in schedule]

        assert indices == sorted(indices)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def test_render_frame_updates_every_layer_with_scheduled_frame():
    fig = plt.figure()
    frames = tracking_frames(5)
    first, second = RecordingLayer(), RecordingLayer()
    animator = SequenceAnimator(fig, frames, [first, second])

    animator.render_frame(3)

    assert first.frames == [frames[3]]
    assert second.frames == [frames[3]]


def test_render_frame_returns_artists_of_all_layers():
    fig = plt.figure()
    ax = draw_pitch(fig.add_subplot())
    frames = tracking_frames(3)
    ball = BallLayer(ax)
    animator = SequenceAnimator(fig, frames, [ball, RecordingLayer()])

    assert animator.render_frame(1) == [ball.marker]


@pytest.mark.parametrize("index", [-1, 5])
def test_render_frame_rejects_out_of_range_index(index):
    animator = SequenceAnimator(plt.figure(), tracking_frames(5), [])

    with pytest.raises(IndexError):
        animator.render_frame(index)


def test_frame_count_and_duration():
    animator = SequenceAnimator(plt.figure(), tracking_frames(51), [], AnimationSettings(fps=25))

    assert animator.frame_count == 51
    assert animator.duration_seconds == pytest.approx(2.0)


def test_build_creates_funcanimation_with_settings(tmp_path):
    settings = AnimationSettings(fps=20, repeat=True, blit=False)
    animator = SequenceAnimator(plt.figure(), tracking_frames(21), [], settings)

    animation = animator.build()

    assert isinstance(animation, FuncAnimation)
    assert animation._interval == 50
    assert animation._repeat is True
    # 21 tracking frames span 0.8 s, i.e. 17 output frames at 20 fps.
    assert animator.frame_count == 17
    assert animation._save_count == 17

    # Render it so Matplotlib does not warn about an animation deleted unused.
    animation.save(tmp_path / "settings.gif", writer="pillow", fps=settings.fps)


def test_animation_saves_every_frame_in_order(tmp_path):
    fig = plt.figure()
    layer = RecordingLayer()
    frames = tracking_frames(6)

    animation = animate_sequence(fig, frames, [layer], AnimationSettings(fps=25))
    animation.save(tmp_path / "sequence.gif", writer="pillow", fps=25)

    assert (tmp_path / "sequence.gif").stat().st_size > 0

    # FuncAnimation draws the first frame once more for its initial draw.
    assert [f.frame_index for f in layer.frames[-6:]] == [0, 1, 2, 3, 4, 5]


def test_animation_drives_real_layers():
    fig, ax = plt.subplots()
    draw_pitch(ax)
    team = Team(team_id="home", name="Home", side=TeamSide.HOME)
    player = Player(player_id="h1", team_id="home", shirt_number=1)
    trails = TrailLayer(ax, (player,), resolve_team_styles((team,)) | {"away": None})
    ball = BallLayer(ax)
    frames = tracking_frames(26)

    animator = SequenceAnimator(fig, frames, [trails, ball])

    for index in range(animator.frame_count):
        animator.render_frame(index)

    assert [tuple(row) for row in ball.marker.get_offsets()] == [(25.0, 20.0)]
    assert len(trails.lines["home"].get_segments()) > 0


def test_downsampled_animation_feeds_intervening_frames_to_trails():
    fig, ax = plt.subplots()
    draw_pitch(ax)
    team = Team(team_id="home", name="Home", side=TeamSide.HOME)
    player = Player(player_id="h1", team_id="home", shirt_number=1)
    trails = TrailLayer(ax, (player,), resolve_team_styles((team,)))
    frames = tracking_frames(51)
    animator = SequenceAnimator(fig, frames, [trails], AnimationSettings(fps=1))

    assert [scheduled.frame.frame_index for scheduled in animator.schedule] == [0, 25, 50]

    for index in range(animator.frame_count):
        animator.render_frame(index)

    assert len(trails.lines["home"].get_segments()) == 50


def test_trails_reset_when_animation_loops():
    fig, ax = plt.subplots()
    draw_pitch(ax)
    team = Team(team_id="home", name="Home", side=TeamSide.HOME)
    player = Player(player_id="h1", team_id="home", shirt_number=1)
    trails = TrailLayer(ax, (player,), resolve_team_styles((team,)))
    animator = SequenceAnimator(fig, tracking_frames(26), [trails])

    for index in range(animator.frame_count):
        animator.render_frame(index)

    assert len(trails.lines["home"].get_segments()) > 0

    animator.render_frame(0)

    assert len(trails.lines["home"].get_segments()) == 0

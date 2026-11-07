from collections import deque
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any

from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.colors import to_rgba

from tracking_visualized.config import RenderingConfig
from tracking_visualized.domain import Frame, Match, PeriodType, Player
from tracking_visualized.rendering.teams import (
    TeamStyle,
    resolve_team_styles,
    validate_team_styles,
)

DEFAULT_MAX_GAP_FRAMES = 5

type TrailPoint = tuple[int, float, float, float]


class TrailLayer:
    """Fading movement trails behind player markers.

    The layer remembers each player's recent positions and redraws them as
    line segments that fade out with age. Artists are created once; ``update``
    only replaces their segments.

    Trails are cut off after ``duration_seconds`` of source match time. A trail
    is broken where a player has no observed position for more than
    ``max_gap_frames`` frames, so lines are never drawn across long tracking
    gaps.

    History is cleared automatically when frames go backwards, when the match
    period changes, and can be cleared explicitly with ``reset``.
    Updating again with the same frame index does not add a duplicate point.
    """

    def __init__(
        self,
        ax: Axes,
        players: Sequence[Player],
        team_styles: Mapping[str, TeamStyle],
        *,
        duration_seconds: float = 2.0,
        line_width: float = 2.0,
        max_alpha: float = 0.6,
        max_gap_frames: int = DEFAULT_MAX_GAP_FRAMES,
        zorder: float = 2.0,
    ) -> None:
        if duration_seconds < 0:
            raise ValueError("duration_seconds must not be negative.")

        if line_width <= 0:
            raise ValueError("line_width must be positive.")

        if not 0 < max_alpha <= 1:
            raise ValueError("max_alpha must be in (0, 1].")

        if max_gap_frames < 1:
            raise ValueError("max_gap_frames must be at least 1.")

        validate_team_styles(players, team_styles)

        self.duration_seconds = duration_seconds

        self._max_alpha = max_alpha
        self._max_gap_frames = max_gap_frames

        self._players = {player.player_id: player for player in players}
        self._team_ids = tuple(dict.fromkeys(player.team_id for player in players))
        self._team_colors = {
            team_id: to_rgba(team_styles[team_id].marker_color) for team_id in self._team_ids
        }

        self._history: dict[str, deque[TrailPoint]] = {
            player.player_id: deque() for player in players
        }
        self._last_frame_index: int | None = None
        self._last_period: PeriodType | None = None

        self.lines: dict[str, LineCollection] = {}

        for team_id in self._team_ids:
            collection = LineCollection(
                [],
                linewidths=line_width,
                capstyle="round",
                zorder=zorder,
                gid=f"trails_{team_id}",
            )
            ax.add_collection(collection, autolim=False)
            self.lines[team_id] = collection

    @classmethod
    def from_match(
        cls,
        ax: Axes,
        match: Match,
        config: RenderingConfig | None = None,
        *,
        home_style: TeamStyle | None = None,
        away_style: TeamStyle | None = None,
        **kwargs: Any,
    ) -> "TrailLayer":
        """Create a layer for all players of a match.

        Trail duration comes from ``config`` (RenderingConfig defaults when
        omitted). Expiry is measured against source timestamps, independently
        of the output rendering frame rate.
        """

        config = config or RenderingConfig()

        return cls(
            ax,
            match.players,
            resolve_team_styles(match.teams, home=home_style, away=away_style),
            duration_seconds=config.trail_duration_seconds,
            **kwargs,
        )

    @property
    def artists(self) -> list[Artist]:
        return list(self.lines.values())

    def reset(self) -> None:
        """Forget all stored positions and clear the drawn trails."""

        for history in self._history.values():
            history.clear()

        self._last_frame_index = None
        self._last_period = None

        for collection in self.lines.values():
            collection.set_segments([])

    def update(self, frame: Frame) -> list[Artist]:
        """Add ``frame`` to the trail history and redraw the trails.

        Returns:
            All artists of the layer, as expected by Matplotlib's FuncAnimation.
        """

        self.update_history(frame)
        self._redraw(frame.time.seconds)

        return self.artists

    def update_history(self, frame: Frame) -> None:
        """Advance trail history without redrawing the current artists."""

        index = frame.frame_index
        period = frame.time.period

        period_changed = self._last_period is not None and period != self._last_period
        index_went_backwards = self._last_frame_index is not None and index < self._last_frame_index

        if period_changed or index_went_backwards:
            self.reset()

        if self._last_frame_index is None or index > self._last_frame_index:
            self._record(frame)

        self._last_frame_index = index
        self._last_period = period
        self._prune(frame.time.seconds)

    def _record(self, frame: Frame) -> None:
        """Record the positions of all observed players in the current frame."""
        for position in frame.player_positions:
            if position.player_id not in self._players or not position.is_observed:
                continue

            self._history[position.player_id].append(
                (frame.frame_index, frame.time.seconds, position.x, position.y)
            )

    def _prune(self, current_seconds: float) -> None:
        """Remove old positions that are outside the source-time window."""
        oldest_kept = current_seconds - self.duration_seconds

        for history in self._history.values():
            while history and history[0][1] < oldest_kept:
                history.popleft()

    def _redraw(self, current_seconds: float) -> None:
        """Redraw trails based on the current source timestamp."""
        segments: dict[str, list[list[tuple[float, float]]]] = {t: [] for t in self._team_ids}
        colors: dict[str, list[tuple[float, float, float, float]]] = {t: [] for t in self._team_ids}

        if self.duration_seconds > 0:
            for player_id, history in self._history.items():
                team_id = self._players[player_id].team_id
                red, green, blue, _ = self._team_colors[team_id]

                for (start_index, _, x0, y0), (end_index, end_seconds, x1, y1) in pairwise(history):
                    if end_index - start_index > self._max_gap_frames:
                        continue

                    age = current_seconds - end_seconds
                    alpha = self._max_alpha * (1 - age / self.duration_seconds)

                    segments[team_id].append([(x0, y0), (x1, y1)])
                    colors[team_id].append((red, green, blue, max(alpha, 0.0)))

        for team_id, collection in self.lines.items():
            collection.set_segments(segments[team_id])
            collection.set_color(colors[team_id] or [(0.0, 0.0, 0.0, 0.0)])


__all__ = [
    "TrailLayer",
]

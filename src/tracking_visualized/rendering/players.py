from collections.abc import Mapping, Sequence

import numpy as np
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.text import Text

from tracking_visualized.domain import Frame, Match, Player
from tracking_visualized.rendering.teams import TeamStyle, resolve_team_styles

NUMBER_FONT_SCALE = 0.55
NUMBER_ZORDER_OFFSET = 0.1


class PlayerLayer:
    """Player markers and shirt numbers that can be moved frame by frame.

    Artists are created once; ``update`` only moves or hides them, which
    keeps per-frame rendering cheap for animations.

    Players that are missing from a frame, or whose position is not
    observed, are hidden until they reappear.
    """

    def __init__(
        self,
        ax: Axes,
        players: Sequence[Player],
        team_styles: Mapping[str, TeamStyle],
        *,
        marker_size: float = 10.0,
        zorder: float = 3.0,
    ) -> None:
        if marker_size <= 0:
            raise ValueError("marker_size must be positive.")

        for player in players:
            if player.team_id not in team_styles:
                raise ValueError(
                    f"No style for team '{player.team_id}' of player '{player.player_id}'."
                )

        self._players = {player.player_id: player for player in players}
        self._team_ids = tuple(dict.fromkeys(player.team_id for player in players))

        self.unknown_player_ids: frozenset[str] = frozenset()
        self.visible_player_ids: frozenset[str] = frozenset()

        self.markers: dict[str, PathCollection] = {}

        for team_id in self._team_ids:
            style = team_styles[team_id]

            self.markers[team_id] = ax.scatter(
                [],
                [],
                s=marker_size**2,
                facecolors=style.marker_color,
                edgecolors=style.edge_color,
                linewidths=style.edge_width,
                zorder=zorder,
                gid=f"players_{team_id}",
            )

        self.labels: dict[str, Text] = {}

        for player in players:
            if player.shirt_number is None:
                continue

            style = team_styles[player.team_id]

            self.labels[player.player_id] = ax.text(
                0,
                0,
                str(player.shirt_number),
                color=style.number_color,
                fontsize=marker_size * NUMBER_FONT_SCALE,
                fontweight="bold",
                ha="center",
                va="center",
                zorder=zorder + NUMBER_ZORDER_OFFSET,
                visible=False,
                gid=f"player_number_{player.player_id}",
            )

    @classmethod
    def from_match(
        cls,
        ax: Axes,
        match: Match,
        *,
        home_style: TeamStyle | None = None,
        away_style: TeamStyle | None = None,
        marker_size: float = 10.0,
        zorder: float = 3.0,
    ) -> "PlayerLayer":
        """Create a layer for all players of a match."""

        return cls(
            ax,
            match.players,
            resolve_team_styles(match.teams, home=home_style, away=away_style),
            marker_size=marker_size,
            zorder=zorder,
        )

    @property
    def artists(self) -> list[Artist]:
        return [*self.markers.values(), *self.labels.values()]

    def update(self, frame: Frame) -> list[Artist]:
        """Move markers and numbers to the positions in ``frame``.

        Returns:
            All artists of the layer, as expected by Matplotlib's FuncAnimation.
        """

        offsets: dict[str, list[tuple[float, float]]] = {team_id: [] for team_id in self._team_ids}
        visible: set[str] = set()
        unknown: set[str] = set()

        for position in frame.player_positions:
            player = self._players.get(position.player_id)

            if player is None:
                unknown.add(position.player_id)
                continue

            if not position.is_observed:
                continue

            offsets[player.team_id].append((position.x, position.y))
            visible.add(player.player_id)

            label = self.labels.get(player.player_id)

            if label is not None:
                label.set_position((position.x, position.y))

        for team_id, marker in self.markers.items():
            marker.set_offsets(np.array(offsets[team_id], dtype=float).reshape(-1, 2))

        for player_id, label in self.labels.items():
            label.set_visible(player_id in visible)

        self.visible_player_ids = frozenset(visible)
        self.unknown_player_ids = frozenset(unknown)

        return self.artists


def draw_players(
    ax: Axes,
    frame: Frame,
    players: Sequence[Player],
    team_styles: Mapping[str, TeamStyle],
    *,
    marker_size: float = 10.0,
) -> PlayerLayer:
    """Draw players for a single frame, e.g. for still images."""

    layer = PlayerLayer(ax, players, team_styles, marker_size=marker_size)
    layer.update(frame)

    return layer


__all__ = [
    "PlayerLayer",
    "draw_players",
]

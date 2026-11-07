from collections.abc import Iterable

from matplotlib.colors import is_color_like


def validate_colors(style: object, names: Iterable[str]) -> None:
    """Raise ValueError if any named attribute of ``style`` is not a Matplotlib color."""

    for name in names:
        value = getattr(style, name)

        if not is_color_like(value):
            raise ValueError(f"{name} is not a valid color: {value!r}.")

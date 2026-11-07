import math

import pytest

from tracking_visualized.domain import CoordinateSystem
from tracking_visualized.providers.dfl import (
    DflCoordinateError,
    is_on_pitch,
    normalize_tracking_coordinates,
    validate_event_coordinates,
)


@pytest.fixture
def pitch() -> CoordinateSystem:
    return CoordinateSystem(
        pitch_length=105.0,
        pitch_width=68.0,
    )


def test_tracking_center_maps_to_pitch_center(
    pitch: CoordinateSystem,
):
    x, y = normalize_tracking_coordinates(
        0.0,
        0.0,
        pitch,
    )

    assert x == 52.5
    assert y == 34.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ((-52.5, -34.0), (0.0, 0.0)),
        ((-52.5, 34.0), (0.0, 68.0)),
        ((52.5, -34.0), (105.0, 0.0)),
        ((52.5, 34.0), (105.0, 68.0)),
    ],
)
def test_tracking_corners(
    pitch: CoordinateSystem,
    raw: tuple[float, float],
    expected: tuple[float, float],
):
    assert (
        normalize_tracking_coordinates(
            *raw,
            pitch,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ((0.0, 0.0), (0.0, 0.0)),
        ((0.0, 68.0), (0.0, 68.0)),
        ((105.0, 0.0), (105.0, 0.0)),
        ((105.0, 68.0), (105.0, 68.0)),
        ((52.5, 34.0), (52.5, 34.0)),
    ],
)
def test_event_coordinates_are_validated_without_conversion(
    raw: tuple[float, float],
    expected: tuple[float, float],
):
    assert (
        validate_event_coordinates(
            *raw,
        )
        == expected
    )


def test_tracking_missing_coordinates_are_preserved(
    pitch: CoordinateSystem,
):
    assert normalize_tracking_coordinates(
        None,
        None,
        pitch,
    ) == (None, None)


def test_event_missing_coordinates_are_preserved():
    assert validate_event_coordinates(
        None,
        None,
    ) == (None, None)


@pytest.mark.parametrize(
    "value",
    [
        math.nan,
        math.inf,
        -math.inf,
    ],
)
def test_tracking_rejects_non_finite_coordinates(
    pitch: CoordinateSystem,
    value: float,
):
    with pytest.raises(
        DflCoordinateError,
        match="finite",
    ):
        normalize_tracking_coordinates(
            value,
            0.0,
            pitch,
        )


def test_coordinate_inside_pitch(
    pitch: CoordinateSystem,
):
    assert is_on_pitch(
        52.5,
        34.0,
        pitch,
    )


def test_coordinate_outside_pitch(
    pitch: CoordinateSystem,
):
    assert not is_on_pitch(
        106.0,
        34.0,
        pitch,
    )


def test_validated_event_center_matches_canonical_tracking_center(
    pitch: CoordinateSystem,
):
    tracking = normalize_tracking_coordinates(
        0.0,
        0.0,
        pitch,
    )

    event = validate_event_coordinates(
        52.5,
        34.0,
    )

    assert tracking == event
    assert tracking == (52.5, 34.0)


def test_event_and_tracking_coordinates_agree_for_the_same_spot(
    pitch: CoordinateSystem,
):
    # Real sample-match goal: the shooter was tracked at (37.03, 13.48) in centered
    # Sportec coordinates, and the event was recorded at (89.51, 47.63).
    tracked = normalize_tracking_coordinates(37.03, 13.48, pitch)
    event = validate_event_coordinates(89.51, 47.63)

    assert tracked == pytest.approx((89.53, 47.48))
    assert event == pytest.approx(tracked, abs=0.25)


def test_event_rejects_non_finite_coordinates():
    with pytest.raises(DflCoordinateError, match="finite"):
        validate_event_coordinates(0.0, math.nan)

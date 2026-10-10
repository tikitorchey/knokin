import math

import pytest

from knokin_core.coords import angular_diff, camera_position, direction, look_direction, norm_theta


def close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


@pytest.mark.parametrize(
    "theta,phi,expected",
    [
        (90, 0, (1, 0, 0)),  # spec check: camera on +X
        (0, 0, (0, -1, 0)),  # theta zero: camera on -Y
        (180, 0, (0, 1, 0)),
        (270, 0, (-1, 0, 0)),
        (0, 90, (0, 0, 1)),
        (123, -90, (0, 0, -1)),
    ],
)
def test_direction(theta, phi, expected):
    assert close(direction(theta, phi), expected)


def test_theta_is_ccw_seen_from_above():
    # moving from theta=0 (-Y) to theta=90 (+X) must rotate counter-clockwise about +Z
    a, b = direction(0, 0), direction(90, 0)
    assert a[0] * b[1] - a[1] * b[0] > 0


def test_phi_up_positive():
    assert direction(40, 30)[2] > 0 > direction(40, -30)[2]


def test_camera_position_uses_pivot_and_distance():
    assert close(camera_position(90, 0, 3.0, (0, 0, 0.9)), (3, 0, 0.9))


def test_unit_vector_and_look_direction():
    d = direction(37, 21)
    assert math.isclose(sum(c * c for c in d), 1.0)
    assert close(look_direction(37, 21), tuple(-c for c in d))


def test_norm_theta():
    assert norm_theta(-30) == 330
    assert norm_theta(360) == 0
    assert norm_theta(725) == 5
    assert norm_theta(-1e-18) == 0
    assert angular_diff(359, 1) == 2

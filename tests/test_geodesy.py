import math

import pytest

from neoreef.common import geodesy as g


def test_survey_area_defaults():
    assert g.SURVEY_AREA["center_lon"] == pytest.approx(124.205)
    assert g.SURVEY_AREA["center_lat"] == pytest.approx(24.470)
    assert g.SURVEY_AREA["default_altitude_m"] == 15000


def test_geodetic_to_ecef_reference_points():
    x, y, z = g.geodetic_to_ecef(0, 0, 0)
    assert (x, y, z) == pytest.approx((g.WGS84_A, 0, 0), abs=1e-6)
    x, y, z = g.geodetic_to_ecef(90, 0, 0)
    assert (x, y, z) == pytest.approx((0, g.WGS84_A, 0), abs=1e-6)
    x, y, z = g.geodetic_to_ecef(0, 90, 0)
    b = g.WGS84_A * (1 - g.WGS84_F)
    assert (x, y, z) == pytest.approx((0, 0, b), abs=1e-6)


def _col(m, i):
    return m[4 * i:4 * i + 3]


def test_enu_matrix_is_rigid_and_places_origin():
    m = g.enu_to_ecef_matrix(124.205, 24.470, 5.0)
    assert len(m) == 16
    assert m[3] == m[7] == m[11] == 0.0 and m[15] == 1.0
    cols = [_col(m, i) for i in range(3)]
    for c in cols:
        assert math.sqrt(sum(v * v for v in c)) == pytest.approx(1.0)
    for i in range(3):
        for j in range(i + 1, 3):
            assert sum(a * b for a, b in zip(cols[i], cols[j])) == pytest.approx(0.0, abs=1e-12)
    assert tuple(_col(m, 3)) == pytest.approx(g.geodetic_to_ecef(124.205, 24.470, 5.0))


def test_enu_axes_at_equator_prime_meridian():
    m = g.enu_to_ecef_matrix(0, 0, 0)
    assert _col(m, 0) == pytest.approx([0, 1, 0], abs=1e-12)   # east  -> +Y
    assert _col(m, 1) == pytest.approx([0, 0, 1], abs=1e-12)   # north -> +Z
    assert _col(m, 2) == pytest.approx([1, 0, 0], abs=1e-12)   # up    -> +X


def test_heading_rotates_about_up():
    m0 = g.enu_to_ecef_matrix(0, 0, 0, heading_deg=0)
    m90 = g.enu_to_ecef_matrix(0, 0, 0, heading_deg=90)
    # With heading 90 (clockwise from north), the model's +Y axis points east.
    assert _col(m90, 1) == pytest.approx(_col(m0, 0), abs=1e-12)
    assert _col(m90, 2) == pytest.approx(_col(m0, 2), abs=1e-12)  # up unchanged

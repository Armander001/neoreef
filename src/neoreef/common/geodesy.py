"""Survey-area constants and the WGS84 maths needed to place local-frame models.

Underwater surveys are processed without GPS (Metashape local coordinates),
so a 3D tileset only becomes visible on the globe once a ``root.transform``
maps its local east-north-up frame onto Earth-centred, Earth-fixed (ECEF)
coordinates. :func:`enu_to_ecef_matrix` builds that 4x4 matrix in the
column-major order that 3D Tiles and CesiumJS expect.
"""

from __future__ import annotations

import math
from typing import List, Tuple

#: Default camera target / manifest ``survey_area``. Previously hard-coded in
#: the pipeline and as a fallback in all three viewers.
SURVEY_AREA = {
    "name": "Ishigaki Island",
    "center_lon": 124.205,
    "center_lat": 24.470,
    "default_altitude_m": 15000,
}

# WGS84 ellipsoid
WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


def geodetic_to_ecef(lon_deg: float, lat_deg: float, height_m: float = 0.0) -> Tuple[float, float, float]:
    """Longitude/latitude (degrees) + ellipsoidal height (m) -> ECEF metres."""
    lon = math.radians(lon_deg)
    lat = math.radians(lat_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + height_m) * cos_lat * math.cos(lon)
    y = (n + height_m) * cos_lat * math.sin(lon)
    z = (n * (1.0 - WGS84_E2) + height_m) * sin_lat
    return x, y, z


def enu_to_ecef_matrix(lon_deg: float, lat_deg: float, height_m: float = 0.0,
                       heading_deg: float = 0.0) -> List[float]:
    """4x4 column-major transform from a local ENU frame to ECEF.

    *heading_deg* rotates the model about its local up axis, clockwise from
    north, before placement (so a survey laid out with +Y pointing north-east
    uses ``heading_deg=45``).

    Returns 16 floats in column-major order, directly usable as
    ``tileset.json`` ``root.transform`` or ``Cesium.Matrix4.fromArray``.
    """
    lon = math.radians(lon_deg)
    lat = math.radians(lat_deg)
    sl, cl = math.sin(lon), math.cos(lon)
    sp, cp = math.sin(lat), math.cos(lat)

    # ENU basis vectors expressed in ECEF (columns of the rotation matrix).
    east = (-sl, cl, 0.0)
    north = (-sp * cl, -sp * sl, cp)
    up = (cp * cl, cp * sl, sp)

    # Heading: rotate the ENU frame about "up" (clockwise from north).
    h = math.radians(heading_deg)
    ch, sh = math.cos(h), math.sin(h)
    x_axis = tuple(ch * e - sh * n for e, n in zip(east, north))
    y_axis = tuple(sh * e + ch * n for e, n in zip(east, north))

    tx, ty, tz = geodetic_to_ecef(lon_deg, lat_deg, height_m)

    return [
        x_axis[0], x_axis[1], x_axis[2], 0.0,
        y_axis[0], y_axis[1], y_axis[2], 0.0,
        up[0],     up[1],     up[2],     0.0,
        tx,        ty,        tz,        1.0,
    ]

// Camera helpers.

export function bboxToRect(bbox) {
  return bbox ? Cesium.Rectangle.fromDegrees(bbox[0], bbox[1], bbox[2], bbox[3]) : null;
}

export function flyToIsland(viewer, manifest, { altitude = null, pitchDeg = -45, duration = 2.0 } = {}) {
  const sa = manifest.survey_area;
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(sa.center_lon, sa.center_lat, altitude ?? sa.default_altitude_m),
    orientation: { heading: 0, pitch: Cesium.Math.toRadians(pitchDeg), roll: 0 },
    duration,
  });
}

// Fly to an ortho's bbox; falls back to the island when it has none. Returns whether it had one.
export function flyToOrtho(viewer, manifest, rec, { pitchDeg = -55, duration = 2.0 } = {}) {
  if (!rec.bbox_wgs84) {
    flyToIsland(viewer, manifest, { duration });
    return false;
  }
  viewer.camera.flyTo({
    destination: bboxToRect(rec.bbox_wgs84),
    orientation: { heading: 0, pitch: Cesium.Math.toRadians(pitchDeg), roll: 0 },
    duration,
  });
  return true;
}

export function flyToPosition(viewer, position, { altitude = 300, pitchDeg = -45, duration = 2.0 } = {}) {
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(position.lon, position.lat, (position.height ?? 0) + altitude),
    orientation: { heading: 0, pitch: Cesium.Math.toRadians(pitchDeg), roll: 0 },
    duration,
  });
}

// Pepper's ghost display mode:  index.html?mode=peppers-ghost[&mirror=true][&speed=0.1]
// Black scene, no UI, fixed 45-degree close-up, slow auto-rotation.

export function readModeParams(search = window.location.search) {
  const p = new URLSearchParams(search);
  return {
    peppersGhost: p.get("mode") === "peppers-ghost",
    mirror: p.get("mirror") === "true",
    speedDeg: parseFloat(p.get("speed") || "0.05"),   // degrees per tick
  };
}

export function applyPeppersGhost(viewer, surveyArea, params, { altitude = 2000 } = {}) {
  const scene = viewer.scene;
  scene.backgroundColor = Cesium.Color.BLACK;
  scene.globe.baseColor = Cesium.Color.BLACK;
  scene.skyBox.show = false;
  scene.skyAtmosphere.show = false;
  scene.sun.show = false;
  scene.moon.show = false;
  scene.fog.enabled = false;

  document.body.classList.add("no-ui");
  for (const id of ["toolbar", "legend", "status"]) {
    const el = document.getElementById(id);
    if (el) el.style.display = "none";
  }
  viewer.cesiumWidget.creditContainer.style.display = "none";

  const ctrl = scene.screenSpaceCameraController;
  ctrl.enableRotate = ctrl.enableTranslate = ctrl.enableZoom = ctrl.enableTilt = ctrl.enableLook = false;

  viewer.camera.setView({
    destination: Cesium.Cartesian3.fromDegrees(surveyArea.center_lon, surveyArea.center_lat, altitude),
    orientation: { heading: 0, pitch: Cesium.Math.toRadians(-45), roll: 0 },
  });
  viewer.clock.onTick.addEventListener(() => {
    viewer.camera.rotate(Cesium.Cartesian3.UNIT_Z, Cesium.Math.toRadians(params.speedDeg));
  });

  if (params.mirror) document.getElementById("cesiumContainer").style.transform = "scaleX(-1)";

  // Data against black only: drop the base imagery.
  if (viewer.imageryLayers.length > 0) viewer.imageryLayers.remove(viewer.imageryLayers.get(0));
}

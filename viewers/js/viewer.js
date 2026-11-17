// Cesium.Viewer construction and base layers shared by every page.

const INVALID_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.invalid";

// Must run BEFORE new Cesium.Viewer(). Uses the read-only viewer token only.
export function applyIonToken(manifest) {
  const t = manifest.viewer_ion_token;
  Cesium.Ion.defaultAccessToken = (t && t.length > 20) ? t : INVALID_TOKEN; // silences the default-token warning
  return Boolean(t && t.length > 20);
}

export function createViewer(containerId = "cesiumContainer", opts = {}) {
  // imageryProvider:false prevents the default Bing Maps (ion asset 2) request,
  // which 404s on accounts without Bing access.
  return new Cesium.Viewer(containerId, {
    baseLayerPicker: false,
    navigationHelpButton: false,
    homeButton: false,
    sceneModePicker: false,
    animation: false,
    timeline: false,
    fullscreenButton: false,
    geocoder: false,
    infoBox: opts.infoBox ?? true,
    selectionIndicator: opts.selectionIndicator ?? true,
    scene3DOnly: true,
    imageryProvider: false,
  });
}

// Cesium World Terrain gives the camera a surface to pivot against. Needs an ion token.
export async function addWorldTerrain(viewer) {
  try {
    viewer.terrainProvider = await Cesium.createWorldTerrainAsync();
    return true;
  } catch (e) {
    console.warn("World terrain unavailable:", e);
    return false;
  }
}

export function addOsmBase(viewer) {
  return viewer.imageryLayers.addImageryProvider(
    new Cesium.OpenStreetMapImageryProvider({ url: "https://tile.openstreetmap.org/" }));
}

export function setDarkGlobe(viewer, css = "#060912") {
  viewer.imageryLayers.removeAll();
  viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString(css);
}

// Google Photorealistic 3D Tiles (or a legacy imagery asset) from ion.
// Returns { tileset, imagery } so the page can toggle them.
export async function addIonBase(viewer, manifest) {
  const out = { tileset: null, imagery: null };
  if (!manifest.use_ion) return out;
  if (manifest.base_ion_3dtiles_asset != null) {
    try {
      out.tileset = await Cesium.Cesium3DTileset.fromIonAssetId(manifest.base_ion_3dtiles_asset);
      viewer.scene.primitives.add(out.tileset);
    } catch (e) {
      console.warn("3D tileset base failed:", e);
    }
  } else if (manifest.base_ion_imagery_asset != null) {
    try {
      out.imagery = viewer.imageryLayers.addImageryProvider(
        await Cesium.IonImageryProvider.fromAssetId(manifest.base_ion_imagery_asset));
    } catch (e) {
      console.warn("Base imagery asset failed:", e);
    }
  }
  return out;
}

export function setInitialView(viewer, surveyArea, { altitude = null, pitchDeg = -45 } = {}) {
  viewer.camera.setView({
    destination: Cesium.Cartesian3.fromDegrees(
      surveyArea.center_lon, surveyArea.center_lat, altitude ?? surveyArea.default_altitude_m),
    orientation: { heading: 0, pitch: Cesium.Math.toRadians(pitchDeg), roll: 0 },
  });
}

// 3D models (coral meshes): 3D Tiles or glTF. A model is loaded only when the
// pipeline could place it on the globe (`placed`), so nothing ever renders at
// Earth's centre.

function modelMatrixFor(position) {
  const pos = Cesium.Cartesian3.fromDegrees(position.lon, position.lat, position.height ?? 0);
  const hpr = new Cesium.HeadingPitchRoll(Cesium.Math.toRadians(position.heading_deg ?? 0), 0, 0);
  return Cesium.Transforms.headingPitchRollToFixedFrame(pos, hpr);
}

export async function addModel(viewer, rec) {
  try {
    if (rec.format === "3dtiles") {
      if (!rec.tileset_url || !rec.placed) {
        console.warn(`Model ${rec.id}: skipped (not placed; add it to survey_positions.json)`);
        return null;
      }
      const tileset = await Cesium.Cesium3DTileset.fromUrl(rec.tileset_url);
      viewer.scene.primitives.add(tileset);
      console.log(`3D Tiles loaded: ${rec.id}`);
      return tileset;
    }
    if (rec.gltf_url) {
      if (!rec.position) {
        console.warn(`Model ${rec.id}: skipped (no position)`);
        return null;
      }
      const model = await Cesium.Model.fromGltfAsync({
        url: rec.gltf_url, modelMatrix: modelMatrixFor(rec.position), scale: 1.0 });
      viewer.scene.primitives.add(model);
      console.log(`glTF model loaded: ${rec.id}`);
      return model;
    }
    return null;
  } catch (e) {
    console.error(`3D model load failed [${rec.id}]:`, e);
    return null;
  }
}

/** Loads every placeable model in parallel; returns the loaded primitives. */
export async function loadModels(viewer, manifest) {
  const loaded = (await Promise.all(manifest.models_3d.map(r => addModel(viewer, r)))).filter(Boolean);
  if (loaded.length) {
    // Underwater meshes sit below the terrain surface; don't let the globe occlude them.
    viewer.scene.globe.depthTestAgainstTerrain = false;
  }
  return loaded;
}

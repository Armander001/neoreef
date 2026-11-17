// Orthomosaic layers. Source preference: ion imagery -> PNG preview draped on the
// bbox -> nothing. A raw GeoTIFF is never handed to the browser.

import { bboxToRect } from "../camera.js";

export function orthoSource(manifest, rec) {
  if (manifest.use_ion && rec.ion_asset_id != null) return "ion";
  if (rec.preview_url && rec.bbox_wgs84) return "preview";
  return null;
}

export class OrthoLayers {
  constructor(viewer, manifest) {
    this.viewer = viewer;
    this.manifest = manifest;
    this.entries = {};   // rec.id -> { kind:"ion", layer } | { kind:"image", ground, lifted, url, rect, show, alpha }
  }

  hasSource(rec) { return orthoSource(this.manifest, rec) != null; }

  async add(rec) {
    if (this.entries[rec.id]) return this.entries[rec.id];
    const source = orthoSource(this.manifest, rec);
    try {
      if (source === "ion") {
        const provider = await Cesium.IonImageryProvider.fromAssetId(rec.ion_asset_id);
        const layer = this.viewer.imageryLayers.addImageryProvider(provider);
        layer.show = true;
        layer.alpha = 1.0;
        this.entries[rec.id] = { kind: "ion", layer };
      } else if (source === "preview") {
        const rect = bboxToRect(rec.bbox_wgs84);
        // GroundPrimitive drapes the image over terrain AND 3D tiles.
        const ground = new Cesium.GroundPrimitive({
          geometryInstances: new Cesium.GeometryInstance({
            geometry: new Cesium.RectangleGeometry({
              rectangle: rect, vertexFormat: Cesium.EllipsoidSurfaceAppearance.VERTEX_FORMAT }),
          }),
          appearance: new Cesium.EllipsoidSurfaceAppearance({
            material: Cesium.Material.fromType("Image", { image: rec.preview_url }),
            aboveGround: false,
          }),
          classificationType: Cesium.ClassificationType.BOTH,
        });
        this.viewer.scene.primitives.add(ground);
        this.entries[rec.id] = { kind: "image", ground, lifted: null, url: rec.preview_url, rect, show: true, alpha: 1.0 };
      } else {
        console.warn(`Ortho ${rec.id}: no usable source (ion_asset_id=${rec.ion_asset_id}, preview_url=${rec.preview_url}, bbox=${rec.bbox_wgs84})`);
        return null;
      }
      console.log(`Ortho ${rec.id} loaded from ${source}`);
      return this.entries[rec.id];
    } catch (e) {
      console.error(`Ortho load failed [${rec.id}]:`, e);
      return null;
    }
  }

  setShow(id, v) {
    const e = this.entries[id];
    if (!e) return;
    if (e.kind === "ion") { e.layer.show = v; return; }
    e.show = v;
    if (e.lifted) { e.lifted.show = v; e.ground.show = false; }
    else { e.ground.show = v; }
  }

  setAlpha(id, alpha) {
    const e = this.entries[id];
    if (!e) return;
    if (e.kind === "ion") { e.layer.alpha = alpha; return; }
    e.alpha = alpha;
    const color = new Cesium.Color(1, 1, 1, alpha);
    if (e.ground.appearance) e.ground.appearance.material.uniforms.color = color;
    if (e.lifted?.appearance) e.lifted.appearance.material.uniforms.color = color;
  }

  /** Image-backed entries in the given record order (what separation mode can lift). */
  liftable(records) {
    return records.map(r => [r, this.entries[r.id]]).filter(([, e]) => e && e.kind === "image");
  }
}

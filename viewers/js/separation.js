// "Separate layers" mode: floats each data layer at its own altitude so all of
// them are visible at once with a clear vertical gap.

export class SeparationMode {
  constructor(viewer, manifest, { landuse = null, orthos = null, gapM = 400 } = {}) {
    this.viewer = viewer;
    this.manifest = manifest;
    this.landuse = landuse;
    this.orthos = orthos;
    this.gapM = gapM;
    this.active = false;
  }

  toggle(btn = null) {
    this.active = !this.active;
    if (btn) {
      btn.classList.toggle("active", this.active);
      btn.title = this.active ? "Collapse layers to ground" : "Separate layers in 3D space";
    }
    const luCount = this._applyLanduse();
    const orthoCount = this._applyOrthos(luCount);
    if (this.active) {
      const topM = this.gapM * (luCount + orthoCount + 1) + 200;
      const sa = this.manifest.survey_area;
      this.viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(sa.center_lon, sa.center_lat - 0.04, topM + 8000),
        orientation: { heading: 0, pitch: Cesium.Math.toRadians(-35), roll: 0 },
        duration: 1.5,
      });
    }
    return this.active;
  }

  _applyLanduse() {
    if (!this.landuse) return 0;
    const ids = this.landuse.ids;
    ids.forEach((id, idx) => {
      const src = this.landuse.sources[id];
      const extMap = this.landuse.extH[id] || {};
      const baseH = this.active ? this.gapM * (idx + 1) : 0;
      for (const entity of src.entities.values) {
        if (!entity.polygon) continue;
        const origExt = extMap[entity.id] ?? 8;
        if (this.active) {
          entity.polygon.heightReference = Cesium.HeightReference.NONE;
          entity.polygon.extrudedHeightReference = Cesium.HeightReference.NONE;
          entity.polygon.height = baseH;
          entity.polygon.extrudedHeight = baseH + origExt;
        } else {
          entity.polygon.heightReference = Cesium.HeightReference.CLAMP_TO_GROUND;
          entity.polygon.extrudedHeightReference = Cesium.HeightReference.RELATIVE_TO_GROUND;
          entity.polygon.height = 0;
          entity.polygon.extrudedHeight = origExt;
        }
      }
    });
    return ids.length;
  }

  // Coral below drone. A GroundPrimitive cannot take an altitude, so a regular
  // Primitive copy is created at height while separated.
  _applyOrthos(offsetLayers) {
    if (!this.orthos) return 0;
    const ordered = [
      ...this.manifest.orthomosaics.filter(r => r.ortho_type === "coral"),
      ...this.manifest.orthomosaics.filter(r => r.ortho_type !== "coral"),
    ];
    const liftable = this.orthos.liftable(ordered);
    liftable.forEach(([, entry], i) => {
      const height = this.gapM * (offsetLayers + 1 + i);
      if (this.active) {
        if (!entry.lifted) {
          entry.lifted = new Cesium.Primitive({
            geometryInstances: new Cesium.GeometryInstance({
              geometry: new Cesium.RectangleGeometry({
                rectangle: entry.rect, height, vertexFormat: Cesium.EllipsoidSurfaceAppearance.VERTEX_FORMAT }),
            }),
            appearance: new Cesium.EllipsoidSurfaceAppearance({
              material: Cesium.Material.fromType("Image", { image: entry.url }),
              aboveGround: true,
            }),
          });
          this.viewer.scene.primitives.add(entry.lifted);
          if (entry.alpha < 1.0) {
            entry.lifted.appearance.material.uniforms.color = new Cesium.Color(1, 1, 1, entry.alpha);
          }
        }
        entry.lifted.show = entry.show;
        entry.ground.show = false;
      } else {
        if (entry.lifted) {
          this.viewer.scene.primitives.remove(entry.lifted);
          entry.lifted = null;
        }
        entry.ground.show = entry.show;
      }
    });
    return liftable.length;
  }
}

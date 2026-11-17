// Land-use GeoJSON layers: extruded, coloured polygons styled from the shared legend.
// Always loaded from the local GeoJSON: ion re-tiles the file and strips the
// custom properties the styling depends on.

export class LanduseLayers {
  constructor(viewer, legend, { alpha = 0.55, outlineAlpha = 0.2, onChange = null } = {}) {
    this.viewer = viewer;
    this.legend = legend;
    this.alpha = alpha;
    this.outlineAlpha = outlineAlpha;
    this.onChange = onChange;      // called after a layer loads or its visibility changes
    this.sources = {};             // rec.id -> GeoJsonDataSource
    this.colors = {};              // rec.id -> { entityId -> hex }
    this.extH = {};                // rec.id -> { entityId -> extrude height }
    this.codes = {};               // rec.id -> Set<TOCHICD code>
  }

  get ids() { return Object.keys(this.sources); }

  async add(rec) {
    if (this.sources[rec.id]) return this.sources[rec.id];
    if (!rec.geojson_url) { console.warn("No source for landuse", rec.id); return null; }
    try {
      const now = Cesium.JulianDate.now();
      const source = await Cesium.GeoJsonDataSource.load(rec.geojson_url, {
        stroke: Cesium.Color.WHITE.withAlpha(0.3),
        strokeWidth: 1,
        fill: Cesium.Color.WHITE.withAlpha(0),
        clampToGround: false,
      });

      const colorMap = {}, extMap = {}, codes = new Set();
      let colored = 0;
      for (const entity of source.entities.values) {
        const props = entity.properties;
        const code = props?.TOCHICD?.getValue(now);
        const entry = this.legend.get(code);
        const hex = this.legend.byCode.has(Number(code))
          ? entry.color
          : (props?.fill_color?.getValue(now) ?? entry.color);
        const extH = props?.extrude_h?.getValue(now) ?? entry.extrude_h;
        colorMap[entity.id] = hex;
        extMap[entity.id] = extH;
        if (code != null) codes.add(Number(code));
        if (!entity.polygon) continue;
        try {
          entity.polygon.material = Cesium.Color.fromCssColorString(hex).withAlpha(this.alpha);
          entity.polygon.outline = true;
          entity.polygon.outlineColor = Cesium.Color.WHITE.withAlpha(this.outlineAlpha);
          entity.polygon.outlineWidth = 1;
          entity.polygon.heightReference = Cesium.HeightReference.CLAMP_TO_GROUND;
          entity.polygon.extrudedHeight = extH;
          entity.polygon.extrudedHeightReference = Cesium.HeightReference.RELATIVE_TO_GROUND;
          colored++;
        } catch (err) {
          console.warn("Colour parse failed for entity", entity.id, hex, err);
        }
      }
      console.log(`Landuse ${rec.id}: ${colored} polygons coloured, ${codes.size} TOCHICD codes`);

      this.colors[rec.id] = colorMap;
      this.extH[rec.id] = extMap;
      this.codes[rec.id] = codes;
      source.show = true;
      await this.viewer.dataSources.add(source);
      this.sources[rec.id] = source;
      this.onChange?.();
      return source;
    } catch (e) {
      console.error("Landuse load failed:", rec.id, e);
      return null;
    }
  }

  setShow(id, v) {
    const src = this.sources[id];
    if (!src) return;
    src.show = v;
    this.onChange?.();
  }

  setAlpha(id, alpha) {
    const src = this.sources[id];
    const colorMap = this.colors[id] || {};
    if (!src) return;
    for (const e of src.entities.values) {
      if (!e.polygon) continue;
      const hex = colorMap[e.id] || "#CCCCCC";
      try { e.polygon.material = Cesium.Color.fromCssColorString(hex).withAlpha(alpha); } catch (_) { /* skip */ }
    }
  }

  /** TOCHICD codes present in the layers that are currently shown. */
  activeCodes() {
    const out = new Set();
    for (const id of this.ids) {
      if (!this.sources[id].show) continue;
      for (const c of this.codes[id] ?? []) out.add(c);
    }
    return out;
  }
}

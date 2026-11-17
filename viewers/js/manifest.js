// manifest.json loader. Mirrors src/neoreef/pipeline/manifest_schema.py (schema v2).

export const SUPPORTED_SCHEMA = 2;

// Only used when manifest.json is missing, so the globe still has somewhere to
// look. The authoritative value is neoreef.common.geodesy.SURVEY_AREA.
const FALLBACK_SURVEY_AREA = {
  name: "Ishigaki Island", center_lon: 124.205, center_lat: 24.470, default_altitude_m: 15000,
};

export function emptyManifest(error = null) {
  return {
    schema_version: SUPPORTED_SCHEMA,
    error,
    use_ion: false,
    viewer_ion_token: "",
    base_ion_imagery_asset: null,
    base_ion_3dtiles_asset: null,
    legend_url: null,
    survey_area: { ...FALLBACK_SURVEY_AREA },
    orthomosaics: [],
    landuse_layers: [],
    models_3d: [],
  };
}

export async function loadManifest(url = "manifest.json") {
  const resp = await fetch(url, { cache: "no-cache" });
  if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`);
  const m = await resp.json();
  if (m.schema_version !== SUPPORTED_SCHEMA) {
    throw new Error(
      `manifest schema ${m.schema_version ?? "(none)"} is not supported by this viewer ` +
      `(expects ${SUPPORTED_SCHEMA}); re-run the pipeline manifest stage`);
  }
  m.orthomosaics ??= [];
  m.landuse_layers ??= [];
  m.models_3d ??= [];
  m.survey_area ??= { ...FALLBACK_SURVEY_AREA };
  return m;
}

// Loads the manifest or returns an empty one carrying the error message.
export async function loadManifestOrEmpty(url = "manifest.json") {
  try {
    return await loadManifest(url);
  } catch (e) {
    console.error("Manifest load failed:", e);
    return emptyManifest(e.message);
  }
}

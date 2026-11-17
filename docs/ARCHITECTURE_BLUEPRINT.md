# NeoReef — Modularization Blueprint

**Generated:** 2026-11-16
**Status:** Implemented 2026-11-17 (Phases 0-5). Deviations from the plan below: `Batch_metashape.py` stays at the repo root as the USER CONFIG file that builds a `MetashapeConfig`; `cesium_pipeline.py` stays as a shim over `neoreef-pipeline`; the Docker config mounts the whole `config/` directory; the architecture SVGs were not redrawn (see `docs/architecture/README.md`).
**Companion:** `docs/REPORT_code_duplication.md` (2026-04-29) covers *what is duplicated*. This document covers *where everything should live* and *how data moves between the pieces*.

---

## 0. Executive summary

NeoReef is really three programs that share one filesystem and one JSON contract:

| Program | Runtime | Today | Lines |
|---|---|---|---|
| Photogrammetry batch | Metashape's bundled Python (`metashape.exe -r`) | `Batch_metashape.py` + 4 legacy forks | 618 (+ ~940 legacy) |
| Cesium post-processing | Standalone Python (conda: rasterio/geopandas) | `cesium_pipeline.py` monolith | 1,074 |
| Browser viewers | Vanilla JS, CesiumJS from CDN, no build step | 3 self-contained HTML files | 1,750 |

The disjointedness comes from each program having been grown by separate AI sessions with no shared module. Three concrete symptoms:

1. **The same facts are hand-copied** (TOCHICD legend in 3 places and already drifted; survey-name regex in 2 places with different years; island center coordinates in 4 places).
2. **State is re-derived instead of persisted.** Each pipeline stage re-scans disk when run standalone and *guesses* what earlier stages did (ortho type from a filename suffix that never exists, COG paths by convention). This is where several real bugs live.
3. **The viewers each re-implement the Cesium glue** (viewer construction, manifest load, ortho/landuse layer adders, camera, toast, separation mode).

The target is one installable Python package `neoreef` with three sub-packages (`common`, `metashape`, `pipeline`), one `viewers/` directory of ES modules, one `deploy/` directory, and a `tests/` directory. The pipeline becomes a chain of stages that read and write a persisted `RecordSet`, and the manifest becomes a versioned contract both Python and JS validate against.

---

## 1. Target directory layout

```
neoreef/
├── pyproject.toml                  # package metadata; console script `neoreef-pipeline`
├── environment.yml                 # conda env (rasterio, geopandas, fiona) + pip deps
├── README.md
├── CLAUDE.md                       # update "Project structure" + conventions after migration
├── .gitignore                      # + Processed_Projects/, *.log, config/*.json (except *.example.json)
│
├── config/
│   ├── cesium_config.example.json
│   ├── cesium_config.docker.example.json
│   ├── survey_positions.example.json    # NEW: per-survey lon/lat/height/heading for 3D models
│   └── (cesium_config.json, cesium_config.docker.json — gitignored, live here)
│
├── src/neoreef/
│   ├── __init__.py                 # __version__
│   │
│   ├── common/                     # RULE: stdlib only. Importable inside Metashape AND conda.
│   │   ├── __init__.py
│   │   ├── naming.py               # SURVEY_PATTERN, parse_survey_name(), cog_filename(), landuse_layer_id(), model_id()
│   │   ├── landuse_codes.py        # TOCHICD_MAP (name_ja, name_en, color, extrude_h), TOCHICD_DEFAULT, ERA_OFFSETS, era_to_calendar()
│   │   ├── geodesy.py              # SURVEY_AREA (Ishigaki center/altitude), enu_to_ecef_matrix(lon, lat, h, heading)
│   │   ├── logging.py              # make_cli_logger(path), make_metashape_logger(handle)
│   │   └── fs.py                   # ensure_dir(), safe_unlink(), copy_tree()
│   │
│   ├── metashape/                  # RULE: imports `Metashape`; never imports pipeline/ or geospatial libs.
│   │   ├── __init__.py
│   │   ├── config.py               # USER CONFIG constants -> `MetashapeConfig` dataclass (paths, alignment, depth, ortho, export flags)
│   │   ├── discovery.py            # IMAGE_EXTENSIONS, collect_survey_folders(), get_images_from_folder()
│   │   ├── processing.py           # align_photos(chunk, cfg), build_depth_maps(), build_model(), build_orthomosaic()
│   │   ├── export_preview.py       # export_jpeg_preview()
│   │   ├── export_model.py         # export_3d_model(), run_tool(), compute_model_bbox(), make_tileset()
│   │   └── batch.py                # run(cfg) — the per-survey loop; writes survey_meta.json (see section 3)
│   │
│   └── pipeline/                   # RULE: standalone Python; may import rasterio/geopandas/requests/boto3.
│       ├── __init__.py
│       ├── cli.py                  # argparse -> PipelineContext -> run_stages([...])
│       ├── config.py               # PipelineConfig dataclass, load_config(), validate(); resolves two ion tokens
│       ├── context.py              # PipelineContext(cfg, log, out_dir, viewers_dir)
│       ├── records.py              # OrthoRecord, LanduseRecord, Model3DRecord, RecordSet; one to_dict via a PathRecord base
│       ├── state.py                # save_records(out_dir, rs) / load_records(out_dir) -> .state/records.json
│       ├── manifest_schema.py      # MANIFEST_SCHEMA_VERSION = 2; build_manifest(rs, cfg) -> dict (pure, testable)
│       │
│       ├── geo/                    # thin wrappers around GDAL libs; no pipeline/stage knowledge
│       │   ├── raster.py           # convert_to_cog(), bbox_wgs84(), render_preview_png()
│       │   └── vector.py           # read_shapefile(), detect_crs(), to_wgs84_geojson()
│       │
│       ├── ion/                    # Cesium ion REST client; no knowledge of records
│       │   ├── client.py           # IonClient(token): list_assets, find_by_name, get_status, create, upload_s3, notify_complete, poll_ready
│       │   └── upload.py           # upload_file(client, path, spec: IonUploadSpec) -> asset_id | None
│       │
│       └── stages/                 # each: `def run(ctx: PipelineContext, rs: RecordSet) -> RecordSet`
│           ├── __init__.py         # STAGES = {"cog": cog.run, ...}; ORDER = ["cog","landuse","model3d","upload","manifest"]
│           ├── cog.py              # scan *_ortho.tif + EXTRA_ORTHOS -> COG + bbox + preview
│           ├── landuse.py          # Land-useMap_* shapefiles -> GeoJSON WGS84 with TOCHICD attrs
│           ├── model3d.py          # scan tilesets/glb + survey_positions -> copy + inject root.transform
│           ├── upload.py           # ion upload of ortho + landuse records (uses ion/)
│           ├── manifest.py         # manifest.json + tochicd_legend.json + copy viewers/
│           └── serve.py            # threaded local HTTP server with Range support
│
├── viewers/                        # served verbatim; copied by the manifest stage; ES modules, still no build step
│   ├── index.html                  # was cesium_viewer.html (full viewer + Pepper's ghost)
│   ├── ortho.html                  # was ortho_viewer.html
│   ├── landuse.html                # was landuse_viewer.html
│   ├── css/
│   │   ├── common.css              # toolbar / card / legend rules using var(--accent)
│   │   └── themes.css              # :root[data-theme=ortho|landuse] accent overrides
│   └── js/
│       ├── manifest.js             # loadManifest(url): validates schema_version, no hardcoded fallback coords
│       ├── viewer.js               # createViewer(container, opts), applyIonToken(manifest)
│       ├── camera.js               # bboxToRect(), flyToIsland(viewer, manifest), flyToOrtho()
│       ├── legend.js               # loadLegend(url) -> Map<code, entry>; buildLegend(el, activeCodes)
│       ├── layers/
│       │   ├── ortho.js            # addOrthoLayer(viewer, rec, manifest): ion first, preview PNG fallback
│       │   ├── landuse.js          # addLanduseLayer(viewer, rec, legend)
│       │   └── models.js           # addModel(viewer, rec): 3dtiles vs glb
│       ├── separation.js           # toggleSeparation(viewer, layers, opts)
│       ├── ui/
│       │   ├── toolbar.js          # makeCard(), makeGroupLabel(), buildToolbar(spec)
│       │   └── status.js           # showStatus()
│       └── modes/peppers_ghost.js  # URL-param mode: hide UI, fixed camera, rotation
│
├── scripts/
│   ├── metashape_batch.py          # 10-line shim: sys.path.insert(src) -> neoreef.metashape.batch.run()
│   ├── run_metashape.ps1           # metashape.exe -r scripts/metashape_batch.py
│   └── run_pipeline.ps1            # conda activate + neoreef-pipeline --config config/cesium_config.json
│
├── deploy/
│   ├── docker-compose.yml
│   ├── Dockerfile.pipeline         # was Dockerfile.app
│   ├── Dockerfile.devtools         # was Dockerfile (Claude Code / Node), or move into .devcontainer/
│   └── nginx/default.conf
│
├── tests/
│   ├── conftest.py                 # tmp output dirs, tiny GeoTIFF + shapefile fixtures
│   ├── test_naming.py
│   ├── test_landuse_codes.py
│   ├── test_manifest_schema.py     # build_manifest is pure: golden-file test
│   ├── test_state_roundtrip.py
│   ├── test_stage_cog.py           # marked `geo` (needs rasterio); skipped where unavailable
│   ├── test_stage_landuse.py
│   └── test_ion_client.py          # requests mocked
│
├── legacy/                         # OR delete outright (recommended). If kept: never imported, README says why.
│   └── NeoReef.py, NeoReef_slim, NeoReef_batch.py, Batch_metashape, Agisoft_test.py
│
└── docs/                           # unchanged; update architecture SVGs after migration
```

### Boundary rules (enforce in code review and with an import-linter test)

| From | May import | Must not import |
|---|---|---|
| `neoreef.common` | stdlib only | anything else in the repo, `Metashape`, GDAL libs |
| `neoreef.metashape` | `common`, `Metashape` | `pipeline`, rasterio, geopandas |
| `neoreef.pipeline.geo` | `common`, rasterio, geopandas | `stages`, `ion`, `records` |
| `neoreef.pipeline.ion` | `common`, requests, boto3 | `stages`, `records` |
| `neoreef.pipeline.stages` | everything in `pipeline` + `common` | `metashape` |
| `viewers/js/*` | each other via relative `import` | nothing inline-duplicated across pages |

Why `common` must be stdlib-only: the Metashape runtime cannot `pip install` rasterio, so any shared constant that drags in GDAL would be unimportable from the batch script. This is the single most important rule in the layout.

---

## 2. Data flow (end to end)

```
 S:\...\Ishigaki_2025\Ishi25_S008_0915_A1\{A..Z}\*.jpg
          |
          v  [metashape.batch.run]  (runs under metashape.exe)
 OUTPUT_BASE/
   |-- Ishi25_S008_0915_A1.psx
   |-- Ishi25_S008_0915_A1_ortho.tif            (BigTIFF, local CRS, no georef)
   |-- Ishi25_S008_0915_A1_coral_ortho.tif      (optional second ortho type)
   |-- Complete Images/<ts>/Ishi25_S008_0915_A1.jpg
   `-- 3d_models/Ishi25_S008_0915_A1/
         |-- Ishi25_S008_0915_A1_compressed.glb
         |-- tileset.json                       (local-origin bbox, NO root.transform)
         `-- survey_meta.json                   <- NEW (section 3): bbox, units, crs=None, producer version
          |
          v  [pipeline.cli -> stages, in ORDER]   (runs in conda / Docker)
 CESIUM_OUTPUT_DIR/
   |-- .state/records.json        <- NEW: RecordSet persisted after every stage
   |-- cogs/<survey>_<type>_cog.tif            <- type now encoded in filename
   |-- previews/<survey>_<type>.png           <- NEW: browser-decodable fallback + bbox
   |-- landuse/landuse_H23_<stem>.geojson      (WGS84, TOCHICD + land_use_en/ja + fill_color)
   |-- models/<survey>/tileset.json            (root.transform injected from survey_positions)
   |-- models/<survey>/<survey>_compressed.glb
   |-- tochicd_legend.json                     <- NEW: generated from common.landuse_codes
   |-- manifest.json                           (schema_version 2, viewer token only)
   |-- index.html, ortho.html, landuse.html
   `-- css/, js/                               (copied from viewers/)
          |
          v  nginx (Docker) or stages/serve.py (dev)
 Browser
   js/manifest.js -- fetch manifest.json --> validate schema_version
   js/legend.js   -- fetch tochicd_legend.json
   js/viewer.js   -- createViewer + applyIonToken(manifest.viewer_ion_token)
   js/layers/*    -- one adder per record type, driven purely by manifest entries
```

### 2.1 Stage contract

Every stage has the same signature and is the *only* thing `cli.py` knows about:

```
run(ctx: PipelineContext, rs: RecordSet) -> RecordSet
```

- `PipelineContext` carries config, logger, `out_dir`, `viewers_dir`. Stages never call `load_config` or build loggers.
- `RecordSet` is `{orthos: [OrthoRecord], landuse: [LanduseRecord], models: [Model3DRecord]}` plus `generated_by: {stage: timestamp}`.
- `cli.py` does: `rs = state.load(out_dir)`; for each requested stage: `rs = stage.run(ctx, rs)`; `state.save(out_dir, rs)`.

This replaces the three copies of "if the list is empty, re-scan and guess" in today's `main()`. Running `--stage manifest` alone reads what `--stage cog` wrote last week, with ortho types and bboxes intact. A `--rescan` flag clears `.state/` for the rare case where the source tree changed.

### 2.2 What each stage reads and writes

| Stage | Reads | Writes to disk | Mutates records |
|---|---|---|---|
| `cog` | `OUTPUT_BASE/**/*_ortho.tif`, `EXTRA_ORTHOS` | `cogs/*.tif`, `previews/*.png` | creates `orthos[]`; sets `cog_path`, `preview_path`, `bbox_wgs84` |
| `landuse` | `LANDUSE_DIR/Land-useMap_*/**/*.shp` | `landuse/*.geojson` | creates `landuse[]`; layer id = `landuse_{era}_{stem}` so two shapefiles per year don't collide |
| `model3d` | `MODELS_3D_DIR/**/tileset.json` (+ sibling `survey_meta.json`), `EXTRA_3D_MODELS`, `survey_positions.json` | `models/<survey>/` with `root.transform` written into the copied `tileset.json` | creates `models[]`; sets `position`, `transform`; skips `.glb` files that live inside a tileset directory |
| `upload` | records with a local file and no `ion_asset_id` | nothing local | sets `ion_asset_id` only after `IonClient.get_status == COMPLETE`; a stale ERROR asset is deleted and re-uploaded |
| `manifest` | records, `known_ion_assets`, `BASE_ION_*`, `SERVER_BASE_URL` | `manifest.json`, `tochicd_legend.json`, copy of `viewers/` | none |
| `serve` | `out_dir` | nothing | none |

### 2.3 Manifest v2 (the Python <-> JS contract)

`pipeline/manifest_schema.py::build_manifest()` is a pure function of `(RecordSet, PipelineConfig)` and is the only place the manifest shape is defined. `viewers/js/manifest.js` refuses to load a manifest whose `schema_version` it does not know.

```jsonc
{
  "schema_version": 2,
  "generated": "2026-11-16T05:00:00Z",
  "viewer_ion_token": "<assets:read token or empty>",     // was cesium_ion_token (the write token)
  "use_ion": true,
  "base_ion_imagery_asset": null,
  "base_ion_3dtiles_asset": 2275207,
  "legend_url": "tochicd_legend.json",
  "survey_area": { "name": "Ishigaki Island", "center_lon": 124.205, "center_lat": 24.470, "default_altitude_m": 15000 },
  "orthomosaics": [{
    "id": "Ishi25_S008_0915_A1:coral", "survey_name": "...", "ortho_type": "coral",
    "bbox_wgs84": [W,S,E,N] | null, "ion_asset_id": 123 | null,
    "cog_url": "cogs/..._coral_cog.tif", "preview_url": "previews/..._coral.png" | null
  }],
  "landuse_layers": [{ "id": "landuse_H23_Ishigaki", "year_label": "H23", "calendar_year": 2011,
                       "feature_count": 1234, "ion_asset_id": null, "geojson_url": "landuse/landuse_H23_Ishigaki.geojson" }],
  "models_3d": [{ "id": "Ishi25_S008_0915_A1:mesh", "survey_name": "...", "model_type": "mesh", "format": "3dtiles",
                  "tileset_url": "models/.../tileset.json", "position": {"lon":..,"lat":..,"height":..,"heading_deg":..},
                  "ion_asset_id": null }]
}
```

Rules baked into the builder (today they are scattered or missing):
- The ion **write** token never enters the manifest. Config gains `CESIUM_ION_WRITE_TOKEN` (pipeline only) and `CESIUM_ION_VIEWER_TOKEN` (assets:read, optional). `CESIUM_ION_TOKEN` stays accepted as a deprecated alias for the write token with a warning.
- `base_ion_*` are parameters of `build_manifest`, not a post-hoc re-read-and-patch of the file.
- Ortho ids include the type so a survey with both a drone and a coral ortho is two entries, not one overwrite.
- Viewer source preference is explicit: `ion_asset_id` -> `preview_url` -> nothing. A raw `.tif` is never handed to an `<img>`.

### 2.4 Viewer module flow

```
index.html
  <script type="module">
    import { loadManifest }  from "./js/manifest.js";
    import { loadLegend }    from "./js/legend.js";
    import { createViewer, applyIonToken } from "./js/viewer.js";
    import { addOrthoLayer } from "./js/layers/ortho.js";
    ...
    const manifest = await loadManifest("manifest.json");
    const legend   = await loadLegend(manifest.legend_url);
    const viewer   = createViewer("cesiumContainer", { mode: params.mode });
    applyIonToken(manifest);
    await Promise.all([ ...manifest.orthomosaics.map(r => addOrthoLayer(viewer, r, manifest)),
                        ...manifest.landuse_layers.map(r => addLanduseLayer(viewer, r, legend)),
                        ...manifest.models_3d.map(r => addModel(viewer, r)) ]);
    buildToolbar(...); buildLegend(...);
  </script>
```

Each page differs only in which adders it imports, its toolbar spec, and its `data-theme`. Everything else is shared. ES modules need HTTP, which the project already requires, so the "no build step" convention survives intact.

---

## 3. New shared artifacts the refactor introduces

| Artifact | Producer | Consumer | Why |
|---|---|---|---|
| `src/neoreef/common/naming.py` | - | both batch and pipeline | one `SURVEY_PATTERN` (any 2-digit year), one place that knows `_coral_ortho.tif` vs `_ortho.tif` |
| `src/neoreef/common/landuse_codes.py` | - | `stages/landuse.py`, `stages/manifest.py` | single TOCHICD table incl. `extrude_h`; generates `tochicd_legend.json` so JS never embeds it |
| `survey_meta.json` (next to each tileset) | `metashape/export_model.py` | `stages/model3d.py` | records local bbox/units and that CRS is None, so the pipeline knows a transform is required rather than assuming |
| `config/survey_positions.json` | human | `stages/model3d.py` | underwater surveys have no GPS; this is the one place a survey gets a lon/lat/height/heading. `EXTRA_3D_MODELS.position` is folded into it |
| `.state/records.json` | every stage | every stage | resumable, inspectable, standalone-stage-safe |
| `previews/*.png` | `stages/cog.py` via `geo/raster.py` | `layers/ortho.js` | the only ortho fallback a browser can actually decode |
| `tochicd_legend.json` | `stages/manifest.py` | `legend.js` | ends the 3-way legend drift |

---

## 4. Correctness issues the refactor must absorb (from the 2026-11-16 review)

Each is assigned to the module that owns the fix so it cannot be reintroduced.

| # | Issue | Owning module |
|---|---|---|
| 1 | The write-scope ion JWT is published into `manifest.json`, which nginx serves with `Access-Control-Allow-Origin: *` | `pipeline/config.py` (two tokens), `manifest_schema.py` (only viewer token) |
| 2 | `Processed_Projects/` is not gitignored, and the local config writes the manifest (with the token) inside the repo | `.gitignore`; `config/` moves out of repo root |
| 3 | `tileset.json` has no `root.transform`; every exported coral mesh renders at Earth's center | `metashape/export_model.py` (emit `survey_meta.json`), `stages/model3d.py` + `common/geodesy.py` (inject ENU-to-ECEF transform) |
| 4 | Viewers hand a multi-GB `.tif` to `Cesium.Material` Image and never try ion; `preview_url` referenced but never produced | `geo/raster.py::render_preview_png`, `layers/ortho.js` source preference |
| 5 | Docker config scans the empty output volume; `Dockerfile.app` copies viewers to a path the code never looks at | `deploy/`, `PipelineContext.viewers_dir` resolved from package location or `VIEWERS_DIR` |
| 6 | An ion asset whose tiling failed is "reused" forever by name | `ion/client.py::get_status`, `stages/upload.py` |
| 7 | Standalone manifest stage guesses ortho type from a suffix that never exists; drone + coral COGs collide on one filename | `state.py` (no guessing), `naming.py::cog_filename(survey, type)` |
| 8 | Tileset's own `.glb` is also registered as a standalone model at island center | `stages/model3d.py` skip rule |
| 9 | Batch script's folder regex hardcodes years 24/25 | `common/naming.py` shared pattern |
| 10 | TOCHICD legend copied into 3 files and drifted (codes 12,13,15,16,17) | `common/landuse_codes.py` + generated JSON |

Lower-priority items from the same review, to fold in while touching the module: threaded HTTP server with real Range support (`stages/serve.py`); landuse layer id includes the shapefile stem (`stages/landuse.py`); drop the redundant fiona open in CRS detection (`geo/vector.py`); legend hides only the unchecked layer's codes (`legend.js`); layers load with `Promise.all` (`index.html`); model bbox computed in one pass (`metashape/export_model.py`).

---

## 5. Migration plan (ordered, each phase leaves the repo working)

### Phase 0 — Hygiene (no code moves)
- Delete `Layer_Landuse.py`, `Agisoft_test.py`, `NeoReef_slim`, `NeoReef_batch.py`, `Batch_metashape` (no ext), `short_scripts.txt`, `error_file.txt`. Decide on `NeoReef.py` (recommend delete; `TARGET_FOLDER` mode covers it).
- `.gitignore`: add `Processed_Projects/`, `*.log`, `config/*.json`, `!config/*.example.json`. `git rm --cached` the tracked log.
- Rotate the Cesium ion token, since a live JWT exists in git history. Create a second, read-only token for viewers.
- **Gate:** `git status` clean, pipeline `--stage manifest` still runs from the root.

### Phase 1 — Package skeleton + `common`
- Create `pyproject.toml`, `src/neoreef/{__init__,common/*}.py`. Move constants (regex, TOCHICD, era offsets, island center) into `common`. Both `Batch_metashape.py` and `cesium_pipeline.py` import from `common` but are otherwise untouched.
- Add `scripts/metashape_batch.py` shim that inserts `src/` on `sys.path`.
- Add `tests/test_naming.py`, `tests/test_landuse_codes.py`.
- **Gate:** `pytest tests/` green; `metashape.exe -r scripts/metashape_batch.py` runs on one folder; `--stage all` output identical to before (diff `manifest.json`).

### Phase 2 — Split the pipeline (mechanical, then behavioral)
- 2a *Mechanical:* cut `cesium_pipeline.py` into `records.py`, `geo/`, `ion/`, `stages/*`, `cli.py`. Function bodies unchanged. `cesium_pipeline.py` becomes a 3-line shim calling `neoreef.pipeline.cli.main()` for one release, then is deleted.
- 2b *Behavioral:* add `config.py` dataclass + two tokens, `state.py`, `manifest_schema.py` (v2), the `model3d` transform injection, preview rendering, ion status check. Each is its own commit with a test.
- **Gate:** golden-file test on `build_manifest`; standalone `--stage manifest` after a fresh `--stage cog` produces correct `ortho_type`.

### Phase 3 — Viewers
- Create `viewers/css/*` and `viewers/js/*` by extracting from `cesium_viewer.html` first (it is the superset). Rebuild `ortho.html` and `landuse.html` as thin pages importing the modules.
- `stages/manifest.py` copies the whole `viewers/` tree; nginx config unchanged (it already serves `$uri`).
- **Gate:** all three pages load the same `manifest.json`; Pepper's ghost mode works via `modes/peppers_ghost.js`; legend labels match `common/landuse_codes.py`.

### Phase 4 — Split the Metashape batch
- Move `Batch_metashape.py` body into `metashape/{config,discovery,processing,export_preview,export_model,batch}.py`. `processing.py` turns the inline align/depth/mesh/ortho block into one function per step so the per-survey loop in `batch.py` reads as a recipe.
- Emit `survey_meta.json` next to each tileset.
- **Gate:** one survey processed end to end; `3d_models/<survey>/` contains `survey_meta.json`; the pipeline's `model3d` stage places the mesh at the configured position.

### Phase 5 — Deploy + docs
- Move Docker/nginx into `deploy/`, fix the Docker config (`OUTPUT_BASE` -> `/app/input/...`), `COPY src/ viewers/` into the image, `pip install -e .` in the Dockerfile.
- Update `CLAUDE.md` project structure and conventions (file naming becomes snake_case modules; the config-at-top pattern becomes `metashape/config.py`). Regenerate `docs/architecture/*.svg`.
- Optional: GitHub Actions running `pytest -m "not geo"` on every push, and the `geo` tests in a conda job.

---

## 6. Decisions and alternatives considered

| Decision | Alternative rejected | Why |
|---|---|---|
| `src/` layout + `pyproject.toml` | Flat modules in repo root | `pip install -e .` gives the pipeline a stable import root in conda, Docker, and tests; the Metashape shim still works via `sys.path` |
| ES modules, no bundler | Vite/esbuild bundle | Project convention is no build step; modules give the same dedup at zero toolchain cost. Only constraint is HTTP serving, already mandatory |
| Persist `records.json` between stages | Keep re-scanning | Re-scanning is the root of findings 7 and 8 and makes stages non-deterministic |
| `survey_positions.json` as a config file | Position inside `EXTRA_3D_MODELS` | Positions are per-survey facts measured in the field, not pipeline options; a dedicated file is easier for lab members to edit |
| Generated `tochicd_legend.json` | Import a shared JS constant | Python is the producer of the GeoJSON attributes, so Python must own the table |
| Two ion tokens | Keep one token, strip it from manifest | Viewers do need a token for ion assets; it just must not be the one with write scope |
| Delete legacy scripts | `legacy/` folder | Git history preserves them; a folder invites accidental reuse. Keep `legacy/` only if someone objects |

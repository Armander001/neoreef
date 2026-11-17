# NeoReef

Coral reef ecological data visualized as interactive 3D layers on a CesiumJS globe. Processes underwater photogrammetry from Ishigaki Island field surveys (Nakamura Lab, Tokyo Tech) and serves the results on-premise via Docker.

## Tech stack

| Layer | Technology |
|---|---|
| Photogrammetry | Agisoft Metashape Pro 2.x (Python scripting API, bundled Python 3.9) |
| Geospatial processing | rasterio, geopandas, fiona (conda-forge; GDAL-backed) |
| 3D globe & viewers | CesiumJS 1.117 (CDN), vanilla ES modules, no build step |
| Cloud tile hosting | Cesium ion REST API, boto3 for S3 uploads |
| On-premise hosting | Docker Compose: nginx:alpine (static files) + miniconda3 pipeline |
| Dev environment | VS Code devcontainer (Python 3.11 + conda); tests with pytest |

## Project structure

Three programs share one installable package (`src/neoreef`) and one JSON contract (`manifest.json`).
`docs/ARCHITECTURE_BLUEPRINT.md` has the full design and data flow.

```
pyproject.toml                 # package `neoreef`; console script `neoreef-pipeline`; pytest config
environment.yml                # conda env (rasterio/geopandas/fiona)
Batch_metashape.py             # USER CONFIG block for the photogrammetry batch (run with metashape.exe -r)
cesium_pipeline.py             # compatibility shim -> neoreef.pipeline.cli (same as `neoreef-pipeline`)

src/neoreef/
  common/                      # stdlib ONLY (must import inside Metashape's Python 3.9)
    naming.py                  #   survey/ortho/COG/landuse/model naming; IMAGE_EXTENSIONS
    landuse_codes.py           #   TOCHICD legend (single source of truth) + era_to_calendar()
    geodesy.py                 #   SURVEY_AREA + ENU->ECEF transform for placing 3D tilesets
    logging.py, fs.py          #   logger factories, small fs helpers
  metashape/                   # imports Metashape lazily; unit-tested with a stub module
    config.py                  #   MetashapeConfig (enum names resolved at call time)
    discovery.py               #   survey-folder + image discovery (sorted, deterministic)
    processing.py              #   one function per Metashape step
    export_preview.py          #   JPEG preview
    export_model.py            #   OBJ -> glb -> gltfpack -> tileset.json + survey_meta.json
    batch.py                   #   the per-survey loop: run(cfg)
  pipeline/                    # conda / Docker runtime
    cli.py                     #   argparse; loads state, runs stages, saves state
    config.py                  #   PipelineConfig; TWO ion tokens (write vs read-only viewer)
    context.py                 #   PipelineContext (out_dir, viewers_dir, log)
    records.py                 #   OrthoRecord / LanduseRecord / Model3DRecord / RecordSet
    state.py                   #   .state/records.json persisted between stage runs
    manifest_schema.py         #   build_manifest(): manifest.json schema v2 (pure function)
    geo/raster.py, geo/vector.py   # COG, bbox, PNG preview; shapefile -> GeoJSON
    ion/client.py, ion/upload.py   # ion REST client; upload with status-aware reuse
    stages/{cog,landuse,model3d,upload,manifest,serve}.py   # run(ctx, rs) -> rs

viewers/                       # copied verbatim next to manifest.json by the manifest stage
  index.html                   #   main viewer (orthos + land use + 3D models + Pepper's ghost)
  ortho.html, landuse.html     #   single-purpose pages
  css/common.css, css/themes.css
  js/manifest.js, viewer.js, camera.js, legend.js, separation.js
  js/layers/{ortho,landuse,models}.js, js/ui/{toolbar,status}.js, js/modes/peppers_ghost.js

config/                        # *.json gitignored except *.example.json
  cesium_config.example.json, cesium_config.docker.example.json, survey_positions.example.json
deploy/                        # docker-compose.yml, Dockerfile.pipeline, nginx/default.conf, Dockerfile.devtools
scripts/                       # metashape_batch.py shim, run_metashape.ps1, run_pipeline.ps1
tests/                         # pytest (171 tests); `geo` marker for tests needing rasterio/geopandas
LANDUSE/                       # land-use shapefiles (Land-useMap_H23/...) + legend PDFs
docs/                          # ARCHITECTURE_BLUEPRINT.md, architecture/*.svg, DEPLOY_MDX.md, REMOTE_DEV_MDX.md
Processed_Projects/            # gitignored local pipeline output (testbed)
```

## How to run

### 1. Metashape photogrammetry (inside Metashape, not plain Python)

```bash
metashape.exe -r Batch_metashape.py      # edit the USER CONFIG block first (TARGET_FOLDER, paths)
# or: .\scripts\run_metashape.ps1
```

`EXPORT_3D_MODEL = True` runs OBJ -> `obj2gltf` -> `gltfpack` -> `tileset.json` and writes
`survey_meta.json` beside it. Requires `obj2gltf` (`npm install -g obj2gltf`) and `gltfpack` on PATH.
The tileset has no globe transform until the pipeline's `model3d` stage adds one from `config/survey_positions.json`.

### 2. Cesium pipeline (conda environment)

```bash
conda env create -f environment.yml && conda activate neoreef
pip install -e ".[pipeline,dev]"
cp config/cesium_config.example.json config/cesium_config.json       # fill in paths + tokens
cp config/survey_positions.example.json config/survey_positions.json # one entry per 3D model

neoreef-pipeline --stage all                      # = python cesium_pipeline.py --stage all
neoreef-pipeline --stage cog|landuse|model3d|upload|manifest
neoreef-pipeline --stage serve --port 8765        # dev server with Range + CORS
neoreef-pipeline --stage manifest --rescan        # discard .state/records.json first
pytest                                            # run the test suite (Anaconda/conda Python, not Metashape's)
```

Stages read and write `CESIUM_OUTPUT_DIR/.state/records.json`, so a stage run on its own
sees exactly what earlier stages produced (ortho types, bboxes, ion ids). Nothing is re-guessed from filenames.

### 3. Docker deployment (on-premise / MDX)

```bash
cd deploy
cp ../config/cesium_config.docker.example.json ../config/cesium_config.docker.json
docker compose build pipeline
docker compose run --rm pipeline --config /app/config/cesium_config.docker.json --stage all
docker compose up -d nginx                        # NEOREEF_PORT=8080 docker compose up -d nginx
```

`DATA_SOURCE_DIR` (default: repo root) is mounted at `/app/input`; `config/` at `/app/config`; output goes to a named volume nginx serves. See `docs/DEPLOY_MDX.md` for the mdx VM.

### 4. Viewers

Must be served over HTTP (ES modules + `fetch()` do not work from `file://`). Use `--stage serve` for dev or nginx in production.

- `index.html` — main viewer; `index.html?mode=peppers-ghost[&mirror=true][&speed=0.1]` for holographic displays
- `ortho.html` — orthomosaics only; `landuse.html` — land use only

## Config reference (`config/cesium_config.json`)

| Key | Purpose |
|---|---|
| `OUTPUT_BASE` | Directory containing Metashape `*_ortho.tif` / `*_coral_ortho.tif` outputs |
| `LANDUSE_DIR` | Directory with `Land-useMap_*` shapefile subdirectories |
| `CESIUM_OUTPUT_DIR` | Where the pipeline writes cogs/, previews/, landuse/, models/, manifest.json, viewers, .state/ |
| `MODELS_3D_DIR` | Directory scanned for `tileset.json` dirs and standalone `.glb/.gltf` |
| `CESIUM_ION_WRITE_TOKEN` | assets:write token; used by `--stage upload` only, never published |
| `CESIUM_ION_VIEWER_TOKEN` | separate assets:read token; written into manifest.json for the browser |
| `CESIUM_ION_TOKEN` | deprecated alias of the write token (warns) |
| `USE_ION` | `false` for local-only serving (PNG previews + GeoJSON) |
| `SERVER_BASE_URL` | `""` for relative URLs; full URL when data is on another origin |
| `SURVEY_PATTERN` | regex for survey names (default accepts any two-digit year) |
| `SURVEY_POSITIONS` / `SURVEY_POSITIONS_FILE` | lon/lat/height/heading per survey for 3D models (default: `survey_positions.json` beside the config) |
| `EXTRA_ORTHOS`, `EXTRA_3D_MODELS`, `known_ion_assets`, `BASE_ION_3DTILES_ASSET`, `BASE_ION_IMAGERY_ASSET` | as before |
| `VIEWERS_DIR` (or env `NEOREEF_VIEWERS_DIR`) | override the viewer directory to copy (default `<repo>/viewers`) |

## Conventions

- **Import boundaries**: `neoreef.common` is stdlib-only. `neoreef.metashape` may import `Metashape` and `common`, never the pipeline or GDAL libs. `neoreef.pipeline` imports GDAL/requests/boto3 lazily inside functions. Viewer JS shares code via relative `import`, never by copy.
- **Python version**: everything under `common/` and `metashape/` must run on Python 3.9 (Metashape's interpreter): no `X | None`, no `match`.
- **Naming lives in `common/naming.py`**: survey folders `Ishi{YY}_S{NNN}_{MMDD}_A{N}`; orthos `{survey}_ortho.tif` / `{survey}_coral_ortho.tif`; COGs `{survey}_{type}_cog.tif`; land-use layers `landuse_{era}_{stem}`; manifest ids `{survey}:{type}`.
- **TOCHICD legend** is defined once in `common/landuse_codes.py`; the pipeline emits `tochicd_legend.json` and the viewers fetch it. Never hand-copy it into JS.
- **manifest.json is versioned** (`schema_version`); `manifest_schema.build_manifest` is the only place its shape is defined and `viewers/js/manifest.js` refuses unknown versions. Bump both together.
- **Config-at-top for Metashape**: `Batch_metashape.py` is the user-facing config and builds a `MetashapeConfig`; enum tunables are strings (`"MildFiltering"`).
- **Error resilience**: `CONTINUE_ON_ERROR = True` everywhere; stages log and keep going; the CLI always saves state after each stage.
- **CRS handling**: underwater surveys have no CRS (local coords); land-use shapefiles are JGD2011 (`EPSG:6684/6685`); the pipeline reprojects to WGS84 for the viewers. Models get a globe transform only via `survey_positions.json`.
- **No build step** for viewers: plain ES modules + CesiumJS from CDN.
- **Tests**: `pytest` with the conda/Anaconda interpreter. Geospatial tests carry the `geo` marker. Metashape modules are tested against a stub `Metashape` module (`tests/test_metashape_modules.py`).

## Workflow rules

1. **Never commit `config/*.json`** except the `*.example.json` templates; they hold ion tokens. `Processed_Projects/` and `*.log` are gitignored too (manifest.json carries the viewer token).
2. **Metashape scripts need the Metashape runtime** (`metashape.exe -r`), not plain `python`.
3. **Check the USER CONFIG paths** in `Batch_metashape.py` before running.
4. **Proxy on campus**: set `HTTP_PROXY`/`HTTPS_PROXY` to `http://proxy.noc.titech.ac.jp:3128`. The devcontainer and Docker Compose inherit them. Loopback tests bypass the proxy explicitly.
5. **Large files**: BigTIFF, windowed COG writes, multipart S3 uploads; nginx and the dev server both honour Range requests.
6. **Two Dockerfiles** in `deploy/`: `Dockerfile.pipeline` is the app; `Dockerfile.devtools` is a Claude Code/Node image (also `.devcontainer/Dockerfile`).
7. **Legacy scripts were deleted** in the modularization (NeoReef*.py, Batch_metashape without extension, Agisoft_test.py). They are in git history if ever needed.

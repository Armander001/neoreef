# NeoReef

Coral reef ecological data visualized as interactive 3D layers on a CesiumJS globe. Processes underwater photogrammetry from Ishigaki Island field surveys (Nakamura Lab, Tokyo Tech) and serves the results on-premise via Docker.

## Tech stack

| Layer | Technology |
|---|---|
| Photogrammetry | Agisoft Metashape Pro 2.x (Python scripting API) |
| Geospatial processing | rasterio, geopandas, fiona (conda-forge; GDAL-backed) |
| 3D globe & viewers | CesiumJS 1.117 (loaded from CDN), vanilla JS, no build step |
| Cloud tile hosting | Cesium ion REST API, boto3 for S3 uploads |
| HTTP deps | requests (ion API calls) |
| On-premise hosting | Docker Compose: nginx:alpine (static files) + miniconda3 pipeline |
| Dev environment | VS Code devcontainer (Python 3.11 + conda) |

## Project structure

```
Batch_metashape.py          # Active batch processor (single-folder or full-year mode)
NeoReef.py                  # Single-survey Metashape script
NeoReef_slim                # Variant with different default paths
NeoReef_batch.py            # Older Ishi25-only batch runner
Batch_metashape             # Older Ishi24/25 batch runner (no JPEG/glTF export)
Agisoft_test.py             # Minimal Metashape smoke test
Layer_Landuse.py            # Empty placeholder

cesium_pipeline.py          # Post-processing pipeline (COG, GeoJSON, 3D models,
                            #   ion upload, manifest, local HTTP server)
cesium_config.example.json  # Config template — copy to cesium_config.json
cesium_config.json          # GITIGNORED — contains Cesium ion token

cesium_viewer.html          # Main viewer (ortho + landuse + 3D models + Pepper's ghost mode)
ortho_viewer.html           # Ortho-only viewer (simpler UI)
landuse_viewer.html         # Land-use-only viewer

requirements_cesium.txt     # Python deps for the pipeline
Dockerfile.app              # Production container (miniconda3 + geospatial stack)
Dockerfile                  # Claude Code dev container (Node.js, not for the app)
docker-compose.yml          # nginx + pipeline services
nginx/default.conf          # Static file serving with CORS and range request support
.devcontainer/              # VS Code devcontainer config (Python 3.11 + conda)
.vscode/settings.json       # Claude Code terminal integration
docs/                       # Diagrams (environment-setup.svg)
```

## How to run

### 1. Metashape photogrammetry (not standalone Python)

Scripts require the Metashape Python environment. Run inside Metashape:

```bash
metashape.exe -r Batch_metashape.py        # batch — edit TARGET_FOLDER first
metashape.exe -r NeoReef.py                # single survey — edit USER CONFIG first
```

Set `EXPORT_GLTF = True` in `Batch_metashape.py` to also export textured meshes as `.glb` for 3D viewing.

### 2. Cesium pipeline (standalone Python)

```bash
# Install deps — GDAL packages must come from conda on Windows
conda install -c conda-forge rasterio geopandas fiona
pip install requests boto3

# Full pipeline
python cesium_pipeline.py --config cesium_config.json --stage all

# Individual stages
python cesium_pipeline.py --config cesium_config.json --stage cog
python cesium_pipeline.py --config cesium_config.json --stage landuse
python cesium_pipeline.py --config cesium_config.json --stage model3d
python cesium_pipeline.py --config cesium_config.json --stage upload
python cesium_pipeline.py --config cesium_config.json --stage manifest
python cesium_pipeline.py --config cesium_config.json --stage serve --port 8765
```

Pipeline stages: `cog` (GeoTIFF to COG), `landuse` (shapefile to GeoJSON), `model3d` (scan/copy glTF and 3D Tiles), `upload` (push to Cesium ion), `manifest` (write manifest.json + copy viewers), `serve` (local HTTP server on 0.0.0.0).

### 3. Docker deployment (on-premise / MDX)

```bash
docker compose up -d nginx                  # start web server (port 80 default)
docker compose run --rm pipeline \          # run data pipeline on-demand
  --config /app/config/cesium_config.json --stage all
NEOREEF_PORT=8080 docker compose up -d nginx  # custom port
```

### 4. Viewers

Must be served over HTTP — `file://` breaks `fetch()`. Use `--stage serve` for dev or `docker compose up nginx` for production.

- **Main viewer**: `cesium_viewer.html`
- **Pepper's ghost mode**: `cesium_viewer.html?mode=peppers-ghost` — black background, no UI, fixed 45-degree camera, auto-rotation. Add `&mirror=true` for reflected setups, `&speed=0.1` to adjust rotation speed.
- **Ortho-only**: `ortho_viewer.html`
- **Land-use-only**: `landuse_viewer.html`

## Config reference (`cesium_config.json`)

| Key | Purpose |
|---|---|
| `OUTPUT_BASE` | Directory containing Metashape `*_ortho.tif` outputs |
| `LANDUSE_DIR` | Directory with `Land-useMap_*` shapefile subdirectories |
| `CESIUM_OUTPUT_DIR` | Where pipeline writes COGs, GeoJSON, manifest, and copies viewers |
| `CESIUM_ION_TOKEN` | Cesium ion JWT (never commit) |
| `USE_ION` | `true` to upload to ion, `false` for local-only serving |
| `SERVER_BASE_URL` | Leave `""` for relative URLs; set to e.g. `http://163.220.179.199/neoreef` for cross-origin |
| `LOCAL_SERVER_PORT` | Port for `--stage serve` (default 8765) |
| `SURVEY_PATTERN` | Regex matching survey folder names |
| `SHAPEFILE_FALLBACK_CRS` | CRS for shapefiles without a `.prj` (default `EPSG:6685`) |
| `MODELS_3D_DIR` | Directory to scan for `.glb`, `.gltf`, `tileset.json` |
| `EXTRA_ORTHOS` | Array of `{path, survey_name, ortho_type}` for non-standard orthos |
| `EXTRA_3D_MODELS` | Array of `{path, survey_name, model_type, format, position}` |
| `known_ion_assets` | Map of `name -> asset_id` for pre-uploaded ion assets |
| `BASE_ION_3DTILES_ASSET` | Ion asset ID for base 3D tileset (e.g. Google Photorealistic) |

## Coding conventions

- **Config-at-top pattern**: Metashape scripts define all tunables as ALL_CAPS constants in a `USER CONFIG` block. The Cesium pipeline reads from `cesium_config.json`.
- **Survey folder naming**: `Ishi{YY}_S{NNN}_{MMDD}_A{N}` (e.g. `Ishi25_S008_0915_A1`). The pipeline regex is configurable via `SURVEY_PATTERN`.
- **Image discovery**: Metashape scripts scan single-letter A-Z subdirectories for image files.
- **Error resilience**: `CONTINUE_ON_ERROR = True` everywhere. Batch scripts log failures and keep processing. All stages are wrapped in try/except.
- **Logging**: Metashape scripts use `make_logger()` (console + file). The pipeline uses Python `logging`. Metashape scripts guard against closed stdout/stderr.
- **CRS handling**: underwater surveys use `SET_CRS = None` (local arbitrary coords). Land-use shapefiles use `EPSG:6684`/`EPSG:6685` (JGD2011 Japan zones). The pipeline reprojects everything to WGS84 (`EPSG:4326`) for the viewers.
- **Manifest URLs**: relative by default (co-hosted viewers+data). Set `SERVER_BASE_URL` in config for cross-origin deployments.
- **No build step**: viewers are single-file HTML with inline CSS/JS, loading CesiumJS from CDN.
- **File naming**: Python scripts use PascalCase with underscores (`Batch_metashape.py`). Config and infra files use lowercase (`cesium_pipeline.py`, `docker-compose.yml`).

## Workflow rules

1. **Never commit `cesium_config.json`**. It contains a Cesium ion JWT. Copy `cesium_config.example.json` and fill in values. The `.gitignore` already excludes it.
2. **Metashape scripts need the Metashape runtime**. Run with `metashape.exe -r`, not `python`. They import the `Metashape` module which only exists in the Metashape Python environment.
3. **Check hardcoded paths before running**. Metashape scripts have Windows paths to photo libraries and output directories baked into their `USER CONFIG` sections.
4. **Proxy on campus**: set `HTTP_PROXY`/`HTTPS_PROXY` to `http://proxy.noc.titech.ac.jp:3128`. The devcontainer and Docker Compose inherit these from host env vars.
5. **Large file handling**: orthomosaic TIFFs can be multi-GB. The pipeline uses BigTIFF, windowed reads, and multipart S3 uploads. nginx is configured with `sendfile on` and supports range requests for efficient COG serving.
6. **Two Dockerfiles**: `Dockerfile` is for Claude Code (dev tooling, Node.js). `Dockerfile.app` is the production pipeline (miniconda3 + geospatial). Don't confuse them.
7. **Script lineage**: `NeoReef.py` -> `NeoReef_slim` -> `NeoReef_batch.py` -> `Batch_metashape` -> `Batch_metashape.py`. Only `Batch_metashape.py` is actively maintained; the others are kept for reference.

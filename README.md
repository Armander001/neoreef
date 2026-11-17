# NeoReef

Coral reef ecological data visualized as interactive 3D layers on a [CesiumJS](https://cesium.com/platform/cesiumjs/) globe. NeoReef processes underwater photogrammetry from Ishigaki Island field surveys (Nakamura Lab, Institute of Science Tokyo) and serves the results as browser-based viewers — orthomosaics, land-use maps, and compressed 3D reef models draped over a realistic globe.

## What's here today

| Stage | Tooling | Entry point |
|---|---|---|
| Photogrammetry | Agisoft Metashape Pro 2.x (Python API) | `Batch_metashape.py` (run with `metashape.exe -r`) → `src/neoreef/metashape/` |
| Geospatial post-processing | rasterio / geopandas / Cesium ion | `neoreef-pipeline` (or `python cesium_pipeline.py`) → `src/neoreef/pipeline/` |
| Visualization | CesiumJS 1.117, ES modules, no build step | `viewers/index.html`, `viewers/ortho.html`, `viewers/landuse.html` |
| Hosting | Docker Compose (nginx + pipeline) | `deploy/docker-compose.yml` |

The pipeline converts Metashape orthomosaic GeoTIFFs to Cloud Optimized GeoTIFFs (plus browser-ready PNG previews), land-use shapefiles to styled GeoJSON, and places exported 3D models on the globe, then writes a versioned `manifest.json` that the viewers consume. Layers can be served locally (nginx with range-request support) or uploaded to Cesium ion.

The main viewer also has a **Pepper's ghost mode** (`index.html?mode=peppers-ghost`) for holographic prism displays.

## Quick start

```bash
# 1. Photogrammetry (inside Metashape — edit the USER CONFIG block first)
metashape.exe -r Batch_metashape.py

# 2. Post-process for Cesium (conda env; see environment.yml)
conda env create -f environment.yml && conda activate neoreef
pip install -e ".[pipeline,dev]"
cp config/cesium_config.example.json config/cesium_config.json   # fill in paths + ion tokens
neoreef-pipeline --stage all

# 3. Serve the viewers (file:// won't work — ES modules + fetch() need HTTP)
neoreef-pipeline --stage serve
# or, production:
cd deploy && docker compose up -d nginx

# Tests
pytest
```

Full run instructions, config reference, and conventions: [CLAUDE.md](CLAUDE.md).

## Documentation

- [CLAUDE.md](CLAUDE.md) — project structure, how to run, config reference, conventions
- [docs/ARCHITECTURE_BLUEPRINT.md](docs/ARCHITECTURE_BLUEPRINT.md) — module layout, data flow, manifest contract
- [docs/architecture/](docs/architecture/README.md) — subsystem diagrams
- [docs/DEPLOY_MDX.md](docs/DEPLOY_MDX.md) — deploying to the mdx research cloud
- [docs/REPORT_code_duplication.md](docs/REPORT_code_duplication.md) — the pre-refactor code-health report

## Vision

NeoReef aims to grow into an immersive platform that layers ecological data — satellite SST, bleaching-risk indices, time-lapse survey comparisons — over photorealistic reef models, supporting research, education, and conservation storytelling ("the living twin of Earth's ecosystems"). The current codebase is the data foundation: repeatable survey processing and web-based 3D delivery. AR/VR interaction, global climate layers, and collaborative annotation are future work.

## License

[MIT](LICENSE)

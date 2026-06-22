# NeoReef

Coral reef ecological data visualized as interactive 3D layers on a [CesiumJS](https://cesium.com/platform/cesiumjs/) globe. NeoReef processes underwater photogrammetry from Ishigaki Island field surveys (Nakamura Lab, Institute of Science Tokyo) and serves the results as browser-based viewers — orthomosaics, land-use maps, and compressed 3D reef models draped over a realistic globe.

## What's here today

| Stage | Tooling | Entry point |
|---|---|---|
| Photogrammetry | Agisoft Metashape Pro 2.x (Python API) | `Batch_metashape.py` (run with `metashape.exe -r`) |
| Geospatial post-processing | rasterio / geopandas / Cesium ion | `cesium_pipeline.py` |
| Visualization | CesiumJS 1.117, no build step | `cesium_viewer.html`, `ortho_viewer.html`, `landuse_viewer.html` |
| Hosting | Docker Compose (nginx + pipeline) | `docker-compose.yml` |

The pipeline converts Metashape orthomosaic GeoTIFFs to Cloud Optimized GeoTIFFs, land-use shapefiles to styled GeoJSON, and OBJ exports to meshopt/KTX2-compressed glTF, then writes a `manifest.json` that the viewers consume. Layers can be served locally (nginx with range-request support) or uploaded to Cesium ion.

The main viewer also has a **Pepper's ghost mode** (`cesium_viewer.html?mode=peppers-ghost`) for holographic prism displays.

## Quick start

```bash
# 1. Photogrammetry (inside Metashape — edit USER CONFIG block first)
metashape.exe -r Batch_metashape.py

# 2. Post-process for Cesium (standalone Python; see requirements_cesium.txt)
cp cesium_config.example.json cesium_config.json   # fill in paths + ion token
python cesium_pipeline.py --config cesium_config.json --stage all

# 3. Serve the viewers (file:// won't work — fetch() needs HTTP)
python cesium_pipeline.py --config cesium_config.json --stage serve
# or, production:
docker compose up -d nginx
```

Full run instructions, config reference, and conventions: [CLAUDE.md](CLAUDE.md).

## Documentation

- [CLAUDE.md](CLAUDE.md) — project structure, how to run, config reference, conventions
- [docs/architecture/](docs/architecture/README.md) — subsystem diagrams (data flow, pipelines, viewers, Docker stack)
- [docs/DEPLOY_MDX.md](docs/DEPLOY_MDX.md) — deploying to the mdx research cloud
- [docs/REPORT_code_duplication.md](docs/REPORT_code_duplication.md) — code-health report and cleanup plan

## Vision

NeoReef aims to grow into an immersive platform that layers ecological data — satellite SST, bleaching-risk indices, time-lapse survey comparisons — over photorealistic reef models, supporting research, education, and conservation storytelling ("the living twin of Earth's ecosystems"). The current codebase is the data foundation: repeatable survey processing and web-based 3D delivery. AR/VR interaction, global climate layers, and collaborative annotation are future work.

## License

[MIT](LICENSE)

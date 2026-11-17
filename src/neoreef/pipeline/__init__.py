"""Cesium post-processing pipeline.

Turns Metashape outputs (orthomosaic GeoTIFFs, 3D models) and land-use
shapefiles into web-ready artefacts (COGs, PNG previews, GeoJSON, placed
3D Tiles) plus a versioned ``manifest.json`` the viewers consume.

Layout
------
config.py          PipelineConfig + load_config()        (two ion tokens)
context.py         PipelineContext: config, logger, output directories
records.py         OrthoRecord / LanduseRecord / Model3DRecord / RecordSet
state.py           persist the RecordSet between stage runs (.state/records.json)
manifest_schema.py build_manifest(): the Python <-> JS contract, schema v2
geo/               rasterio / geopandas wrappers (lazy imports)
ion/               Cesium ion REST client + upload workflow
stages/            one module per stage: run(ctx, rs) -> rs
cli.py             argparse entry point (``neoreef-pipeline``)

RULE: runs in the conda / Docker environment; may import rasterio,
geopandas, requests, boto3 (always lazily, inside functions, so the
scan-only paths and tests work without them).
"""

# NeoReef Pipeline — production container
# Processes Metashape outputs into Cesium-ready formats (COGs, GeoJSON, manifest).
#
# Usage:
#   docker compose run --rm pipeline --config /app/config/cesium_config.json --stage all

FROM continuumio/miniconda3

# Optional proxy build args — pass with --build-arg when inside the lab
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY="localhost,127.0.0.1"
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

# Install geospatial stack (GDAL-based packages must come from conda-forge)
RUN conda install -y -c conda-forge rasterio geopandas fiona \
    && pip install --no-cache-dir requests boto3 \
    && conda clean -afy

# Copy pipeline code and viewer HTML
COPY cesium_pipeline.py /app/
COPY cesium_viewer.html ortho_viewer.html landuse_viewer.html /app/viewers/

WORKDIR /app

ENTRYPOINT ["python", "cesium_pipeline.py"]

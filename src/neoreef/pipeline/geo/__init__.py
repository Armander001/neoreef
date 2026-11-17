"""Thin wrappers around the GDAL-backed libraries (rasterio, geopandas).

All heavy imports happen inside functions so that scanning, state handling
and tests work in an environment without the geospatial stack.
"""

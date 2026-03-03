# -*- coding: utf-8 -*-
"""
Metashape 2.x photomosaic workflow for Ishigaki_2025 sets
- Adds all images from A..Z subfolders
- Aligns photos with strong settings suited to underwater
- Builds depth maps, mesh (from depth maps), and orthomosaic
- Saves project and exports orthomosaic (GeoTIFF if CRS present)

Run in Metashape:
  1) Tools -> Run Script... (select this file), or
  2) metashape.exe -r path\to\this_script.py
"""

import Metashape
from pathlib import Path
import os

import sys
sys.path.append(r"C:\Program Files\Agisoft\Metashape Pro\python")
import Metashape

# -------------------
# USER CONFIG
# -------------------
PROJECT_PSX = r"D:\Armando\Ishi25_S008_0915_A1\Ishi25_S008_0915_A1.psx"
IMAGE_ROOT  = r"D:\Armando\Ishi25_S008_0915_A1"
ORTHO_OUT   = r"D:\Armando\Ishi25_S008_0915_A1\Ishi25_S008_0915_A1_ortho.tif"

# If your TG-7 wrote GPS EXIF (linked via OM Workspace), keep True to try reference preselection.
# If not (common underwater), set to False.
USE_REFERENCE_PRESELECTION = False

# Optional: set a CRS if you KNOW you have valid GPS (e.g., EPSG:4326).
# Leave as None for arbitrary local coords.
SET_CRS = None  # e.g., "EPSG::4326"

# Downscale 1 = highest quality matching, 2 is faster; underwater often benefits from 1
MATCH_DOWNSCALE = 1

# Depth maps quality (downscale): 2 is a good balance; 1 is highest quality
DEPTH_DOWNSCALE = 2

# Filtering for depth maps; Mild keeps more detail for low-texture substrates
DEPTH_FILTER = Metashape.MildFiltering

# -------------------
# DISCOVER IMAGES
# -------------------
root = Path(IMAGE_ROOT)
subdirs = [p for p in root.iterdir() if p.is_dir() and len(p.name) == 1 and p.name.isalpha()]
subdirs.sort()  # A, B, C ...

exts = {".jpg", ".jpeg", ".JPG", ".JPEG", ".png", ".PNG", ".orf", ".ORF", ".tif", ".tiff", ".TIF", ".TIFF"}
image_list = []
for d in subdirs:
    for f in d.iterdir():
        if f.suffix in exts and f.is_file():
            image_list.append(str(f))

if not image_list:
    raise RuntimeError(f"No images found in A..Z subfolders under: {IMAGE_ROOT}")

print(f"Discovered {len(image_list)} images from {len(subdirs)} subfolders: {', '.join(p.name for p in subdirs)}")

# -------------------
# PROJECT / CHUNK
# -------------------
app = Metashape.app
# Save absolute paths into the .psx to avoid future path resolution issues
app.settings.project_absolute_paths = True  # documented settings flag

doc = Metashape.Document()
if os.path.exists(PROJECT_PSX):
    print(f"Opening existing project: {PROJECT_PSX}")
    doc.open(PROJECT_PSX)
else:
    print(f"Creating new project: {PROJECT_PSX}")
    doc.save(PROJECT_PSX)

# Work on the active chunk or create one if none
chunk = doc.chunk if doc.chunk is not None else doc.addChunk()
chunk.label = "Ishi25_S008_0915_A1" 

# Assign CRS if the images have valid GPS and you want georeferencing
if SET_CRS:
    try:
        chunk.crs = Metashape.CoordinateSystem(SET_CRS)
        print(f"Assigned CRS: {SET_CRS}")
    except Exception as e:
        print(f"Warning: failed to set CRS {SET_CRS}: {e}")

# Add photos (skip already added)
if not chunk.cameras:
    print("Adding photos...")
    chunk.addPhotos(image_list)
else:
    print("Photos already present in chunk; skipping addPhotos().")

doc.save()

# -------------------
# ALIGNMENT
# -------------------
print("Matching photos...")
chunk.matchPhotos(
    downscale=MATCH_DOWNSCALE,
    generic_preselection=True,
    reference_preselection=USE_REFERENCE_PRESELECTION,
    # mask handling: keep tie points away from masked areas if any masks exist
    mask_tiepoints=True,
    filter_stationary_points=True,
    # underwater often benefits from higher limits (more features retained)
    keypoint_limit=60000,
    tiepoint_limit=8000
)

print("Aligning cameras...")
chunk.alignCameras()

# Optional: refine optimization (keep default flags to avoid version-specific args)
print("Optimizing cameras...")
try:
    chunk.optimizeCameras()
except Exception as e:
    print(f"optimizeCameras() warning (continuing): {e}")

doc.save()

# -------------------
# DEPTH MAPS & MODEL
# -------------------
print("Building depth maps...")
chunk.buildDepthMaps(downscale=DEPTH_DOWNSCALE, filter_mode=DEPTH_FILTER)

print("Building mesh from depth maps...")
chunk.buildModel(
    source_data=Metashape.DepthMapsData,
    surface_type=Metashape.Arbitrary,  # HeightField is OK for flatter bottoms; Arbitrary is safer in reefs
    interpolation=Metashape.EnabledInterpolation
)

doc.save()

# -------------------
# ORTHOMOSAIC
# -------------------
# If you have a fairly planar scene, you can also build DEM and ortho from DEM.
# Underwater, building ortho from the mesh surface commonly yields good results.
print("Building orthomosaic from model surface...")
chunk.buildOrthomosaic(  # keep defaults; resolution chosen automatically if none specified
    surface=Metashape.ModelData,
    blending_mode=Metashape.MosaicBlending,
    refine_seamlines=True,
    fill_holes=True
)

# Export orthomosaic (GeoTIFF if CRS present; will include world file/GeoTIFF tags)
print(f"Exporting orthomosaic to: {ORTHO_OUT}")
chunk.exportOrthomosaic(
    ORTHO_OUT,
    image_format=Metashape.ImageFormatTIFF,
    tiff_big=True,  # allow BigTIFF for large areas
    write_kml=False,
    world_file=True  # writes .tfw if not georeferenced
)

doc.save()
print("Done.")

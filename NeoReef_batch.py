# -*- coding: utf-8 -*-
"""
Batch Metashape 2.x photomosaic workflow for Ishigaki_2025 survey
- Finds each survey folder (Ishi25_S###_MMDD_A#)
- For each one, creates/opens a project and processes it
- Aligns photos, builds depth maps, mesh, and orthomosaic
- Saves project and exports orthomosaic (GeoTIFF if CRS present)

Run in Metashape:
  1) Tools -> Run Script... (select this file), or
  2) metashape.exe -r path\to\this_script.py
"""

import Metashape
from pathlib import Path
import os
import re

import sys

try:
    if sys.stdout is None or getattr(sys.stdout, "closed", False):
        sys.stdout = sys.__stdout__
    if sys.stderr is None or getattr(sys.stderr, "closed", False):
        sys.stderr = sys.__stderr__
except Exception:
    pass




sys.path.append(r"C:\Program Files\Agisoft\Metashape Pro\python")
import Metashape





# -------------------
# USER CONFIG - PATHS
# -------------------
PHOTO_LIBRARY = r"S:\Armando\SURVEY_PHOTO_LIBRARY\Ishigaki_2024"
OUTPUT_BASE   = r"D:\Armando\Processed_Projects"

# -------------------
# IMAGE DISCOVERY CONFIG
# -------------------
# File extensions to include in image discovery
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".JPG", ".JPEG", ".png", ".PNG", ".orf", ".ORF", ".tif", ".tiff", ".TIF", ".TIFF"}

# -------------------
# PHOTO ALIGNMENT CONFIG
# -------------------
# Generic keypoint detection (True = more robust; set False to rely only on reference preselection)
ALIGNMENT_GENERIC_PRESELECTION = True

# Reference preselection: Use GPS/EXIF data if available (True for TG-7 with GPS in shallow water)
# Set False for underwater or when GPS is unreliable/absent
ALIGNMENT_REFERENCE_PRESELECTION = False

# Photo matching downscale: 1 = highest quality (slower), 2 = faster, 4 = much faster
# Underwater often benefits from 1 for better feature matching on low-texture substrates
ALIGNMENT_MATCH_DOWNSCALE = 1

# Maximum keypoints to extract per image (higher = more detail but slower)
# Underwater scenes benefit from higher limits (more features retained)
ALIGNMENT_KEYPOINT_LIMIT = 60000

# Maximum tie points to use for alignment (higher = more robust but slower)
ALIGNMENT_TIEPOINT_LIMIT = 8000

# Mask tie points away from masked regions (if masks exist in images)
ALIGNMENT_MASK_TIEPOINTS = True

# Filter out stationary/background points before alignment
ALIGNMENT_FILTER_STATIONARY = True

# -------------------
# DEPTH MAPS CONFIG
# -------------------
# Depth map quality (downscale): 1 = highest quality (slow), 2 = balanced, 4 = faster
# For reef surveys, 2 is good balance between detail and processing time
DEPTH_DOWNSCALE = 2

# Filtering mode: MildFiltering, ModerateFiltering, AggressiveFiltering
# MildFiltering keeps more detail for low-texture underwater substrates
DEPTH_FILTER = Metashape.MildFiltering

# -------------------
# MESH & ORTHOMOSAIC CONFIG
# -------------------
# Surface type: Arbitrary (most robust for complex reefs), HeightField (for flatter bottoms)
MESH_SURFACE_TYPE = Metashape.Arbitrary

# Orthomosaic interpolation: EnabledInterpolation (fill gaps), DisabledInterpolation (keep holes)
ORTHO_INTERPOLATION = Metashape.EnabledInterpolation

# Blending mode: MosaicBlending (smooth transitions), AverageBlending, DisabledBlending
ORTHO_BLENDING = Metashape.MosaicBlending

# Refine seamlines for better blending at image boundaries
ORTHO_REFINE_SEAMLINES = True

# Fill small holes in orthomosaic
ORTHO_FILL_HOLES = True

# Use BigTIFF format for large outputs (handles >4GB files)
ORTHO_BIGTIFF = True

# -------------------
# COORDINATE SYSTEM CONFIG
# -------------------
# Optional: set a CRS if you KNOW you have valid GPS (e.g., EPSG:4326).
# Leave as None for arbitrary local coords and relative positioning.
SET_CRS = None  # e.g., "EPSG:4326"

# -------------------
# ERROR RECOVERY CONFIG
# -------------------
# Continue processing remaining surveys if one fails (True = robust batch processing)
# Set False to stop on first error for debugging
CONTINUE_ON_ERROR = True

# Log all processing results to file
LOG_FILE = os.path.join(OUTPUT_BASE, "batch_processing.log")

# -------------------
# HELPER: DISCOVER IMAGES IN FOLDER
# -------------------
def get_images_from_folder(folder_path):
    """Scan A..Z subfolders and collect all image files."""
    root = Path(folder_path)
    subdirs = [p for p in root.iterdir() if p.is_dir() and len(p.name) == 1 and p.name.isalpha()]
    subdirs.sort()  # A, B, C ...

    image_list = []
    for d in subdirs:
        for f in d.iterdir():
            if f.suffix in IMAGE_EXTENSIONS and f.is_file():
                image_list.append(str(f))

    return image_list, [(p.name) for p in subdirs]

# -------------------
# MAIN BATCH LOOP
# -------------------
app = Metashape.app
app.settings.project_absolute_paths = True

# Ensure output directory exists
os.makedirs(OUTPUT_BASE, exist_ok=True)

# Initialize logging
log_handle = open(LOG_FILE, "w", encoding="utf-8", errors="replace")
def log_msg(msg):
    """Print and log message."""
    #print(msg)
    log_handle.write(msg + "\n")
    log_handle.flush()

log_msg("Batch Processing Started")
log_msg(f"Source Library: {PHOTO_LIBRARY}")
log_msg(f"Output Directory: {OUTPUT_BASE}")
log_msg("=" * 80)

# Find all survey folders matching pattern: Ishi25_S###_MMDD_A#
survey_folders = []
for item in Path(PHOTO_LIBRARY).iterdir():
    if item.is_dir() and re.match(r"Ishi25_S\d{3}_\d{4}_A\d", item.name):
        survey_folders.append(item)

survey_folders.sort()

if not survey_folders:
    log_msg(f"ERROR: No survey folders found in {PHOTO_LIBRARY}")
    log_handle.close()
    exit(1)

log_msg(f"\nFound {len(survey_folders)} survey folders to process.\n")

# Track results
results = {"successful": [], "failed": [], "skipped": []}

for idx, survey_dir in enumerate(survey_folders, 1):
    survey_name = survey_dir.name  # e.g., "Ishi25_S001_0907_A1"
    
    log_msg(f"\n[{idx}/{len(survey_folders)}] {'='*78}")
    log_msg(f"Processing: {survey_name}")
    log_msg(f"{'='*78}")

    try:
        # Set up paths for this survey
        PROJECT_PSX = os.path.join(OUTPUT_BASE, f"{survey_name}.psx")
        ORTHO_OUT   = os.path.join(OUTPUT_BASE, f"{survey_name}_ortho.tif")

        # Discover images
        try:
            image_list, subdir_names = get_images_from_folder(str(survey_dir))
            if not image_list:
                log_msg(f"  WARNING: No images found; skipping.")
                results["skipped"].append(survey_name)
                continue

            log_msg(f"  Images: {len(image_list)} files from {len(subdir_names)} subfolders: {', '.join(subdir_names)}")
        except Exception as e:
            log_msg(f"  ERROR discovering images: {e}")
            results["failed"].append((survey_name, f"Image discovery: {str(e)}"))
            if not CONTINUE_ON_ERROR:
                raise
            continue

        # Open or create project
        try:
            doc = Metashape.Document()
            if os.path.exists(PROJECT_PSX):
                log_msg(f"  Opening existing project: {PROJECT_PSX}")
                doc.open(PROJECT_PSX)
            else:
                log_msg(f"  Creating new project: {PROJECT_PSX}")
                doc.save(PROJECT_PSX)
        except Exception as e:
            log_msg(f"  ERROR loading/creating project: {e}")
            results["failed"].append((survey_name, f"Project init: {str(e)}"))
            if not CONTINUE_ON_ERROR:
                raise
            continue

        # Work on chunk
        try:
            chunk = doc.chunk if doc.chunk is not None else doc.addChunk()
            chunk.label = survey_name
            log_msg(f"  Chunk: {chunk.label}")
        except Exception as e:
            log_msg(f"  ERROR accessing chunk: {e}")
            results["failed"].append((survey_name, f"Chunk access: {str(e)}"))
            if not CONTINUE_ON_ERROR:
                raise
            continue

        # Assign CRS if needed
        if SET_CRS:
            try:
                chunk.crs = Metashape.CoordinateSystem(SET_CRS)
                log_msg(f"  CRS assigned: {SET_CRS}")
            except Exception as e:
                log_msg(f"  WARNING: Failed to set CRS {SET_CRS}: {e}")

        # Add photos if not already present
        try:
            if not chunk.cameras:
                log_msg(f"  Adding {len(image_list)} photos...")
                chunk.addPhotos(image_list)
                log_msg(f"  Photos added: {len(chunk.cameras)} cameras")
            else:
                log_msg(f"  Photos already in chunk ({len(chunk.cameras)} cameras); skipping addPhotos().")
            doc.save()
        except Exception as e:
            log_msg(f"  ERROR adding photos: {e}")
            results["failed"].append((survey_name, f"Add photos: {str(e)}"))
            if not CONTINUE_ON_ERROR:
                raise
            continue

        # ALIGNMENT
        try:
            log_msg(f"  [ALIGNMENT] Matching photos (downscale={ALIGNMENT_MATCH_DOWNSCALE})...")
            chunk.matchPhotos(
                downscale=ALIGNMENT_MATCH_DOWNSCALE,
                generic_preselection=ALIGNMENT_GENERIC_PRESELECTION,
                reference_preselection=ALIGNMENT_REFERENCE_PRESELECTION,
                mask_tiepoints=ALIGNMENT_MASK_TIEPOINTS,
                filter_stationary_points=ALIGNMENT_FILTER_STATIONARY,
                keypoint_limit=ALIGNMENT_KEYPOINT_LIMIT,
                tiepoint_limit=ALIGNMENT_TIEPOINT_LIMIT
            )
            log_msg(f"    [OK] Matching complete")

            log_msg(f"  [ALIGNMENT] Aligning cameras...")
            chunk.alignCameras()
            log_msg(f"    [OK] Alignment complete ({len(chunk.cameras)} cameras aligned)")

            log_msg(f"  [ALIGNMENT] Optimizing cameras...")
            try:
                chunk.optimizeCameras()
                log_msg(f"    [OK] Optimization complete")
            except Exception as e:
                log_msg(f"    WARNING: optimizeCameras() failed (continuing): {e}")

            doc.save()
        except Exception as e:
            log_msg(f"  ERROR during alignment: {e}")
            results["failed"].append((survey_name, f"Alignment: {str(e)}"))
            if not CONTINUE_ON_ERROR:
                raise
            continue

        # DEPTH MAPS & MODEL
        try:
            log_msg(f"  [DEPTH MAPS] Building depth maps (downscale={DEPTH_DOWNSCALE}, filter={DEPTH_FILTER})...")
            chunk.buildDepthMaps(downscale=DEPTH_DOWNSCALE, filter_mode=DEPTH_FILTER)
            log_msg(f"    [OK] Depth maps complete")

            log_msg(f"  [MODEL] Building mesh (surface={MESH_SURFACE_TYPE})...")
            chunk.buildModel(
                source_data=Metashape.DepthMapsData,
                surface_type=MESH_SURFACE_TYPE,
                interpolation=ORTHO_INTERPOLATION
            )
            log_msg(f"    [OK] Mesh complete")

            doc.save()
        except Exception as e:
            log_msg(f"  ERROR during depth maps/model: {e}")
            results["failed"].append((survey_name, f"Depth/Mesh: {str(e)}"))
            if not CONTINUE_ON_ERROR:
                raise
            continue

        # ORTHOMOSAIC
        try:
            log_msg(f"  [ORTHOMOSAIC] Building orthomosaic (blending={ORTHO_BLENDING})...")
            chunk.buildOrthomosaic(
                surface=Metashape.ModelData,
                blending_mode=ORTHO_BLENDING,
                refine_seamlines=ORTHO_REFINE_SEAMLINES,
                fill_holes=ORTHO_FILL_HOLES
            )
            log_msg(f"    [OK] Orthomosaic building complete")

            log_msg(f"  [EXPORT] Exporting orthomosaic...")
            log_msg(f"    File: {ORTHO_OUT}")
            chunk.exportOrthomosaic(
                ORTHO_OUT,
                image_format=Metashape.ImageFormatTIFF,
                tiff_big=ORTHO_BIGTIFF,
                write_kml=False,
                world_file=True
            )
            log_msg(f"    [OK] Export complete")

            doc.save()
        except Exception as e:
            log_msg(f"  ERROR during orthomosaic/export: {e}")
            results["failed"].append((survey_name, f"Ortho/Export: {str(e)}"))
            if not CONTINUE_ON_ERROR:
                raise
            continue

        log_msg(f"  [PASS] COMPLETED SUCCESSFULLY: {survey_name}")
        results["successful"].append(survey_name)

    except Exception as e:
        log_msg(f"  [FAIL] UNEXPECTED ERROR: {e}")
        results["failed"].append((survey_name, f"Unexpected: {str(e)}"))
        if not CONTINUE_ON_ERROR:
            raise

# Summary
log_msg("\n" + "=" * 80)
log_msg("BATCH PROCESSING SUMMARY")
log_msg("=" * 80)
log_msg(f"Successful: {len(results['successful'])}/{len(survey_folders)}")
for name in results["successful"]:
    log_msg(f"  [PASS] {name}")

if results["skipped"]:
    log_msg(f"\nSkipped: {len(results['skipped'])}")
    for name in results["skipped"]:
        log_msg(f"  [SKIP] {name}")

if results["failed"]:
    log_msg(f"\nFailed: {len(results['failed'])}")
    for name, reason in results["failed"]:
        log_msg(f"  [FAIL] {name}: {reason}")

log_msg("\n" + "=" * 80)
log_msg(f"Log file: {LOG_FILE}")
log_handle.close()

print("\n[DONE] Batch processing complete!")


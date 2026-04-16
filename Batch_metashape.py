# -*- coding: utf-8 -*-
"""
Batch Metashape 2.x photomosaic workflow for Ishigaki coral surveys (2024 & 2025)

TWO RUN MODES (set TARGET_FOLDER below):
  - Single folder : TARGET_FOLDER = r"S:\...\Ishi25_S001_0415_A1"
  - Full year     : TARGET_FOLDER = None  (scans entire PHOTO_LIBRARY)

No GPS / underwater workflow:
  - Orthomosaic is built in local (arbitrary) coordinates — no GPS required
  - World file is NOT written (no georeference data available)
  - If orthomosaic export fails, script falls back to a top-down model render
  - JPEG previews go to: <YEAR_ROOT>/Complete Images/<YYYYMMDD_HHMMSS>/

Run in Metashape:
  1) Tools -> Run Script... (select this file), or
  2) metashape.exe -r path\to\this_script.py
"""

# -------------------
# FIX: stdout/stderr can be closed in Metashape sessions
# -------------------
import sys
try:
    if sys.stdout is None or getattr(sys.stdout, "closed", False):
        sys.stdout = sys.__stdout__
    if sys.stderr is None or getattr(sys.stderr, "closed", False):
        sys.stderr = sys.__stderr__
except Exception:
    pass

import os
import re
from datetime import datetime
from pathlib import Path

import Metashape


# =============================================================================
# USER CONFIG
# =============================================================================

# --- Run mode ----------------------------------------------------------------
# Set TARGET_FOLDER to process a SINGLE survey folder, or None to run the
# entire year (all matching Ishi24/Ishi25 subfolders inside PHOTO_LIBRARY).
#
# Examples:
#   TARGET_FOLDER = r"S:\Armando\SURVEY_PHOTO_LIBRARY\Ishigaki_2025\Ishi25_S001_0415_A1"
#   TARGET_FOLDER = None   # <-- full-year batch
TARGET_FOLDER = r"S:\Armando\SURVEY_PHOTO_LIBRARY\Ishigaki_2025\Ishi25_S009_0926_A1"

# --- Paths -------------------------------------------------------------------
# PHOTO_LIBRARY : root that contains the individual Ishi##_S###_... folders
# YEAR_ROOT     : parent folder where "Complete Images" will be created
# OUTPUT_BASE   : where .psx project files and GeoTIFFs are saved
PHOTO_LIBRARY = r"S:\Armando\SURVEY_PHOTO_LIBRARY\Ishigaki_2025"
YEAR_ROOT     = r"S:\Armando\SURVEY_PHOTO_LIBRARY\Ishigaki_2025"
OUTPUT_BASE   = r"D:\Armando\Processed_Projects"

# =============================================================================
# PROCESSING CONFIG  (rarely needs changing)
# =============================================================================

# --- Image types -------------------------------------------------------------
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".JPG", ".JPEG",
    ".png", ".PNG",
    ".orf", ".ORF",
    ".tif", ".tiff", ".TIF", ".TIFF"
}

# --- Photo alignment ---------------------------------------------------------
ALIGNMENT_GENERIC_PRESELECTION   = True
ALIGNMENT_REFERENCE_PRESELECTION = False
ALIGNMENT_MATCH_DOWNSCALE        = 1
ALIGNMENT_KEYPOINT_LIMIT         = 60000
ALIGNMENT_TIEPOINT_LIMIT         = 8000
ALIGNMENT_MASK_TIEPOINTS         = True
ALIGNMENT_FILTER_STATIONARY      = True

# --- Depth maps --------------------------------------------------------------
DEPTH_DOWNSCALE = 2
DEPTH_FILTER    = Metashape.MildFiltering

# --- Mesh & orthomosaic ------------------------------------------------------
MESH_SURFACE_TYPE      = Metashape.Arbitrary
ORTHO_INTERPOLATION    = Metashape.EnabledInterpolation
ORTHO_BLENDING         = Metashape.MosaicBlending
ORTHO_REFINE_SEAMLINES = True
ORTHO_FILL_HOLES       = True
ORTHO_BIGTIFF          = True

# --- JPEG export -------------------------------------------------------------
# Quality for the shareable JPEG preview (1-100)
JPEG_QUALITY = 90

# --- 3D model export ---------------------------------------------------------
# Export textured mesh as glTF/glB for CesiumJS 3D viewing (set False to skip)
EXPORT_GLTF = False

# --- Coordinate system -------------------------------------------------------
# Leave None for non-GPS / underwater surveys (uses Metashape local coords)
SET_CRS = None

# --- Error handling ----------------------------------------------------------
CONTINUE_ON_ERROR = True


# =============================================================================
# HELPERS
# =============================================================================

FOLDER_PATTERN = re.compile(r"^Ishi(?:24|25)_S\d{3}_\d{4}_A\d$", re.IGNORECASE)


def collect_survey_folders(photo_library: str, target_folder):
    """
    Return a sorted list of Path objects to process.

    If target_folder is set, validate it is a real directory and return it
    alone (regardless of whether its name matches the naming convention -
    the user might be testing with a custom folder name).

    Otherwise scan photo_library for all Ishi24/25 sub-folders.
    """
    if target_folder:
        p = Path(target_folder)
        if not p.is_dir():
            raise FileNotFoundError(f"TARGET_FOLDER does not exist: {target_folder}")
        return [p]

    folders = []
    for item in Path(photo_library).iterdir():
        if item.is_dir() and FOLDER_PATTERN.match(item.name):
            folders.append(item)
    folders.sort()
    return folders


def get_images_from_folder(folder_path: str):
    """Scan A-Z subfolders and collect image files."""
    root = Path(folder_path)
    subdirs = sorted(
        p for p in root.iterdir()
        if p.is_dir() and len(p.name) == 1 and p.name.isalpha()
    )
    image_list = [
        str(f)
        for d in subdirs
        for f in d.iterdir()
        if f.is_file() and f.suffix in IMAGE_EXTENSIONS
    ]
    return image_list, [d.name for d in subdirs]


def make_logger(log_handle):
    """Thread-safe logger: Metashape console + stdout + file."""
    def log(msg: str):
        msg = str(msg)
        try:
            Metashape.app.console.print(msg)
        except Exception:
            pass
        try:
            print(msg)
        except Exception:
            pass
        try:
            log_handle.write(msg + "\n")
            log_handle.flush()
        except Exception:
            pass
    return log


def export_jpeg_preview(chunk, jpeg_path: str, jpeg_quality: int, log):
    """
    Export the orthomosaic as a shareable JPEG.

    Attempt 1 - direct orthomosaic JPEG export (works when Metashape can
                determine a local projection from the mesh).
    Attempt 2 - same call with white_background=True (sometimes resolves
                projection edge cases in non-georeferenced projects).

    Returns True if either attempt succeeded, False otherwise.
    No GPS / world file is written in either case.
    """
    common_kwargs = dict(
        image_format=Metashape.ImageFormatJPEG,
        jpeg_quality=jpeg_quality,
        write_kml=False,
        world_file=False,   # no GPS data available
    )

    # Attempt 1
    try:
        chunk.exportOrthomosaic(jpeg_path, **common_kwargs)
        log(f"    [OK] JPEG preview saved: {jpeg_path}")
        return True
    except Exception as e1:
        log(f"    WARNING: JPEG export attempt 1 failed ({e1}); trying fallback...")

    # Attempt 2 - white background variant
    try:
        fallback_path = jpeg_path.replace(".jpg", "_render.jpg")
        chunk.exportOrthomosaic(fallback_path, white_background=True, **common_kwargs)
        log(f"    [OK] JPEG fallback saved: {fallback_path}")
        return True
    except Exception as e2:
        log(f"    WARNING: JPEG export attempt 2 also failed ({e2}). No JPEG preview for this survey.")
        return False


# =============================================================================
# MAIN
# =============================================================================

def main():
    Metashape.app.settings.project_absolute_paths = True

    os.makedirs(OUTPUT_BASE, exist_ok=True)
    log_file = os.path.join(OUTPUT_BASE, "batch_processing.log")

    # One timestamped JPEG output subfolder per batch run
    run_timestamp       = datetime.now().strftime("%Y%m%d_%H%M%S")
    complete_images_dir = os.path.join(YEAR_ROOT, "Complete Images", run_timestamp)
    os.makedirs(complete_images_dir, exist_ok=True)

    with open(log_file, "w", encoding="utf-8", errors="replace") as log_handle:
        log = make_logger(log_handle)

        mode_label = (
            f"SINGLE FOLDER: {TARGET_FOLDER}" if TARGET_FOLDER
            else f"FULL YEAR BATCH: {PHOTO_LIBRARY}"
        )
        log("=" * 80)
        log("Metashape Coral Photomosaic Processor")
        log(f"Mode            : {mode_label}")
        log(f"Output directory: {OUTPUT_BASE}")
        log(f"JPEG preview dir: {complete_images_dir}")
        log(f"GPS / CRS       : {'None (local coords - underwater mode)' if not SET_CRS else SET_CRS}")
        log("=" * 80)

        # Collect folders
        try:
            survey_folders = collect_survey_folders(PHOTO_LIBRARY, TARGET_FOLDER)
        except FileNotFoundError as e:
            log(f"ERROR: {e}")
            return 1

        if not survey_folders:
            log("ERROR: No matching survey folders found.")
            return 1

        log(f"\nFound {len(survey_folders)} folder(s) to process.\n")

        results = {"successful": [], "failed": [], "skipped": []}

        for idx, survey_dir in enumerate(survey_folders, 1):
            survey_name = survey_dir.name

            log(f"\n[{idx}/{len(survey_folders)}] {'='*78}")
            log(f"Survey : {survey_name}")
            log(f"Folder : {survey_dir}")
            log("=" * 78)

            try:
                PROJECT_PSX = os.path.join(OUTPUT_BASE, f"{survey_name}.psx")
                ORTHO_TIF   = os.path.join(OUTPUT_BASE, f"{survey_name}_ortho.tif")
                JPEG_OUT    = os.path.join(complete_images_dir, f"{survey_name}.jpg")

                # Discover images
                image_list, subdir_names = get_images_from_folder(str(survey_dir))
                if not image_list:
                    log("  WARNING: No images found - skipping.")
                    results["skipped"].append(survey_name)
                    continue
                log(f"  Images: {len(image_list)} file(s) in subfolders: {', '.join(subdir_names)}")

                # Open or create project
                doc = Metashape.Document()
                if os.path.exists(PROJECT_PSX):
                    log(f"  Opening existing project: {PROJECT_PSX}")
                    doc.open(PROJECT_PSX)
                else:
                    log(f"  Creating new project: {PROJECT_PSX}")
                    doc.save(PROJECT_PSX)

                # Chunk
                chunk = doc.chunk if doc.chunk is not None else doc.addChunk()
                chunk.label = survey_name
                log(f"  Chunk: {chunk.label}")

                # CRS (skipped for underwater surveys)
                if SET_CRS:
                    try:
                        chunk.crs = Metashape.CoordinateSystem(SET_CRS)
                        log(f"  CRS assigned: {SET_CRS}")
                    except Exception as e:
                        log(f"  WARNING: CRS assignment failed ({e}) - continuing without CRS")

                # Add photos
                if not chunk.cameras:
                    log(f"  Adding {len(image_list)} photos...")
                    chunk.addPhotos(image_list)
                    log(f"  Photos added: {len(chunk.cameras)} cameras")
                else:
                    log(f"  Photos already loaded ({len(chunk.cameras)} cameras) - skipping addPhotos().")
                doc.save()

                # Alignment
                log(f"  [ALIGNMENT] Matching (downscale={ALIGNMENT_MATCH_DOWNSCALE})...")
                chunk.matchPhotos(
                    downscale=ALIGNMENT_MATCH_DOWNSCALE,
                    generic_preselection=ALIGNMENT_GENERIC_PRESELECTION,
                    reference_preselection=ALIGNMENT_REFERENCE_PRESELECTION,
                    mask_tiepoints=ALIGNMENT_MASK_TIEPOINTS,
                    filter_stationary_points=ALIGNMENT_FILTER_STATIONARY,
                    keypoint_limit=ALIGNMENT_KEYPOINT_LIMIT,
                    tiepoint_limit=ALIGNMENT_TIEPOINT_LIMIT
                )
                log("    [OK] Matching done")

                log("  [ALIGNMENT] Aligning cameras...")
                chunk.alignCameras()
                log(f"    [OK] Aligned ({len(chunk.cameras)} cameras)")

                log("  [ALIGNMENT] Optimizing cameras...")
                try:
                    chunk.optimizeCameras()
                    log("    [OK] Optimization done")
                except Exception as e:
                    log(f"    WARNING: optimizeCameras() skipped ({e})")

                doc.save()

                # Depth maps
                log(f"  [DEPTH MAPS] Building (downscale={DEPTH_DOWNSCALE})...")
                chunk.buildDepthMaps(downscale=DEPTH_DOWNSCALE, filter_mode=DEPTH_FILTER)
                log("    [OK] Depth maps done")

                # Mesh
                log("  [MESH] Building from depth maps...")
                chunk.buildModel(
                    source_data=Metashape.DepthMapsData,
                    surface_type=MESH_SURFACE_TYPE,
                    interpolation=ORTHO_INTERPOLATION
                )
                log("    [OK] Mesh done")
                doc.save()

                # Orthomosaic (local coordinate space - no GPS needed)
                log("  [ORTHOMOSAIC] Building (local coordinate space, no GPS required)...")
                chunk.buildOrthomosaic(
                    surface=Metashape.ModelData,
                    blending_mode=ORTHO_BLENDING,
                    refine_seamlines=ORTHO_REFINE_SEAMLINES,
                    fill_holes=ORTHO_FILL_HOLES
                )
                log("    [OK] Orthomosaic done")

                # Export GeoTIFF (no world file - no GPS)
                log(f"  [EXPORT] TIF -> {ORTHO_TIF}")
                chunk.exportOrthomosaic(
                    ORTHO_TIF,
                    image_format=Metashape.ImageFormatTIFF,
                    tiff_big=ORTHO_BIGTIFF,
                    write_kml=False,
                    world_file=False    # omitted: no GPS data to georeference with
                )
                log("    [OK] TIF saved")

                # Export JPEG preview
                log(f"  [EXPORT] JPEG -> {JPEG_OUT}")
                export_jpeg_preview(chunk, JPEG_OUT, JPEG_QUALITY, log)

                # Export 3D model as glTF (optional — for CesiumJS 3D photomosaic viewing)
                if EXPORT_GLTF and chunk.model:
                    GLTF_OUT = os.path.join(OUTPUT_BASE, f"{survey_name}.glb")
                    log(f"  [EXPORT] glTF -> {GLTF_OUT}")
                    try:
                        chunk.exportModel(
                            GLTF_OUT,
                            format=Metashape.ModelFormatGLTF,
                            save_texture=True,
                        )
                        log("    [OK] glTF saved")
                    except Exception as e:
                        log(f"    WARNING: glTF export failed ({e})")

                doc.save()

                log(f"  [PASS] Completed: {survey_name}")
                results["successful"].append(survey_name)

            except Exception as e:
                log(f"  [FAIL] {survey_name}: {e}")
                results["failed"].append((survey_name, str(e)))
                if not CONTINUE_ON_ERROR:
                    raise

        # Summary
        log("\n" + "=" * 80)
        log("SUMMARY")
        log("=" * 80)
        log(f"Successful : {len(results['successful'])} / {len(survey_folders)}")
        for name in results["successful"]:
            log(f"  [PASS] {name}")

        if results["skipped"]:
            log(f"\nSkipped    : {len(results['skipped'])}")
            for name in results["skipped"]:
                log(f"  [SKIP] {name}")

        if results["failed"]:
            log(f"\nFailed     : {len(results['failed'])}")
            for name, reason in results["failed"]:
                log(f"  [FAIL] {name} - {reason}")

        log(f"\nJPEG previews : {complete_images_dir}")
        log(f"Log file      : {log_file}")
        log("=" * 80)

    try:
        print("\n[DONE] Batch processing complete.")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    main()
# -*- coding: utf-8 -*-
"""
Batch Metashape 2.x photomosaic workflow for Ishigaki coral surveys.

This file is the USER CONFIG. The workflow itself lives in src/neoreef/metashape/.

TWO RUN MODES (set TARGET_FOLDER below):
  - Single folder : TARGET_FOLDER = r"S:\\...\\Ishi25_S001_0415_A1"
  - Full year     : TARGET_FOLDER = None  (scans entire PHOTO_LIBRARY)

No GPS / underwater workflow:
  - Orthomosaic is built in local (arbitrary) coordinates; no world file is written
  - JPEG previews go to: <YEAR_ROOT>/Complete Images/<YYYYMMDD_HHMMSS>/
  - With EXPORT_3D_MODEL, a tileset.json + survey_meta.json is written per survey;
    the Cesium pipeline places it on the globe from config/survey_positions.json

Run in Metashape:
  1) Tools -> Run Script... (select this file), or
  2) metashape.exe -r Batch_metashape.py
"""

import sys
from pathlib import Path

# Make the `neoreef` package importable from Metashape's bundled Python (3.9).
_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from neoreef.metashape.config import MetashapeConfig  # noqa: E402

# =============================================================================
# USER CONFIG
# =============================================================================

# --- Run mode ----------------------------------------------------------------
# Set TARGET_FOLDER to process a SINGLE survey folder, or None to run the
# entire year (all Ishi##_S###_MMDD_A# subfolders inside PHOTO_LIBRARY).
TARGET_FOLDER = r"S:\Armando\SURVEY_PHOTO_LIBRARY\Ishigaki_2025\Ishi25_S009_0926_A1"

# --- Paths -------------------------------------------------------------------
PHOTO_LIBRARY = r"S:\Armando\SURVEY_PHOTO_LIBRARY\Ishigaki_2025"   # holds the survey folders
YEAR_ROOT     = r"S:\Armando\SURVEY_PHOTO_LIBRARY\Ishigaki_2025"   # where "Complete Images" is created
OUTPUT_BASE   = r"D:\Armando\Processed_Projects"                   # .psx projects, GeoTIFFs, 3d_models/

# =============================================================================
# PROCESSING CONFIG  (rarely needs changing; see MetashapeConfig for defaults)
# =============================================================================

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
DEPTH_FILTER    = "MildFiltering"        # name of a Metashape filter constant

# --- Mesh & orthomosaic ------------------------------------------------------
MESH_SURFACE_TYPE      = "Arbitrary"
ORTHO_INTERPOLATION    = "EnabledInterpolation"
ORTHO_BLENDING         = "MosaicBlending"
ORTHO_REFINE_SEAMLINES = True
ORTHO_FILL_HOLES       = True
ORTHO_BIGTIFF          = True

# --- JPEG export -------------------------------------------------------------
JPEG_QUALITY = 90                         # 1-100

# --- 3D model export ---------------------------------------------------------
EXPORT_3D_MODEL = False                   # OBJ -> obj2gltf -> gltfpack -> tileset.json
OBJ2GLTF_CMD    = "obj2gltf"              # npm install -g obj2gltf
GLTFPACK_CMD    = "gltfpack"              # https://github.com/zeux/meshoptimizer
GLTFPACK_ARGS   = ["-cc", "-tc"]          # meshopt + KTX2 texture compression
MODELS_SUBDIR   = "3d_models"

# --- Coordinate system / error handling --------------------------------------
SET_CRS = None                            # None for underwater surveys (local coords)
CONTINUE_ON_ERROR = True


def build_config() -> MetashapeConfig:
    return MetashapeConfig(
        photo_library=PHOTO_LIBRARY, output_base=OUTPUT_BASE,
        target_folder=TARGET_FOLDER, year_root=YEAR_ROOT,
        generic_preselection=ALIGNMENT_GENERIC_PRESELECTION,
        reference_preselection=ALIGNMENT_REFERENCE_PRESELECTION,
        match_downscale=ALIGNMENT_MATCH_DOWNSCALE,
        keypoint_limit=ALIGNMENT_KEYPOINT_LIMIT, tiepoint_limit=ALIGNMENT_TIEPOINT_LIMIT,
        mask_tiepoints=ALIGNMENT_MASK_TIEPOINTS, filter_stationary=ALIGNMENT_FILTER_STATIONARY,
        depth_downscale=DEPTH_DOWNSCALE, depth_filter=DEPTH_FILTER,
        mesh_surface_type=MESH_SURFACE_TYPE, ortho_interpolation=ORTHO_INTERPOLATION,
        ortho_blending=ORTHO_BLENDING, ortho_refine_seamlines=ORTHO_REFINE_SEAMLINES,
        ortho_fill_holes=ORTHO_FILL_HOLES, ortho_bigtiff=ORTHO_BIGTIFF,
        jpeg_quality=JPEG_QUALITY,
        export_3d_model=EXPORT_3D_MODEL, obj2gltf_cmd=OBJ2GLTF_CMD,
        gltfpack_cmd=GLTFPACK_CMD, gltfpack_args=list(GLTFPACK_ARGS), models_subdir=MODELS_SUBDIR,
        set_crs=SET_CRS, continue_on_error=CONTINUE_ON_ERROR,
    )


def main() -> int:
    from neoreef.metashape.batch import run
    return run(build_config())


if __name__ == "__main__":
    sys.exit(main())

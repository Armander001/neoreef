"""Batch configuration for the Metashape photogrammetry run.

The root-level ``Batch_metashape.py`` keeps the familiar USER CONFIG block of
ALL_CAPS constants and builds one of these from it. Metashape enum values are
stored as *names* (``"MildFiltering"``) and resolved at call time with
:func:`enum`, so this module imports without the Metashape runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

PathLike = Union[str, Path]


@dataclass
class MetashapeConfig:
    # --- Run mode / paths ---------------------------------------------------
    photo_library: Path                     # root holding the Ishi##_S###_... folders
    output_base: Path                       # .psx projects, GeoTIFFs, 3d_models/
    target_folder: Optional[Path] = None    # process just this folder (None = full year)
    year_root: Optional[Path] = None        # where "Complete Images" goes; default photo_library

    # --- Photo alignment ----------------------------------------------------
    generic_preselection: bool = True
    reference_preselection: bool = False
    match_downscale: int = 1
    keypoint_limit: int = 60000
    tiepoint_limit: int = 8000
    mask_tiepoints: bool = True
    filter_stationary: bool = True

    # --- Depth maps ----------------------------------------------------------
    depth_downscale: int = 2
    depth_filter: str = "MildFiltering"

    # --- Mesh & orthomosaic ---------------------------------------------------
    mesh_surface_type: str = "Arbitrary"
    ortho_interpolation: str = "EnabledInterpolation"
    ortho_blending: str = "MosaicBlending"
    ortho_refine_seamlines: bool = True
    ortho_fill_holes: bool = True
    ortho_bigtiff: bool = True

    # --- Exports -------------------------------------------------------------
    jpeg_quality: int = 90
    export_3d_model: bool = False
    obj2gltf_cmd: str = "obj2gltf"
    gltfpack_cmd: str = "gltfpack"
    gltfpack_args: List[str] = field(default_factory=lambda: ["-cc", "-tc"])
    models_subdir: str = "3d_models"
    tool_timeout_s: int = 600

    # --- Coordinate system / errors -----------------------------------------
    set_crs: Optional[str] = None           # None for underwater (local coords)
    continue_on_error: bool = True

    def __post_init__(self):
        self.photo_library = Path(self.photo_library)
        self.output_base = Path(self.output_base)
        if self.target_folder:
            self.target_folder = Path(self.target_folder)
        self.year_root = Path(self.year_root) if self.year_root else self.photo_library

    @property
    def models_dir(self) -> Path:
        return self.output_base / self.models_subdir

    def mode_label(self) -> str:
        return (f"SINGLE FOLDER: {self.target_folder}" if self.target_folder
                else f"FULL YEAR BATCH: {self.photo_library}")

    def problems(self) -> List[str]:
        """Config mistakes worth reporting before touching Metashape."""
        out = []
        if not self.target_folder and not self.photo_library.is_dir():
            out.append(f"PHOTO_LIBRARY does not exist: {self.photo_library}")
        if self.target_folder and not self.target_folder.is_dir():
            out.append(f"TARGET_FOLDER does not exist: {self.target_folder}")
        if not 1 <= self.jpeg_quality <= 100:
            out.append(f"JPEG_QUALITY must be 1-100, got {self.jpeg_quality}")
        return out


def enum(metashape_module, name: str):
    """Resolve an enum/constant name such as ``"MildFiltering"`` on the Metashape module."""
    try:
        return getattr(metashape_module, name)
    except AttributeError:
        raise ValueError(f"Metashape has no constant named {name!r}") from None

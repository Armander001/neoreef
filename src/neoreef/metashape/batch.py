"""The batch loop: for each survey folder, run the Metashape recipe and export.

Run through ``metashape.exe -r Batch_metashape.py`` (root of the repo), which
builds a :class:`MetashapeConfig` from its USER CONFIG block and calls :func:`run`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from neoreef.common.fs import ensure_dir
from neoreef.common.logging import make_metashape_logger, restore_std_streams
from neoreef.common.naming import ortho_filename
from . import processing as ms
from .config import MetashapeConfig
from .discovery import collect_survey_folders, discover_images, skipped_survey_folders
from .export_model import export_3d_model
from .export_preview import export_jpeg_preview

Log = Callable[[str], None]
LOG_FILENAME = "batch_processing.log"
COMPLETE_IMAGES_DIRNAME = "Complete Images"


@dataclass
class BatchResults:
    successful: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    failed: List[Tuple[str, str]] = field(default_factory=list)


def process_survey(survey_dir: Path, cfg: MetashapeConfig, complete_images_dir: Path,
                   log: Log) -> Optional[Path]:
    """Full recipe for one survey. Returns the ortho path, or None when skipped (no images)."""
    survey_name = survey_dir.name
    psx = cfg.output_base / f"{survey_name}.psx"
    ortho_tif = cfg.output_base / ortho_filename(survey_name, "drone")
    jpeg_out = complete_images_dir / f"{survey_name}.jpg"

    images = discover_images(survey_dir)
    if not images.count:
        log("  WARNING: No images found - skipping.")
        return None
    log(f"  Images: {images.summary()}")

    doc = ms.open_or_create_project(psx, log)
    chunk = ms.get_chunk(doc, survey_name)
    log(f"  Chunk: {chunk.label}")
    ms.apply_crs(chunk, cfg, log)
    ms.add_photos(chunk, images.image_paths, log)
    doc.save()

    ms.align_photos(chunk, cfg, log)
    doc.save()
    ms.build_depth_maps(chunk, cfg, log)
    ms.build_mesh(chunk, cfg, log)
    doc.save()
    ms.build_orthomosaic(chunk, cfg, log)
    ms.export_orthomosaic_tiff(chunk, ortho_tif, cfg, log)

    log(f"  [EXPORT] JPEG -> {jpeg_out}")
    export_jpeg_preview(chunk, jpeg_out, cfg.jpeg_quality, log)

    if cfg.export_3d_model and getattr(chunk, "model", None):
        model_dir = cfg.models_dir / survey_name
        log(f"  [3D MODEL] Pipeline -> {model_dir}")
        tileset = export_3d_model(chunk, survey_name, model_dir, cfg, log)
        log(f"  [3D MODEL] Complete: {tileset}" if tileset
            else "  [3D MODEL] WARNING: pipeline did not produce a tileset")

    doc.save()
    return ortho_tif


def _console_printer() -> Optional[Callable[[str], None]]:
    try:
        import Metashape
        return Metashape.app.console.print
    except Exception:
        return None


def run(cfg: MetashapeConfig) -> int:
    """Execute the batch. Returns a process exit code (0 = all good)."""
    restore_std_streams()
    import Metashape
    Metashape.app.settings.project_absolute_paths = True

    ensure_dir(cfg.output_base)
    log_file = cfg.output_base / LOG_FILENAME
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    complete_images_dir = ensure_dir(cfg.year_root / COMPLETE_IMAGES_DIRNAME / run_ts)

    with open(log_file, "w", encoding="utf-8", errors="replace") as handle:
        log = make_metashape_logger(handle, console_print=_console_printer())
        log("=" * 80)
        log("Metashape Coral Photomosaic Processor")
        log(f"Mode            : {cfg.mode_label()}")
        log(f"Output directory: {cfg.output_base}")
        log(f"JPEG preview dir: {complete_images_dir}")
        log(f"3D model export : {'ON (OBJ -> glb -> compressed glb -> tileset.json)' if cfg.export_3d_model else 'OFF'}")
        log(f"GPS / CRS       : {cfg.set_crs or 'None (local coords - underwater mode)'}")
        log("=" * 80)

        for problem in cfg.problems():
            log(f"ERROR: {problem}")
        try:
            folders = collect_survey_folders(cfg.photo_library, cfg.target_folder)
        except FileNotFoundError as e:
            log(f"ERROR: {e}")
            return 1
        if not folders:
            log("ERROR: No matching survey folders found.")
            return 1
        if not cfg.target_folder:
            for p in skipped_survey_folders(cfg.photo_library):
                log(f"  (ignored, not a survey folder: {p.name})")
        log(f"\nFound {len(folders)} folder(s) to process.\n")

        results = BatchResults()
        for idx, survey_dir in enumerate(folders, 1):
            name = survey_dir.name
            log(f"\n[{idx}/{len(folders)}] {'=' * 78}")
            log(f"Survey : {name}")
            log(f"Folder : {survey_dir}")
            log("=" * 78)
            try:
                if process_survey(survey_dir, cfg, complete_images_dir, log) is None:
                    results.skipped.append(name)
                    continue
                log(f"  [PASS] Completed: {name}")
                results.successful.append(name)
            except Exception as e:
                log(f"  [FAIL] {name}: {e}")
                results.failed.append((name, str(e)))
                if not cfg.continue_on_error:
                    raise

        _log_summary(log, results, len(folders), cfg, complete_images_dir, log_file)

    try:
        print("\n[DONE] Batch processing complete.")
    except Exception:
        pass
    return 0 if not results.failed else 1


def _log_summary(log: Log, r: BatchResults, total: int, cfg: MetashapeConfig,
                 complete_images_dir: Path, log_file: Path) -> None:
    log("\n" + "=" * 80)
    log("SUMMARY")
    log("=" * 80)
    log(f"Successful : {len(r.successful)} / {total}")
    for n in r.successful:
        log(f"  [PASS] {n}")
    if r.skipped:
        log(f"\nSkipped    : {len(r.skipped)}")
        for n in r.skipped:
            log(f"  [SKIP] {n}")
    if r.failed:
        log(f"\nFailed     : {len(r.failed)}")
        for n, reason in r.failed:
            log(f"  [FAIL] {n} - {reason}")
    log(f"\nJPEG previews : {complete_images_dir}")
    if cfg.export_3d_model:
        log(f"3D models     : {cfg.models_dir}")
    log(f"Log file      : {log_file}")
    log("=" * 80)

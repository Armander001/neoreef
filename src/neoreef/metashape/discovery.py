"""Survey folder and image discovery for the Metashape batch.

Layout this module understands (unchanged from the historical batch script):

    PHOTO_LIBRARY/                      e.g. S:\\...\\SURVEY_PHOTO_LIBRARY\\Ishigaki_2025
    └── Ishi25_S008_0915_A1/            survey folder, matches SURVEY_PATTERN
        ├── A/  *.jpg ...               one single-letter subfolder per camera pass
        ├── B/  *.jpg ...
        └── notes.txt                   anything not in a letter folder is ignored

Ordering guarantees (the batch script relied on filesystem order before):
    * survey folders   sorted case-insensitively by name
    * letter subfolders sorted case-insensitively (A, B, ... Z)
    * image files      sorted case-insensitively by filename within each subfolder

Nothing here imports ``Metashape``; it is plain-Python testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Pattern, Sequence, Tuple, Union

from neoreef.common.naming import (
    SURVEY_PATTERN,
    is_image_file,
    survey_folder_sort_key,
)

PathLike = Union[str, Path]


# ---------------------------------------------------------------------------
# Survey folders
# ---------------------------------------------------------------------------

def collect_survey_folders(photo_library: PathLike,
                           target_folder: Optional[PathLike] = None,
                           pattern: Pattern[str] = SURVEY_PATTERN) -> List[Path]:
    """Return the survey folders to process, in batch order.

    * ``target_folder`` set: validate it exists and return it alone. Its name
      is *not* checked against the pattern (users test with ad-hoc names).
    * otherwise: every direct subdirectory of ``photo_library`` whose name
      matches ``pattern``, sorted case-insensitively.

    Raises ``FileNotFoundError`` if the chosen root does not exist.
    """
    if target_folder:
        p = Path(target_folder)
        if not p.is_dir():
            raise FileNotFoundError(f"TARGET_FOLDER does not exist: {target_folder}")
        return [p]

    root = Path(photo_library)
    if not root.is_dir():
        raise FileNotFoundError(f"PHOTO_LIBRARY does not exist: {photo_library}")

    folders = [p for p in root.iterdir() if p.is_dir() and pattern.match(p.name)]
    folders.sort(key=lambda p: survey_folder_sort_key(p.name))
    return folders


def skipped_survey_folders(photo_library: PathLike,
                           pattern: Pattern[str] = SURVEY_PATTERN) -> List[Path]:
    """Subdirectories of the library that do NOT match the pattern.

    Useful for logging what a full-year run silently ignored (the old script
    gave no hint when, say, a 2026 folder was skipped by a 24|25 regex).
    """
    root = Path(photo_library)
    if not root.is_dir():
        return []
    out = [p for p in root.iterdir() if p.is_dir() and not pattern.match(p.name)]
    out.sort(key=lambda p: survey_folder_sort_key(p.name))
    return out


# ---------------------------------------------------------------------------
# Images inside one survey folder
# ---------------------------------------------------------------------------

def is_camera_subdir(path: Path) -> bool:
    """A camera pass folder is a directory named with exactly one letter."""
    return path.is_dir() and len(path.name) == 1 and path.name.isalpha()


def list_camera_subdirs(survey_dir: PathLike) -> List[Path]:
    """Single-letter subfolders of a survey, sorted A..Z (case-insensitive)."""
    root = Path(survey_dir)
    subdirs = [p for p in root.iterdir() if is_camera_subdir(p)]
    subdirs.sort(key=lambda p: p.name.lower())
    return subdirs


def list_images_in(subdir: PathLike) -> List[Path]:
    """Image files directly inside *subdir*, sorted by filename (case-insensitive)."""
    files = [p for p in Path(subdir).iterdir() if p.is_file() and is_image_file(p.name)]
    files.sort(key=lambda p: p.name.lower())
    return files


@dataclass
class ImageSet:
    """Result of scanning one survey folder."""

    survey_dir: Path
    images: List[Path] = field(default_factory=list)      # ordered: subdir, then filename
    subdirs: List[str] = field(default_factory=list)      # letter names, ordered
    empty_subdirs: List[str] = field(default_factory=list)  # letter folders with no images

    @property
    def count(self) -> int:
        return len(self.images)

    @property
    def image_paths(self) -> List[str]:
        """String paths, which is what ``chunk.addPhotos`` wants."""
        return [str(p) for p in self.images]

    def summary(self) -> str:
        parts = [f"{self.count} image(s)"]
        if self.subdirs:
            parts.append("in subfolders: " + ", ".join(self.subdirs))
        if self.empty_subdirs:
            parts.append("(empty: " + ", ".join(self.empty_subdirs) + ")")
        return " ".join(parts)


def discover_images(survey_dir: PathLike) -> ImageSet:
    """Scan a survey folder's letter subfolders and return an ordered ImageSet."""
    root = Path(survey_dir)
    result = ImageSet(survey_dir=root)
    for sub in list_camera_subdirs(root):
        imgs = list_images_in(sub)
        if imgs:
            result.images.extend(imgs)
            result.subdirs.append(sub.name)
        else:
            result.empty_subdirs.append(sub.name)
    return result


def get_images_from_folder(folder_path: PathLike) -> Tuple[List[str], List[str]]:
    """Drop-in replacement for the old batch helper.

    Returns ``(image_paths, subdir_names)`` exactly as before, except that
    image paths are now deterministically sorted and empty letter folders
    are no longer listed in ``subdir_names``.
    """
    s = discover_images(folder_path)
    return s.image_paths, list(s.subdirs)

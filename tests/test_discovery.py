from pathlib import Path

import pytest

from neoreef.metashape import discovery as d


def _touch(p: Path, content: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """A miniature SURVEY_PHOTO_LIBRARY/Ishigaki_2025 with realistic contents."""
    lib = tmp_path / "Ishigaki_2025"
    s1 = lib / "Ishi25_S001_0415_A1"
    _touch(s1 / "A" / "P4150003.JPG")
    _touch(s1 / "A" / "P4150001.JPG")
    _touch(s1 / "A" / "P4150002.jpg")
    _touch(s1 / "A" / "Thumbs.db")           # ignored: not an image
    _touch(s1 / "B" / "P4150010.ORF")
    _touch(s1 / "b2" / "P4150099.JPG")       # ignored: not a single-letter folder
    _touch(s1 / "notes.txt")                 # ignored: file at survey root
    _touch(s1 / "P4150000.JPG")              # ignored: image at survey root, not in a pass folder
    (s1 / "C").mkdir()                       # empty pass folder

    s2 = lib / "Ishi25_S010_0916_A1"
    _touch(s2 / "a" / "x.png")               # lowercase letter folder still counts

    s3 = lib / "Ishi26_S001_0101_A1"         # next season: must NOT be skipped
    _touch(s3 / "A" / "y.tif")

    _touch(lib / "Complete Images" / "20250916_120000" / "Ishi25_S001_0415_A1.jpg")  # output dir, ignored
    _touch(lib / "Todoroki_Drone_1111_2024" / "A" / "z.jpg")                         # non-standard name, ignored
    _touch(lib / "Ishi25_S001_0415_A1.psx")                                          # file, ignored
    return lib


# --- survey folders -----------------------------------------------------------

def test_collect_survey_folders_full_year(library):
    folders = d.collect_survey_folders(library)
    assert [f.name for f in folders] == ["Ishi25_S001_0415_A1", "Ishi25_S010_0916_A1", "Ishi26_S001_0101_A1"]


def test_collect_survey_folders_matches_legacy_sort(library):
    names = [f.name for f in d.collect_survey_folders(library)]
    assert names == sorted(names)


def test_skipped_survey_folders_reports_ignored(library):
    skipped = [p.name for p in d.skipped_survey_folders(library)]
    assert skipped == ["Complete Images", "Todoroki_Drone_1111_2024"]


def test_collect_survey_folders_target_folder_bypasses_pattern(library):
    target = library / "Todoroki_Drone_1111_2024"
    assert d.collect_survey_folders(library, target) == [target]
    assert d.collect_survey_folders(library, str(target)) == [target]


def test_collect_survey_folders_missing_target(library):
    with pytest.raises(FileNotFoundError):
        d.collect_survey_folders(library, library / "nope")


def test_collect_survey_folders_missing_library(tmp_path):
    with pytest.raises(FileNotFoundError):
        d.collect_survey_folders(tmp_path / "nope")


def test_collect_survey_folders_custom_pattern(library):
    import re
    folders = d.collect_survey_folders(library, pattern=re.compile(r"^Todoroki_"))
    assert [f.name for f in folders] == ["Todoroki_Drone_1111_2024"]


# --- images -------------------------------------------------------------------

def test_discover_images_order_and_filtering(library):
    s = d.discover_images(library / "Ishi25_S001_0415_A1")
    rel = [p.relative_to(s.survey_dir).as_posix() for p in s.images]
    assert rel == [
        "A/P4150001.JPG",   # sorted by filename inside the pass folder
        "A/P4150002.jpg",
        "A/P4150003.JPG",
        "B/P4150010.ORF",   # pass folders in A..Z order
    ]
    assert s.subdirs == ["A", "B"]
    assert s.empty_subdirs == ["C"]
    assert s.count == 4
    assert "4 image(s)" in s.summary() and "A, B" in s.summary() and "empty: C" in s.summary()


def test_discover_images_lowercase_pass_folder(library):
    s = d.discover_images(library / "Ishi25_S010_0916_A1")
    assert s.subdirs == ["a"] and s.count == 1


def test_discover_images_no_pass_folders(tmp_path):
    survey = tmp_path / "Ishi25_S099_0101_A1"
    _touch(survey / "loose.jpg")
    s = d.discover_images(survey)
    assert s.count == 0 and s.subdirs == [] and s.empty_subdirs == []


def test_get_images_from_folder_legacy_shape(library):
    images, subdirs = d.get_images_from_folder(library / "Ishi25_S001_0415_A1")
    assert all(isinstance(p, str) for p in images)
    assert len(images) == 4
    assert subdirs == ["A", "B"]          # empty folder C no longer reported
    assert images == sorted(images, key=lambda p: (Path(p).parent.name.lower(), Path(p).name.lower()))


def test_image_paths_are_absolute_strings_for_metashape(library):
    s = d.discover_images(library / "Ishi25_S001_0415_A1")
    for p in s.image_paths:
        assert Path(p).is_absolute() and Path(p).is_file()

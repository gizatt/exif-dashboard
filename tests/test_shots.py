from pathlib import Path

from exif_dashboard.discovery import FoundFile
from exif_dashboard.shots import (
    ROW_KEYS, build_shots, is_derivative_name, parse_datetime, top_folder,
)

ROOT = Path("/r").resolve()


def ff(rel: str) -> FoundFile:
    return FoundFile(path=ROOT / rel, scan_root=ROOT)


def test_raw_jpg_pair_is_one_shot_with_raw_canonical():
    found = [ff("trip/DSC_1.JPG"), ff("trip/DSC_1.NEF")]
    meta = {
        str(ROOT / "trip/DSC_1.NEF"): {"Model": "NIKON Z 6", "FocalLength": 35.0},
        str(ROOT / "trip/DSC_1.JPG"): {"Model": "WRONG", "FocalLength": 1.0},
    }
    rows = build_shots(found, meta)
    assert len(rows) == 1
    assert rows[0]["camera_model"] == "NIKON Z 6"
    assert rows[0]["focal_length"] == 35.0
    assert rows[0]["extensions"] == ["JPG", "NEF"]


def test_two_raws_canonical_by_raw_ext_order():
    # nef precedes dng in RAW_EXTS
    found = [ff("t/DSC_1.dng"), ff("t/DSC_1.nef")]
    meta = {
        str(ROOT / "t/DSC_1.nef"): {"Model": "FROM_NEF"},
        str(ROOT / "t/DSC_1.dng"): {"Model": "FROM_DNG"},
    }
    assert build_shots(found, meta)[0]["camera_model"] == "FROM_NEF"


def test_cross_folder_same_basename_stays_separate():
    rows = build_shots([ff("a/DSC_1.jpg"), ff("b/DSC_1.jpg")], {})
    assert len(rows) == 2


def test_derivative_names():
    assert is_derivative_name("DSC_1-Edit")
    assert is_derivative_name("DSC_1-Edit-2")
    assert is_derivative_name("DSC_1 (2)")
    assert is_derivative_name("DSC_1-HDR")
    assert is_derivative_name("DSC_1-Pano")
    assert not is_derivative_name("DSC_1")
    assert not is_derivative_name("Editorial_shot")


def test_lens_tag_priority_is_fixed():
    meta = {str(ROOT / "a/x.jpg"): {"Lens": "third", "LensModel": "second", "LensID": "first"}}
    assert build_shots([ff("a/x.jpg")], meta)[0]["lens"] == "first"
    meta2 = {str(ROOT / "a/x.jpg"): {"Lens": "third", "LensModel": "second"}}
    assert build_shots([ff("a/x.jpg")], meta2)[0]["lens"] == "second"
    meta3 = {str(ROOT / "a/x.jpg"): {"Lens": "third"}}
    assert build_shots([ff("a/x.jpg")], meta3)[0]["lens"] == "third"


def test_missing_and_zero_values_become_null():
    meta = {str(ROOT / "a/x.jpg"): {"FocalLength": 0, "ISO": 0}}
    row = build_shots([ff("a/x.jpg")], meta)[0]
    assert row["focal_length"] is None
    assert row["iso"] is None
    assert row["lens"] is None
    assert row["datetime"] is None


def test_datetime_prefix_parsing():
    assert parse_datetime("2019:06:12 10:30:00") == "2019:06:12 10:30:00"
    assert parse_datetime("0000:00:00 00:00:00") is None
    assert parse_datetime("garbage") is None
    assert parse_datetime(None) is None


def test_top_folder_rules():
    # Nested folders do not replace the selected organizational root.
    assert top_folder(ROOT / "birds/x/y.jpg", ROOT) == ROOT.name
    assert top_folder(ROOT / "y.jpg", ROOT) == ROOT.name


def test_row_keys_exact():
    rows = build_shots([ff("a/x.jpg")], {})
    assert set(rows[0].keys()) == ROW_KEYS
    # regression guard: GPS/serial must never enter the schema
    assert not any("gps" in k.lower() or "serial" in k.lower() for k in ROW_KEYS)


def test_path_is_relative_to_scan_root():
    row = build_shots([ff("a/x.jpg")], {})[0]
    assert row["path"] == "a/x.jpg"
    assert row["scan_root"] == str(ROOT)

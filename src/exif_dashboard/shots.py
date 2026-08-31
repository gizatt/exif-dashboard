"""Dedup discovered files into shots and map exiftool tags to artifact rows.

Spec rules implemented here: group by (directory, basename), RAW metadata
canonical, derivative-by-suffix-only, verbatim lens strings with fixed tag
priority, YYYY:MM datetime prefix validation, top_folder derivation.
"""
from __future__ import annotations

import re
from pathlib import Path

from exif_dashboard.discovery import RAW_EXTS, FoundFile

DERIVATIVE_RE = re.compile(r"(-Edit(-\d+)?|-HDR|-Pano| \(\d+\))$")
# Fixed priority — never per-file opportunistic. LensID first: it is
# exiftool's decoded MakerNotes composite and stays identical between a
# camera original and a Lightroom export of the same shot, while
# Lightroom writes a generic LensModel that would split the bucket.
LENS_TAGS = ("LensID", "LensModel", "Lens")
DATETIME_TAGS = ("DateTimeOriginal", "CreateDate")
_DT_RE = re.compile(r"^(\d{4}):(\d{2})")

ROW_KEYS = frozenset({
    "path", "scan_root", "camera_make", "camera_model", "lens",
    "focal_length", "focal_length_35", "aperture", "shutter", "iso",
    "datetime", "extensions", "is_derivative", "top_folder",
})


def is_derivative_name(stem: str) -> bool:
    return DERIVATIVE_RE.search(stem) is not None


def parse_datetime(value) -> str | None:
    if not isinstance(value, str):
        return None
    m = _DT_RE.match(value)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if year < 1 or not 1 <= month <= 12:
        return None
    return value


def top_folder(path: Path, scan_root: Path) -> str:
    # Each scan root is the highest-level organizational folder selected by
    # the user.  Always use its name, even when the photo lives in nested
    # folders beneath it.
    path.relative_to(scan_root)  # validate the relationship for callers
    return scan_root.name


def _canonical(files: list[FoundFile]) -> FoundFile:
    def rank(f: FoundFile) -> tuple[int, str]:
        ext = f.path.suffix.lower().lstrip(".")
        return (RAW_EXTS.index(ext) if ext in RAW_EXTS else len(RAW_EXTS), ext)
    return min(files, key=rank)


def _first(tags: dict, names: tuple[str, ...]):
    for n in names:
        v = tags.get(n)
        if v not in (None, ""):
            return v
    return None


def _pos_num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None  # 0mm manual lenses -> Unknown (spec)


def build_shots(found: list[FoundFile], metadata: dict[str, dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[FoundFile]] = {}
    for f in found:
        groups.setdefault((str(f.path.parent), f.path.stem), []).append(f)

    rows: list[dict] = []
    for (_, stem), files in sorted(groups.items()):
        canon = _canonical(files)
        tags = metadata.get(str(canon.path), {})
        iso = _pos_num(tags.get("ISO"))
        rows.append({
            "path": str(canon.path.relative_to(canon.scan_root)),
            "scan_root": str(canon.scan_root),
            "camera_make": tags.get("Make") or None,
            "camera_model": tags.get("Model") or None,
            "lens": _first(tags, LENS_TAGS),
            "focal_length": _pos_num(tags.get("FocalLength")),
            "focal_length_35": _pos_num(tags.get("FocalLengthIn35mmFormat")),
            "aperture": _pos_num(tags.get("FNumber")),
            "shutter": tags.get("ExposureTime") if tags.get("ExposureTime") not in ("", None) else None,
            "iso": int(iso) if iso is not None else None,
            "datetime": parse_datetime(_first(tags, DATETIME_TAGS)),
            "extensions": sorted(f.path.suffix.lstrip(".").upper() for f in files),
            "is_derivative": is_derivative_name(stem),
            "top_folder": top_folder(canon.path, canon.scan_root),
        })
    return rows

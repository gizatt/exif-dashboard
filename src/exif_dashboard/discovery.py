"""Input validation and file discovery for the scan subcommand.

Core constraint 3 (spec): the scan is read-only and its output must
never land inside a scanned root.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from exif_dashboard.cli import ToolError


class DiscoveryError(ToolError):
    pass


def parse_dirs_file(dirs_file: Path) -> list[Path]:
    if not dirs_file.is_file():
        raise DiscoveryError(f"dirs file not found: {dirs_file}")
    roots: list[Path] = []
    for raw in dirs_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        p = Path(line)
        if not p.is_dir():
            raise DiscoveryError(f"not a directory: {line}")
        roots.append(p.resolve())
    if not roots:
        raise DiscoveryError(f"no directories listed in {dirs_file}")
    seen: set[Path] = set()
    for r in roots:
        if r in seen:
            raise DiscoveryError(f"duplicate root: {r}")
        seen.add(r)
    for a in roots:
        for b in roots:
            if a != b and a.is_relative_to(b):
                raise DiscoveryError(f"nested roots: {a} is inside {b}")
    return roots


def validate_output_path(output: Path, roots: list[Path], input_file: Path) -> None:
    out = output.resolve()
    if out == input_file.resolve():
        raise DiscoveryError("output path equals input path")
    for r in roots:
        if out.is_relative_to(r):
            raise DiscoveryError(f"output path {out} is inside scan root {r}")


RAW_EXTS = ("nef", "cr2", "cr3", "arw", "raf", "dng", "orf", "rw2")
IMG_EXTS = ("jpg", "jpeg", "heic", "heif", "tif", "tiff", "png")
IMAGE_EXTS = frozenset(RAW_EXTS + IMG_EXTS)


@dataclass
class FoundFile:
    path: Path       # absolute
    scan_root: Path  # resolved root that contained it


@dataclass
class DiscoveryResult:
    files: list[FoundFile] = field(default_factory=list)
    skipped: int = 0
    unsafe_names: list[str] = field(default_factory=list)


def _is_safe_name(path_str: str) -> bool:
    # Spec, argfile hardening: newlines could inject exiftool options;
    # non-UTF8 surrogates can't be written to the UTF-8 argfile/JSONL.
    if "\n" in path_str or "\r" in path_str:
        return False
    try:
        path_str.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def discover_files(roots: list[Path]) -> DiscoveryResult:
    result = DiscoveryResult()
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                full = Path(dirpath) / name
                if name.startswith(".") or full.suffix.lower().lstrip(".") not in IMAGE_EXTS:
                    result.skipped += 1
                    continue
                if full.is_symlink() or not full.is_file():
                    continue  # symlinks and other non-regular files: reads must not escape roots
                if not _is_safe_name(str(full)):
                    result.unsafe_names.append(repr(str(full)))
                    continue
                result.files.append(FoundFile(path=full, scan_root=root))
    return result

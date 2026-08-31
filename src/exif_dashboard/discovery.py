"""Input validation and file discovery for the scan subcommand.

Core constraint 3 (spec): the scan is read-only and its output must
never land inside a scanned root.
"""
from __future__ import annotations

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

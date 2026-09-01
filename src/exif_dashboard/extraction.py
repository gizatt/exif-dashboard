"""Batch exiftool invocation, read-only by construction.

Never add write-mode options here (`=` assignments, -overwrite_original,
-tagsFromFile, etc.); test_extraction.py pins the exact argv and argfile format.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from exif_dashboard.cli import ToolError

# The # suffix requests numeric values (e.g. FocalLength 35.0, not "35.0 mm").
EXIFTOOL_TAG_ARGS = [
    "-Make", "-Model", "-LensModel", "-LensID", "-Lens",
    "-FocalLength#", "-FocalLengthIn35mmFormat#", "-FNumber",
    "-ExposureTime", "-ISO", "-DateTimeOriginal", "-CreateDate",
]

CHUNK_SIZE = 250        # progress + stall-detection granularity, not memory
CHUNK_TIMEOUT_S = 300.0


class ExiftoolMissingError(ToolError):
    pass


class ExtractionStallError(ToolError):
    pass


def check_exiftool() -> None:
    if shutil.which("exiftool") is None:
        raise ExiftoolMissingError(
            "exiftool not found. Install it with: sudo apt install libimage-exiftool-perl"
        )


def build_argv(argfile: Path) -> list[str]:
    return ["exiftool", "-json", *EXIFTOOL_TAG_ARGS, "-@", str(argfile)]


def write_argfile(paths: list[Path], argfile: Path) -> None:
    lines = []
    for p in paths:
        s = str(p)
        # A relative or newline-bearing path in an argfile can become an exiftool option.
        if not p.is_absolute():
            raise ValueError(f"argfile paths must be absolute: {s}")
        if "\n" in s or "\r" in s:
            raise ValueError(f"unsafe path reached argfile: {s!r}")
        lines.append(s)
    argfile.write_text("\n".join(lines) + "\n", encoding="utf-8")


def extract_metadata(
    paths: list[Path],
    chunk_size: int = CHUNK_SIZE,
    timeout: float = CHUNK_TIMEOUT_S,
    progress=None,
) -> tuple[dict[str, dict], list[str]]:
    meta: dict[str, dict] = {}
    errors: list[str] = []
    for start in range(0, len(paths), chunk_size):
        chunk = paths[start : start + chunk_size]
        # Argfile lives in the system temp dir, never a scan root.
        fd = tempfile.NamedTemporaryFile("w", suffix=".args", delete=False)
        argfile = Path(fd.name)
        fd.close()
        try:
            write_argfile(chunk, argfile)
            try:
                proc = subprocess.run(
                    build_argv(argfile), capture_output=True, text=True, timeout=timeout
                )
            except subprocess.TimeoutExpired:
                raise ExtractionStallError(
                    f"exiftool made no progress for {timeout:.0f}s — is the mount "
                    "responsive? The previous artifact is untouched."
                ) from None
            rows = json.loads(proc.stdout) if proc.stdout.strip() else []
            got = {row["SourceFile"]: row for row in rows}
            for p in chunk:
                row = got.get(str(p))
                # exiftool reports unreadable files as a row with an "Error" tag.
                if row is None or "Error" in row:
                    errors.append(str(p))
                else:
                    meta[str(p)] = row
        finally:
            argfile.unlink(missing_ok=True)
        if progress is not None:
            progress(min(start + chunk_size, len(paths)), len(paths), len(errors))
    return meta, errors

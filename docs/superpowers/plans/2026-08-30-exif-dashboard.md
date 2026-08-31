# exif-dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-subcommand CLI (`scan` → JSONL artifact, `render` → self-contained HTML dashboard) that analyzes camera/lens/focal-length usage across a photo collection.

**Architecture:** `scan` validates a user-supplied directory list, walks it, batch-extracts EXIF via a pinned read-only exiftool invocation, dedups RAW+JPEG pairs into "shots", and atomically writes JSONL. `render` reads the JSONL and emits one HTML file with all data/CSS/JS inline; charts are hand-rolled SVG re-rendered client-side on filter changes.

**Tech Stack:** Python ≥3.13 (stdlib only), uv, exiftool (external binary), pytest (dev), vanilla JS/SVG.

**Spec:** `docs/superpowers/specs/2026-08-30-exif-dashboard-design.md` — read it before implementing any task; it is the authority on every rule referenced below.

## Global Constraints

- Python ≥3.13; package code uses **stdlib only** (pytest is a dev dependency; nothing else).
- `exiftool` is the only external binary; missing → clear install-hint error.
- **The scan is read-only.** No exiftool write-mode options ever (`=` assignments, `-overwrite_original`, `-delete_original`, `-restore_original`, `-tagsFromFile`). Argfiles: absolute paths only, system temp dir only.
- All file outputs are atomic: `<name>.tmp.<pid>` in the destination dir, rename on success, delete on failure.
- Output path refused inside a scan root; output path refused equal to input path (both subcommands).
- The dashboard HTML is fully self-contained: no CDN, no network, CSP deny-all-external.
- Tests never touch anything outside the repo and system tmp dirs. The fixture helper only writes into directories it created via `mkdtemp`.
- JSONL row keys are exactly: `path, scan_root, camera_make, camera_model, lens, focal_length, focal_length_35, aperture, shutter, iso, datetime, extensions, is_derivative, top_folder` (no GPS, no serials — enforced by test).
- Run tests with `uv run pytest` from the repo root.
- Commit after every task (messages given per task).

## File structure

```
src/exif_dashboard/__init__.py      # main() re-export (pyproject entry point)
src/exif_dashboard/cli.py           # argparse wiring, cmd_scan, cmd_render, summary
src/exif_dashboard/discovery.py     # dirs.txt parsing, validation, file walk
src/exif_dashboard/extraction.py    # pinned exiftool invocation, argfile, chunks, timeout
src/exif_dashboard/shots.py         # dedup groups → shot rows, tag mapping
src/exif_dashboard/artifact.py      # JSONL read/write, atomic_output
src/exif_dashboard/render.py        # HTML assembly, JSON embedding/escaping
src/exif_dashboard/static/template.html
src/exif_dashboard/static/dashboard.css
src/exif_dashboard/static/dashboard.js
tests/fixture_tree.py               # confined fixture builder (mkdtemp only)
tests/data/tiny.jpg                 # tiny real JPEG, generated once in Task 7
tests/test_cli.py  test_discovery.py  test_shots.py  test_artifact.py
tests/test_extraction.py  test_scan_integration.py  test_render.py
```

---

### Task 1: Project setup + CLI skeleton

**Files:**
- Modify: `pyproject.toml` (add pytest dev group)
- Modify: `src/exif_dashboard/__init__.py`
- Create: `src/exif_dashboard/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `exif_dashboard.cli.main(argv: list[str] | None = None) -> int` with subcommands `scan DIRS_FILE -o OUT` and `render ARTIFACT -o OUT`; `cmd_scan`/`cmd_render` exist as stubs raising `NotImplementedError`. Errors print `error: <msg>` to stderr and return 1. `__init__.py` exposes `main` (pyproject entry point is `exif_dashboard:main`).

- [ ] **Step 1: Add pytest**

```bash
uv add --dev pytest
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_cli.py
import pytest
from exif_dashboard.cli import main


def test_no_command_is_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_scan_requires_output(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["scan", "dirs.txt"])
    assert exc.value.code == 2


def test_help_lists_subcommands(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "scan" in out and "render" in out
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'exif_dashboard.cli'`

- [ ] **Step 4: Implement**

```python
# src/exif_dashboard/cli.py
"""Command-line entry point: scan and render subcommands."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="exif-dashboard",
        description="Analyze camera/lens/focal-length usage from photo EXIF data.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="scan photo directories into a JSONL artifact")
    p_scan.add_argument("dirs_file", type=Path, help="text file listing directories, one per line")
    p_scan.add_argument("-o", "--output", type=Path, required=True, help="JSONL artifact path")

    p_render = sub.add_parser("render", help="render a JSONL artifact into an HTML dashboard")
    p_render.add_argument("artifact", type=Path, help="JSONL artifact from scan")
    p_render.add_argument("-o", "--output", type=Path, required=True, help="HTML output path")

    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            return cmd_scan(args.dirs_file, args.output)
        return cmd_render(args.artifact, args.output)
    except ToolError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


class ToolError(Exception):
    """Base for all user-facing fatal errors."""


def cmd_scan(dirs_file: Path, output: Path) -> int:
    raise NotImplementedError


def cmd_render(artifact: Path, output: Path) -> int:
    raise NotImplementedError
```

```python
# src/exif_dashboard/__init__.py
from exif_dashboard.cli import main

__all__ = ["main"]
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_cli.py -v` — Expected: 3 passed.
Also run: `uv run exif-dashboard --help` — Expected: usage text listing scan and render.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/exif_dashboard tests/test_cli.py
git commit -m "feat: CLI skeleton with scan/render subcommands"
```

---

### Task 2: Input validation (dirs file + output path)

**Files:**
- Create: `src/exif_dashboard/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: `cli.ToolError`.
- Produces: `DiscoveryError(ToolError)`; `parse_dirs_file(dirs_file: Path) -> list[Path]` (resolved roots; raises on missing/empty/duplicate/nested); `validate_output_path(output: Path, roots: list[Path], input_file: Path) -> None` (raises if output inside a root or equals input). Task 3 adds discovery to this same module.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discovery.py
import pytest
from exif_dashboard.discovery import DiscoveryError, parse_dirs_file, validate_output_path


def make_dirs_file(tmp_path, lines):
    f = tmp_path / "dirs.txt"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


def test_parse_happy_path_with_comments_and_blanks(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    f = make_dirs_file(tmp_path, ["# comment", "", str(tmp_path / "a"), str(tmp_path / "b")])
    roots = parse_dirs_file(f)
    assert roots == [(tmp_path / "a").resolve(), (tmp_path / "b").resolve()]


def test_missing_directory_fails_fast(tmp_path):
    f = make_dirs_file(tmp_path, [str(tmp_path / "nope")])
    with pytest.raises(DiscoveryError, match="not a directory"):
        parse_dirs_file(f)


def test_empty_list_rejected(tmp_path):
    f = make_dirs_file(tmp_path, ["# only a comment"])
    with pytest.raises(DiscoveryError, match="no directories"):
        parse_dirs_file(f)


def test_duplicate_roots_rejected(tmp_path):
    (tmp_path / "a").mkdir()
    f = make_dirs_file(tmp_path, [str(tmp_path / "a"), str(tmp_path / "a") + "/"])
    with pytest.raises(DiscoveryError, match="duplicate"):
        parse_dirs_file(f)


def test_nested_roots_rejected(tmp_path):
    (tmp_path / "a" / "inner").mkdir(parents=True)
    f = make_dirs_file(tmp_path, [str(tmp_path / "a"), str(tmp_path / "a" / "inner")])
    with pytest.raises(DiscoveryError, match="nested"):
        parse_dirs_file(f)


def test_output_inside_root_rejected(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    with pytest.raises(DiscoveryError, match="inside scan root"):
        validate_output_path(root / "out.jsonl", [root.resolve()], tmp_path / "dirs.txt")


def test_output_equals_input_rejected(tmp_path):
    f = tmp_path / "dirs.txt"
    f.touch()
    with pytest.raises(DiscoveryError, match="equals input"):
        validate_output_path(f, [], f)


def test_valid_output_accepted(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    validate_output_path(tmp_path / "out.jsonl", [root.resolve()], tmp_path / "dirs.txt")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_discovery.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# src/exif_dashboard/discovery.py
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
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_discovery.py -v` — Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/exif_dashboard/discovery.py tests/test_discovery.py
git commit -m "feat: dirs-file parsing and output-path safety validation"
```

---

### Task 3: File discovery walk

**Files:**
- Modify: `src/exif_dashboard/discovery.py`
- Test: `tests/test_discovery.py` (append)

**Interfaces:**
- Consumes: Task 2's module.
- Produces: constants `RAW_EXTS: tuple[str, ...]`, `IMG_EXTS: tuple[str, ...]`; dataclasses `FoundFile(path: Path, scan_root: Path)` (both absolute/resolved) and `DiscoveryResult(files: list[FoundFile], skipped: int, unsafe_names: list[str])`; `discover_files(roots: list[Path]) -> DiscoveryResult`. Deterministic ordering (sorted walk).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_discovery.py`)

```python
import os
from exif_dashboard.discovery import FoundFile, discover_files


def make_tree(tmp_path):
    root = tmp_path / "photos"
    for rel in [
        "2019_trip/DSC_0001.NEF",
        "2019_trip/DSC_0001.JPG",
        "2019_trip/notes.txt",
        "2019_trip/clip.mov",
        "2019_trip/.hidden.jpg",
        "birds/IMG_1.cr3",
        "loose.jpg",
    ]:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    (root / ".hiddendir").mkdir()
    (root / ".hiddendir" / "x.jpg").touch()
    return root


def test_discovery_filters_and_orders(tmp_path):
    root = make_tree(tmp_path)
    result = discover_files([root.resolve()])
    names = [f.path.name for f in result.files]
    assert names == ["loose.jpg", "DSC_0001.JPG", "DSC_0001.NEF", "IMG_1.cr3"]
    assert all(f.scan_root == root.resolve() for f in result.files)
    assert all(f.path.is_absolute() for f in result.files)
    # notes.txt, clip.mov, .hidden.jpg skipped; .hiddendir not entered
    assert result.skipped == 3


def test_symlinked_file_and_dir_skipped(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "escape.jpg").touch()
    os.symlink(outside / "escape.jpg", root / "link.jpg")
    os.symlink(outside, root / "linkdir")
    result = discover_files([root.resolve()])
    assert result.files == []


def test_unsafe_names_skipped_and_reported(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    (root / "ok.jpg").touch()
    newline_name = root / "bad\nname.jpg"
    newline_name.touch()
    # non-UTF8 byte in the name (surrogate-escaped by the OS layer)
    os.close(os.open(os.path.join(bytes(root), b"bad\xff.jpg"), os.O_CREAT))
    result = discover_files([root.resolve()])
    assert [f.path.name for f in result.files] == ["ok.jpg"]
    assert len(result.unsafe_names) == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_discovery.py -v`
Expected: new tests FAIL — `discover_files` not defined; existing 8 still pass.

- [ ] **Step 3: Implement** (append to `src/exif_dashboard/discovery.py`)

```python
import os
from dataclasses import dataclass, field

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
                if not full.is_file(follow_symlinks=False):
                    continue  # symlinks and other non-regular files: reads must not escape roots
                if not _is_safe_name(str(full)):
                    result.unsafe_names.append(repr(str(full)))
                    continue
                result.files.append(FoundFile(path=full, scan_root=root))
    return result
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_discovery.py -v` — Expected: 11 passed. If `test_discovery_filters_and_orders` fails on `skipped` count, check whether the symlink/hidden ordering of the skip checks matches the test's expectation (hidden/extension check must come first so `.hidden.jpg` counts as skipped, not unsafe).

- [ ] **Step 5: Commit**

```bash
git add src/exif_dashboard/discovery.py tests/test_discovery.py
git commit -m "feat: recursive file discovery with extension/symlink/unsafe-name filtering"
```

---

### Task 4: Shots — dedup, derivative detection, field mapping

**Files:**
- Create: `src/exif_dashboard/shots.py`
- Test: `tests/test_shots.py`

**Interfaces:**
- Consumes: `discovery.FoundFile`, `discovery.RAW_EXTS`.
- Produces: `ROW_KEYS: frozenset[str]` (the exact artifact schema); `build_shots(found: list[FoundFile], metadata: dict[str, dict]) -> list[dict]` where `metadata` maps absolute path str → raw exiftool tag dict; helpers `is_derivative_name(stem: str) -> bool`, `parse_datetime(value) -> str | None`, `top_folder(path: Path, scan_root: Path) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_shots.py
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
    meta = {str(ROOT / "a/x.jpg"): {"Lens": "third", "LensID": "second", "LensModel": "first"}}
    assert build_shots([ff("a/x.jpg")], meta)[0]["lens"] == "first"
    meta2 = {str(ROOT / "a/x.jpg"): {"Lens": "third", "LensID": "second"}}
    assert build_shots([ff("a/x.jpg")], meta2)[0]["lens"] == "second"


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
    assert top_folder(ROOT / "birds/x/y.jpg", ROOT) == "birds"
    # file directly in the scan root: use the root's own name (spec, Derived fields)
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_shots.py -v` — Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

```python
# src/exif_dashboard/shots.py
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
LENS_TAGS = ("LensModel", "LensID", "Lens")  # fixed priority — never per-file opportunistic
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
    rel = path.relative_to(scan_root)
    return scan_root.name if len(rel.parts) == 1 else rel.parts[0]


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
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_shots.py -v` — Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/exif_dashboard/shots.py tests/test_shots.py
git commit -m "feat: shot dedup, derivative detection, and tag-to-row mapping"
```

---

### Task 5: Artifact I/O (atomic JSONL)

**Files:**
- Create: `src/exif_dashboard/artifact.py`
- Test: `tests/test_artifact.py`

**Interfaces:**
- Consumes: nothing project-internal.
- Produces: `atomic_output(output: Path)` contextmanager yielding a text file handle (temp `<name>.tmp.<pid>` in destination dir; rename on success, delete on failure); `write_artifact(rows: list[dict], meta: dict, output: Path) -> None` (first line `{"_meta": meta}`); `read_artifact(path: Path) -> tuple[dict, list[dict]]` (raises `ArtifactError` on missing `_meta`). `ArtifactError` subclasses `cli.ToolError`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_artifact.py
import json
import os

import pytest
from exif_dashboard.artifact import ArtifactError, atomic_output, read_artifact, write_artifact


def test_round_trip(tmp_path):
    rows = [{"path": "a/x.jpg", "lens": "Nikkor Z 50mm f/1.8 S"}]
    meta = {"scanned_at": "2026-08-30T12:00:00Z", "tool_version": "0.1.0"}
    out = tmp_path / "photos.jsonl"
    write_artifact(rows, meta, out)
    got_meta, got_rows = read_artifact(out)
    assert got_meta == meta
    assert got_rows == rows


def test_header_is_first_line(tmp_path):
    out = tmp_path / "p.jsonl"
    write_artifact([], {"tool_version": "x"}, out)
    first = json.loads(out.read_text().splitlines()[0])
    assert "_meta" in first


def test_failed_write_preserves_previous_and_cleans_temp(tmp_path):
    out = tmp_path / "p.jsonl"
    out.write_text("precious\n")
    with pytest.raises(RuntimeError):
        with atomic_output(out) as f:
            f.write("partial")
            raise RuntimeError("boom")
    assert out.read_text() == "precious\n"
    assert list(tmp_path.iterdir()) == [out]  # no stranded temp file


def test_temp_file_lives_in_destination_dir(tmp_path):
    out = tmp_path / "p.jsonl"
    with atomic_output(out) as f:
        siblings = [p.name for p in tmp_path.iterdir()]
        assert f"p.jsonl.tmp.{os.getpid()}" in siblings
        f.write("done\n")
    assert out.read_text() == "done\n"


def test_read_rejects_non_artifact(tmp_path):
    bad = tmp_path / "x.jsonl"
    bad.write_text('{"not_meta": 1}\n')
    with pytest.raises(ArtifactError, match="_meta"):
        read_artifact(bad)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_artifact.py -v` — Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

```python
# src/exif_dashboard/artifact.py
"""JSONL artifact read/write with atomic replacement (spec: Output)."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

from exif_dashboard.cli import ToolError


class ArtifactError(ToolError):
    pass


@contextmanager
def atomic_output(output: Path):
    """A failed run never truncates a previous output file.

    Temp file sits in the destination directory (same filesystem, so the
    rename is atomic) with a recognizable name, and is deleted on failure.
    """
    tmp = output.with_name(f"{output.name}.tmp.{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            yield f
        tmp.replace(output)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_artifact(rows: list[dict], meta: dict, output: Path) -> None:
    with atomic_output(output) as f:
        f.write(json.dumps({"_meta": meta}) + "\n")
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_artifact(path: Path) -> tuple[dict, list[dict]]:
    if not path.is_file():
        raise ArtifactError(f"artifact not found: {path}")
    with open(path, encoding="utf-8") as f:
        try:
            first = json.loads(f.readline())
        except json.JSONDecodeError as e:
            raise ArtifactError(f"{path} is not a JSONL artifact: {e}") from e
        if not isinstance(first, dict) or "_meta" not in first:
            raise ArtifactError(f"{path} has no _meta header — not a scan artifact")
        rows = [json.loads(line) for line in f if line.strip()]
    return first["_meta"], rows
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_artifact.py -v` — Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/exif_dashboard/artifact.py tests/test_artifact.py
git commit -m "feat: atomic JSONL artifact read/write"
```

---

### Task 6: exiftool extraction (pinned, chunked, timed out)

**Files:**
- Create: `src/exif_dashboard/extraction.py`
- Test: `tests/test_extraction.py`

**Interfaces:**
- Consumes: `cli.ToolError`.
- Produces: `EXIFTOOL_TAG_ARGS: list[str]` (pinned allowlist); `build_argv(argfile: Path) -> list[str]`; `write_argfile(paths: list[Path], argfile: Path) -> None`; `check_exiftool() -> None` (raises `ExiftoolMissingError`); `extract_metadata(paths: list[Path], chunk_size=1000, timeout=300.0, progress=None) -> tuple[dict[str, dict], list[str]]` returning ({abs path str → raw tag dict}, [failed paths]); `ExtractionStallError` on chunk timeout. All errors subclass `ToolError`. These tests mock subprocess — real exiftool runs in Task 7.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_extraction.py
import json
import subprocess
from pathlib import Path

import pytest
from exif_dashboard.extraction import (
    EXIFTOOL_TAG_ARGS, ExiftoolMissingError, ExtractionStallError,
    build_argv, check_exiftool, extract_metadata, write_argfile,
)

FORBIDDEN = {"-overwrite_original", "-delete_original", "-restore_original", "-tagsFromFile"}


def test_argv_is_pinned_and_read_only():
    argv = build_argv(Path("/tmp/x.args"))
    assert argv[0] == "exiftool"
    assert argv[1] == "-json"
    assert argv[-2:] == ["-@", "/tmp/x.args"]
    assert argv[2:-2] == EXIFTOOL_TAG_ARGS
    for arg in argv:
        assert arg not in FORBIDDEN
        assert "=" not in arg  # no tag assignments, ever


def test_allowlist_has_no_gps_or_serial():
    joined = " ".join(EXIFTOOL_TAG_ARGS).lower()
    assert "gps" not in joined and "serial" not in joined


def test_argfile_absolute_paths_only(tmp_path):
    argfile = tmp_path / "x.args"
    with pytest.raises(AssertionError):
        write_argfile([Path("relative.jpg")], argfile)


def test_argfile_rejects_newline_paths(tmp_path):
    argfile = tmp_path / "x.args"
    with pytest.raises(AssertionError):
        write_argfile([Path("/a/bad\nname.jpg")], argfile)


def test_argfile_contents(tmp_path):
    argfile = tmp_path / "x.args"
    write_argfile([Path("/a/one.jpg"), Path("/a/two.nef")], argfile)
    assert argfile.read_text(encoding="utf-8") == "/a/one.jpg\n/a/two.nef\n"


def test_check_exiftool_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(ExiftoolMissingError, match="libimage-exiftool-perl"):
        check_exiftool()


def test_extract_chunks_and_collects_errors(monkeypatch, tmp_path):
    calls = []

    def fake_run(argv, **kwargs):
        argfile = Path(argv[-1])
        paths = argfile.read_text().splitlines()
        calls.append(len(paths))
        rows = [{"SourceFile": p, "Model": "CamX"} for p in paths if "bad" not in p]
        return subprocess.CompletedProcess(argv, 1, stdout=json.dumps(rows), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    paths = [Path(f"/p/img{i}.jpg") for i in range(5)] + [Path("/p/bad.jpg")]
    meta, errors = extract_metadata(paths, chunk_size=4)
    assert calls == [4, 2]
    assert len(meta) == 5
    assert meta["/p/img0.jpg"]["Model"] == "CamX"
    assert errors == ["/p/bad.jpg"]


def test_timeout_raises_stall(monkeypatch):
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 0))

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ExtractionStallError, match="responsive"):
        extract_metadata([Path("/p/x.jpg")], timeout=1.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_extraction.py -v` — Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

```python
# src/exif_dashboard/extraction.py
"""Batch exiftool invocation. Read-only by construction (spec: argfile hardening).

Never add write-mode options here: no `=` assignments, -overwrite_original,
-delete_original, -restore_original, -tagsFromFile. test_extraction.py pins
the exact argv and argfile format.
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

CHUNK_SIZE = 1000       # progress + stall-detection granularity, not memory
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
        # Belt-and-braces: discovery already filtered these, but a relative
        # or newline-bearing path in an argfile can become an exiftool OPTION.
        assert p.is_absolute(), f"argfile paths must be absolute: {s}"
        assert "\n" not in s and "\r" not in s, f"unsafe path reached argfile: {s!r}"
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
        # System temp dir, never a scan root or CWD (spec).
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
                # exiftool reports unreadable files as a row with an "Error"
                # tag rather than omitting them; both are extraction errors.
                if row is None or "Error" in row:
                    errors.append(str(p))
                else:
                    meta[str(p)] = row
        finally:
            argfile.unlink(missing_ok=True)
        if progress is not None:
            progress(min(start + chunk_size, len(paths)), len(paths))
    return meta, errors
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_extraction.py -v` — Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/exif_dashboard/extraction.py tests/test_extraction.py
git commit -m "feat: pinned read-only exiftool batch extraction with stall detection"
```

---

### Task 7: Fixture tree + scan command wiring + integration test

Requires exiftool installed: `sudo apt install libimage-exiftool-perl` (ask the user to run this if sudo is needed; verify with `exiftool -ver`).

**Files:**
- Create: `tests/data/tiny.jpg` (generated once, checked in)
- Create: `tests/fixture_tree.py`
- Modify: `src/exif_dashboard/cli.py` (implement `cmd_scan`)
- Test: `tests/test_scan_integration.py`

**Interfaces:**
- Consumes: everything from Tasks 2–6.
- Produces: `tests.fixture_tree.make_fixture_tree() -> Path` — creates its own `mkdtemp` directory (asserts it is under `tempfile.gettempdir()`), populates the layout below, returns the root. Takes NO directory argument (spec: fixture confinement). `cmd_scan` fully working; prints summary lines `files seen/skipped/unsafe names/shots/pairs merged/derivatives/extraction errors`.

Fixture layout (touched empty files unless noted):

```
<mkdtemp>/photos/
  trip_2019/DSC_0001.jpg      <- real tiny JPEG, tags: Model="CamA", LensModel="LensZoom",
                                 FocalLength=35, DateTimeOriginal="2019:06:12 10:00:00"
  trip_2019/DSC_0001.nef      <- touched (pairs with above; nef canonical but has no tags,
                                 so metadata comes up empty -> tests Unknown handling)
  trip_2019/DSC_0002.jpg      <- real tiny JPEG, tags: Model="CamA", LensModel="Lens</script>50mm",
                                 FocalLength=50, DateTimeOriginal="2020:01:05 09:00:00"
  trip_2019/DSC_0002-Edit.jpg <- real tiny JPEG, same tags as DSC_0002 (derivative)
  birds/DSC_0001.jpg          <- real tiny JPEG, tags: Model="CamB", FocalLength=400 (no lens tag)
  birds/notes.txt             <- skipped
  birds/clip.mov              <- skipped
```

- [ ] **Step 1: Generate the tiny JPEG fixture**

```bash
mkdir -p tests/data
uv run --with pillow python -c "from PIL import Image; Image.new('RGB', (8, 8), (128, 128, 128)).save('tests/data/tiny.jpg')"
exiftool -FileType tests/data/tiny.jpg
```

Expected: `File Type : JPEG`. (Pillow is used once here at dev time to create a checked-in binary fixture; it is NOT a project dependency.)

- [ ] **Step 2: Write the fixture helper**

```python
# tests/fixture_tree.py
"""Confined fixture-tree builder.

This is the ONLY write-capable exiftool code in the project (spec: Testing).
It creates its own mkdtemp directory and never accepts an existing one.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

TINY_JPG = Path(__file__).parent / "data" / "tiny.jpg"


def _plant(dest: Path, **tags: str) -> None:
    assert str(dest).startswith(tempfile.gettempdir()), "fixture writes confined to tmp"
    shutil.copy(TINY_JPG, dest)
    args = [f"-{k}={v}" for k, v in tags.items()]
    subprocess.run(
        ["exiftool", "-overwrite_original", *args, str(dest)],
        check=True, capture_output=True,
    )


def make_fixture_tree() -> Path:
    base = Path(tempfile.mkdtemp(prefix="exif_dashboard_fixture_"))
    assert str(base).startswith(tempfile.gettempdir())
    root = base / "photos"
    (root / "trip_2019").mkdir(parents=True)
    (root / "birds").mkdir()

    _plant(root / "trip_2019" / "DSC_0001.jpg", Model="CamA", LensModel="LensZoom",
           FocalLength="35", DateTimeOriginal="2019:06:12 10:00:00")
    (root / "trip_2019" / "DSC_0001.nef").touch()  # pairs; canonical but tagless
    _plant(root / "trip_2019" / "DSC_0002.jpg", Model="CamA", LensModel="Lens</script>50mm",
           FocalLength="50", DateTimeOriginal="2020:01:05 09:00:00")
    _plant(root / "trip_2019" / "DSC_0002-Edit.jpg", Model="CamA", LensModel="Lens</script>50mm",
           FocalLength="50", DateTimeOriginal="2020:01:05 09:00:00")
    _plant(root / "birds" / "DSC_0001.jpg", Model="CamB", FocalLength="400")
    (root / "birds" / "notes.txt").write_text("not an image\n")
    (root / "birds" / "clip.mov").touch()
    return root
```

- [ ] **Step 3: Write the failing integration test**

```python
# tests/test_scan_integration.py
import shutil

import pytest
from exif_dashboard.artifact import read_artifact
from exif_dashboard.cli import main
from exif_dashboard.shots import ROW_KEYS
from fixture_tree import make_fixture_tree  # pytest prepends tests/ to sys.path

pytestmark = pytest.mark.skipif(shutil.which("exiftool") is None, reason="exiftool not installed")


@pytest.fixture(scope="module")
def scanned(tmp_path_factory):
    root = make_fixture_tree()
    work = tmp_path_factory.mktemp("scanout")
    dirs_file = work / "dirs.txt"
    dirs_file.write_text(f"# fixture roots\n{root}\n", encoding="utf-8")
    out = work / "photos.jsonl"
    assert main(["scan", str(dirs_file), "-o", str(out)]) == 0
    return read_artifact(out)


def test_shot_counts(scanned):
    meta, rows = scanned
    # 4 shots: DSC_0001 pair, DSC_0002, DSC_0002-Edit, birds/DSC_0001
    assert len(rows) == 4
    assert sum(r["is_derivative"] for r in rows) == 1


def test_pair_merged_with_raw_canonical_but_tagless(scanned):
    _, rows = scanned
    pair = next(r for r in rows if r["extensions"] == ["JPG", "NEF"])
    # nef is canonical; the touched nef has no readable tags -> Unknowns
    assert pair["camera_model"] is None
    assert pair["top_folder"] == "trip_2019"


def test_real_tags_extracted(scanned):
    _, rows = scanned
    bird = next(r for r in rows if r["top_folder"] == "birds")
    assert bird["camera_model"] == "CamB"
    assert bird["focal_length"] == 400.0
    assert bird["lens"] is None


def test_all_rows_have_exact_keys(scanned):
    _, rows = scanned
    for r in rows:
        assert set(r.keys()) == ROW_KEYS


def test_meta_header(scanned):
    meta, _ = scanned
    assert set(meta.keys()) == {"scanned_at", "tool_version"}
```

- [ ] **Step 4: Run to verify failure**

Run: `uv run pytest tests/test_scan_integration.py -v`
Expected: FAIL — `cmd_scan` raises `NotImplementedError`. (If it skips instead, exiftool is missing — install it before continuing; this task cannot be completed without it.)

- [ ] **Step 5: Implement cmd_scan** (replace the stub in `src/exif_dashboard/cli.py`; add imports at top of the function to avoid an import cycle)

```python
def cmd_scan(dirs_file: Path, output: Path) -> int:
    from datetime import datetime, timezone
    from importlib.metadata import version

    from exif_dashboard.artifact import write_artifact
    from exif_dashboard.discovery import discover_files, parse_dirs_file, validate_output_path
    from exif_dashboard.extraction import check_exiftool, extract_metadata
    from exif_dashboard.shots import build_shots

    check_exiftool()
    roots = parse_dirs_file(dirs_file)
    validate_output_path(output, roots, dirs_file)

    result = discover_files(roots)
    print(f"discovered {len(result.files)} image files "
          f"({result.skipped} skipped, {len(result.unsafe_names)} unsafe names)")

    def progress(done: int, total: int) -> None:
        print(f"  extracted {done}/{total}")

    meta_by_path, errors = extract_metadata([f.path for f in result.files], progress=progress)
    rows = build_shots(result.files, meta_by_path)

    header = {
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool_version": version("exif-dashboard"),
    }
    write_artifact(rows, header, output)

    pairs_merged = len(result.files) - len(rows)
    derivatives = sum(r["is_derivative"] for r in rows)
    print(f"wrote {output}")
    print(f"  files seen:         {len(result.files)}")
    print(f"  skipped (non-image):{result.skipped}")
    print(f"  unsafe names:       {len(result.unsafe_names)}")
    for name in result.unsafe_names:
        print(f"    skipped unsafe: {name}")
    print(f"  shots after dedup:  {len(rows)}")
    print(f"  pairs merged:       {pairs_merged}")
    print(f"  derivatives:        {derivatives}")
    print(f"  extraction errors:  {len(errors)}")
    for e in errors:
        print(f"    failed: {e}")
    return 0
```

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest tests/test_scan_integration.py -v` — Expected: 5 passed.
Note: the touched `.nef` will appear in `extraction errors` in the summary (exiftool can't read an empty file) — that is correct spec behavior (per-file failures are non-fatal), and the shot row still exists with null fields.

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest -v` — Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add tests/data/tiny.jpg tests/fixture_tree.py tests/test_scan_integration.py src/exif_dashboard/cli.py
git commit -m "feat: working scan command with confined fixture tree and integration test"
```

---

### Task 8: Render pipeline (HTML assembly, escaping, CSP, atomicity)

**Files:**
- Create: `src/exif_dashboard/render.py`
- Create: `src/exif_dashboard/static/template.html`
- Create: `src/exif_dashboard/static/dashboard.css` (empty placeholder file this task; filled in Task 9)
- Create: `src/exif_dashboard/static/dashboard.js` (empty placeholder file this task; filled in Task 9)
- Modify: `src/exif_dashboard/cli.py` (implement `cmd_render`)
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `artifact.read_artifact`, `artifact.atomic_output`, `cli.ToolError`.
- Produces: `RenderError(ToolError)`; `embed_json(data) -> str` (JSON with `</` → `<\/`); `render_dashboard(artifact: Path, output: Path) -> None`. The payload is embedded as `<script id="payload" type="application/json">…</script>`; Task 9's JS reads it via `JSON.parse(document.getElementById("payload").textContent)`. Payload shape: `{"meta": {...}, "shots": [row, ...]}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_render.py
import json
import re

import pytest
from exif_dashboard.artifact import write_artifact
from exif_dashboard.render import RenderError, embed_json, render_dashboard


def extract_payload(html: str) -> dict:
    m = re.search(
        r'<script id="payload" type="application/json">(.*?)</script>', html, re.S
    )
    assert m, "payload script block missing"
    return json.loads(m.group(1))


def sample_rows():
    return [{
        "path": "trip/DSC_1.jpg", "scan_root": "/r", "camera_make": "Nikon",
        "camera_model": "Z 6", "lens": "Evil</script><b>lens", "focal_length": 35.0,
        "focal_length_35": 52.0, "aperture": 1.8, "shutter": "1/250", "iso": 400,
        "datetime": "2019:06:12 10:00:00", "extensions": ["JPG"],
        "is_derivative": False, "top_folder": "trip",
    }]


def test_embed_json_escapes_close_tags():
    out = embed_json({"lens": "a</script>b"})
    assert "</script>" not in out
    assert json.loads(out.replace("<\\/", "</")) == {"lens": "a</script>b"}


def test_render_round_trip(tmp_path):
    art = tmp_path / "p.jsonl"
    write_artifact(sample_rows(), {"scanned_at": "t", "tool_version": "v"}, art)
    out = tmp_path / "dash.html"
    render_dashboard(art, out)
    html = out.read_text(encoding="utf-8")
    payload = extract_payload(html)
    assert payload["meta"]["tool_version"] == "v"
    assert payload["shots"][0]["lens"] == "Evil</script><b>lens"
    assert payload["shots"][0]["focal_length"] == 35.0


def test_html_is_self_contained_with_csp(tmp_path):
    art = tmp_path / "p.jsonl"
    write_artifact(sample_rows(), {"scanned_at": "t", "tool_version": "v"}, art)
    out = tmp_path / "dash.html"
    render_dashboard(art, out)
    html = out.read_text(encoding="utf-8")
    assert "Content-Security-Policy" in html
    assert "default-src 'none'" in html
    # The SVG XML namespace is a required identifier, not a network ref.
    stripped = html.replace("http-equiv", "").replace("http://www.w3.org/2000/svg", "")
    for pattern in ("http://", "https://", "src=", "href="):
        assert pattern not in stripped, f"external ref? {pattern}"


def test_render_refuses_output_equals_input(tmp_path):
    art = tmp_path / "p.jsonl"
    write_artifact([], {"scanned_at": "t", "tool_version": "v"}, art)
    with pytest.raises(RenderError, match="equals"):
        render_dashboard(art, art)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_render.py -v` — Expected: FAIL, module not found.

- [ ] **Step 3: Implement render.py and template; touch the placeholder assets**

```python
# src/exif_dashboard/render.py
"""Render the JSONL artifact into one self-contained HTML file."""
from __future__ import annotations

import json
from importlib.resources import files as resource_files
from pathlib import Path

from exif_dashboard.artifact import atomic_output, read_artifact
from exif_dashboard.cli import ToolError


class RenderError(ToolError):
    pass


def embed_json(data) -> str:
    # '</' -> '<\/' so EXIF strings containing '</script>' cannot close the
    # data block (spec: Render subcommand). Valid JSON either way.
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def render_dashboard(artifact: Path, output: Path) -> None:
    if artifact.resolve() == output.resolve():
        raise RenderError("output path equals input path — refusing to clobber the artifact")
    meta, rows = read_artifact(artifact)
    static = resource_files("exif_dashboard") / "static"
    html = (static / "template.html").read_text(encoding="utf-8")
    html = html.replace("/*__CSS__*/", (static / "dashboard.css").read_text(encoding="utf-8"))
    html = html.replace("/*__JS__*/", (static / "dashboard.js").read_text(encoding="utf-8"))
    html = html.replace("__PAYLOAD__", embed_json({"meta": meta, "shots": rows}))
    with atomic_output(output) as f:
        f.write(html)
```

```html
<!-- src/exif_dashboard/static/template.html -->
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EXIF Dashboard</title>
<style>/*__CSS__*/</style>
</head>
<body>
<header>
  <h1>EXIF Dashboard</h1>
  <p id="meta-line"></p>
</header>
<section id="stat-row"></section>
<section id="filters"></section>
<main id="charts"></main>
<footer id="footnote"></footer>
<div id="tooltip" hidden></div>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>/*__JS__*/</script>
</body>
</html>
```

```bash
touch src/exif_dashboard/static/dashboard.css src/exif_dashboard/static/dashboard.js
```

Implement `cmd_render` in `src/exif_dashboard/cli.py` (replace the stub):

```python
def cmd_render(artifact: Path, output: Path) -> int:
    from exif_dashboard.render import render_dashboard

    render_dashboard(artifact, output)
    print(f"wrote {output}")
    return 0
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_render.py -v` — Expected: 4 passed.
Note: `test_html_is_self_contained_with_csp` will FAIL later if anyone adds `src=`/`href=` to the template — that is the point. Keep the template attribute-free; all assets are inlined by replacement.

- [ ] **Step 5: Commit**

```bash
git add src/exif_dashboard/render.py src/exif_dashboard/static src/exif_dashboard/cli.py tests/test_render.py
git commit -m "feat: render pipeline with escaped payload embedding and CSP"
```

---

### Task 9: Dashboard front-end (filters + SVG charts) and end-to-end check

**Files:**
- Modify: `src/exif_dashboard/static/dashboard.css`
- Modify: `src/exif_dashboard/static/dashboard.js`
- Test: `tests/test_render.py` (append), manual browser verification via Playwright

**Interfaces:**
- Consumes: the payload contract from Task 8 (`{"meta", "shots"}`, row schema from Task 4).
- Produces: the finished dashboard. No new Python API.

**Design rules (from the dataviz method — follow, don't improvise):** single data series (slot-1 blue) over a light "all shots" track; bars ≤24px thick with 4px rounded data-ends (square at baseline) and 2px surface gaps; hairline gridlines; axis/label text in muted ink, never the series color; a two-entry legend ("selected" / "all shots") shown once above the charts; per-mark hover tooltip; light/dark via `prefers-color-scheme` with explicit body background. Colors below are from the skill's pre-validated reference palette used verbatim — no re-validation needed.

- [ ] **Step 1: Write the failing test** (append to `tests/test_render.py`)

```python
def test_dashboard_assets_are_nonempty_and_wired(tmp_path):
    art = tmp_path / "p.jsonl"
    write_artifact(sample_rows(), {"scanned_at": "t", "tool_version": "v"}, art)
    out = tmp_path / "dash.html"
    render_dashboard(art, out)
    html = out.read_text(encoding="utf-8")
    # JS actually shipped and reads the payload; CSS defines the theme tokens
    assert 'getElementById("payload")' in html
    assert "--series-1" in html
    assert "prefers-color-scheme: dark" in html
    # money-plot binning constants present
    assert "BIN_EDGES" in html
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_render.py::test_dashboard_assets_are_nonempty_and_wired -v`
Expected: FAIL — assets are empty.

- [ ] **Step 3: Write the CSS**

```css
/* src/exif_dashboard/static/dashboard.css */
:root {
  color-scheme: light;
  --page: #f9f9f7;
  --surface-1: #fcfcfb;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --muted: #898781;
  --grid: #e1e0d9;
  --baseline: #c3c2b7;
  --series-1: #2a78d6;
  --track: #cde2fb;
  --border: rgba(11, 11, 11, 0.10);
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --page: #0d0d0d;
    --surface-1: #1a1a19;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --muted: #898781;
    --grid: #2c2c2a;
    --baseline: #383835;
    --series-1: #3987e5;
    --track: #184f95;
  }
}
* { box-sizing: border-box; margin: 0; }
body {
  background: var(--page);
  color: var(--text-primary);
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
}
h1 { font-size: 20px; margin-bottom: 2px; }
#meta-line { color: var(--muted); margin-bottom: 16px; }
#stat-row { display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.stat-tile {
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 16px; min-width: 140px;
}
.stat-tile .label { color: var(--text-secondary); font-size: 12px; }
.stat-tile .value { font-size: 28px; font-weight: 600; }
#filters {
  display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end;
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;
}
#filters label { display: flex; flex-direction: column; gap: 4px;
  font-size: 12px; color: var(--text-secondary); }
#filters select {
  font: inherit; color: var(--text-primary); background: var(--surface-1);
  border: 1px solid var(--baseline); border-radius: 6px; padding: 4px 6px;
}
#filters select[multiple] { min-width: 160px; height: 92px; }
#filters button {
  font: inherit; padding: 6px 12px; border-radius: 6px;
  border: 1px solid var(--baseline); background: var(--surface-1);
  color: var(--text-primary); cursor: pointer;
}
.legend { display: flex; gap: 16px; align-items: center; margin: 0 0 8px;
  font-size: 12px; color: var(--text-secondary); }
.legend .swatch { display: inline-block; width: 10px; height: 10px;
  border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
.chart-card {
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px; margin-bottom: 16px; overflow-x: auto;
}
.chart-card h2 { font-size: 14px; margin-bottom: 8px; }
.chart-card h3 { font-size: 12px; font-weight: 600; margin: 4px 0 2px; }
.chart-card .sub { font-size: 11px; color: var(--muted); }
.facet-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
svg { display: block; }
svg text { font: 11px system-ui, -apple-system, "Segoe UI", sans-serif;
  fill: var(--muted); font-variant-numeric: tabular-nums; }
svg .lbl { fill: var(--text-secondary); }
#footnote { color: var(--muted); font-size: 12px; margin-top: 8px; }
#tooltip {
  position: fixed; pointer-events: none; z-index: 10;
  background: var(--surface-1); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: 6px;
  padding: 6px 10px; font-size: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
```

- [ ] **Step 4: Write the JS**

```javascript
// src/exif_dashboard/static/dashboard.js
"use strict";
const PAYLOAD = JSON.parse(document.getElementById("payload").textContent);
// Derivatives are always excluded from charts (spec); footnote shows the count.
const ALL = PAYLOAD.shots.filter(s => !s.is_derivative);
const N_DERIV = PAYLOAD.shots.length - ALL.length;

// Spec: fixed focal-length bin edges, closed underflow, open top.
const BIN_EDGES = [0, 10, 14, 18, 24, 35, 50, 70, 85, 105, 135, 200, 300, 400, Infinity];
const BIN_LABELS = ["<10", "10", "14", "18", "24", "35", "50", "70", "85", "105", "135", "200", "300", "400+"];

const UNKNOWN = "Unknown";
const val = (s, k) => (s[k] == null ? UNKNOWN : String(s[k]));
const year = s => (s.datetime ? +s.datetime.slice(0, 4) : null);
const fmt = n => n.toLocaleString("en-US");

// ---------- filters ----------
const uniq = key => [...new Set(ALL.map(s => val(s, key)))].sort();
const years = [...new Set(ALL.map(year).filter(y => y !== null))].sort((a, b) => a - b);
const state = { top_folder: new Set(), camera_model: new Set(), lens: new Set(),
                yearMin: null, yearMax: null };

function filtered() {
  return ALL.filter(s => {
    for (const key of ["top_folder", "camera_model", "lens"]) {
      if (state[key].size && !state[key].has(val(s, key))) return false;
    }
    const y = year(s);
    if (state.yearMin !== null && (y === null || y < state.yearMin)) return false;
    if (state.yearMax !== null && (y === null || y > state.yearMax)) return false;
    return true;
  });
}

function multiSelect(labelText, key) {
  const label = document.createElement("label");
  label.textContent = labelText;
  const sel = document.createElement("select");
  sel.multiple = true;
  for (const v of uniq(key)) {
    const o = document.createElement("option");
    o.value = o.textContent = v;
    sel.appendChild(o);
  }
  sel.addEventListener("change", () => {
    state[key] = new Set([...sel.selectedOptions].map(o => o.value));
    renderAll();
  });
  label.appendChild(sel);
  return label;
}

function yearSelect(labelText, stateKey, defaultLabel) {
  const label = document.createElement("label");
  label.textContent = labelText;
  const sel = document.createElement("select");
  sel.appendChild(new Option(defaultLabel, ""));
  for (const y of years) sel.appendChild(new Option(y, y));
  sel.addEventListener("change", () => {
    state[stateKey] = sel.value === "" ? null : +sel.value;
    renderAll();
  });
  label.appendChild(sel);
  return label;
}

function buildFilters() {
  const el = document.getElementById("filters");
  el.appendChild(multiSelect("Top folder", "top_folder"));
  el.appendChild(multiSelect("Camera", "camera_model"));
  el.appendChild(multiSelect("Lens", "lens"));
  el.appendChild(yearSelect("From year", "yearMin", "first"));
  el.appendChild(yearSelect("To year", "yearMax", "last"));
  const clear = document.createElement("button");
  clear.textContent = "Clear filters";
  clear.addEventListener("click", () => {
    for (const k of ["top_folder", "camera_model", "lens"]) state[k] = new Set();
    state.yearMin = state.yearMax = null;
    el.querySelectorAll("select").forEach(s => { s.selectedIndex = -1; if (!s.multiple) s.selectedIndex = 0; });
    renderAll();
  });
  el.appendChild(clear);
}

// ---------- svg helpers ----------
const SVG_NS = "http://www.w3.org/2000/svg";
function el(name, attrs) {
  const e = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}
// Bar with 4px rounded data-end, square at the baseline (dataviz mark spec).
function barPathH(x, y, w, h) {   // grows rightward
  const r = Math.min(4, w, h / 2);
  return `M${x},${y} h${w - r} a${r},${r} 0 0 1 ${r},${r} v${h - 2 * r} a${r},${r} 0 0 1 -${r},${r} h${-(w - r)} z`;
}
function barPathV(x, y, w, h, baseY) {  // grows upward from baseY
  const r = Math.min(4, h, w / 2);
  return `M${x},${baseY} v${-(h - r)} a${r},${r} 0 0 1 ${r},-${r} h${w - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${h - r} z`;
}
const tooltip = document.getElementById("tooltip");
function hover(target, text) {
  target.addEventListener("mousemove", ev => {
    tooltip.hidden = false;
    tooltip.textContent = text();
    tooltip.style.left = Math.min(ev.clientX + 12, window.innerWidth - 180) + "px";
    tooltip.style.top = (ev.clientY + 12) + "px";
  });
  target.addEventListener("mouseleave", () => { tooltip.hidden = true; });
}

// ---------- charts ----------
function countBy(rows, keyFn) {
  const m = new Map();
  for (const r of rows) {
    const k = keyFn(r);
    m.set(k, (m.get(k) || 0) + 1);
  }
  return m;
}

// Horizontal bar chart: filtered (series) bar over an "all shots" track.
function hBarChart(container, title, keyFn, rows) {
  const totals = countBy(ALL, keyFn);
  const counts = countBy(rows, keyFn);
  const cats = [...totals.keys()].sort((a, b) => (totals.get(b) - totals.get(a)) || a.localeCompare(b));
  const card = document.createElement("div");
  card.className = "chart-card";
  card.innerHTML = `<h2>${title}</h2>`;
  const labelW = 230, valueW = 60, barMaxW = 420, rowH = 24, barH = 16;
  const svg = el("svg", { width: labelW + barMaxW + valueW, height: cats.length * rowH + 4 });
  const max = Math.max(...totals.values(), 1);
  cats.forEach((c, i) => {
    const y = i * rowH + (rowH - barH) / 2;
    const name = el("text", { x: labelW - 8, y: y + barH - 4, "text-anchor": "end", class: "lbl" });
    name.textContent = c.length > 34 ? c.slice(0, 33) + "…" : c;
    svg.appendChild(name);
    const tw = Math.round((totals.get(c) / max) * barMaxW);
    const fw = Math.round(((counts.get(c) || 0) / max) * barMaxW);
    if (tw > 0) svg.appendChild(el("path", { d: barPathH(labelW, y, tw, barH), fill: "var(--track)" }));
    if (fw > 0) svg.appendChild(el("path", { d: barPathH(labelW, y, fw, barH), fill: "var(--series-1)" }));
    const v = el("text", { x: labelW + tw + 6, y: y + barH - 4 });
    v.textContent = fmt(counts.get(c) || 0);
    svg.appendChild(v);
    const hit = el("rect", { x: 0, y: i * rowH, width: labelW + barMaxW + valueW, height: rowH, fill: "transparent" });
    hover(hit, () => `${c}: ${fmt(counts.get(c) || 0)} selected of ${fmt(totals.get(c))}`);
    svg.appendChild(hit);
  });
  card.appendChild(svg);
  container.appendChild(card);
}

// Money plot: per-lens focal-length small multiples on the fixed bins.
function moneyPlot(container, rows) {
  const card = document.createElement("div");
  card.className = "chart-card";
  card.innerHTML = "<h2>Focal length by lens</h2>";
  const grid = document.createElement("div");
  grid.className = "facet-grid";
  const byLens = new Map();
  for (const s of rows) {
    const k = val(s, "lens");
    if (!byLens.has(k)) byLens.set(k, []);
    byLens.get(k).push(s);
  }
  const lenses = [...byLens.keys()].sort((a, b) => byLens.get(b).length - byLens.get(a).length);
  const W = 240, H = 110, padB = 18, padT = 6;
  for (const lens of lenses) {
    const shots = byLens.get(lens);
    const bins = new Array(BIN_LABELS.length).fill(0);
    let unknown = 0;
    for (const s of shots) {
      const f = s.focal_length;
      if (f == null) { unknown++; continue; }
      for (let i = 0; i < BIN_LABELS.length; i++) {
        if (f >= BIN_EDGES[i] && f < BIN_EDGES[i + 1]) { bins[i]++; break; }
      }
    }
    const facet = document.createElement("div");
    const h3 = document.createElement("h3");
    h3.textContent = lens;
    const sub = document.createElement("div");
    sub.className = "sub";
    sub.textContent = `${fmt(shots.length)} shots` + (unknown ? ` · ${fmt(unknown)} unknown fl` : "");
    facet.appendChild(h3);
    facet.appendChild(sub);
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
    const max = Math.max(...bins, 1);
    const slot = W / BIN_LABELS.length, barW = Math.min(24, slot - 2);  // 2px surface gap
    const baseY = H - padB;
    svg.appendChild(el("line", { x1: 0, y1: baseY, x2: W, y2: baseY, stroke: "var(--baseline)", "stroke-width": 1 }));
    bins.forEach((n, i) => {
      const x = i * slot + (slot - barW) / 2;
      if (n > 0) {
        const h = Math.max(2, Math.round((n / max) * (baseY - padT)));
        const p = el("path", { d: barPathV(x, baseY - h, barW, h, baseY), fill: "var(--series-1)" });
        hover(p, () => `${lens} @ ${BIN_LABELS[i]}mm: ${fmt(n)} shots`);
        svg.appendChild(p);
      }
      if (i % 2 === 0 || BIN_LABELS.length <= 8) {
        const t = el("text", { x: x + barW / 2, y: H - 5, "text-anchor": "middle" });
        t.textContent = BIN_LABELS[i];
        svg.appendChild(t);
      }
    });
    facet.appendChild(svg);
    grid.appendChild(facet);
  }
  card.appendChild(grid);
  container.appendChild(card);
}

// Shots over time: per-month columns.
function timeChart(container, rows) {
  const card = document.createElement("div");
  card.className = "chart-card";
  card.innerHTML = "<h2>Shots over time</h2>";
  const months = countBy(rows.filter(s => s.datetime), s => s.datetime.slice(0, 7));
  if (!months.size) {
    card.insertAdjacentHTML("beforeend", '<div class="sub">No dated shots in selection.</div>');
    container.appendChild(card);
    return;
  }
  const keys = [...months.keys()].sort();
  const [y0, m0] = keys[0].split(":").map(Number);
  const [y1, m1] = keys[keys.length - 1].split(":").map(Number);
  const seq = [];
  for (let y = y0, m = m0; y < y1 || (y === y1 && m <= m1); m === 12 ? (m = 1, y++) : m++) {
    seq.push(`${y}:${String(m).padStart(2, "0")}`);
  }
  const W = 1000, H = 140, padB = 18, padT = 6, baseY = H - padB;
  const svg = el("svg", { width: "100%", height: H, viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });
  const slot = W / seq.length, barW = Math.max(1, Math.min(24, slot - 2));
  const max = Math.max(...months.values());
  seq.forEach((k, i) => {
    const n = months.get(k) || 0;
    if (n === 0) return;
    const h = Math.max(1, Math.round((n / max) * (baseY - padT)));
    const x = i * slot + (slot - barW) / 2;
    const p = el("path", { d: barPathV(x, baseY - h, barW, h, baseY), fill: "var(--series-1)" });
    hover(p, () => `${k.replace(":", "-")}: ${fmt(n)} shots`);
    svg.appendChild(p);
  });
  svg.appendChild(el("line", { x1: 0, y1: baseY, x2: W, y2: baseY, stroke: "var(--baseline)", "stroke-width": 1 }));
  for (let y = y0; y <= y1; y++) {
    const i = seq.indexOf(`${y}:01`);
    if (i < 0) continue;
    const t = el("text", { x: i * slot, y: H - 5 });
    t.textContent = y;
    svg.appendChild(t);
  }
  card.appendChild(svg);
  container.appendChild(card);
}

// ---------- page assembly ----------
function renderAll() {
  const rows = filtered();
  const stat = document.getElementById("stat-row");
  stat.innerHTML =
    `<div class="stat-tile"><div class="label">Shots selected</div><div class="value">${fmt(rows.length)}</div></div>` +
    `<div class="stat-tile"><div class="label">All shots</div><div class="value">${fmt(ALL.length)}</div></div>` +
    `<div class="stat-tile"><div class="label">Lenses</div><div class="value">${fmt(new Set(rows.map(s => val(s, "lens"))).size)}</div></div>` +
    `<div class="stat-tile"><div class="label">Cameras</div><div class="value">${fmt(new Set(rows.map(s => val(s, "camera_model"))).size)}</div></div>`;
  const charts = document.getElementById("charts");
  charts.innerHTML = "";
  const legend = document.createElement("div");
  legend.className = "legend";
  legend.innerHTML =
    '<span><span class="swatch" style="background:var(--series-1)"></span>selected</span>' +
    '<span><span class="swatch" style="background:var(--track)"></span>all shots</span>';
  charts.appendChild(legend);
  moneyPlot(charts, rows);
  hBarChart(charts, "Shots per lens", s => val(s, "lens"), rows);
  hBarChart(charts, "Shots per camera", s => val(s, "camera_model"), rows);
  hBarChart(charts, "Shots per folder", s => val(s, "top_folder"), rows);
  timeChart(charts, rows);
}

document.getElementById("meta-line").textContent =
  `${fmt(ALL.length)} shots · scanned ${PAYLOAD.meta.scanned_at} · exif-dashboard ${PAYLOAD.meta.tool_version}`;
document.getElementById("footnote").textContent =
  N_DERIV ? `${fmt(N_DERIV)} derivative files (−Edit, −HDR, …) excluded from all charts.` : "";
buildFilters();
renderAll();
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_render.py -v` — Expected: all pass, including the new asset test.
Note: `test_html_is_self_contained_with_csp` strips only `http-equiv` before checking for `src=`/`href=` — the JS above deliberately avoids those substrings (no `img.src`, no links). If you add one, inline it differently.

- [ ] **Step 6: End-to-end + visual check**

```bash
uv run pytest -v
uv run python -c "
from tests.fixture_tree import make_fixture_tree
root = make_fixture_tree()
open('/tmp/claude-1000/-home-gizatt-projects-exif-dashboard/0489210d-7d33-4e39-9e27-cad67398e789/scratchpad/dirs.txt','w').write(str(root)+'\n')
"
uv run exif-dashboard scan /tmp/claude-1000/-home-gizatt-projects-exif-dashboard/0489210d-7d33-4e39-9e27-cad67398e789/scratchpad/dirs.txt -o /tmp/claude-1000/-home-gizatt-projects-exif-dashboard/0489210d-7d33-4e39-9e27-cad67398e789/scratchpad/photos.jsonl
uv run exif-dashboard render /tmp/claude-1000/-home-gizatt-projects-exif-dashboard/0489210d-7d33-4e39-9e27-cad67398e789/scratchpad/photos.jsonl -o /tmp/claude-1000/-home-gizatt-projects-exif-dashboard/0489210d-7d33-4e39-9e27-cad67398e789/scratchpad/dashboard.html
```

Then open `file:///…/scratchpad/dashboard.html` with the Playwright browser tools (`browser_navigate`, `browser_snapshot`, `browser_take_screenshot`) and verify: stat tiles show 4 selected / 4 all shots; the money plot shows facets including "Unknown" and the literal lens name containing `</script>` rendered as text (not markup); selecting the "birds" folder filter drops the selection to 1 and the track bars still show totals; tooltip appears on bar hover; no console errors (`browser_console_messages`). Check both a light and dark screenshot (emulate via `browser_evaluate` toggling `matchMedia` is unreliable — just confirm the dark tokens exist; the media query is exercised by the OS). Fix what looks broken — label collisions, overflow — before calling it done.

- [ ] **Step 7: Commit**

```bash
git add src/exif_dashboard/static tests/test_render.py
git commit -m "feat: interactive SVG dashboard with filters, money plot, and time chart"
```

---

## Final verification (after all tasks)

- [ ] `uv run pytest -v` — everything passes.
- [ ] `uv run exif-dashboard --help` works.
- [ ] Grep the codebase for forbidden exiftool options outside `tests/fixture_tree.py`: `grep -rn "overwrite_original\|delete_original\|tagsFromFile" src/` → no hits.
- [ ] Add `.gitignore` with a `data/` entry and create `data/` — the user keeps `dirs.txt`, artifacts, and generated dashboards there without committing them.
- [ ] Rewrite `README.md`, **preserving the user's existing read-only mount instructions** (the file already has a TODO skeleton mentioning `sudo mount -t drvfs Z: /mnt/z -o ro` — keep that step verbatim). Setup must be exactly two commands, binaries only via apt or uv:

```markdown
## Setup

    sudo apt install libimage-exiftool-perl   # the one binary dependency
    # everything else is handled by uv automatically on first run

## Usage

1. Mount the photo drive read-only (kernel-enforced safety):
   `sudo mount -t drvfs Z: /mnt/z -o ro`
2. List the directories to scan, one per line, in `data/dirs.txt`
   (`#` comments allowed; gitignored).
3. Scan (the only step that touches the drive; read-only, atomic output):
   `uv run exif-dashboard scan data/dirs.txt -o data/photos.jsonl`
4. Generate the dashboard (re-run freely; never touches the drive):
   `uv run exif-dashboard render data/photos.jsonl -o data/dashboard.html`
5. Open `data/dashboard.html` in a browser. It is fully self-contained.
```

  Also note: RAW+JPEG pairs count as one shot, `-Edit`/`-HDR`/`-Pano`/` (N)` files are excluded from charts (count shown in the footnote), and Lightroom star ratings are out of scope by design.
- [ ] Commit: `git commit -m "docs: setup/usage README and gitignored data dir"`.

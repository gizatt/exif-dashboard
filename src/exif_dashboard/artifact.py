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

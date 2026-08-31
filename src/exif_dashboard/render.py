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

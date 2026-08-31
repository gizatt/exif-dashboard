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

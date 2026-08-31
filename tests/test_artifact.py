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

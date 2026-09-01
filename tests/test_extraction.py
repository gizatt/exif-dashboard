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
    with pytest.raises(ValueError):
        write_argfile([Path("relative.jpg")], argfile)


def test_argfile_rejects_newline_paths(tmp_path):
    argfile = tmp_path / "x.args"
    with pytest.raises(ValueError):
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
    progress_calls = []
    meta, errors = extract_metadata(
        paths, chunk_size=4,
        progress=lambda done, total, errs: progress_calls.append((done, total, errs)),
    )
    assert calls == [4, 2]
    assert len(meta) == 5
    assert meta["/p/img0.jpg"]["Model"] == "CamX"
    assert errors == ["/p/bad.jpg"]
    # progress reports (done, total, errors-so-far) after each chunk
    assert progress_calls == [(4, 6, 0), (6, 6, 1)]


def test_timeout_raises_stall(monkeypatch):
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 0))

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ExtractionStallError, match="responsive"):
        extract_metadata([Path("/p/x.jpg")], timeout=1.0)

import shutil

import pytest
from exif_dashboard.artifact import read_artifact
from exif_dashboard.cli import main
from exif_dashboard.shots import ROW_KEYS
from fixture_tree import make_fixture_tree  # pytest prepends tests/ to sys.path
from test_render import extract_payload

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
    assert pair["top_folder"] == "photos"


def test_real_tags_extracted(scanned):
    _, rows = scanned
    bird = next(r for r in rows if r["path"] == "birds/DSC_0001.jpg")
    assert bird["top_folder"] == "photos"
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


def test_scan_then_render_roundtrip(tmp_path):
    # Parse the embedded JSON back out of the HTML and assert aggregate counts.
    root = make_fixture_tree()
    dirs_file = tmp_path / "dirs.txt"
    dirs_file.write_text(f"{root}\n", encoding="utf-8")
    artifact = tmp_path / "photos.jsonl"
    assert main(["scan", str(dirs_file), "-o", str(artifact)]) == 0

    html_out = tmp_path / "dash.html"
    assert main(["render", str(artifact), "-o", str(html_out)]) == 0

    html = html_out.read_text(encoding="utf-8")
    payload = extract_payload(html)
    shots = payload["shots"]

    assert len(shots) == 4
    assert sum(s["is_derivative"] for s in shots) == 1

    lenses = {s["lens"] for s in shots if s["lens"]}
    assert "Lens</script>50mm" in lenses

    assert all("scan_root" not in s for s in shots)

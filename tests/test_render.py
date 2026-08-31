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


def test_render_updates_legacy_nested_folder_group_without_rescan(tmp_path):
    rows = sample_rows()
    rows[0]["scan_root"] = "/mnt/z/2024 Acadia"
    rows[0]["path"] = "day-1/selects/DSC_1.jpg"
    rows[0]["top_folder"] = "day-1"
    art = tmp_path / "p.jsonl"
    write_artifact(rows, {"scanned_at": "t", "tool_version": "v"}, art)
    out = tmp_path / "dash.html"

    render_dashboard(art, out)

    shot = extract_payload(out.read_text(encoding="utf-8"))["shots"][0]
    assert shot["top_folder"] == "2024 Acadia"


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


def test_scan_root_not_embedded_in_html(tmp_path):
    rows = sample_rows()
    rows[0]["scan_root"] = "/secret/location/photos"
    art = tmp_path / "p.jsonl"
    write_artifact(rows, {"scanned_at": "t", "tool_version": "v"}, art)
    out = tmp_path / "dash.html"
    render_dashboard(art, out)
    html = out.read_text(encoding="utf-8")
    assert "/secret/location/photos" not in html
    payload = extract_payload(html)
    shot = payload["shots"][0]
    assert "scan_root" not in shot
    assert shot["path"] == "trip/DSC_1.jpg"
    assert shot["lens"] == "Evil</script><b>lens"
    assert shot["camera_make"] == "Nikon"


def test_render_to_missing_output_dir_raises_cleanly(tmp_path):
    art = tmp_path / "p.jsonl"
    write_artifact(sample_rows(), {"scanned_at": "t", "tool_version": "v"}, art)
    with pytest.raises(RenderError, match="output directory does not exist"):
        render_dashboard(art, tmp_path / "typo_dir" / "dash.html")


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
    assert "Aperture by lens" in html
    assert "Focal length × aperture by lens" in html
    assert "APERTURE_EDGES" in html
    assert "with both values" in html

import os

import pytest
from exif_dashboard.discovery import DiscoveryError, FoundFile, discover_files, parse_dirs_file, validate_output_path


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


def test_output_parent_dir_missing_rejected(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    with pytest.raises(DiscoveryError, match="output directory does not exist"):
        validate_output_path(
            tmp_path / "typo_dir" / "out.jsonl", [root.resolve()], tmp_path / "dirs.txt"
        )


def test_valid_output_accepted(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    validate_output_path(tmp_path / "out.jsonl", [root.resolve()], tmp_path / "dirs.txt")


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


def test_discovery_progress_callback(tmp_path):
    root = make_tree(tmp_path)
    calls = []
    discover_files(
        [root.resolve()],
        on_progress=lambda dirpath, found, skipped, unsafe: calls.append(
            (dirpath.name, found, skipped, unsafe)
        ),
    )
    # one call per visited directory (root, 2019_trip, birds; .hiddendir pruned)
    assert [c[0] for c in calls] == ["photos", "2019_trip", "birds"]
    # counts are cumulative and final call reflects the full result
    assert [c[1] for c in calls] == [1, 3, 4]
    assert calls[-1][2] == 3 and calls[-1][3] == 0

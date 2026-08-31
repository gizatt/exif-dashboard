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

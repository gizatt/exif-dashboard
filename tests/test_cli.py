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

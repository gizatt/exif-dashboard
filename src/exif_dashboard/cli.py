"""Command-line entry point: scan and render subcommands."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="exif-dashboard",
        description="Analyze camera/lens/focal-length usage from photo EXIF data.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="scan photo directories into a JSONL artifact")
    p_scan.add_argument("dirs_file", type=Path, help="text file listing directories, one per line")
    p_scan.add_argument("-o", "--output", type=Path, required=True, help="JSONL artifact path")

    p_render = sub.add_parser("render", help="render a JSONL artifact into an HTML dashboard")
    p_render.add_argument("artifact", type=Path, help="JSONL artifact from scan")
    p_render.add_argument("-o", "--output", type=Path, required=True, help="HTML output path")

    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            return cmd_scan(args.dirs_file, args.output)
        return cmd_render(args.artifact, args.output)
    except ToolError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


class ToolError(Exception):
    """Base for all user-facing fatal errors."""


def cmd_scan(dirs_file: Path, output: Path) -> int:
    from datetime import datetime, timezone
    from importlib.metadata import version

    from exif_dashboard.artifact import write_artifact
    from exif_dashboard.discovery import discover_files, parse_dirs_file, validate_output_path
    from exif_dashboard.extraction import check_exiftool, extract_metadata
    from exif_dashboard.shots import build_shots

    check_exiftool()
    roots = parse_dirs_file(dirs_file)
    validate_output_path(output, roots, dirs_file)

    result = discover_files(roots)
    print(f"discovered {len(result.files)} image files "
          f"({result.skipped} skipped, {len(result.unsafe_names)} unsafe names)")

    def progress(done: int, total: int) -> None:
        print(f"  extracted {done}/{total}")

    meta_by_path, errors = extract_metadata([f.path for f in result.files], progress=progress)
    rows = build_shots(result.files, meta_by_path)

    header = {
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool_version": version("exif-dashboard"),
    }
    write_artifact(rows, header, output)

    pairs_merged = len(result.files) - len(rows)
    derivatives = sum(r["is_derivative"] for r in rows)
    print(f"wrote {output}")
    print(f"  files seen:         {len(result.files)}")
    print(f"  skipped (non-image):{result.skipped}")
    print(f"  unsafe names:       {len(result.unsafe_names)}")
    for name in result.unsafe_names:
        print(f"    skipped unsafe: {name}")
    print(f"  shots after dedup:  {len(rows)}")
    print(f"  pairs merged:       {pairs_merged}")
    print(f"  derivatives:        {derivatives}")
    print(f"  extraction errors:  {len(errors)}")
    for e in errors:
        print(f"    failed: {e}")
    return 0


def cmd_render(artifact: Path, output: Path) -> int:
    raise NotImplementedError

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
    raise NotImplementedError


def cmd_render(artifact: Path, output: Path) -> int:
    raise NotImplementedError

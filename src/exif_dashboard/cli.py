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
    except (ToolError, OSError) as e:
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

    from tqdm import tqdm

    from exif_dashboard.shots import top_folder

    check_exiftool()
    roots = parse_dirs_file(dirs_file)
    validate_output_path(output, roots, dirs_file)

    with tqdm(desc="discovering", unit=" files", leave=True) as bar:
        def on_dir(dirpath: Path, found: int, skipped: int, unsafe: int) -> None:
            shown = str(dirpath)
            bar.set_description(f"discovering …{shown[-40:]}" if len(shown) > 40
                                else f"discovering {shown}")
            bar.update(found - bar.n)
            postfix = {"skipped": skipped}
            if unsafe:
                postfix["unsafe"] = unsafe
            bar.set_postfix(postfix)

        result = discover_files(roots, on_progress=on_dir)
        bar.set_description("discovering done")

    files = [f.path for f in result.files]
    with tqdm(total=len(files), desc="extracting EXIF", unit=" files", leave=True) as bar:
        def on_chunk(done: int, total: int, errs: int) -> None:
            bar.update(done - bar.n)
            if errs:
                bar.set_postfix(errors=errs)
            if done < total:
                nxt = result.files[done]
                bar.set_description(f"extracting {top_folder(nxt.path, nxt.scan_root)}")

        meta_by_path, errors = extract_metadata(files, progress=on_chunk)
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
    from exif_dashboard.render import render_dashboard

    render_dashboard(artifact, output)
    print(f"wrote {output}")
    return 0

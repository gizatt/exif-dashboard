# exif-dashboard — Design Spec

Date: 2026-08-30
Status: Draft for review

## Purpose

A personal tool to understand a decade of photography habits: which
cameras, lenses, and focal lengths get used, sliceable by
organizational folder. The money plot is a per-lens histogram of focal
length. Collection is ~20k shots on a network drive that only the user
touches.

## Core constraints

1. **The user runs the scan themselves.** The tool never receives a
   hard-coded path to the photo drive; it takes a user-supplied list
   of directories. Development and testing use synthetic fixtures
   only.
2. **Scan and render are strictly separated.** Scanning (touches the
   drive, slow, run rarely) and dashboard generation (local, instant,
   run freely) are independent subcommands communicating only through
   an artifact file.
3. **The scan is read-only.** It must never write, rename, or modify
   anything inside the scanned directories. All output goes to the
   user-specified output path.
4. **The dashboard is a single self-contained HTML file.** No server,
   no CDN, no network access; it opens from disk and works forever.

## Architecture

One Python package (`exif_dashboard`), Python ≥3.13, managed by uv.
Two subcommands:

```
exif-dashboard scan dirs.txt -o photos.jsonl     # touches the drive
exif-dashboard render photos.jsonl -o dashboard.html   # local only
```

The JSONL artifact is the sole interface between the halves.

### External dependency

`exiftool` (Perl, `apt install libimage-exiftool-perl`) is the one
external binary, chosen for its coverage of every RAW flavor. The
scan command checks for it at startup and exits with an install hint
if absent. The Python package itself uses stdlib only.

## Scan subcommand

### Input

A text file, one directory per line. Blank lines and `#` comments
ignored. Each listed directory must exist; missing ones are reported
and the scan aborts before any work (fail fast rather than silently
scanning a partial set).

### File discovery

Recursive walk of each listed directory. Files are included by
extension (case-insensitive):

- RAW: `nef cr2 cr3 arw raf dng orf rw2`
- Non-RAW image: `jpg jpeg heic heif tif tiff png`

Everything else (videos, `.xmp`, `.thm`, hidden files) is skipped.
Symlinks are not followed (loop and escape protection).

### Metadata extraction

exiftool runs in batch JSON mode, reading its file list from a
temporary argfile (`exiftool -json -@ argfile`) in chunks (~1000
files per invocation) to bound memory and give progress output.
Extraction failures on individual files are counted and listed in the
summary, never fatal.

Fields captured per file (exiftool tag → JSONL key):

| JSONL key         | Source tags (first present wins)          |
|-------------------|-------------------------------------------|
| `path`            | SourceFile                                 |
| `camera_make`     | Make                                       |
| `camera_model`    | Model                                      |
| `lens`            | LensModel, LensID, Lens                    |
| `focal_length`    | FocalLength (numeric mm)                   |
| `focal_length_35` | FocalLengthIn35mmFormat (numeric mm)       |
| `aperture`        | FNumber                                    |
| `shutter`         | ExposureTime                               |
| `iso`             | ISO                                        |
| `datetime`        | DateTimeOriginal, CreateDate               |
| `width`,`height`  | ImageWidth, ImageHeight                    |
| `file_type`       | FileType                                   |

Missing values are stored as `null` and rendered as "Unknown" buckets
downstream — rows are never dropped for missing metadata. Values like
0mm focal length (manual lenses) map to "Unknown" at render time.

### Dedup: files → shots

- Group key: `(containing directory, basename without extension)`.
  `DSC_1234.NEF` + `DSC_1234.JPG` in the same folder are one shot.
- When a group has both RAW and non-RAW, the RAW file's metadata is
  canonical. The shot records `extensions: ["NEF","JPG"]`.
- Basename collisions in *different* directories remain separate
  shots (camera counter resets are expected).
- Derivative detection: basenames matching `-Edit`, `-Edit-N`,
  ` (N)`, or `-HDR`/`-Pano` suffixes relative to a sibling original
  set `is_derivative: true`. They are kept in the artifact; the
  dashboard excludes them by default with a toggle.

### Derived fields

- `top_folder`: the first path component of the file relative to the
  scanned root directory it was found under (the user's
  organizational folder name). If the file sits directly in the
  scanned root — i.e. the user listed organizational folders
  themselves in dirs.txt — the basename of the scan root is used
  instead, so both listing styles yield sensible folder names.
- `scan_root`: the root from dirs.txt that contained the file.

### Output

JSONL: one JSON object per shot, UTF-8, written to the `-o` path.
First line is a header object: `{"_meta": {"scanned_at": ...,
"tool_version": ..., "roots": [...], "files_seen": N,
"shots": N, "errors": N}}`.

Writes go to a temporary file in the destination directory, renamed
into place on success — a failed scan never truncates a previous
artifact.

### Summary output

Printed at end of scan: files seen, files skipped by extension, shots
after dedup, RAW+JPEG pairs merged, derivatives flagged, extraction
errors (with paths).

## Render subcommand

Reads the JSONL, emits one self-contained HTML file. All data
embedded as a JSON blob; all CSS/JS inline; no external requests of
any kind. Target size: a few MB for 20k shots.

### Charts (hand-rolled SVG, vanilla JS)

Charts are rendered client-side from the embedded data so all slicing
is instant. No chart library initially; histograms and bar charts are
simple SVG. Fallback plan if hand-rolling proves painful: vendor one
small chart library (uPlot-class) inline — a build-time decision that
does not change this spec's interfaces.

1. **Money plot — per-lens focal length small multiples.** One
   histogram per lens, ordered by shot count, shared log-scaled x
   axis with bin edges at classic focal lengths
   (e.g. 10,14,18,24,35,50,70,85,105,135,200,300,400+). Uses actual
   `focal_length`; a global toggle switches to `focal_length_35` for
   cross-format comparison.
2. Shots per camera (bar).
3. Shots per lens (bar).
4. Shots over time (per-month histogram).
5. Shots per top folder (bar).

### Slicing controls

Client-side, combinable, applied to every chart:

- Top folder (multi-select)
- Camera (multi-select)
- Lens (multi-select)
- Year range
- Include-derivatives toggle (default off)

Each chart shows the filtered count against the unfiltered total.

## Testing

- Fixture tree generated by a test helper: small real image files
  with EXIF planted via exiftool, covering: RAW+JPEG pairs, JPEG-only
  and RAW-only shots, `-Edit` derivatives, cross-folder basename
  collisions, files with missing lens/focal tags, non-image files to
  skip.
- Unit tests: discovery/extension filtering, dedup grouping,
  derivative detection, top_folder derivation, JSONL round-trip.
- Integration test: scan fixture tree → render → assert the HTML
  contains the embedded dataset and expected aggregate counts.
- Render tests parse the embedded JSON back out of the HTML rather
  than screenshotting.
- The test suite never accesses anything outside the repo/tmp dirs.

## Non-goals (YAGNI)

- Lightroom catalog/rating integration (explicitly dropped).
- Incremental/resumable scans; content hashing; duplicate-image
  detection beyond the basename rule. Full rescan is minutes at 20k.
- Thumbnails or image display in the dashboard (metadata only — also
  keeps the artifact free of actual photo content).
- Any database. JSONL is the artifact.
- Watching/syncing; the tool runs on demand only.

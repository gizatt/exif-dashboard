# exif-dashboard — Design Spec

Date: 2026-08-30
Status: Draft for review (rev 2 — incorporates adversarial simplicity
and safety reviews)

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
   user-specified output path, which is refused if it resolves to a
   location inside any scanned root. (Mount-level atime updates from
   reading are unavoidable and not a violation.) Recommended
   operational practice, documented in the README: mount the network
   drive read-only in WSL (`sudo mount -t drvfs Z: /mnt/z -o ro`), so
   read-only is kernel-enforced defense in depth, not just
   code-enforced.
4. **The dashboard is a single self-contained HTML file.** No server,
   no CDN, no network access; it opens from disk and works forever.

## Architecture

One Python package (`exif_dashboard`), managed by uv. `requires-python`
stays permissive (≥3.10, no modern-only APIs); the dev interpreter is
pinned via uv's `.python-version` for stability, not as a stack
requirement.
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

A text file, one directory per line. Blank lines and `#`-prefixed
comment lines ignored (limitation, documented: a root whose name
starts with `#` cannot be listed). Validation happens fail-fast,
before any scanning:

- Every listed directory must exist.
- After `realpath` resolution: duplicate roots and nested roots
  (one root inside another) are rejected — they would double-count
  shots and make `top_folder` order-dependent.
- The resolved `-o` output path must not lie inside any resolved
  scan root (core constraint 3).
- Resolved output path must not equal the input file path.

### File discovery

Recursive walk of each listed directory. Symlinked directories are
not followed, and non-regular files (including symlinked files) are
skipped, so reads never escape the listed roots. Files are included
by extension (case-insensitive):

- RAW: `nef cr2 cr3 arw raf dng orf rw2`
- Non-RAW image: `jpg jpeg heic heif tif tiff png`

Everything else (videos, `.xmp`, `.thm`, hidden files) is skipped.

Paths containing `\n` or `\r`, and paths that cannot be encoded as
UTF-8 (surrogates from undecodable filesystem bytes), are skipped
and reported as unsafe-name errors rather than scanned — see
argfile hardening below. (Expected count on a real photo tree: zero.)

### Metadata extraction

exiftool runs in batch JSON mode with an **explicit tag allowlist**
(only the tags in the field table below are requested), reading its
file list from an argfile. The exact invocation is pinned:

```
exiftool -json -Make -Model -LensModel -LensID -Lens \
  -FocalLength# -FocalLengthIn35mmFormat# -FNumber -ExposureTime \
  -ISO -DateTimeOriginal -CreateDate -@ <argfile>
```

**Argfile hardening (safety-critical).** exiftool's argfile format
treats lines starting with `-` as options and `#` as comments, so a
hostile-or-unlucky filename could otherwise inject a *write*
operation. Invariants, each enforced in code and covered by a unit
test asserting the exact constructed argv and argfile contents:

- Argfile contains **absolute paths only** (kills leading-`-`/`#`
  interpretation).
- Paths containing newline/carriage-return characters were already
  rejected at discovery (kills line-splitting injection).
- The argfile lives in the **system temp directory**, never in a
  scan root or the CWD.
- No write-mode options ever appear in any exiftool argv: no `=`
  assignments, `-overwrite_original`, `-delete_original`,
  `-restore_original`, `-tagsFromFile`.

Files are processed in chunks of ~1000 per exiftool invocation — not
for memory (the tag allowlist keeps output small) but for **progress
reporting and stall detection**: each chunk gets a generous
wall-clock timeout (minutes); on timeout the child is killed and the
scan aborts with a "mount unresponsive" error. The previous artifact
survives (atomic write, below).

Per-file extraction failures are counted and listed in the summary,
never fatal.

Fields captured per shot:

| JSONL key         | Source tags (fixed priority, first present) |
|-------------------|---------------------------------------------|
| `path`            | SourceFile, stored **relative to scan_root** (privacy: no username/drive layout in the artifact) |
| `scan_root`       | the root from dirs.txt containing the file  |
| `camera_make`     | Make                                        |
| `camera_model`    | Model                                       |
| `lens`            | LensID, LensModel, Lens                     |
| `focal_length`    | FocalLength (numeric mm)                    |
| `focal_length_35` | FocalLengthIn35mmFormat (numeric mm)        |
| `aperture`        | FNumber                                     |
| `shutter`         | ExposureTime                                |
| `iso`             | ISO                                         |
| `datetime`        | DateTimeOriginal, CreateDate                |
| `extensions`      | from dedup (which files formed this shot)   |

Rationale for aperture/shutter/iso despite no v1 chart: capture is
free, and avoiding a future rescan of the precious drive is worth
three columns. Width/height/file_type were cut (no consumer).

A regression test asserts each JSONL row's keys are exactly this
set — a guard against capture-everything drift (and against GPS or
serial-number tags ever entering the artifact; they are deliberately
absent from the allowlist).

**Lens strings are used verbatim: one string = one bucket.** No
normalization, aliasing, or fuzzy matching. The tag priority order
(LensID → LensModel → Lens) is fixed and applied uniformly to every
file, so a given lens doesn't split buckets by which tags a body
wrote. LensID leads because it is exiftool's decoded MakerNotes
composite and stays identical between a camera original and a
Lightroom export of the same shot, where Lightroom's generic
LensModel string would split the bucket (verified on real files
2026-08-30). Near-duplicate buckets are the user's to eyeball.

**Datetime parsing:** only the fixed `YYYY:MM` prefix of
DateTimeOriginal/CreateDate is parsed (charts need year+month);
anything unparseable (e.g. `0000:00:00 ...`) becomes null →
"Unknown". No date libraries.

Missing values are stored as `null` and rendered as "Unknown"
buckets downstream — rows are never dropped for missing metadata.
0mm focal length (manual lenses) maps to "Unknown" at render time.

### Dedup: files → shots

- Group key: `(containing directory, basename without extension)`.
  `DSC_1234.NEF` + `DSC_1234.JPG` in the same folder are one shot.
- When a group has both RAW and non-RAW, the RAW file's metadata is
  canonical. Two RAW files in one group (e.g. NEF + DNG): canonical
  is the first by the RAW extension list order above.
- Basename collisions in *different* directories remain separate
  shots (camera counter resets are expected).
- **Derivative detection is by basename suffix pattern alone** —
  `-Edit`, `-Edit-N`, ` (N)`, `-HDR`, `-Pano` — no sibling-original
  lookup. A file so named is a derivative whether or not its
  original still exists. Sets `is_derivative: true`; kept in the
  artifact, **always excluded from charts** (the dashboard shows the
  excluded count in a footnote — no toggle; derivatives share the
  original's EXIF, so including them only double-counts).

### Derived fields

- `top_folder`: the basename of the scan root (the user's highest-level
  non-drive organizational folder). Nested directories beneath that root do
  not create separate groups. Render recomputes this field from `scan_root`
  and the relative `path`, so existing scan artifacts adopt this rule without
  re-reading image metadata.

### Output

JSONL, UTF-8, one JSON object per shot, written to the `-o` path.
First line is a small header object:
`{"_meta": {"scanned_at": ..., "tool_version": ...}}` (displayed in
the dashboard header). Scan counts live in the printed summary only,
not the header, so the file is written strictly front-to-back.

Atomic write: output goes to a recognizably-named temp file
(`<name>.tmp.<pid>`) in the destination directory, renamed into
place on success and deleted on failure — a failed scan never
truncates a previous artifact. (No fsync-before-rename: accepted
risk for a regenerable artifact on a personal tool.)

### Summary output

Printed at end of scan: files seen, files skipped by extension,
unsafe-name skips, shots after dedup, RAW+JPEG pairs merged,
derivatives flagged, extraction errors (with paths).

## Render subcommand

Reads the JSONL, emits one self-contained HTML file. All data
embedded as a JSON blob; all CSS/JS inline; no external requests of
any kind. Target size: a few MB for 20k shots.

Safety mirrors the scan side:

- Refuses to run when resolved output path equals resolved input
  path (protects the artifact from a tab-completion slip like
  `render photos.jsonl -o photos.jsonl`).
- Same temp-file + rename atomic write for the HTML.
- The embedded JSON blob escapes `</` (as `<\/`) so EXIF strings
  containing `</script>` cannot break out of the data block; a
  `<meta http-equiv="Content-Security-Policy">` deny-all-external
  tag enforces (not just intends) "no network access". A fixture
  with `</script>` planted in LensModel covers this in tests.
- Residual privacy surface, accepted: the dashboard embeds relative
  paths, folder names, and timestamps. No GPS, serials, absolute
  paths, or image content.

### Charts (hand-rolled SVG, vanilla JS)

Charts render client-side from the embedded data so slicing is
instant. No chart library initially; histograms and bar charts are
simple SVG. Fallback if hand-rolling proves painful: vendor one
small chart library (uPlot-class) inline — a build-time decision
that doesn't change this spec's interfaces.

1. **Money plot — per-lens focal length small multiples.** One
   histogram per lens, ordered by shot count, shared log-scaled x
   axis. Fixed bin edges (mm): `<10, 10, 14, 18, 24, 35, 50, 70,
   85, 105, 135, 200, 300, 400+` — closed underflow bucket below
   10, open-ended top bucket. Uses actual `focal_length`.
   (`focal_length_35` is captured in the artifact but has no v1 UI;
   a cross-format toggle can be added later if the rendered data
   shows it's wanted.)
2. Shots per camera (bar).
3. Shots per lens (bar).
4. Shots over time (per-month histogram).
5. Shots per top folder (bar).

### Slicing controls

Client-side, combinable, applied to every chart:

- Top folder (multi-select)
- Camera (multi-select)
- Lens (multi-select — shares the multi-select widget with the
  other two, so ~free)
- Year range (two plain `<select>` dropdowns: min year, max year)

Each chart shows the filtered count against the unfiltered total.
Derivative shots are always excluded (footnote shows how many).

## Testing

- **Path-logic tests use empty `touch`ed files** — discovery,
  extension filtering, dedup grouping, derivative detection,
  top_folder derivation need no EXIF. The RAW-metadata-is-canonical
  rule is unit-tested on merged dicts.
- **Extraction tests use tiny real JPEG/TIFF fixtures** with tags
  planted via exiftool. No real RAW files are checked in or
  fabricated (exiftool can't create RAWs from scratch).
- **The fixture helper is the only write-capable exiftool code in
  the project and is confined:** it creates its own fresh directory
  via `mkdtemp` and returns the path; it never accepts an existing
  directory to populate; it asserts its target is under the system
  tmp root; it is importable from tests only, never installed as a
  console script.
- Fixture tree covers: RAW+JPEG pairs (touched files), JPEG-only
  and RAW-only shots, `-Edit` derivatives, cross-folder basename
  collisions, missing lens/focal tags, non-image files to skip, a
  filename with a non-UTF8 byte, and `</script>` in LensModel.
- Unit tests additionally assert: exact exiftool argv + argfile
  contents (no write flags, absolute paths), JSONL row key set,
  JSONL round-trip.
- Integration test: scan fixture tree → render → parse the embedded
  JSON back out of the HTML and assert expected aggregate counts
  (no screenshotting).
- The test suite never accesses anything outside the repo and
  system tmp dirs.

## Non-goals (YAGNI)

- Lightroom catalog/rating integration (explicitly dropped).
- Incremental/resumable scans; content hashing; duplicate-image
  detection beyond the basename rule. Full rescan is minutes at 20k.
- Thumbnails or image display in the dashboard (metadata only — also
  keeps the artifact free of actual photo content).
- Any database. JSONL is the artifact.
- Lens-name normalization/aliasing.
- Derivative include-toggle, `focal_length_35` UI, custom slider
  widgets.
- Watching/syncing; the tool runs on demand only.

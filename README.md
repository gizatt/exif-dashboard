# EXIF Dashboard

Analyze camera/lens/focal-length usage across a photo collection. The `scan` command extracts EXIF from your photos into a JSON artifact; `render` produces a fully self-contained HTML dashboard with interactive filters and charts.

## Setup

```bash
sudo apt install libimage-exiftool-perl   # the one binary dependency
# everything else is handled by uv automatically on first run
```

## Usage

1. Mount the photo drive read-only (kernel-enforced safety):
   ```bash
   sudo mount -t drvfs Z: /mnt/z -o ro
   ```

2. List the directories to scan, one per line, in `data/dirs.txt` (`#` comments allowed; gitignored).

3. Scan (the only step that touches the drive; read-only, atomic output):
   ```bash
   uv run exif-dashboard scan data/dirs.txt -o data/photos.jsonl
   ```

4. Generate the dashboard (re-run freely; never touches the drive):
   ```bash
   uv run exif-dashboard render data/photos.jsonl -o data/dashboard.html
   ```

5. Open `data/dashboard.html` in a browser. It is fully self-contained.

## Notes

- **RAW+JPEG pairs:** Counted as one shot; metadata comes from the RAW file if available.
- **Derivatives:** Files matching `-Edit`, `-HDR`, `-Pano`, or ` (N)` patterns are excluded from all charts; the count is shown in the footer.
- **Lightroom ratings:** Out of scope by design.

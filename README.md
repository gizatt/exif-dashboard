# EXIF Dashboard

Analyze camera/lens/focal-length usage across a photo collection: `scan` extracts EXIF into JSONL, `render` turns that into a self-contained interactive HTML dashboard.

**[Live example](https://gizatt.github.io/exif-dashboard/example-dashboard.html)** — my own ~20k-shot catalog.

## Use

```bash
sudo apt install libimage-exiftool-perl      # the only binary dependency; uv handles the rest
echo /path/to/photos >> data/dirs.txt        # directories to scan, one per line
uv run exif-dashboard scan data/dirs.txt -o data/photos.jsonl
uv run exif-dashboard render data/photos.jsonl -o data/dashboard.html
```

Open `data/dashboard.html` in a browser.

Scanning never writes to your photos — for kernel-enforced safety, mount the drive read-only (e.g. `sudo mount -t drvfs Z: /mnt/z -o ro` on WSL). RAW+JPEG pairs count as one shot, with metadata from the RAW; `-Edit`/`-HDR`/`-Pano`/`(N)` derivatives are excluded from charts.

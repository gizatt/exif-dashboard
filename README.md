# EXIF Dashboard

## What and why

I rely on zoom lenses quite a bit. I'm currently considering getting a new camera and lenses. This repo contains code to scrape my photo library and tell me what settings -- primarily aperture and focal length -- I tend to use.

**[Live example](https://gizatt.github.io/exif-dashboard/example-dashboard.html)** — computed from 20k shots I took 2021-2026.

## Deets

Analyze camera/lens/focal-length usage across a photo collection: `scan` extracts EXIF into JSONL, `render` turns that into a self-contained interactive HTML dashboard.

## Use

```bash
sudo apt install libimage-exiftool-perl      # the only binary dependency; uv handles the rest
echo /path/to/photos >> data/dirs.txt        # directories to scan, one per line
uv run exif-dashboard scan data/dirs.txt -o data/photos.jsonl
uv run exif-dashboard render data/photos.jsonl -o data/dashboard.html
```

Open `data/dashboard.html` in a browser.

Scanning never writes to your photos — for kernel-enforced safety, mount the drive read-only (e.g. `sudo mount -t drvfs Z: /mnt/z -o ro` on WSL). RAW+JPEG pairs count as one shot, with metadata from the RAW; `-Edit`/`-HDR`/`-Pano`/`(N)` derivatives are excluded from charts.

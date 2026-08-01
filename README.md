# Image to Clip — Render deployment

Upload a photo from your phone, get back a 6-second captioned zoom clip.
Processing runs on Render's server (real ffmpeg, not a browser-based
version), so it's fast regardless of your phone.

## Deploy to Render

1. Push this folder to a GitHub repo.
2. Go to render.com → **New** → **Web Service** → connect that repo.
3. Render will detect the `Dockerfile` automatically — leave environment
   as **Docker**.
4. Instance type: the free tier works, but spins down after inactivity
   (the first request after idling takes ~30-60s to "wake up"). If you're
   using this often, the cheapest paid tier ($7/mo "Starter") stays warm
   and responds instantly every time.
5. Deploy. Open the given `onrender.com` URL on your phone.

No environment variables or extra config needed — ffmpeg and the font are
both bundled in the Docker image.

## Test locally first (optional but recommended)

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```
Open `http://localhost:8000` — make sure ffmpeg is installed on your machine
for this (it's already inside the Docker image for the deployed version).

## What's in here

- `main.py` — FastAPI server: serves the upload page, handles `/generate`.
- `captions.py` — the actual clip-rendering logic (captions, rounded title
  pill, zoom presets) ported directly from the working `image_to_clip.py`
  script, refactored to handle one request at a time instead of reading a
  fixed file path from CONFIG.
- `static/index.html` — the mobile upload page.
- `Poppins-Bold.ttf` — openly-licensed bold font (SIL Open Font License),
  used instead of the Windows Arial path from the desktop script.
- `Dockerfile` — installs ffmpeg + Python deps, runs the server.

## Performance note

Photos are capped to a 1920px longer edge before processing (configurable
via `MAX_OUTPUT_DIM` in `captions.py`) — full 12MP+ phone photos don't need
to be processed at full resolution for a short social clip, and skipping
that cut render time from ~40s down to ~5s per clip in testing. If you want
higher-resolution output, raise `MAX_OUTPUT_DIM`, but expect slower renders.

## Tuning

Same knobs as the Python script, all in `captions.py`:
- `CAPTIONS` — text, timing, position, width, colors, outline thickness,
  title box padding/roundness.
- `ZOOM_PRESETS` — `start_zoom`/`end_zoom` for the two motion styles.
- `MAX_OUTPUT_DIM` — resolution cap (speed vs. quality trade-off).

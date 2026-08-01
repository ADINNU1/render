import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from captions import render_clip, ZOOM_PRESETS

app = FastAPI()

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate")
async def generate(
    image: UploadFile = File(...),
    zoom_style: str = Form(...),
):
    if zoom_style not in ZOOM_PRESETS:
        raise HTTPException(400, f"zoom_style must be one of {list(ZOOM_PRESETS.keys())}")

    suffix = Path(image.filename or "upload.jpg").suffix or ".jpg"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / f"input{suffix}"
        with open(input_path, "wb") as f:
            shutil.copyfileobj(image.file, f)

        out_name = f"{uuid.uuid4().hex}.mp4"
        out_path = tmp_path / out_name

        try:
            render_clip(str(input_path), str(out_path), zoom_style, tmp_path)
        except RuntimeError as e:
            raise HTTPException(500, f"ffmpeg failed: {e}")

        # Copy result out of the temp dir before it's cleaned up, so
        # FileResponse can still stream it after this function returns.
        final_path = Path(tempfile.gettempdir()) / out_name
        shutil.copyfile(out_path, final_path)

    return FileResponse(
        final_path,
        media_type="video/mp4",
        filename=out_name,
        background=BackgroundTask(lambda: os.remove(final_path) if final_path.exists() else None),
    )

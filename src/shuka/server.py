"""src/shuka/server.py — FastAPI app for the shuka OPD intake demo."""
from __future__ import annotations

import base64
import shutil
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from shuka.pipeline import run_intake

_ROOT = Path(__file__).resolve().parent.parent.parent  # repo root (opd-intake/)
_WEB = _ROOT / "web"
_ASSETS = _ROOT / "assets"
_SAMPLES = _ROOT / "samples"
_UPLOADS = _ROOT / "out" / "uploads"
_UPLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="shuka — OPD Pre-Consult Voice Intake")

if _ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(_ASSETS)), name="assets")


@app.get("/")
def index():
    return FileResponse(str(_WEB / "index.html"))


@app.get("/favicon.ico")
def favicon():
    ico = _ASSETS / "model-01.svg"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/svg+xml")
    return JSONResponse({}, status_code=204)


@app.get("/mode")
def mode():
    from shuka.config import settings
    return JSONResponse({"mode": settings.intake_mode})


@app.get("/samples")
def list_samples():
    if not _SAMPLES.exists():
        return JSONResponse({"samples": []})
    names = sorted(p.name for p in _SAMPLES.glob("*.wav"))
    return JSONResponse({"samples": names})


@app.get("/samples/{name}")
def get_sample(name: str):
    # Guard against path traversal
    safe = Path(name).name
    path = _SAMPLES / safe
    if not path.exists():
        return JSONResponse({"error": f"sample not found: {safe}"}, status_code=404)
    return FileResponse(str(path), media_type="audio/wav")


@app.post("/intake")
async def intake(audio: UploadFile = File(...), image: UploadFile | None = File(None)):
    # Preserve the original stem so mock fixtures resolve.
    audio_name = Path(audio.filename or "upload.wav").name
    audio_path = _UPLOADS / audio_name
    with audio_path.open("wb") as f:
        shutil.copyfileobj(audio.file, f)

    image_path = None
    if image is not None and image.filename:
        image_path = _UPLOADS / Path(image.filename).name
        with image_path.open("wb") as f:
            shutil.copyfileobj(image.file, f)

    try:
        note, audio_bytes = run_intake(audio_path, image_path)
    except Exception as exc:
        return JSONResponse(
            {"error": f"{type(exc).__name__}: {exc}"}, status_code=500
        )

    return JSONResponse({
        "note": note.model_dump(mode="json"),
        "readback_wav_b64": base64.b64encode(audio_bytes).decode(),
    })

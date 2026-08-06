import asyncio
import os
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from rapidocr_onnxruntime import RapidOCR


MODEL_NAME = os.getenv("OCR_MODEL", "PP-OCRv4-ONNX")
API_KEY = os.getenv("LOCAL_AI_API_KEY", "")
MAX_UPLOAD_MB = int(os.getenv("OCR_MAX_UPLOAD_MB", "20"))
engine = RapidOCR()
app = FastAPI(title="OpenVMA Local OCR")


def authorize(authorization: str | None = Header(default=None)) -> None:
    if API_KEY and authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="invalid local AI token")


@app.get("/health")
def health():
    return {"status": "ready", "model": MODEL_NAME}


def run_ocr(path: str) -> tuple[list[dict], str]:
    raw = engine(path)
    result = raw[0] if isinstance(raw, tuple) else raw
    lines = []
    for item in result or []:
        if len(item) < 3:
            continue
        text = str(item[1]).strip()
        score = float(item[2])
        if text:
            lines.append({"text": text, "score": score})
    return lines, "\n".join(item["text"] for item in lines)


@app.post("/ocr", dependencies=[Depends(authorize)])
async def ocr(file: UploadFile = File(...), model: str = Form(default="PP-OCRv4-ONNX")):
    if model and model not in {MODEL_NAME, "PP-OCRv4", "PP-OCRv5"}:
        raise HTTPException(status_code=400, detail=f"model {model} is not loaded")
    suffix = Path(file.filename or "frame.jpg").suffix or ".jpg"
    handle = tempfile.NamedTemporaryFile(prefix="openvma_ocr_", suffix=suffix, delete=False)
    path = handle.name
    total = 0
    try:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_MB * 1024 * 1024:
                raise HTTPException(status_code=413, detail="image file is too large")
            handle.write(chunk)
        handle.close()
        lines, text = await asyncio.to_thread(run_ocr, path)
        return {"model": MODEL_NAME, "text": text, "lines": lines}
    finally:
        if not handle.closed:
            handle.close()
        try:
            os.unlink(path)
        except OSError:
            pass

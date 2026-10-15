import asyncio
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from funasr import AutoModel


ASR_MODEL = os.getenv(
    "ASR_MODEL_ID",
    "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
)
VAD_MODEL = os.getenv("ASR_VAD_MODEL_ID", "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch")
PUNC_MODEL = os.getenv(
    "ASR_PUNC_MODEL_ID",
    "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
)
MODEL_DEVICE = os.getenv("MODEL_DEVICE", "cpu")
API_KEY = os.getenv("LOCAL_AI_API_KEY", "")
MAX_UPLOAD_MB = int(os.getenv("ASR_MAX_UPLOAD_MB", "1024"))
model: AutoModel | None = None
model_status = "loading"
model_error = ""


def authorize(authorization: str | None = Header(default=None)) -> None:
    if API_KEY and authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="invalid local AI token")


def load_model() -> AutoModel:
    return AutoModel(
        model=ASR_MODEL,
        vad_model=VAD_MODEL,
        punc_model=PUNC_MODEL,
        device=MODEL_DEVICE,
        disable_update=True,
    )


async def load_model_in_background() -> None:
    global model, model_status, model_error
    try:
        model = await asyncio.to_thread(load_model)
        model_status = "ready"
    except Exception as error:
        model_error = f"{type(error).__name__}: {str(error)[:300]}"
        model_status = "error"


@asynccontextmanager
async def lifespan(_: FastAPI):
    global model
    task = asyncio.create_task(load_model_in_background())
    yield
    task.cancel()
    model = None


app = FastAPI(title="VideoX Local ASR", lifespan=lifespan)


@app.get("/health")
def health():
    payload = {"status": model_status, "model": ASR_MODEL, "source": "modelscope"}
    if model_error:
        payload["error"] = model_error
    return JSONResponse(status_code=200 if model_status == "ready" else 503, content=payload)


def run_transcription(path: str) -> str:
    if model is None:
        raise RuntimeError("ASR model is loading")
    result = model.generate(input=path, batch_size_s=300)
    if not result:
        return ""
    return "\n".join(str(item.get("text") or "").strip() for item in result if item.get("text")).strip()


@app.post("/transcribe", dependencies=[Depends(authorize)])
async def transcribe(file: UploadFile = File(...), model_name: str = Form(default="paraformer-zh", alias="model")):
    del model_name
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    handle = tempfile.NamedTemporaryFile(prefix="videox_asr_", suffix=suffix, delete=False)
    path = handle.name
    total = 0
    try:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_MB * 1024 * 1024:
                raise HTTPException(status_code=413, detail="audio file is too large")
            handle.write(chunk)
        handle.close()
        text = await asyncio.to_thread(run_transcription, path)
        return {"model": ASR_MODEL, "text": text}
    finally:
        if not handle.closed:
            handle.close()
        try:
            os.unlink(path)
        except OSError:
            pass

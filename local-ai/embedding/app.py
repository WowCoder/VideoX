import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from modelscope.hub.snapshot_download import snapshot_download
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
MODEL_DEVICE = os.getenv("MODEL_DEVICE", "cpu")
API_KEY = os.getenv("LOCAL_AI_API_KEY", "")
EXPECTED_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
MODEL_SOURCE = os.getenv("MODEL_SOURCE", "modelscope").lower()
MODELSCOPE_CACHE = os.getenv("MODELSCOPE_CACHE", "/models/modelscope")
# The ModelScope BGE-M3 repository stores its main Transformers weights as
# pytorch_model.bin and also publishes a separate ONNX copy. Keep the PyTorch
# weights required by SentenceTransformer, but skip the duplicate ONNX export
# and documentation assets.
MODELSCOPE_IGNORE_PATTERNS = [
    "onnx/*",
    "imgs/*",
    "*.md",
]
model: SentenceTransformer | None = None
model_status = "loading"
model_error = ""


def authorize(authorization: str | None = Header(default=None)) -> None:
    if API_KEY and authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="invalid local AI token")


def load_model() -> SentenceTransformer:
    model_path = (
        snapshot_download(
            model_id=MODEL_NAME,
            cache_dir=MODELSCOPE_CACHE,
            ignore_patterns=MODELSCOPE_IGNORE_PATTERNS,
        )
        if MODEL_SOURCE == "modelscope"
        else MODEL_NAME
    )
    loaded_model = SentenceTransformer(model_path, device=MODEL_DEVICE)
    dimensions = loaded_model.get_sentence_embedding_dimension()
    if dimensions != EXPECTED_DIMENSIONS:
        raise RuntimeError(
            f"embedding dimension mismatch: expected {EXPECTED_DIMENSIONS}, got {dimensions}"
        )
    return loaded_model


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


app = FastAPI(title="OpenVMA Local Embedding", lifespan=lifespan)


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str | None = None
    dimensions: int | None = None


@app.get("/health")
def health():
    payload = {"status": model_status, "model": MODEL_NAME, "source": MODEL_SOURCE}
    if model_error:
        payload["error"] = model_error
    return JSONResponse(status_code=200 if model_status == "ready" else 503, content=payload)


@app.post("/v1/embeddings", dependencies=[Depends(authorize)])
def embeddings(request: EmbeddingRequest):
    if model is None:
        raise HTTPException(status_code=503, detail="embedding model is loading")
    if request.model and request.model != MODEL_NAME:
        raise HTTPException(status_code=400, detail=f"model {request.model} is not loaded")
    if request.dimensions and request.dimensions != EXPECTED_DIMENSIONS:
        raise HTTPException(status_code=400, detail="requested dimensions do not match loaded model")

    inputs = [request.input] if isinstance(request.input, str) else request.input
    if not inputs or any(not isinstance(item, str) or not item.strip() for item in inputs):
        raise HTTPException(status_code=422, detail="input must contain non-empty text")
    vectors = model.encode(
        inputs,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return {
        "object": "list",
        "model": MODEL_NAME,
        "data": [
            {"object": "embedding", "index": index, "embedding": vector.tolist()}
            for index, vector in enumerate(vectors)
        ],
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }

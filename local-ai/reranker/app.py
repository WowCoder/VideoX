import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from FlagEmbedding import FlagReranker
from modelscope.hub.snapshot_download import snapshot_download


MODEL_NAME = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
MODEL_DEVICE = os.getenv("MODEL_DEVICE", "cpu")
API_KEY = os.getenv("LOCAL_AI_API_KEY", "")
MODEL_SOURCE = os.getenv("MODEL_SOURCE", "modelscope").lower()
MODELSCOPE_CACHE = os.getenv("MODELSCOPE_CACHE", "/models/modelscope")
MODELSCOPE_IGNORE_PATTERNS = [
    "*.bin",
    "onnx/*",
    "imgs/*",
    "*.md",
]
model: FlagReranker | None = None
model_status = "loading"
model_error = ""


def authorize(authorization: str | None = Header(default=None)) -> None:
    if API_KEY and authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="invalid local AI token")


def load_model() -> FlagReranker:
    model_path = (
        snapshot_download(
            model_id=MODEL_NAME,
            cache_dir=MODELSCOPE_CACHE,
            ignore_patterns=MODELSCOPE_IGNORE_PATTERNS,
        )
        if MODEL_SOURCE == "modelscope"
        else MODEL_NAME
    )
    return FlagReranker(
        model_path,
        use_fp16=MODEL_DEVICE.startswith("cuda"),
        devices=[MODEL_DEVICE],
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


app = FastAPI(title="VideoX Local Reranker", lifespan=lifespan)


class RerankRequest(BaseModel):
    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1)
    model: str | None = None
    top_n: int = Field(default=5, ge=1, le=100)


@app.get("/health")
def health():
    payload = {"status": model_status, "model": MODEL_NAME, "source": MODEL_SOURCE}
    if model_error:
        payload["error"] = model_error
    return JSONResponse(status_code=200 if model_status == "ready" else 503, content=payload)


@app.post("/rerank", dependencies=[Depends(authorize)])
def rerank(request: RerankRequest):
    if model is None:
        raise HTTPException(status_code=503, detail="reranker model is loading")
    if request.model and request.model != MODEL_NAME:
        raise HTTPException(status_code=400, detail=f"model {request.model} is not loaded")
    pairs = [[request.query, document] for document in request.documents]
    scores = model.compute_score(pairs, normalize=True)
    if isinstance(scores, float):
        scores = [scores]
    ordered = sorted(
        (
            {"index": index, "relevance_score": float(score)}
            for index, score in enumerate(scores)
        ),
        key=lambda item: item["relevance_score"],
        reverse=True,
    )
    return {
        "model": MODEL_NAME,
        "results": ordered[: min(request.top_n, len(ordered))],
    }

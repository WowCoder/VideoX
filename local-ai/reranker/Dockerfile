FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ARG TORCH_VERSION=2.13.0
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    "torch==${TORCH_VERSION}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip check \
    && python -c "import torch; assert torch.version.cuda is None, 'Expected CPU-only PyTorch'"

COPY app.py .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

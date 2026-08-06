FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

ARG TORCH_VERSION=2.11.0
ARG TORCHAUDIO_VERSION=2.11.0
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    "torch==${TORCH_VERSION}" \
    "torchaudio==${TORCHAUDIO_VERSION}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

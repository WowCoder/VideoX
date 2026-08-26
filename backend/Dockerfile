# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

WORKDIR /app

ARG OPENVMA_APT_MIRROR=""
ARG OPENVMA_PIP_INDEX_URL=""

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    if [ -n "${OPENVMA_APT_MIRROR}" ]; then \
        sed -i "s|deb.debian.org|${OPENVMA_APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    if [ -n "${OPENVMA_PIP_INDEX_URL}" ]; then \
        pip install --index-url "${OPENVMA_PIP_INDEX_URL}" -r requirements.txt; \
    else \
        pip install -r requirements.txt; \
    fi

RUN groupadd --system openvma \
    && useradd --system --gid openvma --create-home --home-dir /home/openvma openvma

COPY --chown=openvma:openvma . .

ENV HOME=/home/openvma \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER openvma

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

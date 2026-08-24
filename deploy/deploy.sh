#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${OPENVMA_COMPOSE_FILE:-${PROJECT_DIR}/compose.prod.yml}"
OPENVMA_ENV_FILE="${OPENVMA_ENV_FILE:-${PROJECT_DIR}/.env.production}"
STATE_DIR="${OPENVMA_STATE_DIR:-${PROJECT_DIR}/.deploy-state}"

if [[ ! -f "${OPENVMA_ENV_FILE}" ]]; then
    echo "生产环境文件不存在：${OPENVMA_ENV_FILE}" >&2
    exit 1
fi

read_env_value() {
    local key="$1"
    awk -F= -v expected="${key}" '$1 == expected {sub(/^[^=]*=/, ""); print; exit}' "${OPENVMA_ENV_FILE}"
}

deploy_tag="${OPENVMA_IMAGE_TAG:-$(read_env_value OPENVMA_IMAGE_TAG)}"
if [[ -z "${deploy_tag}" || "${deploy_tag}" == "latest" ]]; then
    echo "请通过 OPENVMA_IMAGE_TAG 指定不可变版本号，例如 Git commit SHA；生产发布不接受 latest" >&2
    exit 1
fi
if [[ ! "${deploy_tag}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "OPENVMA_IMAGE_TAG 包含非法字符：${deploy_tag}" >&2
    exit 1
fi

source_tag="unknown"
if [[ -f "${STATE_DIR}/current_tag" ]]; then
    recorded_source_tag="$(tr -d '[:space:]' < "${STATE_DIR}/current_tag")"
    if [[ -n "${recorded_source_tag}" && "${recorded_source_tag}" =~ ^[A-Za-z0-9._-]+$ ]]; then
        source_tag="${recorded_source_tag}"
    fi
fi

command -v docker >/dev/null 2>&1 || {
    echo "未找到 docker" >&2
    exit 1
}

export OPENVMA_ENV_FILE
export OPENVMA_IMAGE_TAG="${deploy_tag}"
compose=(docker compose -f "${COMPOSE_FILE}" --env-file "${OPENVMA_ENV_FILE}")

"${compose[@]}" config --quiet

if [[ -n "$("${compose[@]}" ps -q db)" ]]; then
    echo "发布前创建数据备份..."
    OPENVMA_ENV_FILE="${OPENVMA_ENV_FILE}" \
        OPENVMA_COMPOSE_FILE="${COMPOSE_FILE}" \
        OPENVMA_IMAGE_TAG="${source_tag}" \
        OPENVMA_SOURCE_IMAGE_TAG="${source_tag}" \
        OPENVMA_TARGET_IMAGE_TAG="${deploy_tag}" \
        "${SCRIPT_DIR}/backup.sh"
else
    echo "首次部署未发现数据库容器，跳过发布前备份"
fi

echo "构建版本 ${deploy_tag}..."
"${compose[@]}" build backend gateway

echo "启动数据服务并初始化 bucket..."
"${compose[@]}" up -d db redis minio
"${compose[@]}" run --rm minio-init

echo "执行数据库迁移..."
"${compose[@]}" run --rm migrate

echo "更新 API 与任务进程..."
"${compose[@]}" up -d --no-deps --force-recreate backend celery-worker celery-beat

echo "更新内部 Nginx 网关..."
"${compose[@]}" up -d --no-deps --force-recreate gateway

OPENVMA_ENV_FILE="${OPENVMA_ENV_FILE}" "${SCRIPT_DIR}/healthcheck.sh"

mkdir -p "${STATE_DIR}"
if [[ -f "${STATE_DIR}/current_tag" ]]; then
    previous_tag="$(tr -d '[:space:]' < "${STATE_DIR}/current_tag")"
    if [[ -n "${previous_tag}" && "${previous_tag}" != "${deploy_tag}" ]]; then
        printf '%s\n' "${previous_tag}" > "${STATE_DIR}/previous_tag"
    fi
fi
printf '%s\n' "${deploy_tag}" > "${STATE_DIR}/current_tag"

echo "OpenVMA ${deploy_tag} 发布完成"

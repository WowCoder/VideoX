#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${VIDEOX_COMPOSE_FILE:-${PROJECT_DIR}/compose.prod.yml}"
VIDEOX_ENV_FILE="${VIDEOX_ENV_FILE:-${PROJECT_DIR}/.env.production}"
STATE_DIR="${VIDEOX_STATE_DIR:-${PROJECT_DIR}/.deploy-state}"

if [[ ! -f "${VIDEOX_ENV_FILE}" ]]; then
    echo "生产环境文件不存在：${VIDEOX_ENV_FILE}" >&2
    exit 1
fi
if [[ "${CONFIRM_SCHEMA_COMPATIBLE:-0}" != "1" ]]; then
    echo "回滚脚本不会自动回退数据库。确认旧镜像兼容当前 schema 后，设置 CONFIRM_SCHEMA_COMPATIBLE=1" >&2
    exit 1
fi

read_env_value() {
    local key="$1"
    awk -F= -v expected="${key}" '$1 == expected {sub(/^[^=]*=/, ""); print; exit}' "${VIDEOX_ENV_FILE}"
}

rollback_tag="${ROLLBACK_IMAGE_TAG:-}"
if [[ -z "${rollback_tag}" && -f "${STATE_DIR}/previous_tag" ]]; then
    rollback_tag="$(tr -d '[:space:]' < "${STATE_DIR}/previous_tag")"
fi
if [[ -z "${rollback_tag}" || ! "${rollback_tag}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "请设置有效的 ROLLBACK_IMAGE_TAG，或确保 .deploy-state/previous_tag 存在" >&2
    exit 1
fi

backend_image="${VIDEOX_BACKEND_IMAGE:-$(read_env_value VIDEOX_BACKEND_IMAGE)}"
gateway_image="${VIDEOX_GATEWAY_IMAGE:-$(read_env_value VIDEOX_GATEWAY_IMAGE)}"
admin_gateway_image="${VIDEOX_ADMIN_GATEWAY_IMAGE:-$(read_env_value VIDEOX_ADMIN_GATEWAY_IMAGE)}"
backend_image="${backend_image:-videox-backend}"
gateway_image="${gateway_image:-videox-gateway}"
admin_gateway_image="${admin_gateway_image:-videox-admin-gateway}"

docker image inspect "${backend_image}:${rollback_tag}" >/dev/null
docker image inspect "${gateway_image}:${rollback_tag}" >/dev/null
docker image inspect "${admin_gateway_image}:${rollback_tag}" >/dev/null

export VIDEOX_ENV_FILE
export VIDEOX_IMAGE_TAG="${rollback_tag}"
compose=(docker compose -f "${COMPOSE_FILE}" --env-file "${VIDEOX_ENV_FILE}")

current_tag=""
if [[ -f "${STATE_DIR}/current_tag" ]]; then
    current_tag="$(tr -d '[:space:]' < "${STATE_DIR}/current_tag")"
fi

echo "回滚前创建当前数据备份..."
VIDEOX_ENV_FILE="${VIDEOX_ENV_FILE}" \
    VIDEOX_COMPOSE_FILE="${COMPOSE_FILE}" \
    VIDEOX_IMAGE_TAG="${current_tag:-unknown}" \
    "${SCRIPT_DIR}/backup.sh"

"${compose[@]}" up -d --no-deps --force-recreate \
    backend celery-worker celery-control celery-video celery-media celery-export celery-beat
"${compose[@]}" up -d --no-deps --force-recreate gateway admin-gateway
VIDEOX_ENV_FILE="${VIDEOX_ENV_FILE}" "${SCRIPT_DIR}/healthcheck.sh"

mkdir -p "${STATE_DIR}"
printf '%s\n' "${rollback_tag}" > "${STATE_DIR}/current_tag"
if [[ -n "${current_tag}" && "${current_tag}" != "${rollback_tag}" ]]; then
    printf '%s\n' "${current_tag}" > "${STATE_DIR}/previous_tag"
fi

echo "应用镜像已回滚到 ${rollback_tag}；数据库 schema 未做任何自动降级"

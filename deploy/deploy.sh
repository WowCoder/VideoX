#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RELEASES_DIR="$(cd -- "${PROJECT_DIR}/.." && pwd)"
COMPOSE_FILE="${VIDEOX_COMPOSE_FILE:-${PROJECT_DIR}/compose.prod.yml}"
VIDEOX_ENV_FILE="${VIDEOX_ENV_FILE:-${PROJECT_DIR}/.env.production}"
STATE_DIR="${VIDEOX_STATE_DIR:-${PROJECT_DIR}/.deploy-state}"
VIDEOX_BACKUP_PATH="${VIDEOX_BACKUP_PATH:-}"
VIDEOX_MIGRATION_MODE="${VIDEOX_MIGRATION_MODE:-auto}"
VIDEOX_APT_MIRROR="${VIDEOX_APT_MIRROR:-mirrors.aliyun.com}"
VIDEOX_PIP_INDEX_URL="${VIDEOX_PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"
VIDEOX_NPM_REGISTRY="${VIDEOX_NPM_REGISTRY:-https://registry.npmmirror.com}"

if [[ ! -f "${VIDEOX_ENV_FILE}" ]]; then
    echo "生产环境文件不存在：${VIDEOX_ENV_FILE}" >&2
    exit 1
fi

read_env_value() {
    local key="$1"
    awk -F= -v expected="${key}" '$1 == expected {sub(/^[^=]*=/, ""); print; exit}' "${VIDEOX_ENV_FILE}"
}

deploy_tag="${VIDEOX_IMAGE_TAG:-$(read_env_value VIDEOX_IMAGE_TAG)}"
if [[ -z "${deploy_tag}" || "${deploy_tag}" == "latest" ]]; then
    echo "请通过 VIDEOX_IMAGE_TAG 指定不可变版本号，例如 Git commit SHA；生产发布不接受 latest" >&2
    exit 1
fi
if [[ ! "${deploy_tag}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "VIDEOX_IMAGE_TAG 包含非法字符：${deploy_tag}" >&2
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
command -v curl >/dev/null 2>&1 || { echo "未找到 curl，无法预检构建镜像源" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "未找到 python3，无法创建 MinIO 快照" >&2; exit 1; }
case "${VIDEOX_MIGRATION_MODE}" in auto|always) ;; *) echo "VIDEOX_MIGRATION_MODE 必须是 auto 或 always" >&2; exit 1 ;; esac

echo "预检 apt/PyPI/npm 镜像..."
apt_mirror_url="${VIDEOX_APT_MIRROR}"
if [[ "${apt_mirror_url}" != http://* && "${apt_mirror_url}" != https://* ]]; then
    apt_mirror_url="https://${apt_mirror_url}"
fi
curl --fail --silent --show-error --location --max-time 10 "${apt_mirror_url}/debian/dists/bookworm/InRelease" -o /dev/null
curl --fail --silent --show-error --location --max-time 10 "${VIDEOX_PIP_INDEX_URL}" -o /dev/null
curl --fail --silent --show-error --location --max-time 10 "${VIDEOX_NPM_REGISTRY%/}/-/ping" -o /dev/null

export VIDEOX_ENV_FILE
export VIDEOX_IMAGE_TAG="${deploy_tag}"
export VIDEOX_APT_MIRROR VIDEOX_PIP_INDEX_URL VIDEOX_NPM_REGISTRY DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1
compose=(docker compose -f "${COMPOSE_FILE}" --env-file "${VIDEOX_ENV_FILE}")

"${compose[@]}" config --quiet

if [[ -n "$("${compose[@]}" ps -q db)" ]]; then
    if [[ -n "${VIDEOX_BACKUP_PATH}" ]]; then
        echo "校验并复用已创建的发布备份..."
        [[ -d "${VIDEOX_BACKUP_PATH}" && -s "${VIDEOX_BACKUP_PATH}/postgres.dump" && -d "${VIDEOX_BACKUP_PATH}/minio" && -s "${VIDEOX_BACKUP_PATH}/manifest.txt" ]] || { echo "复用备份不完整：${VIDEOX_BACKUP_PATH}" >&2; exit 1; }
        backup_source="$(awk -F= '$1 == "source_image_tag" {print $2; exit}' "${VIDEOX_BACKUP_PATH}/manifest.txt")"
        backup_target="$(awk -F= '$1 == "target_image_tag" {print $2; exit}' "${VIDEOX_BACKUP_PATH}/manifest.txt")"
        [[ "${backup_source}" == "${source_tag}" && "${backup_target}" == "${deploy_tag}" ]] || { echo "复用备份版本不匹配" >&2; exit 1; }
        [[ ! -s "${VIDEOX_BACKUP_PATH}/SHA256SUMS" ]] || (cd "${VIDEOX_BACKUP_PATH}" && sha256sum --ignore-missing --check SHA256SUMS)
    else
    echo "发布前创建数据备份..."
    VIDEOX_ENV_FILE="${VIDEOX_ENV_FILE}" \
        VIDEOX_COMPOSE_FILE="${COMPOSE_FILE}" \
        VIDEOX_IMAGE_TAG="${source_tag}" \
        VIDEOX_SOURCE_IMAGE_TAG="${source_tag}" \
        VIDEOX_TARGET_IMAGE_TAG="${deploy_tag}" \
        "${SCRIPT_DIR}/backup.sh"
    fi
else
    echo "首次部署未发现数据库容器，跳过发布前备份"
fi

echo "构建版本 ${deploy_tag}..."
"${compose[@]}" build backend gateway admin-gateway

echo "启动数据服务并初始化 bucket..."
"${compose[@]}" up -d db redis minio
"${compose[@]}" run --rm minio-init

should_migrate=1
if [[ "${VIDEOX_MIGRATION_MODE}" == "auto" && "${source_tag}" != "unknown" ]]; then
    source_migrations="${RELEASES_DIR}/${source_tag}/backend/alembic/versions"
    target_migrations="${PROJECT_DIR}/backend/alembic/versions"
    db_version="$("${compose[@]}" exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select version_num from alembic_version limit 1"' 2>/dev/null || true)"
    target_head="$(grep -h '^revision = ' "${target_migrations}"/*.py 2>/dev/null | tail -n 1 | sed -E "s/.*['\"]([^'\"]+)['\"].*/\1/")"
    if [[ -n "${db_version}" && -n "${target_head}" && "${db_version}" == "${target_head}" ]]; then
        if [[ -d "${source_migrations}" ]] && diff -qr "${source_migrations}" "${target_migrations}" >/dev/null 2>&1; then
            should_migrate=0
        fi
    fi
fi
if [[ "${should_migrate}" == "1" ]]; then
    echo "执行数据库迁移..."
    "${compose[@]}" run --rm migrate
else
    echo "数据库 schema 已是目标版本且迁移目录未变化，跳过 migration 容器"
fi

echo "更新 API 与任务进程..."
"${compose[@]}" up -d --no-deps --force-recreate \
    backend celery-worker celery-control celery-video celery-media celery-export celery-beat

echo "更新内部 Nginx 网关..."
"${compose[@]}" up -d --no-deps --force-recreate gateway admin-gateway

VIDEOX_ENV_FILE="${VIDEOX_ENV_FILE}" "${SCRIPT_DIR}/healthcheck.sh"

mkdir -p "${STATE_DIR}"
if [[ -f "${STATE_DIR}/current_tag" ]]; then
    previous_tag="$(tr -d '[:space:]' < "${STATE_DIR}/current_tag")"
    if [[ -n "${previous_tag}" && "${previous_tag}" != "${deploy_tag}" ]]; then
        printf '%s\n' "${previous_tag}" > "${STATE_DIR}/previous_tag"
    fi
fi
printf '%s\n' "${deploy_tag}" > "${STATE_DIR}/current_tag"

echo "VideoX ${deploy_tag} 发布完成"

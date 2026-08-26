#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${OPENVMA_COMPOSE_FILE:-${PROJECT_DIR}/compose.prod.yml}"
OPENVMA_ENV_FILE="${OPENVMA_ENV_FILE:-${PROJECT_DIR}/.env.production}"
BACKUP_ROOT="${OPENVMA_BACKUP_DIR:-${PROJECT_DIR}/backups}"
BACKUP_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_PATH="${BACKUP_ROOT}/${BACKUP_TIMESTAMP}"
MINIO_CURRENT="${BACKUP_ROOT}/minio-current"

if [[ ! -f "${OPENVMA_ENV_FILE}" ]]; then
    echo "生产环境文件不存在：${OPENVMA_ENV_FILE}" >&2
    exit 1
fi

command -v docker >/dev/null 2>&1 || {
    echo "未找到 docker" >&2
    exit 1
}

export OPENVMA_ENV_FILE
compose=(docker compose -f "${COMPOSE_FILE}" --env-file "${OPENVMA_ENV_FILE}")

db_container="$("${compose[@]}" ps -q db)"
minio_container="$("${compose[@]}" ps -q minio)"
if [[ -z "${db_container}" || -z "${minio_container}" ]]; then
    echo "数据库或 MinIO 尚未运行，无法创建备份" >&2
    exit 1
fi

mkdir -p "${BACKUP_PATH}" "${MINIO_CURRENT}"
chmod 700 "${BACKUP_PATH}"

echo "正在备份 PostgreSQL..."
"${compose[@]}" exec -T db sh -c \
    'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges' \
    > "${BACKUP_PATH}/postgres.dump"

echo "正在镜像 MinIO bucket..."
"${compose[@]}" run --rm --no-deps \
    --entrypoint /bin/sh \
    -v "${BACKUP_ROOT}:/backup-root" \
    minio-init -c \
    'mc alias set backup http://minio:9000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" >/dev/null && mc mirror --overwrite "backup/$MINIO_BUCKET" /backup-root/minio-current && mc ls --json --recursive "backup/$MINIO_BUCKET" > /backup-root/.minio-list'

python3 "${PROJECT_DIR}/deploy/reconcile_minio_tree.py" "${MINIO_CURRENT}" "${BACKUP_ROOT}/.minio-list"
rm -f "${BACKUP_ROOT}/.minio-list"

previous_snapshot=""
if [[ -L "${BACKUP_ROOT}/minio-last" ]]; then
    previous_snapshot="$(readlink -f "${BACKUP_ROOT}/minio-last")"
elif [[ -d "${BACKUP_ROOT}/minio-last" ]]; then
    previous_snapshot="${BACKUP_ROOT}/minio-last"
fi

snapshot_path="${BACKUP_PATH}/minio"
snapshot_args=("${PROJECT_DIR}/deploy/snapshot_tree.py" "${MINIO_CURRENT}" "${snapshot_path}")
if [[ -n "${previous_snapshot}" && -d "${previous_snapshot}" ]]; then
    snapshot_args+=(--previous "${previous_snapshot}")
fi
python3 "${snapshot_args[@]}"

new_last_link="${BACKUP_ROOT}/.minio-last-${BACKUP_TIMESTAMP}"
ln -s "${snapshot_path}" "${new_last_link}"
mv -Tf "${new_last_link}" "${BACKUP_ROOT}/minio-last"

git_revision="unknown"
if command -v git >/dev/null 2>&1 && git -C "${PROJECT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git_revision="$(git -C "${PROJECT_DIR}" rev-parse HEAD)"
fi

source_image_tag="${OPENVMA_SOURCE_IMAGE_TAG:-${OPENVMA_IMAGE_TAG:-unknown}}"
target_image_tag="${OPENVMA_TARGET_IMAGE_TAG:-unknown}"

{
    echo "created_at=${BACKUP_TIMESTAMP}"
    echo "git_revision=${git_revision}"
    # image_tag 保留为兼容字段，语义与 source_image_tag 一致。
    echo "image_tag=${source_image_tag}"
    echo "source_image_tag=${source_image_tag}"
    echo "target_image_tag=${target_image_tag}"
    echo "compose_file=${COMPOSE_FILE}"
} > "${BACKUP_PATH}/manifest.txt"

if command -v sha256sum >/dev/null 2>&1; then
    (
        cd "${BACKUP_PATH}"
        find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
    )
fi

echo "备份完成：${BACKUP_PATH}"
echo "提示：PostgreSQL dump 各自一致，但在线 MinIO mirror 与数据库之间不是跨服务原子快照"

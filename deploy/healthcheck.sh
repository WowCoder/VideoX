#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VIDEOX_ENV_FILE="${VIDEOX_ENV_FILE:-${PROJECT_DIR}/.env.production}"
COMPOSE_FILE="${VIDEOX_COMPOSE_FILE:-${PROJECT_DIR}/compose.prod.yml}"
HEALTH_RETRIES="${VIDEOX_HEALTH_RETRIES:-20}"
HEALTH_RETRY_DELAY="${VIDEOX_HEALTH_RETRY_DELAY:-3}"

if [[ ! -f "${VIDEOX_ENV_FILE}" ]]; then
    echo "生产环境文件不存在：${VIDEOX_ENV_FILE}" >&2
    exit 1
fi

command -v curl >/dev/null 2>&1 || {
    echo "未找到 curl" >&2
    exit 1
}
command -v docker >/dev/null 2>&1 || {
    echo "未找到 docker" >&2
    exit 1
}
export VIDEOX_ENV_FILE
compose=(docker compose -f "${COMPOSE_FILE}" --env-file "${VIDEOX_ENV_FILE}")

read_env_value() {
    local key="$1"
    awk -F= -v expected="${key}" '$1 == expected {sub(/^[^=]*=/, ""); print; exit}' "${VIDEOX_ENV_FILE}"
}

app_domain="${APP_DOMAIN:-$(read_env_value APP_DOMAIN)}"
media_domain="${MEDIA_DOMAIN:-$(read_env_value MEDIA_DOMAIN)}"
admin_domain="${ADMIN_DOMAIN:-$(read_env_value ADMIN_DOMAIN)}"
gateway_bind_ip="${GATEWAY_BIND_IP:-$(read_env_value GATEWAY_BIND_IP)}"
gateway_port="${GATEWAY_PORT:-$(read_env_value GATEWAY_PORT)}"
admin_gateway_bind_ip="${ADMIN_GATEWAY_BIND_IP:-$(read_env_value ADMIN_GATEWAY_BIND_IP)}"
admin_gateway_port="${ADMIN_GATEWAY_PORT:-$(read_env_value ADMIN_GATEWAY_PORT)}"
gateway_bind_ip="${gateway_bind_ip:-127.0.0.1}"
gateway_port="${gateway_port:-8080}"
admin_gateway_bind_ip="${admin_gateway_bind_ip:-127.0.0.1}"
admin_gateway_port="${admin_gateway_port:-8081}"

if [[ "${gateway_bind_ip}" == "0.0.0.0" ]]; then
    gateway_bind_ip="127.0.0.1"
fi
if [[ "${admin_gateway_bind_ip}" == "0.0.0.0" ]]; then
    admin_gateway_bind_ip="127.0.0.1"
fi
if [[ -z "${app_domain}" || -z "${media_domain}" || -z "${admin_domain}" ]]; then
    echo "APP_DOMAIN、MEDIA_DOMAIN 和 ADMIN_DOMAIN 不能为空" >&2
    exit 1
fi

request_with_retry() {
    local label="$1"
    local host_header="$2"
    local url="$3"
    local attempt
    local status
    for ((attempt = 1; attempt <= HEALTH_RETRIES; attempt += 1)); do
        if status="$(curl --silent --show-error --max-time 10 --output /dev/null \
            --write-out '%{http_code}' -H "Host: ${host_header}" "${url}")" \
            && [[ "${status}" == "200" ]]; then
            echo "通过：${label}"
            return 0
        fi
        if (( attempt < HEALTH_RETRIES )); then
            sleep "${HEALTH_RETRY_DELAY}"
        fi
    done
    echo "失败：${label}（${url}，最后 HTTP 状态 ${status:-不可用}；必须为 200，重定向不算通过）" >&2
    return 1
}

request_expect_status() {
    local label="$1"
    local host_header="$2"
    local url="$3"
    local expected="$4"
    local status
    status="$(curl --silent --show-error --max-time 10 --output /dev/null \
        --write-out '%{http_code}' -H "Host: ${host_header}" "${url}")"
    if [[ "${status}" != "${expected}" ]]; then
        echo "失败：${label}（${url}，HTTP ${status:-不可用}；预期 ${expected}）" >&2
        return 1
    fi
    echo "通过：${label}"
}

require_running_service() {
    local service="$1"
    local attempt
    for ((attempt = 1; attempt <= HEALTH_RETRIES; attempt += 1)); do
        if [[ -n "$("${compose[@]}" ps --status running -q "${service}")" ]]; then
            echo "通过：${service} 容器运行中"
            return 0
        fi
        if (( attempt < HEALTH_RETRIES )); then
            sleep "${HEALTH_RETRY_DELAY}"
        fi
    done
    echo "失败：${service} 容器未运行" >&2
    return 1
}

internal_base="http://${gateway_bind_ip}:${gateway_port}"
admin_internal_base="http://${admin_gateway_bind_ip}:${admin_gateway_port}"
request_with_retry "内部 Nginx" "${app_domain}" "${internal_base}/nginx-health"
request_with_retry "Backend readiness" "${app_domain}" "${internal_base}/api/health/ready"
request_with_retry "MinIO media proxy" "${media_domain}" "${internal_base}/minio/health/live"
request_with_retry "运营后台 Nginx" "${admin_domain}" "${admin_internal_base}/nginx-health"
request_expect_status "用户域名隐藏后台 API" "${app_domain}" "${internal_base}/api/admin/dashboard/summary" "404"
request_expect_status "后台 API 强制管理员认证" "${admin_domain}" "${admin_internal_base}/api/admin/dashboard/summary" "401"
request_expect_status "后台域名隐藏普通 API" "${admin_domain}" "${admin_internal_base}/api/users/me" "404"

for worker_service in \
    celery-worker celery-control celery-video celery-media celery-export celery-beat; do
    require_running_service "${worker_service}"
done

# Worker 启动信号会各自写入短 TTL 心跳；Beat 派发到 control 队列的心跳则
# 证明 Beat -> Broker -> Worker 整条链路可用。首次发布时给 Beat 一个周期的时间。
celery_heartbeat_ready=0
for ((attempt = 1; attempt <= HEALTH_RETRIES; attempt += 1)); do
    if "${compose[@]}" exec -T celery-control python -c \
        'import os, redis, sys; client = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True); workers = sum(1 for _ in client.scan_iter(match="videox:heartbeat:worker:*")); beat = client.get("videox:heartbeat:beat-dispatch"); sys.exit(0 if workers >= 5 and beat else 1)'; then
        celery_heartbeat_ready=1
        break
    fi
    if (( attempt < HEALTH_RETRIES )); then
        sleep "${HEALTH_RETRY_DELAY}"
    fi
done
if [[ "${celery_heartbeat_ready}" != "1" ]]; then
    echo "失败：Celery Worker 或 Beat 调度心跳不完整" >&2
    exit 1
fi
echo "通过：5 个 Celery Worker 与 Beat 调度心跳"

if [[ "${VIDEOX_PUBLIC_CHECK:-0}" == "1" ]]; then
    request_with_retry "雷池后的公网应用" "${app_domain}" "https://${app_domain}/api/health/ready"
    request_with_retry "雷池后的公网媒体" "${media_domain}" "https://${media_domain}/minio/health/live"
    request_with_retry "雷池后的公网运营后台" "${admin_domain}" "https://${admin_domain}/"
fi

echo "VideoX 健康检查全部通过"

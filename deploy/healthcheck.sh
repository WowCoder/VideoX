#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
OPENVMA_ENV_FILE="${OPENVMA_ENV_FILE:-${PROJECT_DIR}/.env.production}"
HEALTH_RETRIES="${OPENVMA_HEALTH_RETRIES:-20}"
HEALTH_RETRY_DELAY="${OPENVMA_HEALTH_RETRY_DELAY:-3}"

if [[ ! -f "${OPENVMA_ENV_FILE}" ]]; then
    echo "生产环境文件不存在：${OPENVMA_ENV_FILE}" >&2
    exit 1
fi

command -v curl >/dev/null 2>&1 || {
    echo "未找到 curl" >&2
    exit 1
}

read_env_value() {
    local key="$1"
    awk -F= -v expected="${key}" '$1 == expected {sub(/^[^=]*=/, ""); print; exit}' "${OPENVMA_ENV_FILE}"
}

app_domain="${APP_DOMAIN:-$(read_env_value APP_DOMAIN)}"
media_domain="${MEDIA_DOMAIN:-$(read_env_value MEDIA_DOMAIN)}"
gateway_bind_ip="${GATEWAY_BIND_IP:-$(read_env_value GATEWAY_BIND_IP)}"
gateway_port="${GATEWAY_PORT:-$(read_env_value GATEWAY_PORT)}"
gateway_bind_ip="${gateway_bind_ip:-127.0.0.1}"
gateway_port="${gateway_port:-8080}"

if [[ "${gateway_bind_ip}" == "0.0.0.0" ]]; then
    gateway_bind_ip="127.0.0.1"
fi
if [[ -z "${app_domain}" || -z "${media_domain}" ]]; then
    echo "APP_DOMAIN 和 MEDIA_DOMAIN 不能为空" >&2
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

internal_base="http://${gateway_bind_ip}:${gateway_port}"
request_with_retry "内部 Nginx" "${app_domain}" "${internal_base}/nginx-health"
request_with_retry "Backend readiness" "${app_domain}" "${internal_base}/api/health/ready"
request_with_retry "MinIO media proxy" "${media_domain}" "${internal_base}/minio/health/live"

if [[ "${OPENVMA_PUBLIC_CHECK:-0}" == "1" ]]; then
    request_with_retry "雷池后的公网应用" "${app_domain}" "https://${app_domain}/api/health/ready"
    request_with_retry "雷池后的公网媒体" "${media_domain}" "https://${media_domain}/minio/health/live"
fi

echo "OpenVMA 健康检查全部通过"

"""第三方下载 URL 的 SSRF 防护。"""

import ipaddress
import socket
from urllib.parse import urlparse

from app.config import get_settings


def validate_external_media_url(url: str) -> None:
    settings = get_settings()
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        raise RuntimeError("AI 服务返回了不安全的媒体地址")

    allowed = settings.ai_media_allowed_host_list
    if not any(
        hostname == item.lstrip(".") or (item.startswith(".") and hostname.endswith(item))
        for item in allowed
    ):
        raise RuntimeError("AI 服务返回的媒体域名不在允许列表中")

    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as error:
        raise RuntimeError("AI 媒体域名无法解析") from error
    if not addresses:
        raise RuntimeError("AI 媒体域名没有可用地址")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast, ip.is_reserved, ip.is_unspecified)):
            raise RuntimeError("AI 媒体地址解析到了不安全的网络")


def validate_public_https_url(url: str) -> None:
    """校验用户配置的公开 HTTPS 来源；每次请求和重定向都必须重新调用。"""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        raise RuntimeError("来源必须是无内嵌凭据的 HTTPS 地址")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                hostname, parsed.port or 443, type=socket.SOCK_STREAM
            )
        }
    except socket.gaierror as error:
        raise RuntimeError("来源域名无法解析") from error
    if not addresses:
        raise RuntimeError("来源域名没有可用地址")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if any(
            (
                ip.is_private,
                ip.is_loopback,
                ip.is_link_local,
                ip.is_multicast,
                ip.is_reserved,
                ip.is_unspecified,
            )
        ):
            raise RuntimeError("来源解析到了不安全的网络地址")

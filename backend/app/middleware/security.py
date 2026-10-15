"""Redis API 限流。生产环境 Redis 故障时拒绝请求，避免静默失去防护。"""

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings


settings = get_settings()
_redis_client = None


def _limit_for_path(path: str) -> tuple[str, int]:
    if path in {
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/send-code",
        "/api/auth/login-phone",
        "/api/auth/wechat/callback",
        "/api/admin/auth/login",
        "/api/admin/auth/refresh",
    }:
        return "auth", settings.auth_rate_limit_per_minute
    if path == "/api/assets/upload":
        return "upload", settings.upload_rate_limit_per_minute
    return "api", settings.api_rate_limit_per_minute


async def _redis():
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def close_rate_limit_redis() -> None:
    """关闭进程级 Redis 客户端，避免应用优雅退出时遗留连接。"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.url.path.startswith("/api/health"):
            return await call_next(request)

        category, limit = _limit_for_path(request.url.path)
        client_host = request.client.host if request.client else "unknown"
        bucket = int(time.time() // 60)
        key = f"videox:rate:{category}:{client_host}:{bucket}"
        try:
            redis_client = await _redis()
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, 70)
        except Exception:
            if settings.environment.lower() == "production":
                return JSONResponse(status_code=503, content={"detail": "请求防护服务暂时不可用"})
            return await call_next(request)

        if count > limit:
            retry_after = 60 - int(time.time() % 60)
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后重试"},
                headers={"Retry-After": str(retry_after)},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
        return response

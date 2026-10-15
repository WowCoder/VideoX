"""FastAPI 应用入口。"""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text

from app.middleware.security import RateLimitMiddleware

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


async def _check_database() -> None:
    from app.database import engine

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def _check_redis() -> None:
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.ping()
    finally:
        await client.aclose()


async def _check_minio() -> None:
    from app.utils.storage import get_minio_client

    client = await asyncio.to_thread(get_minio_client)
    exists = await asyncio.to_thread(client.bucket_exists, settings.minio_bucket)
    if not exists:
        raise RuntimeError("MinIO bucket is unavailable")


async def _readiness_status() -> tuple[bool, dict[str, str]]:
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
        "minio": _check_minio(),
    }
    results = await asyncio.gather(
        *(asyncio.wait_for(check, timeout=5) for check in checks.values()),
        return_exceptions=True,
    )
    status: dict[str, str] = {}
    ready = True
    for name, result in zip(checks, results):
        if isinstance(result, BaseException):
            ready = False
            status[name] = "unavailable"
            logger.warning("Readiness check failed for %s: %s", name, result)
        else:
            status[name] = "ok"
    return ready, status


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理。"""
    from app.api.ws import start_job_update_subscriber, stop_job_update_subscriber
    from app.database import engine
    from app.middleware.security import close_rate_limit_redis

    await start_job_update_subscriber()
    try:
        yield
    finally:
        await stop_job_update_subscriber()
        await close_rate_limit_redis()
        await engine.dispose()


app = FastAPI(
    title="VideoX API",
    description="把脚本和素材交给 AI，几分钟得到一版可改的初剪。",
    version="3.0.0",
    lifespan=lifespan,
    docs_url=None if settings.environment.lower() == "production" else "/docs",
    redoc_url=None if settings.environment.lower() == "production" else "/redoc",
    openapi_url=None if settings.environment.lower() == "production" else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
app.add_middleware(RateLimitMiddleware)


# ── 路由注册 ──
from app.api import activity, auth, projects, assets, jobs, generate, ws, billing, billing_v2, notifications, search, inspiration, voiceover  # noqa: E402
from app.api.admin import (  # noqa: E402
    audit_logs as admin_audit_logs,
    auth as admin_auth,
    billing as admin_billing,
    dashboard as admin_dashboard,
    jobs as admin_jobs,
    search as admin_search,
    users as admin_users,
)

app.include_router(auth.router, prefix="/api/auth", tags=["鉴权"])
app.include_router(activity.router, prefix="/api/activity", tags=["用户活跃"])
app.include_router(projects.router, prefix="/api/projects", tags=["项目"])
app.include_router(assets.router, prefix="/api/assets", tags=["素材"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["任务"])
app.include_router(generate.router, prefix="/api/generate", tags=["AI 生成"])
app.include_router(ws.router, prefix="/api/ws", tags=["WebSocket"])
app.include_router(billing.router, prefix="/api/billing", tags=["会员与支付"])
app.include_router(billing_v2.router, prefix="/api/billing", tags=["V-Credits 计费"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["站内通知"])
app.include_router(search.router, prefix="/api/search", tags=["全局搜索"])
app.include_router(inspiration.router, prefix="/api/inspiration", tags=["灵感岛"])
app.include_router(voiceover.router, prefix="/api/voiceover", tags=["AI 配音"])
app.include_router(admin_auth.router, prefix="/api/admin/auth", tags=["运营后台鉴权"])
app.include_router(admin_dashboard.router, prefix="/api/admin/dashboard", tags=["运营后台工作台"])
app.include_router(admin_search.router, prefix="/api/admin/search", tags=["运营后台搜索"])
app.include_router(admin_users.router, prefix="/api/admin/users", tags=["运营后台用户"])
app.include_router(admin_jobs.router, prefix="/api/admin/jobs", tags=["运营后台任务"])
app.include_router(admin_billing.router, prefix="/api/admin", tags=["运营后台交易"])
app.include_router(admin_audit_logs.router, prefix="/api/admin/audit-logs", tags=["运营后台审计"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "3.0.0"}


@app.get("/api/health/live")
async def health_live():
    return {"status": "ok", "version": "3.0.0"}


@app.get("/api/health/ready")
async def health_ready():
    ready, checks = await _readiness_status()
    payload = {
        "status": "ready" if ready else "unavailable",
        "version": "3.0.0",
        "checks": checks,
    }
    if not ready:
        return JSONResponse(status_code=503, content=payload)
    return payload

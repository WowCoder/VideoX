"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from app.middleware.security import RateLimitMiddleware

from app.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理。"""
    # 启动
    yield
    # 关闭
    from app.database import engine
    await engine.dispose()


app = FastAPI(
    title="OpenVMA API",
    description="把脚本和素材交给 AI，几分钟得到一版可改的初剪。",
    version="3.0.0",
    lifespan=lifespan,
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
from app.api import auth, projects, scripts, assets, jobs, generate, ws, billing, notifications, search, collaboration  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["鉴权"])
app.include_router(projects.router, prefix="/api/projects", tags=["项目"])
app.include_router(scripts.router, prefix="/api/scripts", tags=["脚本"])
app.include_router(assets.router, prefix="/api/assets", tags=["素材"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["任务"])
app.include_router(generate.router, prefix="/api/generate", tags=["AI 生成"])
app.include_router(ws.router, prefix="/api/ws", tags=["WebSocket"])
app.include_router(billing.router, prefix="/api/billing", tags=["会员与支付"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["站内通知"])
app.include_router(search.router, prefix="/api/search", tags=["全局搜索"])
app.include_router(collaboration.router, prefix="/api/projects", tags=["项目协作"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "3.0.0"}

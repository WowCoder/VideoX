"""运营后台工作台的真实指标、待办和基础设施状态。"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.dependencies import AdminPrincipal, require_admin_permission
from app.admin.audit import write_admin_audit
from app.config import get_settings
from app.database import get_db
from app.models.inspiration import InspirationSource
from app.models.invoice import Invoice
from app.models.job import Job
from app.models.order import Order
from app.models.subscription import Subscription
from app.models.monitoring import SystemMetricSnapshot, UserDailyActivity
from app.models.user import User
from app.services.system_metrics import collect_and_store_system_metrics


router = APIRouter()
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _today_utc_range() -> tuple[datetime, datetime]:
    local_now = datetime.now(SHANGHAI)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(timezone.utc), (local_start + timedelta(days=1)).astimezone(timezone.utc)


def _local_activity_range() -> tuple[date, date]:
    local_today = datetime.now(SHANGHAI).date()
    return local_today, local_today.replace(day=1)


def _serialize_system_metric(snapshot: SystemMetricSnapshot | None) -> dict | None:
    if snapshot is None:
        return None
    cpu_count = snapshot.cpu_count or 0
    normalized_load = (
        round((snapshot.load_5m or 0) * 100 / cpu_count, 2) if cpu_count else None
    )
    return {
        "id": snapshot.id,
        "node_name": snapshot.node_name,
        "metric_scope": snapshot.metric_scope,
        "collection_source": snapshot.collection_source,
        "collection_status": snapshot.collection_status,
        "load_1m": snapshot.load_1m,
        "load_5m": snapshot.load_5m,
        "load_15m": snapshot.load_15m,
        "normalized_load_percent": normalized_load,
        "cpu_count": snapshot.cpu_count,
        "memory_total_bytes": snapshot.memory_total_bytes,
        "memory_used_bytes": snapshot.memory_used_bytes,
        "memory_percent": snapshot.memory_percent,
        "disk_total_bytes": snapshot.disk_total_bytes,
        "disk_used_bytes": snapshot.disk_used_bytes,
        "disk_free_bytes": snapshot.disk_free_bytes,
        "disk_percent": snapshot.disk_percent,
        "uptime_seconds": snapshot.uptime_seconds,
        "error_message": snapshot.error_message,
        "collected_at": snapshot.collected_at,
    }


@router.get("/summary")
async def summary(
    _: AdminPrincipal = Depends(require_admin_permission("dashboard.read")),
    db: AsyncSession = Depends(get_db),
):
    start, end = _today_utc_range()
    local_today, local_month_start = _local_activity_range()
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    daily_active_users = (
        await db.execute(
            select(func.count(func.distinct(UserDailyActivity.user_id))).where(
                UserDailyActivity.activity_date == local_today
            )
        )
    ).scalar() or 0
    monthly_active_users = (
        await db.execute(
            select(func.count(func.distinct(UserDailyActivity.user_id))).where(
                UserDailyActivity.activity_date >= local_month_start,
                UserDailyActivity.activity_date <= local_today,
            )
        )
    ).scalar() or 0
    activity_collection_started_at = (
        await db.execute(select(func.min(UserDailyActivity.created_at)))
    ).scalar_one_or_none()
    new_users = (
        await db.execute(select(func.count(User.id)).where(User.created_at >= start, User.created_at < end))
    ).scalar() or 0
    paid_amount = (
        await db.execute(
            select(func.coalesce(func.sum(Order.amount), 0.0)).where(
                Order.status == "paid", Order.paid_at >= start, Order.paid_at < end
            )
        )
    ).scalar() or 0.0
    failed_jobs = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.status == "FAILED", Job.updated_at >= start, Job.updated_at < end
            )
        )
    ).scalar() or 0
    requested_invoices = (
        await db.execute(select(func.count(Invoice.id)).where(Invoice.status == "requested"))
    ).scalar() or 0
    return {
        "period": {"start": start, "end": end, "time_zone": "Asia/Shanghai"},
        "total_users": int(total_users),
        "daily_active_users": int(daily_active_users),
        "monthly_active_users": int(monthly_active_users),
        "activity_collection_started_at": activity_collection_started_at,
        "new_users": int(new_users),
        "paid_amount": float(paid_amount),
        "failed_jobs": int(failed_jobs),
        "requested_invoices": int(requested_invoices),
    }


@router.get("/alerts")
async def alerts(
    _: AdminPrincipal = Depends(require_admin_permission("dashboard.read")),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    queued_stale = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.status == "QUEUED", Job.updated_at < now - timedelta(minutes=30)
            )
        )
    ).scalar() or 0
    running_stale = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.status == "RUNNING", Job.updated_at < now - timedelta(minutes=75)
            )
        )
    ).scalar() or 0
    latest_paid = (
        select(Order.user_id, func.max(Order.paid_at).label("latest_paid_at"))
        .where(Order.status == "paid", Order.paid_at.is_not(None))
        .group_by(Order.user_id)
        .subquery()
    )
    payment_mismatches = (
        await db.execute(
            select(func.count(Order.id))
            .join(
                latest_paid,
                and_(Order.user_id == latest_paid.c.user_id, Order.paid_at == latest_paid.c.latest_paid_at),
            )
            .outerjoin(Subscription, Subscription.user_id == Order.user_id)
            .where(
                or_(
                    Subscription.id.is_(None),
                    Subscription.membership_id != Order.membership_id,
                    Subscription.latest_order_id.is_(None),
                    Subscription.latest_order_id != Order.id,
                )
            )
        )
    ).scalar() or 0
    source_failures = (
        await db.execute(
            select(func.count(InspirationSource.id)).where(
                InspirationSource.enabled.is_(True),
                InspirationSource.consecutive_failures >= 3,
            )
        )
    ).scalar() or 0
    requested_invoices = (
        await db.execute(select(func.count(Invoice.id)).where(Invoice.status == "requested"))
    ).scalar() or 0
    return {
        "items": [
            {"code": "queued_stale", "label": "排队超时任务", "count": int(queued_stale), "severity": "critical"},
            {"code": "running_stale", "label": "运行超时任务", "count": int(running_stale), "severity": "critical"},
            {"code": "payment_mismatch", "label": "已支付但订阅不一致", "count": int(payment_mismatches), "severity": "critical"},
            {"code": "inspiration_source_failure", "label": "灵感来源连续失败", "count": int(source_failures), "severity": "warning"},
            {"code": "requested_invoice", "label": "待处理发票", "count": int(requested_invoices), "severity": "warning"},
        ]
    }


@router.get("/health")
async def health(_: AdminPrincipal = Depends(require_admin_permission("dashboard.read"))):
    from app.main import _readiness_status
    from app.config import get_settings
    import redis.asyncio as aioredis

    ready, checks = await _readiness_status()
    worker_count = 0
    beat_dispatch = False
    client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        async for _key in client.scan_iter(match="videox:heartbeat:worker:*"):
            worker_count += 1
        beat_dispatch = bool(await client.get("videox:heartbeat:beat-dispatch"))
    except Exception:
        checks["celery_worker"] = "unknown"
        checks["celery_beat"] = "unknown"
    else:
        checks["celery_worker"] = "ok" if worker_count else "unavailable"
        checks["celery_beat"] = "ok" if beat_dispatch else "unavailable"
        ready = ready and worker_count > 0 and beat_dispatch
    finally:
        await client.aclose()
    return {
        "status": "ready" if ready else "unavailable",
        "checks": checks,
        "worker_count": worker_count,
    }


@router.get("/system-metrics")
async def system_metrics(
    _: AdminPrincipal = Depends(require_admin_permission("dashboard.read")),
    db: AsyncSession = Depends(get_db),
):
    latest_attempt = (
        await db.execute(
            select(SystemMetricSnapshot).order_by(SystemMetricSnapshot.collected_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    latest_success = (
        await db.execute(
            select(SystemMetricSnapshot)
            .where(SystemMetricSnapshot.collection_status == "succeeded")
            .order_by(SystemMetricSnapshot.collected_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    stale = bool(
        latest_success
        and latest_success.collected_at.astimezone(timezone.utc) < now - timedelta(hours=2)
    )
    return {
        "status": "unavailable" if latest_success is None else "stale" if stale else "ok",
        "latest": _serialize_system_metric(latest_success),
        "latest_attempt": _serialize_system_metric(latest_attempt),
        "stale": stale,
    }


@router.post("/system-metrics/refresh")
async def refresh_system_metrics(
    request: Request,
    principal: AdminPrincipal = Depends(require_admin_permission("dashboard.read")),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    if not settings.system_metrics_enabled:
        raise HTTPException(status_code=503, detail="服务器资源采集未启用")
    now = datetime.now(timezone.utc)
    latest_manual = (
        await db.execute(
            select(SystemMetricSnapshot)
            .where(SystemMetricSnapshot.collection_source == "manual")
            .order_by(SystemMetricSnapshot.collected_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if (
        latest_manual
        and latest_manual.collected_at.astimezone(timezone.utc)
        > now - timedelta(seconds=settings.system_metrics_manual_min_interval_seconds)
    ):
        raise HTTPException(
            status_code=429,
            detail=f"服务器指标手动刷新间隔至少为 {settings.system_metrics_manual_min_interval_seconds} 秒",
        )
    snapshot = await collect_and_store_system_metrics(db, source="manual")
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="SYSTEM_METRICS_REFRESH",
        target_type="system_node",
        target_id=snapshot.node_name,
        reason="管理员手动刷新服务器资源指标",
        after_data={
            "collection_status": snapshot.collection_status,
            "metric_scope": snapshot.metric_scope,
            "collected_at": snapshot.collected_at.isoformat(),
        },
        status="succeeded" if snapshot.collection_status == "succeeded" else "failed",
        error_message=snapshot.error_message,
    )
    return _serialize_system_metric(snapshot)

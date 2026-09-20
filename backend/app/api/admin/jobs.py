"""运营后台全局任务查询与敏感 Payload 查看。"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import reserve_admin_command_audit, write_admin_audit
from app.admin.dependencies import AdminPrincipal, require_admin_permission
from app.admin.redaction import mask_email, redact_mapping
from app.admin.schemas import ReasonRequest
from app.database import get_db
from app.models.inspiration import InspirationRun
from app.models.admin import AdminAuditLog
from app.models.job import Job
from app.models.user import User, UserIdentity
from app.services.job_commands import cancel_job_command, retry_job_command


router = APIRouter()


def _payload_summary(payload: dict) -> dict:
    allowed = {
        key: value for key, value in (payload or {}).items()
        if key.endswith("_id") or key.endswith("_ids") or key in {
            "format", "resolution", "aspect_ratio", "base_revision", "style", "duration_seconds"
        }
    }
    return redact_mapping(allowed)


@router.get("")
async def list_jobs(
    q: str = Query("", max_length=200),
    owner_id: str = Query(""),
    project_id: str = Query(""),
    job_type: str = Query("", alias="type"),
    status_filter: str = Query("", alias="status"),
    quota_type: str = Query(""),
    is_stale: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("created_desc", pattern="^(created_desc|created_asc|updated_desc|updated_asc)$"),
    _: AdminPrincipal = Depends(require_admin_permission("jobs.read")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Job, User).join(User, User.id == Job.owner_id)
    if q.strip():
        term = q.strip()
        prefix = f"{term}%"
        query = query.where(
            or_(
                Job.id == term,
                Job.celery_task_id == term,
                Job.project_id == term,
                User.id == term,
                User.email.ilike(prefix),
                User.id.in_(select(UserIdentity.user_id).where(UserIdentity.identifier.ilike(prefix))),
            )
        )
    if owner_id:
        query = query.where(Job.owner_id == owner_id)
    if project_id:
        query = query.where(Job.project_id == project_id)
    if job_type:
        query = query.where(Job.type == job_type)
    if status_filter:
        query = query.where(Job.status == status_filter)
    if quota_type:
        query = query.where(Job.quota_type == quota_type)
    if is_stale:
        now = datetime.now(timezone.utc)
        query = query.where(
            or_(
                (Job.status == "QUEUED") & (Job.updated_at < now - timedelta(minutes=30)),
                (Job.status == "RUNNING") & (Job.updated_at < now - timedelta(minutes=75)),
            )
        )
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    orderings = {
        "created_desc": Job.created_at.desc(),
        "created_asc": Job.created_at.asc(),
        "updated_desc": Job.updated_at.desc(),
        "updated_asc": Job.updated_at.asc(),
    }
    rows = (
        await db.execute(
            query.order_by(orderings[sort]).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return {
        "items": [
            {
                "id": job.id,
                "name": job.name,
                "type": job.type,
                "status": job.status,
                "stage": job.stage,
                "progress": job.progress,
                "owner": {"id": user.id, "name": user.name, "email": mask_email(user.email)},
                "project_id": job.project_id,
                "subject_type": job.subject_type,
                "subject_id": job.subject_id,
                "quota_type": job.quota_type,
                "quota_amount": job.quota_amount,
                "billing_quote_id": job.billing_quote_id,
                "billing_hold_id": job.billing_hold_id,
                "quoted_credits": job.quoted_credits,
                "billed_credits": job.billed_credits,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
            }
            for job, user in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "sort": sort,
    }


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    _: AdminPrincipal = Depends(require_admin_permission("jobs.read")),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(select(Job, User).join(User, User.id == Job.owner_id).where(Job.id == job_id))
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    job, user = row
    inspiration_run = None
    if job.subject_type == "inspiration_run" or job.type == "灵感岛任务":
        inspiration_run = (
            await db.execute(select(InspirationRun).where(InspirationRun.job_id == job.id))
        ).scalar_one_or_none()
    return {
        "id": job.id,
        "name": job.name,
        "type": job.type,
        "status": job.status,
        "stage": job.stage,
        "stages": job.stages,
        "stage_index": job.stage_index,
        "progress": job.progress,
        "detail": job.detail,
        "eta": job.eta,
        "logs": redact_mapping(job.logs),
        "result": job.result,
        "result_detail": job.result_detail,
        "result_path_exists": bool(job.result_path),
        "payload_summary": _payload_summary(job.payload or {}),
        "owner": {"id": user.id, "name": user.name, "email": mask_email(user.email)},
        "project_id": job.project_id,
        "subject_type": job.subject_type,
        "subject_id": job.subject_id,
        "quota_type": job.quota_type,
        "quota_amount": job.quota_amount,
        "billing_quote_id": job.billing_quote_id,
        "billing_hold_id": job.billing_hold_id,
        "quoted_credits": job.quoted_credits,
        "billed_credits": job.billed_credits,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "celery_task_id": job.celery_task_id,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error_code": job.error_code,
        "error_category": job.error_category,
        "provider": job.provider,
        "model": job.model,
        "provider_request_id": job.provider_request_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "inspiration_run": {
            "id": inspiration_run.id,
            "status": inspiration_run.status,
            "outcome": inspiration_run.outcome,
            "metrics": inspiration_run.metrics,
            "error": inspiration_run.error,
        } if inspiration_run else None,
    }


@router.post("/{job_id}/reveal-payload")
async def reveal_payload(
    job_id: str,
    payload: ReasonRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_admin_permission("jobs.payload.read")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    await write_admin_audit(
        db,
        admin=principal.user,
        request=request,
        action="JOB_PAYLOAD_REVEAL",
        target_type="job",
        target_id=job.id,
        reason=payload.reason,
        after_data={"payload_keys": sorted((job.payload or {}).keys())},
    )
    return {"job_id": job.id, "payload": redact_mapping(job.payload or {})}


def _job_command_snapshot(job: Job) -> dict:
    return {
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "attempts": job.attempts,
        "celery_task_id": job.celery_task_id,
        "quota_type": job.quota_type,
        "quota_amount": job.quota_amount,
    }


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: str,
    payload: ReasonRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
    principal: AdminPrincipal = Depends(require_admin_permission("jobs.retry")),
    db: AsyncSession = Depends(get_db),
):
    audit, is_replay = await reserve_admin_command_audit(
        db, admin=principal.user, request=request, action="JOB_RETRY",
        target_type="job", target_id=job_id, reason=payload.reason,
        idempotency_key=idempotency_key,
    )
    if is_replay:
        if audit.status != "succeeded":
            raise HTTPException(status_code=409, detail="该幂等请求此前执行失败，请使用新的幂等键重试")
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"job": _job_command_snapshot(job), "idempotent_replay": True}
    job = (
        await db.execute(select(Job).where(Job.id == job_id).with_for_update())
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    before = _job_command_snapshot(job)
    audit.before_data = before
    audit_id = audit.id
    try:
        job = await retry_job_command(db, job)
    except HTTPException as exc:
        await db.rollback()
        persisted = await db.get(AdminAuditLog, audit_id)
        if persisted is None:
            persisted = await write_admin_audit(
                db, admin=principal.user, request=request, action="JOB_RETRY",
                target_type="job", target_id=job_id, reason=payload.reason,
                before_data=before, idempotency_key=idempotency_key, status="failed",
                error_message=str(exc.detail),
            )
        else:
            persisted.status = "failed"
            persisted.error_message = str(exc.detail)[:2000]
        await db.commit()
        raise
    after = _job_command_snapshot(job)
    persisted = await db.get(AdminAuditLog, audit_id)
    persisted.status = "succeeded"
    persisted.before_data = before
    persisted.after_data = after
    await db.commit()
    return {"job": after, "idempotent_replay": False}


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    payload: ReasonRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
    principal: AdminPrincipal = Depends(require_admin_permission("jobs.cancel")),
    db: AsyncSession = Depends(get_db),
):
    audit, is_replay = await reserve_admin_command_audit(
        db, admin=principal.user, request=request, action="JOB_CANCEL",
        target_type="job", target_id=job_id, reason=payload.reason,
        idempotency_key=idempotency_key,
    )
    if is_replay:
        if audit.status != "succeeded":
            raise HTTPException(status_code=409, detail="该幂等请求此前执行失败，请使用新的幂等键重试")
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"job": _job_command_snapshot(job), "idempotent_replay": True}
    job = (
        await db.execute(select(Job).where(Job.id == job_id).with_for_update())
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    before = _job_command_snapshot(job)
    audit.before_data = before
    audit_id = audit.id
    try:
        job = await cancel_job_command(db, job, actor_label="运营管理员")
    except HTTPException as exc:
        await db.rollback()
        persisted = await db.get(AdminAuditLog, audit_id)
        if persisted is None:
            persisted = await write_admin_audit(
                db, admin=principal.user, request=request, action="JOB_CANCEL",
                target_type="job", target_id=job_id, reason=payload.reason,
                before_data=before, idempotency_key=idempotency_key, status="failed",
                error_message=str(exc.detail),
            )
        else:
            persisted.status = "failed"
            persisted.error_message = str(exc.detail)[:2000]
        await db.commit()
        raise
    after = _job_command_snapshot(job)
    persisted = await db.get(AdminAuditLog, audit_id)
    persisted.status = "succeeded"
    persisted.before_data = before
    persisted.after_data = after
    await db.commit()
    return {"job": after, "idempotent_replay": False}

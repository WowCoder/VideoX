"""运营后台跨对象快速搜索。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.dependencies import AdminPrincipal, require_admin_permission
from app.admin.redaction import mask_email
from app.database import get_db
from app.models.asset import Asset
from app.models.inspiration import InspirationRun, InspirationTask
from app.models.invoice import Invoice
from app.models.job import Job
from app.models.order import Order
from app.models.project import Project
from app.models.user import User, UserIdentity


router = APIRouter()


@router.get("")
async def global_search(
    q: str = Query(..., min_length=2, max_length=200),
    _: AdminPrincipal = Depends(require_admin_permission("users.read")),
    db: AsyncSession = Depends(get_db),
):
    term = q.strip()
    prefix = f"{term}%"
    users = (
        await db.execute(
            select(User)
            .where(
                or_(
                    User.id == term,
                    User.name.ilike(prefix),
                    User.email.ilike(prefix),
                    User.id.in_(
                        select(UserIdentity.user_id).where(UserIdentity.identifier.ilike(prefix))
                    ),
                )
            )
            .order_by(User.created_at.desc())
            .limit(5)
        )
    ).scalars().all()
    jobs = (
        await db.execute(
            select(Job)
            .where(or_(Job.id == term, Job.celery_task_id == term, Job.project_id == term))
            .order_by(Job.created_at.desc())
            .limit(5)
        )
    ).scalars().all()
    projects = (
        await db.execute(
            select(Project)
            .where(or_(Project.id == term, Project.name.ilike(prefix)))
            .order_by(Project.updated_at.desc())
            .limit(5)
        )
    ).scalars().all()
    assets = (
        await db.execute(
            select(Asset)
            .where(or_(Asset.id == term, Asset.name.ilike(prefix)))
            .order_by(Asset.created_at.desc())
            .limit(5)
        )
    ).scalars().all()
    orders = (
        await db.execute(select(Order).where(Order.id == term).limit(5))
    ).scalars().all()
    invoices = (
        await db.execute(select(Invoice).where(Invoice.id == term).limit(5))
    ).scalars().all()
    inspiration_tasks = (
        await db.execute(
            select(InspirationTask)
            .where(or_(InspirationTask.id == term, InspirationTask.name.ilike(prefix)))
            .limit(5)
        )
    ).scalars().all()
    inspiration_runs = (
        await db.execute(
            select(InspirationRun).where(or_(InspirationRun.id == term, InspirationRun.job_id == term)).limit(5)
        )
    ).scalars().all()
    return {
        "users": [
            {"id": item.id, "name": item.name, "email": mask_email(item.email), "type": "user"}
            for item in users
        ],
        "jobs": [
            {"id": item.id, "name": item.name, "status": item.status, "job_type": item.type, "type": "job"}
            for item in jobs
        ],
        "projects": [{"id": item.id, "name": item.name, "status": item.status, "type": "project"} for item in projects],
        "assets": [{"id": item.id, "name": item.name, "status": item.processing_status, "type": "asset"} for item in assets],
        "orders": [{"id": item.id, "name": item.membership_name, "status": item.status, "type": "order"} for item in orders],
        "invoices": [{"id": item.id, "name": item.company_name, "status": item.status, "type": "invoice"} for item in invoices],
        "inspiration_tasks": [{"id": item.id, "name": item.name, "status": "enabled" if item.enabled else "disabled", "type": "inspiration_task"} for item in inspiration_tasks],
        "inspiration_runs": [{"id": item.id, "name": item.task_id, "status": item.status, "type": "inspiration_run"} for item in inspiration_runs],
    }

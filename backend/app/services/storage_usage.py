"""按实际仍占用对象存储的全局素材同步用户存储用量。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.user import Usage


async def recalculate_storage_usage(db: AsyncSession, user_id: str) -> float:
    """回收站素材仍占物理空间，只有永久删除后才释放额度。"""
    total = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Asset.file_size_mb), 0.0)).where(
                    Asset.owner_id == user_id
                )
            )
        ).scalar()
        or 0.0
    )
    usage = (
        await db.execute(select(Usage).where(Usage.user_id == user_id))
    ).scalar_one_or_none()
    if usage is None:
        usage = Usage(user_id=user_id)
        db.add(usage)
    usage.storage_used_mb = round(total, 2)
    return usage.storage_used_mb

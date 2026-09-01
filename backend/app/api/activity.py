"""显式用户活动心跳，避免把后台轮询误算为活跃。"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.monitoring import UserDailyActivity
from app.models.user import User


router = APIRouter()
SHANGHAI = ZoneInfo("Asia/Shanghai")
HEARTBEAT_WRITE_INTERVAL = timedelta(minutes=15)


@router.post("/heartbeat")
async def heartbeat(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    activity_date = now.astimezone(SHANGHAI).date()
    statement = (
        insert(UserDailyActivity)
        .values(
            user_id=user.id,
            activity_date=activity_date,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[UserDailyActivity.user_id, UserDailyActivity.activity_date],
            set_={"last_seen_at": now, "updated_at": now},
            where=UserDailyActivity.last_seen_at <= now - HEARTBEAT_WRITE_INTERVAL,
        )
        .returning(UserDailyActivity.id)
    )
    activity_id = (await db.execute(statement)).scalar_one_or_none()
    return {
        "activity_date": activity_date,
        "recorded": activity_id is not None,
        "next_write_after_seconds": int(HEARTBEAT_WRITE_INTERVAL.total_seconds()),
    }

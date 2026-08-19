"""灵感任务的唯一调度计算规则。"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.schemas.inspiration import InspirationSchedule


def next_inspiration_run(
    schedule: InspirationSchedule | dict,
    after: datetime | None = None,
) -> datetime | None:
    resolved = schedule if isinstance(schedule, InspirationSchedule) else InspirationSchedule.model_validate(schedule)
    if resolved.type == "manual":
        return None

    current = after or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_zone = ZoneInfo(resolved.time_zone)
    local_now = current.astimezone(local_zone)
    hour, minute = (int(part) for part in resolved.time.split(":", 1))
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if resolved.type == "daily":
        if candidate <= local_now:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)

    # 产品契约沿用浏览器 weekday：周日=0，周一=1 ... 周六=6。
    target_python_weekday = (resolved.weekday + 6) % 7
    days_ahead = (target_python_weekday - local_now.weekday()) % 7
    candidate += timedelta(days=days_ahead)
    if candidate <= local_now:
        candidate += timedelta(days=7)
    return candidate.astimezone(timezone.utc)

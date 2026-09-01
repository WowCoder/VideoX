"""低频系统资源采集与快照持久化。"""

import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.monitoring import SystemMetricSnapshot


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cpu_count() -> int:
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def _cgroup_memory_limit_bytes() -> int | None:
    """容器内优先读取 cgroup v2/v1 的真实内存上限。"""

    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            raw = Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if raw == "max" or not raw.isdigit():
            continue
        value = int(raw)
        # 极大的 v1 哨兵值等同于未限制。
        if 0 < value < 1 << 60:
            return value
    return None


def _memory_usage(meminfo_path: str = "/proc/meminfo") -> tuple[int, int, float]:
    values: dict[str, int] = {}
    with open(meminfo_path, encoding="utf-8") as handle:
        for line in handle:
            key, separator, raw_value = line.partition(":")
            if not separator:
                continue
            amount = raw_value.strip().split()[0]
            if amount.isdigit():
                values[key] = int(amount) * 1024
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    if total <= 0:
        raise RuntimeError("无法读取服务器内存容量")
    used = max(0, total - min(total, available))
    return total, used, round(used * 100 / total, 2)


def _uptime_seconds(uptime_path: str = "/proc/uptime") -> int:
    with open(uptime_path, encoding="utf-8") as handle:
        return max(0, int(float(handle.read().split()[0])))


def collect_system_metrics(
    *,
    disk_path: str,
    metric_scope: str,
    meminfo_path: str = "/proc/meminfo",
    uptime_path: str = "/proc/uptime",
) -> dict[str, Any]:
    """读取一次资源状态；不执行命令、不访问 Docker Socket。"""

    target = Path(disk_path)
    if not target.exists() or not target.is_dir():
        raise RuntimeError(f"服务器磁盘监控目录不可用：{disk_path}")
    load_1m, load_5m, load_15m = os.getloadavg()
    cpu_count = _cpu_count()
    memory_total, memory_used, memory_percent = _memory_usage(meminfo_path)
    if metric_scope == "container":
        memory_limit = _cgroup_memory_limit_bytes()
        if memory_limit and memory_limit < memory_total:
            memory_total = memory_limit
            memory_used = min(memory_used, memory_total)
            memory_percent = round(memory_used * 100 / memory_total, 2)
    disk = shutil.disk_usage(target)
    disk_percent = round(disk.used * 100 / disk.total, 2) if disk.total else 0.0
    return {
        "metric_scope": metric_scope,
        "load_1m": round(load_1m, 3),
        "load_5m": round(load_5m, 3),
        "load_15m": round(load_15m, 3),
        "cpu_count": cpu_count,
        "memory_total_bytes": memory_total,
        "memory_used_bytes": memory_used,
        "memory_percent": memory_percent,
        "disk_total_bytes": disk.total,
        "disk_used_bytes": disk.used,
        "disk_free_bytes": disk.free,
        "disk_percent": disk_percent,
        "uptime_seconds": _uptime_seconds(uptime_path),
    }


async def collect_and_store_system_metrics(
    db: AsyncSession,
    *,
    source: str,
) -> SystemMetricSnapshot:
    settings = get_settings()
    now = _utcnow()
    common = {
        "node_name": settings.system_metrics_node_name,
        "collection_source": source,
        "collected_at": now,
    }
    try:
        values = collect_system_metrics(
            disk_path=settings.system_metrics_disk_path,
            metric_scope=settings.system_metrics_scope,
        )
        snapshot = SystemMetricSnapshot(
            **common,
            **values,
            collection_status="succeeded",
            error_message="",
        )
    except Exception as error:
        snapshot = SystemMetricSnapshot(
            **common,
            metric_scope=settings.system_metrics_scope,
            collection_status="failed",
            error_message=str(error)[:2000],
        )
    db.add(snapshot)
    retention_start = now - timedelta(days=max(1, settings.system_metrics_retention_days))
    await db.execute(
        delete(SystemMetricSnapshot).where(SystemMetricSnapshot.collected_at < retention_start)
    )
    await db.flush()
    return snapshot

"""WebSocket 路由：任务状态实时推送。"""

import asyncio
import contextlib
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """允许同一账号同时保持多个浏览器标签页或设备连接。"""

    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = {}

    def connect(self, websocket: WebSocket, user_id: str) -> None:
        self.active_connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        connections = self.active_connections.get(user_id)
        if not connections:
            return
        connections.discard(websocket)
        if not connections:
            self.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        connections = tuple(self.active_connections.get(user_id, ()))
        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket, user_id)


manager = ConnectionManager()
_subscriber_task: asyncio.Task | None = None


async def _load_job_message(job_id: str) -> dict | None:
    """从数据库读取完整 Job，确保 WebSocket 与 REST 返回结构一致。"""
    from app.database import async_session_factory
    from app.models.job import Job
    from app.schemas.job import JobOut

    async with async_session_factory() as session:
        job = await session.get(Job, job_id)
        if not job:
            return None
        return {
            "type": "job_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "job": JobOut.model_validate(job).model_dump(mode="json"),
        }


def _user_id_from_channel(channel: str) -> str | None:
    prefix = "ws:job_updates:"
    if not channel.startswith(prefix):
        return None
    user_id = channel[len(prefix):].strip()
    return user_id or None


async def _job_update_subscriber() -> None:
    """订阅 Worker 发布的任务更新；Redis 故障时指数退避后重连。"""
    import redis.asyncio as aioredis

    retry_delay = 1.0
    while True:
        client = None
        pubsub = None
        try:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.psubscribe("ws:job_updates:*")
            retry_delay = 1.0

            async for event in pubsub.listen():
                if event.get("type") != "pmessage":
                    continue
                user_id = _user_id_from_channel(str(event.get("channel") or ""))
                if not user_id:
                    continue
                try:
                    payload = json.loads(event.get("data") or "{}")
                except (TypeError, json.JSONDecodeError):
                    logger.warning("Ignoring invalid WebSocket job update payload")
                    continue
                job_id = str(payload.get("job_id") or "").strip()
                if not job_id:
                    continue
                message = await _load_job_message(job_id)
                if message:
                    await manager.send_to_user(user_id, message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "WebSocket Redis subscriber disconnected; retrying in %.1fs: %s",
                retry_delay,
                exc,
            )
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30.0)
        finally:
            if pubsub is not None:
                with contextlib.suppress(Exception):
                    await pubsub.aclose()
            if client is not None:
                with contextlib.suppress(Exception):
                    await client.aclose()


async def start_job_update_subscriber() -> None:
    global _subscriber_task
    if _subscriber_task is None or _subscriber_task.done():
        _subscriber_task = asyncio.create_task(
            _job_update_subscriber(),
            name="openvma-job-update-subscriber",
        )


async def stop_job_update_subscriber() -> None:
    global _subscriber_task
    if _subscriber_task is None:
        return
    _subscriber_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _subscriber_task
    _subscriber_task = None


@router.websocket("/jobs")
async def ws_jobs(websocket: WebSocket):
    """认证后推送当前用户的完整任务状态。"""
    await websocket.accept()
    user_id: str | None = None

    try:
        auth_msg = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        auth_data = json.loads(auth_msg)
        token = (
            auth_data.get("token", "")
            if isinstance(auth_data, dict) and auth_data.get("type") == "auth"
            else ""
        )

        from app.security import decode_token

        payload = decode_token(token)
        token_user_id = payload.get("sub") if payload else None
        if not payload or payload.get("type") != "access" or not isinstance(token_user_id, str):
            await websocket.send_json({"type": "auth_failed", "detail": "认证失败"})
            await websocket.close(code=1008)
            return

        user_id = token_user_id
        manager.connect(websocket, user_id)
        await websocket.send_json({"type": "auth_ok"})

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "ping"})
                continue
            with contextlib.suppress(json.JSONDecodeError):
                message = json.loads(data)
                if isinstance(message, dict) and message.get("type") == "ping":
                    await websocket.send_json({"type": "ping"})
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "auth_failed", "detail": "认证超时"})
            await websocket.close(code=1008)
    except (json.JSONDecodeError, WebSocketDisconnect):
        pass
    finally:
        if user_id:
            manager.disconnect(websocket, user_id)


async def broadcast_job_update(user_id: str, job_data: dict) -> None:
    """供 API 进程内更新调用；当前 Worker 更新通过 Redis Pub/Sub 进入。"""
    job_id = str(job_data.get("job_id") or "")
    message = await _load_job_message(job_id) if job_id else None
    if message:
        await manager.send_to_user(user_id, message)

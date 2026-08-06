"""WebSocket 路由：任务状态实时推送。"""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app

router = APIRouter()


class ConnectionManager:
    """WebSocket 连接管理器。"""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}  # user_id -> WebSocket

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict):
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(user_id)


manager = ConnectionManager()


@router.websocket("/jobs")
async def ws_jobs(websocket: WebSocket):
    """任务状态 WebSocket。

    客户端连接时发送 JWT token 进行认证。
    服务端推送任务状态变更消息。

    消息格式：
    {
        "type": "job_update",
        "job_id": "...",
        "status": "RUNNING",
        "progress": 45,
        "stage": "语音转写(ASR)",
        "detail": "..."
    }
    """
    await websocket.accept()
    user_id: str | None = None

    # 简单认证：等待客户端发送 token
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        auth_data = json.loads(auth_msg)
        token = auth_data.get("token", "")

        from app.security import decode_token
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            await websocket.send_json({"type": "error", "message": "认证失败"})
            await websocket.close()
            return

        user_id = payload.get("sub")
        manager.active_connections[user_id] = websocket

        await websocket.send_json({"type": "connected", "message": "WebSocket 已连接"})

        # 保持连接，等待推送
        while True:
            try:
                data = await websocket.receive_text()
                # 处理心跳
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break

    except (asyncio.TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
        pass
    finally:
        if user_id:
            manager.disconnect(user_id)


async def broadcast_job_update(user_id: str, job_data: dict):
    """广播任务状态更新（供 Celery 任务调用）。"""
    await manager.send_to_user(user_id, {
        "type": "job_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **job_data,
    })

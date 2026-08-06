"""Celery 同步任务中安全运行异步数据库代码。"""

import asyncio
from collections.abc import Coroutine
from typing import Any


def run_async(coro: Coroutine[Any, Any, Any]):
    """每个任务使用独立事件循环，并在关闭前释放异步连接池。

    Celery prefork 子进程会连续执行多个任务。若事件循环关闭后仍保留 asyncpg
    连接，下一任务会复用绑定到旧循环的 Future，导致任务卡在 RUNNING。
    """

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        from app.database import engine

        try:
            loop.run_until_complete(engine.dispose())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


"""会员订阅到期维护任务。"""

from app.database import async_session_factory
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app
from app.services.subscriptions import expire_due_subscriptions


@celery_app.task(name="app.tasks.expire_due_subscriptions")
def expire_due_subscriptions_task() -> int:
    """定时降级已经过期的付费会员；内部和永久会员不受影响。"""

    async def _expire() -> int:
        async with async_session_factory() as session:
            count = await expire_due_subscriptions(session)
            await session.commit()
            return count

    return run_async(_expire())

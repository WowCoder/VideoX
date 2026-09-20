"""会员订阅到期维护任务。"""

from app.database import async_session_factory
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app
from app.services.subscriptions import expire_due_subscriptions
from app.services.billing_v2 import grant_due_subscription_credits


@celery_app.task(name="app.tasks.expire_due_subscriptions")
def expire_due_subscriptions_task() -> int:
    """定时降级已经过期的付费会员；内部和永久会员不受影响。"""

    async def _expire() -> int:
        async with async_session_factory() as session:
            count = await expire_due_subscriptions(session)
            await session.commit()
            return count

    return run_async(_expire())


@celery_app.task(name="app.tasks.grant_due_subscription_credits")
def grant_due_subscription_credits_task() -> int:
    """按月补发月付/年付订阅积分，确保年付不会一次性发放 12 个月。"""

    async def _grant() -> int:
        async with async_session_factory() as session:
            count = await grant_due_subscription_credits(session)
            await session.commit()
            return count

    return run_async(_grant())

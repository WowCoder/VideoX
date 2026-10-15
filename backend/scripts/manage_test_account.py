"""开发/测试环境账号管理工具。

示例（在 backend 目录执行）：
    python scripts/manage_test_account.py create \
        --email test@example.com --password 'TestPassword123!' --name '测试账号'
    python scripts/manage_test_account.py reset-ai-usage --email test@example.com

脚本在生产环境中始终拒绝执行。Makefile 通过环境变量传递密码，避免把密码
打印到终端或放入 Docker exec 的命令参数。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.models.job import Job  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.user import Membership, Usage, User, UserIdentity  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services.auth_identities import EMAIL_PROVIDER  # noqa: E402


FREE_MEMBERSHIP_ID = "membership-free"
PENDING_STATUSES = ("QUEUED", "RUNNING")
IMAGE_JOB_TYPES = ("AI 生图分镜",)
VIDEO_JOB_TYPES = ("分镜图 AI 生视频", "示意图特效视频")
_EMAIL_ADAPTER = TypeAdapter(EmailStr)


class AccountCommandError(ValueError):
    """可安全展示给命令行用户的输入或业务错误。"""


def ensure_not_production(environment: str) -> None:
    """禁止在生产环境执行测试账号维护。"""
    value = environment.strip().lower()
    if not value:
        raise AccountCommandError("ENVIRONMENT 未配置，拒绝执行账号维护")
    if value == "production":
        raise AccountCommandError("生产环境禁止执行测试账号维护")


def normalize_email(value: str) -> str:
    """按注册接口规则校验并标准化邮箱。"""
    try:
        return str(_EMAIL_ADAPTER.validate_python(value.strip())).lower()
    except (ValidationError, ValueError) as error:
        raise AccountCommandError("EMAIL 不是有效的邮箱地址") from error


def validate_password(value: str) -> str:
    """复用注册接口的密码长度约束。"""
    if not 6 <= len(value) <= 128:
        raise AccountCommandError("PASSWORD 长度必须为 6-128 个字符")
    return value


def validate_name(value: str) -> str:
    """复用注册接口的名称长度约束。"""
    name = value.strip()
    if not 1 <= len(name) <= 100:
        raise AccountCommandError("NAME 长度必须为 1-100 个字符")
    return name


def reset_ai_counters(usage: Usage) -> tuple[int, int]:
    """只重置 AI 生图和 AI 生视频计数，返回重置前的值。"""
    previous = (usage.ai_image_used, usage.ai_video_used)
    usage.ai_image_used = 0
    usage.ai_video_used = 0
    return previous


async def ensure_free_membership(session) -> Membership:
    membership = (
        await session.execute(
            select(Membership).where(Membership.id == FREE_MEMBERSHIP_ID)
        )
    ).scalar_one_or_none()
    if membership:
        return membership

    membership = Membership(
        id=FREE_MEMBERSHIP_ID,
        name="Free",
        rank=0,
        billing_cycle="monthly",
        processing_minutes=60,
        ai_image_quota=10,
        ai_video_quota=5,
        storage_gb=5,
        export_quota=10,
        price=0.0,
    )
    session.add(membership)
    await session.flush()
    return membership


async def get_or_create_usage(session, user: User) -> Usage:
    usage = (
        await session.execute(select(Usage).where(Usage.user_id == user.id))
    ).scalar_one_or_none()
    if usage:
        return usage
    usage = Usage(user_id=user.id)
    session.add(usage)
    await session.flush()
    return usage


async def get_membership(session, user: User) -> Membership | None:
    return (
        await session.execute(
            select(Membership).where(Membership.id == user.membership_id)
        )
    ).scalar_one_or_none()


async def create_test_account(
    email: str,
    password: str,
    name: str,
    *,
    reset_password: bool = False,
) -> None:
    settings = get_settings()
    ensure_not_production(settings.environment)
    normalized_email = normalize_email(email)
    valid_password = validate_password(password)
    valid_name = validate_name(name)

    async with async_session_factory() as session:
        try:
            await ensure_free_membership(session)
            user = (
                await session.execute(
                    select(User).where(func.lower(User.email) == normalized_email)
                )
            ).scalar_one_or_none()
            created = user is None
            password_changed = False

            if user is None:
                password_hash = hash_password(valid_password)
                user = User(
                    email=normalized_email,
                    name=valid_name,
                    password_hash=password_hash,
                    avatar_initial=valid_name[0].upper(),
                    membership_id=FREE_MEMBERSHIP_ID,
                )
                session.add(user)
                await session.flush()
                session.add(UserIdentity(
                    user_id=user.id,
                    provider=EMAIL_PROVIDER,
                    identifier=normalized_email,
                    password_hash=password_hash,
                    verified_at=user.created_at,
                ))
                password_changed = True
            elif reset_password:
                password_hash = hash_password(valid_password)
                user.password_hash = password_hash
                password_changed = True

            identity = (
                await session.execute(
                    select(UserIdentity).where(
                        UserIdentity.provider == EMAIL_PROVIDER,
                        UserIdentity.identifier == normalized_email,
                    )
                )
            ).scalar_one_or_none()
            if identity is None:
                identity = UserIdentity(
                    user_id=user.id,
                    provider=EMAIL_PROVIDER,
                    identifier=normalized_email,
                    password_hash=user.password_hash,
                    verified_at=user.created_at,
                )
                session.add(identity)
            elif reset_password:
                identity.password_hash = user.password_hash

            usage = await get_or_create_usage(session, user)
            membership = await get_membership(session, user)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    action = "已创建" if created else "已存在"
    password_note = "已设置" if password_changed else "保持不变（传 RESET_PASSWORD=1 可重置）"
    membership_name = membership.name if membership else user.membership_id
    image_quota = membership.ai_image_quota if membership else "未知"
    video_quota = membership.ai_video_quota if membership else "未知"
    print(f"测试账号{action}")
    print(f"  ID: {user.id}")
    print(f"  邮箱: {user.email}")
    print(f"  名称: {user.name}")
    print(f"  会员: {membership_name}")
    print(f"  密码: {password_note}")
    print(f"  AI 生图: {usage.ai_image_used}/{image_quota}")
    print(f"  AI 生视频: {usage.ai_video_used}/{video_quota}")


async def count_pending_jobs(session, user_id: str, job_types: tuple[str, ...]) -> int:
    return int(
        (
            await session.execute(
                select(func.count(Job.id))
                .select_from(Job)
                .join(Project, Job.project_id == Project.id)
                .where(
                    Project.owner_id == user_id,
                    Job.type.in_(job_types),
                    Job.status.in_(PENDING_STATUSES),
                )
            )
        ).scalar()
        or 0
    )


async def reset_ai_usage(email: str) -> None:
    settings = get_settings()
    ensure_not_production(settings.environment)
    normalized_email = normalize_email(email)

    async with async_session_factory() as session:
        try:
            user = (
                await session.execute(
                    select(User).where(func.lower(User.email) == normalized_email)
                )
            ).scalar_one_or_none()
            if user is None:
                raise AccountCommandError(f"未找到账号：{normalized_email}")

            usage = await get_or_create_usage(session, user)
            membership = await get_membership(session, user)
            pending_images = await count_pending_jobs(session, user.id, IMAGE_JOB_TYPES)
            pending_videos = await count_pending_jobs(session, user.id, VIDEO_JOB_TYPES)
            previous_images, previous_videos = reset_ai_counters(usage)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    image_quota = membership.ai_image_quota if membership else "未知"
    video_quota = membership.ai_video_quota if membership else "未知"
    print("AI 用量已重置")
    print(f"  ID: {user.id}")
    print(f"  邮箱: {user.email}")
    print(f"  AI 生图: {previous_images} -> 0（配额 {image_quota}）")
    print(f"  AI 生视频: {previous_videos} -> 0（配额 {video_quota}）")
    if pending_images or pending_videos:
        print(
            "  提醒：仍有待执行/执行中的 AI 任务，完成后会再次计入用量："
            f"生图 {pending_images}，生视频 {pending_videos}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VideoX 开发测试账号管理")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="创建或检查测试账号")
    create_parser.add_argument(
        "--email", default=os.getenv("VIDEOX_TEST_ACCOUNT_EMAIL")
    )
    create_parser.add_argument(
        "--password", default=os.getenv("VIDEOX_TEST_ACCOUNT_PASSWORD")
    )
    create_parser.add_argument(
        "--name", default=os.getenv("VIDEOX_TEST_ACCOUNT_NAME", "测试账号")
    )
    create_parser.add_argument(
        "--reset-password",
        action="store_true",
        help="账号已存在时显式更新密码",
    )

    reset_parser = subparsers.add_parser("reset-ai-usage", help="重置 AI 生图/视频用量")
    reset_parser.add_argument(
        "--email", default=os.getenv("VIDEOX_TEST_ACCOUNT_EMAIL")
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if not args.email:
            raise AccountCommandError("缺少 EMAIL/--email")
        if args.command == "create":
            if not args.password:
                raise AccountCommandError("缺少 PASSWORD/--password")
            asyncio.run(
                create_test_account(
                    args.email,
                    args.password,
                    args.name,
                    reset_password=args.reset_password,
                )
            )
        else:
            asyncio.run(reset_ai_usage(args.email))
    except AccountCommandError as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()

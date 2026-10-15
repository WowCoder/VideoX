"""创建、查看、停用和维护运营后台管理员。"""

import argparse
import asyncio
import getpass
from pathlib import Path
import sys

# Direct execution sets sys.path[0] to /app/scripts. Add the backend root so
# documented commands such as `python scripts/manage_admin.py ...` can import app.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select, update

from app.admin.security import (
    encrypt_mfa_secret,
    generate_totp_secret,
    print_totp_qr,
    totp_provisioning_uri,
)
from app.database import async_session_factory
from app.models.admin import AdminSession, AdminUser
from app.security import hash_password


ROLES = {"super_admin", "operator", "finance"}


def _password() -> str:
    first = getpass.getpass("管理员密码：")
    second = getpass.getpass("再次输入：")
    if first != second:
        raise ValueError("两次密码不一致")
    if len(first) < 12:
        raise ValueError("管理员密码至少需要 12 位")
    return first


def _print_mfa_enrollment(secret: str, email: str, *, reset: bool = False) -> None:
    uri = totp_provisioning_uri(secret, email)
    qualifier = "新 " if reset else ""
    print("\n请使用 Microsoft Authenticator 的“其他帐户”扫描下方二维码：")
    print_totp_qr(uri)
    print("二维码、TOTP 密钥和 Authenticator URI 均包含同一高敏感凭证，只展示一次。")
    print(f"{qualifier}TOTP 密钥（只展示一次）：{secret}")
    print(f"Authenticator URI（只展示一次）：{uri}")


async def create_admin(email: str, name: str, role: str) -> None:
    if role not in ROLES:
        raise ValueError(f"管理员角色必须是：{', '.join(sorted(ROLES))}")
    normalized_email = email.strip().lower()
    password = _password()
    secret = generate_totp_secret()
    async with async_session_factory() as db:
        exists = (
            await db.execute(select(AdminUser.id).where(AdminUser.email == normalized_email))
        ).scalar_one_or_none()
        if exists:
            raise ValueError("管理员邮箱已经存在")
        admin = AdminUser(
            email=normalized_email,
            name=name.strip(),
            password_hash=hash_password(password),
            role=role,
            status="active",
            mfa_secret_encrypted=encrypt_mfa_secret(secret),
            mfa_enabled=True,
        )
        db.add(admin)
        await db.commit()
    print(f"管理员已创建：{normalized_email}")
    _print_mfa_enrollment(secret, normalized_email)


async def list_admins() -> None:
    async with async_session_factory() as db:
        rows = (await db.execute(select(AdminUser).order_by(AdminUser.created_at))).scalars().all()
        for admin in rows:
            print(f"{admin.id}\t{admin.email}\t{admin.role}\t{admin.status}")


async def disable_admin(email: str) -> None:
    normalized_email = email.strip().lower()
    async with async_session_factory() as db:
        admin = (
            await db.execute(select(AdminUser).where(AdminUser.email == normalized_email).with_for_update())
        ).scalar_one_or_none()
        if not admin:
            raise ValueError("管理员不存在")
        admin.status = "disabled"
        admin.token_version += 1
        await db.execute(
            update(AdminSession)
            .where(AdminSession.admin_user_id == admin.id, AdminSession.revoked_at.is_(None))
            .values(revoked_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        )
        await db.commit()
    print(f"管理员已停用：{normalized_email}")


async def reset_mfa(email: str) -> None:
    normalized_email = email.strip().lower()
    secret = generate_totp_secret()
    async with async_session_factory() as db:
        admin = (
            await db.execute(select(AdminUser).where(AdminUser.email == normalized_email).with_for_update())
        ).scalar_one_or_none()
        if not admin:
            raise ValueError("管理员不存在")
        admin.mfa_secret_encrypted = encrypt_mfa_secret(secret)
        admin.mfa_enabled = True
        admin.token_version += 1
        await db.execute(
            update(AdminSession)
            .where(AdminSession.admin_user_id == admin.id, AdminSession.revoked_at.is_(None))
            .values(revoked_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        )
        await db.commit()
    print(f"TOTP 已重置：{normalized_email}")
    _print_mfa_enrollment(secret, normalized_email, reset=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="VideoX 运营后台管理员维护")
    commands = root.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--role", choices=sorted(ROLES), default="operator")
    commands.add_parser("list")
    disable = commands.add_parser("disable")
    disable.add_argument("--email", required=True)
    reset = commands.add_parser("reset-mfa")
    reset.add_argument("--email", required=True)
    return root


async def main() -> None:
    args = parser().parse_args()
    if args.command == "create":
        await create_admin(args.email, args.name, args.role)
    elif args.command == "list":
        await list_admins()
    elif args.command == "disable":
        await disable_admin(args.email)
    elif args.command == "reset-mfa":
        await reset_mfa(args.email)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)

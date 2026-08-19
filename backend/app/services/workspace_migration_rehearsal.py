"""一次性工作区迁移演练的目标安全规则。"""

from __future__ import annotations

from dataclasses import dataclass
import re

from sqlalchemy.engine import URL, make_url


_DATABASE_NAME = re.compile(r"^openvma_rehearsal_[a-z0-9_]+$")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_POSTGRES_DRIVERS = {"postgresql", "postgresql+asyncpg"}


@dataclass(frozen=True)
class RehearsalTarget:
    async_url: URL
    database_name: str

    @property
    def display_name(self) -> str:
        return self.async_url.render_as_string(hide_password=True)

    @property
    def pg_environment(self) -> dict[str, str]:
        values = {
            "PGHOST": self.async_url.host or "",
            "PGPORT": str(self.async_url.port or 5432),
            "PGUSER": self.async_url.username or "",
            "PGDATABASE": self.database_name,
        }
        if self.async_url.password is not None:
            values["PGPASSWORD"] = self.async_url.password
        return values


def _identity(url: URL) -> tuple[str | None, int, str | None]:
    host = url.host.lower() if url.host else None
    if host in _LOCAL_HOSTS:
        host = "local"
    return (
        host,
        url.port or 5432,
        url.database,
    )


def validate_rehearsal_target(
    database_url: str,
    *,
    confirmation: str,
    application_database_url: str | None = None,
) -> RehearsalTarget:
    try:
        parsed = make_url(database_url)
    except Exception as error:  # SQLAlchemy 会保留具体 URL 解析异常作为 cause。
        raise ValueError("演练数据库 URL 无效") from error

    if parsed.drivername not in _POSTGRES_DRIVERS:
        raise ValueError("演练目标必须是 PostgreSQL，并使用 postgresql 或 postgresql+asyncpg")
    if (parsed.host or "").lower() not in _LOCAL_HOSTS:
        raise ValueError("演练目标必须位于 localhost、127.0.0.1 或 ::1")
    if (parsed.port or 5432) != 55432:
        raise ValueError("演练目标必须使用隔离 Compose 服务的本机端口 55432")
    if not parsed.database or not _DATABASE_NAME.fullmatch(parsed.database):
        raise ValueError("演练数据库名必须以 openvma_rehearsal_ 开头，且只能包含小写字母、数字和下划线")
    if confirmation != parsed.database:
        raise ValueError("--confirm-database 必须与演练数据库名完全一致")

    if application_database_url:
        try:
            application_url = make_url(application_database_url)
        except Exception as error:
            raise ValueError("应用 DATABASE_URL 无效，无法完成目标隔离检查") from error
        if _identity(parsed) == _identity(application_url):
            raise ValueError("演练目标与应用 DATABASE_URL 指向同一个数据库，已拒绝执行")

    async_url = parsed.set(drivername="postgresql+asyncpg")
    return RehearsalTarget(async_url=async_url, database_name=parsed.database)

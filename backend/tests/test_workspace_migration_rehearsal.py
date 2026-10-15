"""一次性迁移演练的目标隔离规则测试。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services.workspace_migration_rehearsal import validate_rehearsal_target
from scripts.rehearse_workspace_migration import _restore_dump


VALID_URL = (
    "postgresql+asyncpg://videox_rehearsal:secret@"
    "127.0.0.1:55432/videox_rehearsal_021"
)
APPLICATION_URL = "postgresql+asyncpg://videox:secret@localhost:5432/videox"


class WorkspaceMigrationRehearsalTargetTests(unittest.TestCase):
    def test_accepts_isolated_local_rehearsal_database(self):
        target = validate_rehearsal_target(
            VALID_URL,
            confirmation="videox_rehearsal_021",
            application_database_url=APPLICATION_URL,
        )

        self.assertEqual(target.database_name, "videox_rehearsal_021")
        self.assertEqual(target.async_url.drivername, "postgresql+asyncpg")
        self.assertNotIn("secret", target.display_name)
        self.assertEqual(
            target.pg_environment,
            {
                "PGHOST": "127.0.0.1",
                "PGPORT": "55432",
                "PGUSER": "videox_rehearsal",
                "PGDATABASE": "videox_rehearsal_021",
                "PGPASSWORD": "secret",
            },
        )

    def test_normalizes_plain_postgresql_driver(self):
        target = validate_rehearsal_target(
            VALID_URL.replace("postgresql+asyncpg", "postgresql"),
            confirmation="videox_rehearsal_021",
        )

        self.assertEqual(target.async_url.drivername, "postgresql+asyncpg")

    def test_rejects_non_postgresql_target(self):
        with self.assertRaisesRegex(ValueError, "必须是 PostgreSQL"):
            validate_rehearsal_target(
                "sqlite:///videox_rehearsal_021",
                confirmation="videox_rehearsal_021",
            )

    def test_rejects_remote_host(self):
        with self.assertRaisesRegex(ValueError, "必须位于"):
            validate_rehearsal_target(
                VALID_URL.replace("127.0.0.1", "database.example.com"),
                confirmation="videox_rehearsal_021",
            )

    def test_rejects_default_or_unexpected_port(self):
        with self.assertRaisesRegex(ValueError, "端口 55432"):
            validate_rehearsal_target(
                VALID_URL.replace(":55432", ":5432"),
                confirmation="videox_rehearsal_021",
            )

    def test_rejects_database_without_rehearsal_prefix(self):
        with self.assertRaisesRegex(ValueError, "videox_rehearsal_"):
            validate_rehearsal_target(
                VALID_URL.replace("videox_rehearsal_021", "videox"),
                confirmation="videox",
            )

    def test_rejects_inexact_confirmation(self):
        with self.assertRaisesRegex(ValueError, "confirm-database"):
            validate_rehearsal_target(
                VALID_URL,
                confirmation="videox_rehearsal_other",
            )

    def test_rejects_application_database_with_different_driver_or_user(self):
        application_url = (
            "postgresql://another-user:other-secret@"
            "localhost:55432/videox_rehearsal_021"
        )

        with self.assertRaisesRegex(ValueError, "同一个数据库"):
            validate_rehearsal_target(
                VALID_URL,
                confirmation="videox_rehearsal_021",
                application_database_url=application_url,
            )

    def test_rejects_invalid_application_database_url(self):
        with self.assertRaisesRegex(ValueError, "应用 DATABASE_URL 无效"):
            validate_rehearsal_target(
                VALID_URL,
                confirmation="videox_rehearsal_021",
                application_database_url="not a database url",
            )

    def test_auto_restore_uses_local_pg_restore_when_available(self):
        target = validate_rehearsal_target(
            VALID_URL,
            confirmation="videox_rehearsal_021",
        )
        with tempfile.TemporaryDirectory() as directory:
            dump_path = Path(directory) / "source.dump"
            dump_path.write_bytes(b"custom dump fixture")
            with (
                patch(
                    "scripts.rehearse_workspace_migration.shutil.which",
                    return_value="/opt/postgresql/bin/pg_restore",
                ),
                patch("scripts.rehearse_workspace_migration._run") as run,
            ):
                _restore_dump(
                    dump_path,
                    target=target,
                    environment={},
                    backend_dir=Path(__file__).resolve().parents[1],
                    restore_mode="auto",
                )

        command = run.call_args.args[0]
        self.assertEqual(command[0], "/opt/postgresql/bin/pg_restore")
        self.assertIn(str(dump_path), command)

    def test_auto_restore_falls_back_to_rehearsal_compose(self):
        target = validate_rehearsal_target(
            VALID_URL,
            confirmation="videox_rehearsal_021",
        )

        def executable(name: str) -> str | None:
            return None if name == "pg_restore" else "/usr/local/bin/docker"

        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            backend_dir = project_dir / "backend"
            backend_dir.mkdir()
            (project_dir / "compose.migration-rehearsal.yml").write_text(
                "services: {}\n",
                encoding="utf-8",
            )
            dump_path = project_dir / "source.dump"
            dump_path.write_bytes(b"custom dump fixture")
            with (
                patch(
                    "scripts.rehearse_workspace_migration.shutil.which",
                    side_effect=executable,
                ),
                patch("scripts.rehearse_workspace_migration._run") as run,
            ):
                _restore_dump(
                    dump_path,
                    target=target,
                    environment={},
                    backend_dir=backend_dir,
                    restore_mode="auto",
                )

        command = run.call_args.args[0]
        self.assertEqual(command[:2], ("docker", "compose"))
        self.assertIn("compose.migration-rehearsal.yml", command[3])
        self.assertIn("rehearsal-db", command)

    def test_explicit_local_restore_requires_pg_restore(self):
        target = validate_rehearsal_target(
            VALID_URL,
            confirmation="videox_rehearsal_021",
        )
        with tempfile.TemporaryDirectory() as directory:
            dump_path = Path(directory) / "source.dump"
            dump_path.write_bytes(b"custom dump fixture")
            with patch(
                "scripts.rehearse_workspace_migration.shutil.which",
                return_value=None,
            ):
                with self.assertRaisesRegex(RuntimeError, "未找到 pg_restore"):
                    _restore_dump(
                        dump_path,
                        target=target,
                        environment={},
                        backend_dir=Path(__file__).resolve().parents[1],
                        restore_mode="local",
                    )


if __name__ == "__main__":
    unittest.main()

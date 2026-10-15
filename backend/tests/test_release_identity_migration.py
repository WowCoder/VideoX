"""发布身份迁移工具的纯逻辑保护测试。"""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from scripts.release_identity_migration import (
    PHONE_PLACEHOLDER_EMAIL_PATTERN,
    ReleaseIdentityError,
    _compare_with_baseline,
    _load_mapping,
    _mask_identifier,
)


def _snapshot(*, version: str, phone_count: int = 0) -> dict:
    return {
        "alembic_version": version,
        "users": [{"id": "user-a"}, {"id": "user-b"}],
        "user_ids_sha256": "users-digest",
        "entities": {
            "users": {"count": 2, "id_sha256": "u", "ownership_sha256": ""},
            "projects": {"count": 3, "id_sha256": "p", "ownership_sha256": "po"},
        },
        "identities": {
            "exists": version != "026_unified_narration_cues",
            "count": 2 + phone_count,
            "provider_counts": {"email": 2, "phone": phone_count},
            "provider_user_counts": {"email": 2, "phone": phone_count},
            "email_mismatches": 0,
            "duplicate_provider_identifiers": 0,
        },
        "guards": {
            "legacy_phone_users": 0,
            "casefold_email_duplicates": 0,
            "snapshot_duplicate_groups": 0,
            "columns_029": {
                "inspiration_tasks.discovery_config": version == "029_inspiration_discovery",
                "inspiration_sources.last_status": version == "029_inspiration_discovery",
                "inspiration_sources.consecutive_failures": version == "029_inspiration_discovery",
                "inspiration_runs.outcome": version == "029_inspiration_discovery",
                "inspiration_runs.metrics": version == "029_inspiration_discovery",
            },
        },
    }


class ReleaseIdentityMigrationTests(unittest.TestCase):
    def test_phone_placeholder_guard_covers_historical_and_current_addresses(self):
        for address in ("18888888888@openvma.cn", "18888888888@videox.cn"):
            with self.subTest(address=address):
                self.assertIsNotNone(re.fullmatch(PHONE_PLACEHOLDER_EMAIL_PATTERN, address))
        for address in ("user@videox.cn", "18888888888@example.com", "18888888888@videoxXcn"):
            with self.subTest(address=address):
                self.assertIsNone(re.fullmatch(PHONE_PLACEHOLDER_EMAIL_PATTERN, address))

    def test_mapping_requires_private_file_and_unique_users_and_phones(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bindings.json"
            path.write_text(
                json.dumps(
                    {
                        "bindings": [
                            {"user_id": "user-a", "phone": "18888888888"},
                            {"user_id": "user-b", "phone": "+86 139-9999-9999"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            path.chmod(0o600)
            self.assertEqual(
                _load_mapping(path),
                {"user-a": "+8618888888888", "user-b": "+8613999999999"},
            )

            path.chmod(0o644)
            with self.assertRaisesRegex(ReleaseIdentityError, "权限"):
                _load_mapping(path)

    def test_mapping_rejects_duplicate_phone(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bindings.json"
            path.write_text(
                json.dumps(
                    {
                        "bindings": [
                            {"user_id": "user-a", "phone": "18888888888"},
                            {"user_id": "user-b", "phone": "18888888888"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            path.chmod(0o600)
            with self.assertRaisesRegex(ReleaseIdentityError, "重复手机号"):
                _load_mapping(path)

    def test_identifiers_are_masked(self):
        self.assertEqual(_mask_identifier("phone", "+8618888888888"), "+86188****8888")
        self.assertEqual(_mask_identifier("email", "user@example.com"), "u***@example.com")

    def test_after_migration_requires_029_and_preserves_entities(self):
        before = _snapshot(version="026_unified_narration_cues")
        after = _snapshot(version="029_inspiration_discovery")
        result = _compare_with_baseline(
            before,
            after,
            phase="after-migration",
            expected_version="029_inspiration_discovery",
        )
        self.assertTrue(result["ok"], result["errors"])

        after["entities"]["projects"]["count"] += 1
        result = _compare_with_baseline(
            before,
            after,
            phase="after-migration",
            expected_version="029_inspiration_discovery",
        )
        self.assertFalse(result["ok"])
        self.assertTrue(any("projects" in error for error in result["errors"]))

    def test_after_binding_requires_one_phone_per_user(self):
        before = _snapshot(version="026_unified_narration_cues")
        after = _snapshot(version="029_inspiration_discovery", phone_count=2)
        result = _compare_with_baseline(
            before,
            after,
            phase="after-binding",
            expected_version="029_inspiration_discovery",
        )
        self.assertTrue(result["ok"], result["errors"])

        after["identities"]["provider_counts"]["phone"] = 1
        after["identities"]["provider_user_counts"]["phone"] = 1
        result = _compare_with_baseline(
            before,
            after,
            phase="after-binding",
            expected_version="029_inspiration_discovery",
        )
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()

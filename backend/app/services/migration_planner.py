"""Pure planning helpers mirrored by the irreversible workspace migration.

The Alembic migration uses PostgreSQL SQL for the actual move.  Keeping the
selection and ID rules here makes the destructive part reviewable and testable
without requiring a live copy of the production schema.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any


def split_project_id(project_id: str, script_id: str) -> str:
    """Return the stable project ID used for a non-primary legacy script."""

    digest = hashlib.md5(  # noqa: S324 - identity compatibility, not security
        f"021-split:{project_id}:{script_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"project-{digest}"


def _sort_key(script: Mapping[str, Any], selected_script_id: str | None) -> tuple:
    script_id = str(script.get("id") or "")
    if script_id == selected_script_id:
        priority = 0
    elif not bool(script.get("is_snapshot")):
        priority = 1
    else:
        priority = 2
    # SQL sorts timestamps descending and IDs ascending.  ISO timestamps sort
    # lexically; negative code points reproduce descending order without a
    # clock or parser dependency in this migration-only helper.
    updated = str(script.get("updated_at") or "")
    created = str(script.get("created_at") or "")
    descending_updated = tuple(-ord(char) for char in updated)
    descending_created = tuple(-ord(char) for char in created)
    return priority, descending_updated, descending_created, script_id


def plan_script_splits(
    project_id: str,
    scripts: Iterable[Mapping[str, Any]],
    *,
    selected_script_id: str | None = None,
) -> dict[str, Any]:
    """Plan one canonical document and zero or more recovery projects."""

    rows = [item for item in scripts if item.get("id")]
    ordered = sorted(rows, key=lambda item: _sort_key(item, selected_script_id))
    if not ordered:
        return {"primary_script_id": None, "splits": []}
    return {
        "primary_script_id": str(ordered[0]["id"]),
        "splits": [
            {
                "script_id": str(item["id"]),
                "project_id": split_project_id(project_id, str(item["id"])),
                "recovery_kind": "snapshot" if item.get("is_snapshot") else "business",
            }
            for item in ordered[1:]
        ],
    }

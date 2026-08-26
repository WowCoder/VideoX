#!/usr/bin/env python3
"""Remove local mirror files that no longer exist in the MinIO object listing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def reconcile(root: Path, listing: Path) -> int:
    keys: set[Path] = set()
    for line in listing.read_text().splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        key = item.get("key") or item.get("Key")
        if not key or key.endswith("/"):
            continue
        relative = Path(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise SystemExit(f"invalid MinIO object key: {key}")
        keys.add(relative)

    removed = 0
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_file() and path.relative_to(root) not in keys:
            path.unlink()
            removed += 1
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    return removed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("listing", type=Path)
    args = parser.parse_args()
    print(f"MinIO 镜像清理：删除 {reconcile(args.root, args.listing)} 个已不存在对象")


if __name__ == "__main__":
    main()

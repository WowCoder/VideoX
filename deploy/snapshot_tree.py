#!/usr/bin/env python3
"""Create a standalone directory snapshot with hard links for unchanged files."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def snapshot(source: Path, destination: Path, previous: Path | None = None) -> None:
    if not source.is_dir():
        raise SystemExit(f"source directory does not exist: {source}")
    if destination.exists():
        raise SystemExit(f"destination already exists: {destination}")

    destination.mkdir(parents=True)
    linked = copied = 0
    for root, dirs, files in os.walk(source):
        relative_root = Path(root).relative_to(source)
        target_root = destination / relative_root
        target_root.mkdir(parents=True, exist_ok=True)
        for directory in dirs:
            (target_root / directory).mkdir(exist_ok=True)
        for filename in files:
            source_file = Path(root) / filename
            target_file = target_root / filename
            previous_file = previous / relative_root / filename if previous else None
            if (
                previous_file
                and previous_file.is_file()
                and source_file.stat().st_size == previous_file.stat().st_size
                and source_file.stat().st_mtime_ns == previous_file.stat().st_mtime_ns
            ):
                os.link(previous_file, target_file)
                linked += 1
            else:
                shutil.copy2(source_file, target_file)
                copied += 1
    print(f"MinIO 快照完成：复用 {linked} 个文件，复制 {copied} 个文件")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    snapshot(args.source, args.destination, args.previous)


if __name__ == "__main__":
    main()

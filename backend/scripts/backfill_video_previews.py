"""Backfill browser-friendly video proxies for legacy assets.

This migration is intentionally idempotent: videos with ``preview_path`` are
skipped, while videos without one are transcoded to the same seek-friendly
proxy format used by normal uploads.  The original file is never replaced or
deleted; it remains the source used by export jobs.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session_factory
from app.models.asset import Asset
from app.tasks.media_tasks import _download_from_minio, _transcode_video_proxy
from app.utils.storage import upload_stream


def needs_preview(asset: Asset) -> bool:
    """Whether an asset needs a browser video proxy generated."""
    return (
        asset.media_type == "video"
        and not asset.preview_path
        and bool(asset.file_path)
        and asset.deleted_at is None
    )


async def backfill(*, asset_id: str | None = None, limit: int | None = None, dry_run: bool = False) -> int:
    """Generate missing proxies and return the number of failures."""
    async with async_session_factory() as session:
        query = (
            select(Asset)
            .where(
                Asset.media_type == "video",
                (Asset.preview_path.is_(None) | (Asset.preview_path == "")),
                Asset.file_path.is_not(None),
                Asset.deleted_at.is_(None),
            )
            .order_by(Asset.created_at, Asset.id)
        )
        if asset_id:
            query = query.where(Asset.id == asset_id)
        if limit is not None:
            query = query.limit(limit)
        assets = list((await session.execute(query)).scalars().all())

    print(f"待回填视频代理：{len(assets)} 个")
    if dry_run:
        for asset in assets:
            print(f"[dry-run] {asset.id} · {asset.name}")
        return 0

    succeeded = 0
    failures = 0
    for index, asset in enumerate(assets, start=1):
        if not needs_preview(asset):
            print(f"[{index}/{len(assets)}] 跳过 {asset.id}（状态已变化或素材已删除）")
            continue
        try:
            with tempfile.TemporaryDirectory(prefix=f"openvma_preview_{asset.id}_") as temp_dir:
                source_path = os.path.join(temp_dir, Path(asset.file_path or "source.mp4").name)
                proxy_path = os.path.join(temp_dir, "preview.mp4")
                await asyncio.to_thread(_download_from_minio, asset.file_path, source_path)
                await asyncio.to_thread(_transcode_video_proxy, source_path, proxy_path)
                storage_path = f"video-previews/{asset.id}/preview.mp4"
                with open(proxy_path, "rb") as stream:
                    await asyncio.to_thread(
                        upload_stream,
                        storage_path,
                        stream,
                        os.path.getsize(proxy_path),
                        "video/mp4",
                    )

            async with async_session_factory() as update_session:
                current = await update_session.get(Asset, asset.id, with_for_update=True)
                if current and needs_preview(current):
                    current.preview_path = storage_path
                    await update_session.commit()
                    succeeded += 1
                    print(f"[{index}/{len(assets)}] 已生成 {asset.id} · {asset.name}")
                else:
                    await update_session.rollback()
                    print(f"[{index}/{len(assets)}] 跳过 {asset.id}（已由其他任务生成代理）")
        except Exception as exc:  # pragma: no cover - exercised by production media/storage failures
            failures += 1
            print(f"[{index}/{len(assets)}] 失败 {asset.id} · {asset.name}：{str(exc)[:300]}")

    print(f"视频代理回填完成：成功 {succeeded}，失败 {failures}，跳过 {len(assets) - succeeded - failures}")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为缺少 preview_path 的历史视频生成浏览器代理")
    parser.add_argument("--asset-id", help="只处理指定素材")
    parser.add_argument("--limit", type=int, help="最多处理多少个素材")
    parser.add_argument("--dry-run", action="store_true", help="只列出待处理素材，不执行转码")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit 必须是正整数")
    return args


if __name__ == "__main__":
    options = parse_args()
    raise SystemExit(asyncio.run(backfill(
        asset_id=options.asset_id,
        limit=options.limit,
        dry_run=options.dry_run,
    )))

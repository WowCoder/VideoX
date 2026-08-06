"""使用当前配置的 Embedding Provider 重建真实 Clip 向量。

用法（在 backend 目录执行）：
    python scripts/reindex_embeddings.py
    python scripts/reindex_embeddings.py --limit 100
    python scripts/reindex_embeddings.py --all

默认跳过已经由当前模型、当前文本哈希生成且状态为 ready 的记录。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.models.asset import Asset, Clip  # noqa: E402
from app.services.ai_provider import generate_embedding, get_active_embedding_model  # noqa: E402


def embedding_source(clip: Clip, asset: Asset) -> str:
    values = [
        clip.transcript_segment or "",
        clip.ocr_segment or "",
        " ".join(str(tag) for tag in (asset.tags or [])),
    ]
    return " ".join(value.strip() for value in values if value.strip())


async def reindex(limit: int | None, force_all: bool) -> None:
    settings = get_settings()
    model_name = get_active_embedding_model()
    processed = 0
    skipped = 0
    failed = 0

    async with async_session_factory() as session:
        statement = select(Clip, Asset).join(Asset, Clip.asset_id == Asset.id).order_by(Clip.created_at)
        if limit:
            statement = statement.limit(limit)
        rows = (await session.execute(statement)).all()

        for clip, asset in rows:
            source = embedding_source(clip, asset)
            if not source:
                clip.embedding_status = "missing"
                skipped += 1
                continue
            source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
            if (
                not force_all
                and clip.embedding_status == "ready"
                and clip.embedding_model == model_name
                and clip.embedding_dimensions == settings.ai_embedding_dimensions
                and clip.embedding_source_hash == source_hash
            ):
                skipped += 1
                continue
            try:
                vector = await generate_embedding(source)
                clip.embedding = vector
                clip.embedding_model = model_name
                clip.embedding_dimensions = settings.ai_embedding_dimensions
                clip.embedding_version = (clip.embedding_version or 0) + 1
                clip.embedding_status = "ready"
                clip.embedding_source_hash = source_hash
                clip.embedding_updated_at = datetime.now(timezone.utc)
                processed += 1
            except Exception as error:
                clip.embedding_status = "failed"
                failed += 1
                print(f"FAILED {clip.id}: {str(error)[:200]}")
            await session.commit()

    print(
        f"embedding reindex complete: model={model_name}, "
        f"processed={processed}, skipped={skipped}, failed={failed}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--all", action="store_true", help="强制重算已是当前模型的记录")
    args = parser.parse_args()
    asyncio.run(reindex(args.limit, args.all))


if __name__ == "__main__":
    main()

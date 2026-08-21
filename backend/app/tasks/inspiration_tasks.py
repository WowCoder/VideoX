"""灵感岛定时扫描与正式抓取/去重/总结任务。"""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "text/xml",
    "application/json",
)


def _clean_content(value: str) -> str:
    value = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:200000]


def _source_label(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.netloc.removeprefix("www.") or url


def _build_generation_prompt(task, changed: list[dict]) -> str:
    source_payload = json.dumps(changed, ensure_ascii=False)
    if task.task_type == "link-update":
        return f"""请逐条整理以下公开链接的新变化。严格返回 JSON 对象：
{{"title":"本次动态标题","summary":"总体摘要","updates":[{{"url":"原始链接","title":"更新标题","summary":"变化摘要"}}]}}
updates 必须覆盖输入中的每个链接，url 必须原样返回；不得编造来源中没有的事实。
来源内容：{source_payload}"""
    return f"""请根据以下公开来源的新内容，为视频创作者生成 {task.topic_count or 5} 个可执行选题。
严格返回 JSON 对象：
{{"title":"本次选题标题","summary":"总体摘要","topics":[{{"title":"选题标题","angle":"内容切口","summary":"选题摘要","reference_urls":["原始链接"]}}]}}
topics 数量必须是 {task.topic_count or 5}；reference_urls 只能使用输入中的原始链接；不得编造来源中没有的事实。
选题方向：{task.topic_brief}
来源内容：{source_payload}"""


def _normalize_generated_content(
    task_type: str,
    data: dict,
    changed: list[dict],
    *,
    task_name: str,
    topic_count: int | None,
) -> tuple[str, str, dict, list[dict]]:
    allowed_urls = {str(item["url"]): item for item in changed}
    citations = [{"url": url, "label": _source_label(url)} for url in allowed_urls]
    title = str(data.get("title") or task_name)[:300]
    summary = str(data.get("summary") or "")[:10000]

    if task_type == "link-update":
        raw_updates = data.get("updates") if isinstance(data.get("updates"), list) else []
        by_url = {
            str(item.get("url")): item
            for item in raw_updates
            if isinstance(item, dict) and str(item.get("url")) in allowed_urls
        }
        updates = []
        for index, (url, source) in enumerate(allowed_urls.items(), start=1):
            item = by_url.get(url, {})
            updates.append(
                {
                    "id": f"update-{index}",
                    "source": _source_label(url),
                    "title": str(item.get("title") or "检测到新的页面更新")[:300],
                    "summary": str(item.get("summary") or source.get("content") or "")[:3000],
                    "url": url,
                }
            )
        return title, summary, {"updates": updates}, citations

    raw_topics = data.get("topics") if isinstance(data.get("topics"), list) else []
    expected_count = topic_count or 5
    topics = []
    for item in raw_topics[:expected_count]:
        if not isinstance(item, dict):
            continue
        references = []
        for url in item.get("reference_urls") or []:
            normalized_url = str(url)
            if normalized_url in allowed_urls and not any(ref["url"] == normalized_url for ref in references):
                references.append({"url": normalized_url, "label": _source_label(normalized_url)})
        if not references:
            references = citations[:1]
        topics.append(
            {
                "id": f"topic-{len(topics) + 1}",
                "order": len(topics) + 1,
                "title": str(item.get("title") or "未命名选题")[:300],
                "angle": str(item.get("angle") or "内容观察")[:200],
                "summary": str(item.get("summary") or "")[:3000],
                "references": references,
            }
        )
    if len(topics) != expected_count:
        raise ValueError(f"AI 返回了 {len(topics)} 个有效选题，预期 {expected_count} 个")
    return title, summary, {"topics": topics}, citations


async def _fetch_source(url: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str]]:
    from app.utils.network_security import validate_public_https_url

    current_url = url
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(25.0, connect=8.0),
        follow_redirects=False,
        headers={"User-Agent": "OpenVMA-Inspiration/1.0", **headers},
    ) as client:
        for _ in range(6):
            validate_public_https_url(current_url)
            async with client.stream("GET", current_url) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise RuntimeError("来源返回了无目标地址的重定向")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status_code == 304:
                    return 304, "", dict(response.headers)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if not any(content_type == item for item in ALLOWED_CONTENT_TYPES):
                    raise RuntimeError(f"来源内容类型不受支持：{content_type or 'unknown'}")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise RuntimeError("来源响应超过 2 MiB 上限")
                    chunks.append(chunk)
                encoding = response.encoding or "utf-8"
                return response.status_code, b"".join(chunks).decode(encoding, errors="replace"), dict(response.headers)
        raise RuntimeError("来源重定向次数过多")


async def _publish(owner_id: str, job_id: str, status: str, progress: int) -> None:
    from app.config import get_settings
    import redis.asyncio as aioredis

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await redis.publish(
            f"ws:job_updates:{owner_id}",
            json.dumps(
                {"job_id": job_id, "status": status, "progress": progress},
                ensure_ascii=False,
            ),
        )
    finally:
        await redis.aclose()


@celery_app.task(bind=True, name="app.tasks.run_inspiration_task")
def run_inspiration_task(self, task_id: str, run_id: str, job_id: str):
    run_async(_run_inspiration_task(task_id, run_id, job_id))


async def _run_inspiration_task(task_id: str, run_id: str, job_id: str) -> None:
    from app.config import get_settings
    from app.database import async_session_factory
    from app.models.inspiration import (
        InspirationResult,
        InspirationRun,
        InspirationSource,
        InspirationSourceSnapshot,
        InspirationTask,
    )
    from app.models.job import Job
    from app.models.notification import Notification
    from app.services.ai_provider import generate_text

    now = datetime.now(timezone.utc)
    owner_id = ""
    try:
        async with async_session_factory() as session:
            task = (
                await session.execute(
                    select(InspirationTask)
                    .where(InspirationTask.id == task_id)
                    .options(selectinload(InspirationTask.sources))
                )
            ).scalar_one()
            owner_id = task.owner_id
            run = await session.get(InspirationRun, run_id)
            job = await session.get(Job, job_id)
            if not run or not job:
                raise RuntimeError("灵感任务运行记录不存在")
            run.status = "RUNNING"
            run.started_at = now
            job.status = "RUNNING"
            job.stage = "安全抓取"
            job.progress = 10
            await session.commit()
            await _publish(owner_id, job_id, "RUNNING", 10)

            changed: list[dict] = []
            for source in task.sources:
                if not source.enabled:
                    continue
                latest = (
                    await session.execute(
                        select(InspirationSourceSnapshot)
                        .where(InspirationSourceSnapshot.source_id == source.id)
                        .order_by(InspirationSourceSnapshot.fetched_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                headers: dict[str, str] = {}
                if latest and latest.etag:
                    headers["If-None-Match"] = latest.etag
                if latest and latest.last_modified:
                    headers["If-Modified-Since"] = latest.last_modified
                try:
                    status, raw_content, response_headers = await _fetch_source(source.url, headers)
                    if status == 304:
                        source.last_error = None
                        source.last_success_at = datetime.now(timezone.utc)
                        continue
                    cleaned = _clean_content(raw_content)
                    content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
                    if latest and latest.content_hash == content_hash:
                        source.last_error = None
                        source.last_success_at = datetime.now(timezone.utc)
                        continue
                    snapshot = InspirationSourceSnapshot(
                        source_id=source.id,
                        run_id=run.id,
                        content_hash=content_hash,
                        etag=response_headers.get("etag"),
                        last_modified=response_headers.get("last-modified"),
                        content_type=response_headers.get("content-type", "")[:120],
                        raw_content=raw_content,
                        cleaned_content=cleaned,
                    )
                    session.add(snapshot)
                    source.last_error = None
                    source.last_success_at = datetime.now(timezone.utc)
                    changed.append({"url": source.url, "content": cleaned[:40000]})
                except Exception as exc:
                    source.last_error = str(exc)[:500]

            job.stage = "内容去重"
            job.progress = 45
            await session.commit()
            await _publish(owner_id, job_id, "RUNNING", 45)

            if changed:
                job.stage = "AI 总结"
                job.progress = 65
                await session.commit()
                prompt = _build_generation_prompt(task, changed)
                raw = await generate_text(
                    prompt=prompt,
                    system_prompt="你是视频内容策划，只输出合法 JSON。",
                    temperature=0.4,
                    max_tokens=2500,
                )
                text = raw.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
                data = json.loads(text)
                title, summary, content, citations = _normalize_generated_content(
                    task.task_type,
                    data,
                    changed,
                    task_name=task.name,
                    topic_count=task.topic_count,
                )
                result = InspirationResult(
                    run_id=run.id,
                    title=title,
                    summary=summary,
                    content=content,
                    citations=citations,
                    model_provider=get_settings().ai_text_provider,
                    model_name=get_settings().active_text_model,
                )
                session.add(result)

            finished = datetime.now(timezone.utc)
            run.status = "SUCCEEDED"
            run.finished_at = finished
            task.last_run_at = finished
            from app.services.inspiration_schedule import next_inspiration_run

            task.next_run_at = next_inspiration_run(task.schedule, finished) if task.enabled else None
            job.status = "SUCCEEDED"
            job.stage = "完成"
            job.progress = 100
            job.result = "查看结果"
            job.result_detail = "已生成新灵感" if changed else "来源内容没有变化"
            session.add(
                Notification(
                    user_id=task.owner_id,
                    job_id=job.id,
                    type="inspiration",
                    title=f"灵感任务已完成：{task.name}",
                    message=job.result_detail,
                    link=f"/workspace/inspiration?run={run.id}",
                )
            )
            await session.commit()
            await _publish(owner_id, job_id, "SUCCEEDED", 100)
    except Exception as exc:
        async with async_session_factory() as session:
            await session.execute(
                update(InspirationRun)
                .where(InspirationRun.id == run_id)
                .values(
                    status="FAILED",
                    error=str(exc)[:1000],
                    finished_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(
                    status="FAILED",
                    stage="执行失败",
                    detail=str(exc)[:500],
                    result=None,
                    result_detail=str(exc)[:500],
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
        if owner_id:
            await _publish(owner_id, job_id, "FAILED", 0)


@celery_app.task(name="app.tasks.scan_due_inspiration_tasks")
def scan_due_inspiration_tasks():
    run_async(_scan_due_inspiration_tasks())


async def _scan_due_inspiration_tasks() -> None:
    from app.database import async_session_factory
    from app.models.inspiration import InspirationRun, InspirationTask
    from app.models.job import Job

    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        tasks = (
            await session.execute(
                select(InspirationTask).where(
                    InspirationTask.enabled.is_(True),
                    InspirationTask.next_run_at.is_not(None),
                    InspirationTask.next_run_at <= now,
                )
            )
        ).scalars().all()
        pending: list[tuple[InspirationTask, InspirationRun, Job]] = []
        for task in tasks:
            active = (
                await session.execute(
                    select(InspirationRun.id).where(
                        InspirationRun.task_id == task.id,
                        InspirationRun.status.in_(["QUEUED", "RUNNING"]),
                    )
                )
            ).first()
            if active:
                continue
            job = Job(
                owner_id=task.owner_id,
                project_id=None,
                subject_type="inspiration_task",
                name=f"灵感更新：{task.name}",
                type="灵感岛任务",
                status="QUEUED",
                stage="等待抓取",
                stages=["安全抓取", "内容去重", "AI 总结", "保存结果"],
                payload={"task_id": task.id},
            )
            run = InspirationRun(task_id=task.id, status="QUEUED")
            session.add_all([job, run])
            await session.flush()
            run.job_id = job.id
            job.subject_id = run.id
            from app.services.inspiration_schedule import next_inspiration_run

            task.next_run_at = next_inspiration_run(task.schedule, now)
            pending.append((task, run, job))
        await session.commit()
        for task, run, job in pending:
            run_inspiration_task.apply_async(args=(task.id, run.id, job.id))

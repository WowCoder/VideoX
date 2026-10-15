"""可审计的公开网页搜索适配器。

搜索只负责返回候选；候选页面仍必须经过灵感任务的 HTTPS/SSRF 校验与真实抓取，
不能把搜索摘要直接当作事实依据。
"""

from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from app.config import get_settings


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str = ""
    published_at: str | None = None


def parse_bing_rss(payload: str, limit: int) -> list[WebSearchResult]:
    """解析 Bing RSS 搜索结果，过滤非 HTTPS 与重复地址。"""
    root = ElementTree.fromstring(payload)
    results: list[WebSearchResult] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        if not title or not url.lower().startswith("https://") or url in seen:
            continue
        seen.add(url)
        published_at = None
        raw_date = (item.findtext("pubDate") or "").strip()
        if raw_date:
            try:
                published_at = parsedate_to_datetime(raw_date).isoformat()
            except (TypeError, ValueError, OverflowError):
                published_at = None
        results.append(
            WebSearchResult(
                title=title[:300],
                url=url,
                snippet=(item.findtext("description") or "").strip()[:2000],
                published_at=published_at,
            )
        )
        if len(results) >= limit:
            break
    return results


def _bing_freshness_filter(recency_days: int | None) -> str | None:
    if recency_days is None:
        return None
    if recency_days <= 1:
        return 'ex1:"ez1"'
    if recency_days <= 7:
        return 'ex1:"ez2"'
    return 'ex1:"ez3"'


async def search_web(
    query: str,
    *,
    limit: int | None = None,
    recency_days: int | None = None,
) -> list[WebSearchResult]:
    """使用显式配置的搜索 Provider 返回真实候选网页。"""
    settings = get_settings()
    provider = settings.web_search_provider.lower()
    resolved_limit = max(1, min(limit or settings.web_search_results_per_query, 20))
    if provider == "disabled":
        raise RuntimeError("联网搜索服务未启用")
    if provider != "bing-rss":
        raise RuntimeError(f"不支持的联网搜索服务：{provider}")

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.web_search_timeout_seconds, connect=8.0),
        headers={"User-Agent": "VideoX-Inspiration-Search/1.0"},
        follow_redirects=True,
    ) as client:
        params = {"q": query, "format": "rss", "setlang": "zh-Hans"}
        freshness_filter = _bing_freshness_filter(recency_days)
        if freshness_filter:
            params["filters"] = freshness_filter
        response = await client.get(settings.web_search_url, params=params)
        response.raise_for_status()
        if len(response.content) > 1024 * 1024:
            raise RuntimeError("联网搜索响应超过 1 MiB 上限")
    try:
        return parse_bing_rss(response.text, resolved_limit)
    except ElementTree.ParseError as error:
        raise RuntimeError("联网搜索服务返回了无效 RSS") from error

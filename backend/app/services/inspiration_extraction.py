"""灵感来源的结构化提取、稳定指纹与有效差异计算。"""

from __future__ import annotations

import hashlib
import html
import json
import re
from difflib import SequenceMatcher
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree import ElementTree


MAX_STATE_TEXT = 60000
MAX_ITEMS = 120
MAX_BLOCKS = 240
_SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template"}
_BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"}
_IGNORED_LINK_WORDS = {
    "首页", "登录", "注册", "更多", "下一页", "上一页", "隐私", "条款", "联系我们",
    "home", "login", "sign up", "privacy", "terms", "contact", "read more",
}
_NOISE_PATTERN = re.compile(
    r"^(?:copyright|all rights reserved|版权所有|cookie|隐私|登录|注册|阅读更多|返回顶部)\b",
    re.IGNORECASE,
)


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _strip_markup(value: str) -> str:
    value = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", value or "")
    return _compact(re.sub(r"(?s)<[^>]+>", " ", value))


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_url(base_url: str, href: str) -> str | None:
    try:
        parsed = urlparse(urljoin(base_url, href))
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    # 列表项身份不应受跟踪参数与锚点影响。
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", "", ""))


class _DocumentParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.skip_depth = 0
        self.preferred_depth = 0
        self.in_title = False
        self.title_parts: list[str] = []
        self.block_tag: str | None = None
        self.block_preferred = False
        self.block_parts: list[str] = []
        self.blocks: list[str] = []
        self.preferred_blocks: list[str] = []
        self.anchor_href: str | None = None
        self.anchor_parts: list[str] = []
        self.anchors: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"main", "article"}:
            self.preferred_depth += 1
        if tag == "title":
            self.in_title = True
        if tag in _BLOCK_TAGS and self.block_tag is None:
            self.block_tag = tag
            self.block_preferred = self.preferred_depth > 0
            self.block_parts = []
        if tag == "a" and self.anchor_href is None:
            href = next((value for name, value in attrs if name.lower() == "href"), None)
            self.anchor_href = href or ""
            self.anchor_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag == "title":
            self.in_title = False
        if self.block_tag == tag:
            value = _compact(" ".join(self.block_parts))
            if 8 <= len(value) <= 4000 and not _NOISE_PATTERN.search(value):
                self.blocks.append(value)
                if self.block_preferred:
                    self.preferred_blocks.append(value)
            self.block_tag = None
            self.block_parts = []
        if tag == "a" and self.anchor_href is not None:
            url = _canonical_url(self.base_url, self.anchor_href)
            title = _compact(" ".join(self.anchor_parts))
            if url and 5 <= len(title) <= 300 and title.lower() not in _IGNORED_LINK_WORDS:
                self.anchors.append((url, title))
            self.anchor_href = None
            self.anchor_parts = []
        if tag in {"main", "article"}:
            self.preferred_depth = max(0, self.preferred_depth - 1)

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        value = _compact(data)
        if not value:
            return
        if self.in_title:
            self.title_parts.append(value)
        if self.block_tag is not None:
            self.block_parts.append(value)
        if self.anchor_href is not None:
            self.anchor_parts.append(value)


def _unique(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _compact(value)
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def _child_text(node: ElementTree.Element, names: set[str]) -> str:
    for child in node:
        if child.tag.split("}")[-1].lower() in names:
            return _strip_markup("".join(child.itertext()))
    return ""


def _extract_feed(raw: str, url: str) -> dict | None:
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return None
    root_name = root.tag.split("}")[-1].lower()
    if root_name not in {"rss", "feed", "rdf"}:
        return None
    items: list[dict] = []
    for node in root.iter():
        if node.tag.split("}")[-1].lower() not in {"item", "entry"}:
            continue
        title = _child_text(node, {"title"})
        link = _child_text(node, {"link"})
        if not link:
            for child in node:
                if child.tag.split("}")[-1].lower() == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        normalized_link = _canonical_url(url, link) if link else None
        guid = _child_text(node, {"guid", "id"})
        summary = _child_text(node, {"description", "summary", "content"})[:1200]
        published = _child_text(node, {"pubdate", "published", "updated", "date"})[:120]
        identity = normalized_link or guid or _fingerprint([title, published])
        if not title and not summary:
            continue
        items.append({
            "id": identity,
            "title": title[:300] or "未命名条目",
            "url": normalized_link or url,
            "published": published,
            "summary": summary,
        })
        if len(items) >= MAX_ITEMS:
            break
    if not items:
        return None
    title = ""
    for node in root.iter():
        if node.tag.split("}")[-1].lower() == "title":
            title = _compact("".join(node.itertext()))
            break
    stable = [{"id": item["id"], "title": item["title"], "summary": item["summary"]} for item in items]
    return {
        "version": 1,
        "mode": "rss",
        "title": title[:300],
        "items": items,
        "blocks": [],
        "text": "\n".join(f"{item['title']} {item['summary']}" for item in items)[:MAX_STATE_TEXT],
        "fingerprint": _fingerprint(stable),
    }


def extract_source_state(url: str, raw: str, content_type: str = "", source_type: str = "web") -> dict:
    """把 RSS、列表页和正文页转成可比较的结构化状态。"""
    if source_type == "rss" or "xml" in content_type or "rss" in content_type or "atom" in content_type:
        feed = _extract_feed(raw, url)
        if feed:
            return feed

    parser = _DocumentParser(url)
    parser.feed(raw)
    parser.close()
    title = _compact(" ".join(parser.title_parts))[:300]
    blocks = _unique(
        parser.preferred_blocks if len(parser.preferred_blocks) >= 3 else parser.blocks,
        MAX_BLOCKS,
    )
    base_host = (urlparse(url).hostname or "").lower()
    items: list[dict] = []
    seen_urls: set[str] = set()
    for item_url, item_title in parser.anchors:
        parsed = urlparse(item_url)
        if (parsed.hostname or "").lower() != base_host or item_url in seen_urls:
            continue
        path = parsed.path.lower()
        if path in {"/", "/about", "/contact", "/privacy", "/terms", "/login", "/signup"}:
            continue
        seen_urls.add(item_url)
        items.append({"id": item_url, "title": item_title[:300], "url": item_url, "published": "", "summary": ""})
        if len(items) >= MAX_ITEMS:
            break

    path = urlparse(url).path.rstrip("/")
    looks_like_listing = len(items) >= 8 and (path == "" or len(blocks) < 12 or len(items) >= len(blocks))
    if looks_like_listing:
        stable = [{"id": item["id"], "title": item["title"]} for item in items]
        mode = "listing"
        text = "\n".join(item["title"] for item in items)
    else:
        mode = "article"
        items = []
        stable = blocks
        text = "\n".join(blocks)
    return {
        "version": 1,
        "mode": mode,
        "title": title,
        "items": items,
        "blocks": blocks,
        "text": text[:MAX_STATE_TEXT],
        "fingerprint": _fingerprint(stable),
    }


def state_from_snapshot(value: str) -> dict | None:
    try:
        state = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return state if isinstance(state, dict) and state.get("version") == 1 else None


def _meaningful_block(value: str) -> bool:
    value = _compact(value)
    if len(value) < 20 or _NOISE_PATTERN.search(value):
        return False
    # 纯时间、数字或非常短的控件状态不形成内容动态。
    return bool(re.search(r"[A-Za-z\u4e00-\u9fff]", value))


def compare_source_states(previous: dict | None, current: dict) -> dict:
    """返回 BASELINE/UNCHANGED/CHANGED/STRUCTURE_CHANGED 及有限证据。"""
    if previous is None:
        return {"status": "BASELINE_CREATED", "change_type": "baseline", "evidence": []}
    if previous.get("fingerprint") == current.get("fingerprint"):
        return {"status": "UNCHANGED", "change_type": "none", "evidence": []}
    if previous.get("mode") != current.get("mode"):
        return {"status": "STRUCTURE_CHANGED", "change_type": "structure", "evidence": []}

    mode = current.get("mode")
    if mode in {"rss", "listing"}:
        old_items = {str(item.get("id")): item for item in previous.get("items") or []}
        new_items = current.get("items") or []
        if len(old_items) >= 8 and len(new_items) < max(2, int(len(old_items) * 0.3)):
            return {"status": "STRUCTURE_CHANGED", "change_type": "structure", "evidence": []}
        evidence: list[dict] = []
        for item in new_items:
            identity = str(item.get("id"))
            old = old_items.get(identity)
            if old is None:
                evidence.append({"type": "new-item", **item})
            elif _fingerprint([old.get("title"), old.get("summary")]) != _fingerprint([item.get("title"), item.get("summary")]):
                evidence.append({"type": "modified-item", **item})
            if len(evidence) >= 20:
                break
        if not evidence:
            return {"status": "UNCHANGED", "change_type": "noise-or-reorder", "evidence": []}
        return {"status": "CHANGED", "change_type": "new-content", "evidence": evidence}

    old_blocks = [str(item) for item in previous.get("blocks") or []]
    new_blocks = [str(item) for item in current.get("blocks") or []]
    matcher = SequenceMatcher(a=old_blocks, b=new_blocks, autojunk=False)
    if min(len(old_blocks), len(new_blocks)) >= 8 and matcher.ratio() < 0.25:
        return {"status": "STRUCTURE_CHANGED", "change_type": "structure", "evidence": []}
    evidence = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag not in {"insert", "replace"}:
            continue
        for block in new_blocks[j1:j2]:
            if _meaningful_block(block):
                evidence.append({"type": "added-or-modified", "text": block[:800]})
            if len(evidence) >= 12:
                break
        if len(evidence) >= 12:
            break
    if not evidence:
        return {"status": "UNCHANGED", "change_type": "noise", "evidence": []}
    return {"status": "CHANGED", "change_type": "content-change", "evidence": evidence}


def state_prompt_text(state: dict, *, limit: int = 12000) -> str:
    """生成供选题发现使用的有限、可验证候选正文。"""
    if state.get("mode") in {"rss", "listing"}:
        values = []
        for item in (state.get("items") or [])[:30]:
            values.append(f"{item.get('title', '')}\n{item.get('summary', '')}".strip())
        return "\n\n".join(values)[:limit]
    return str(state.get("text") or "")[:limit]

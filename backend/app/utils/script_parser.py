"""脚本解析工具（从 MVP2 迁移）。

支持三种输入：
1. 粘贴文本（纯文本或制表符/竖线分隔表格）
2. 表格上传（XLSX/CSV/TSV）
3. AI 生成（直接传入结构化数据）
"""

import re
from typing import Optional
from app.utils.duration import parse_duration, split_long_text


# ── 表头别名匹配 ──
HEADER_ALIASES = {
    "outline": ["大纲", "段落", "章节", "场景", "镜号", "scene", "outline", "title"],
    "text": ["台词", "旁白", "文案", "脚本", "内容", "字幕", "dialogue", "voiceover", "script", "text", "copy"],
    "description": ["分镜描述", "画面描述", "镜头描述", "分镜", "画面", "镜头", "visual", "shot", "description"],
    "notes": ["备注", "拍摄备注", "说明", "notes", "note", "remark"],
    "duration": ["时长", "秒数", "秒", "duration", "seconds", "time"],
}


def normalize_header(text: str) -> str:
    """标准化表头文本：去空格/下划线/标点后小写。"""
    return re.sub(r'[\s_\-\.·]', '', text).lower()


def find_header_row(rows: list[list[str]], max_scan: int = 6) -> int:
    """在前 max_scan 行中查找表头行。"""
    best_row = -1
    best_score = 0

    for row_idx in range(min(max_scan, len(rows))):
        score = 0
        for cell in rows[row_idx]:
            normalized = normalize_header(str(cell))
            for aliases in HEADER_ALIASES.values():
                for alias in aliases:
                    alias_norm = normalize_header(alias)
                    if alias_norm == normalized or alias_norm in normalized:
                        score += 1
                        break
        if score > best_score:
            best_score = score
            best_row = row_idx

    return best_row if best_score >= 2 else -1


def find_column(headers: list[str], field: str) -> int:
    """按别名匹配列索引。"""
    aliases = HEADER_ALIASES.get(field, [])
    for col_idx, header in enumerate(headers):
        normalized = normalize_header(str(header))
        for alias in aliases:
            alias_norm = normalize_header(alias)
            if alias_norm == normalized or alias_norm in normalized or normalized in alias_norm:
                return col_idx
    return -1


def units_from_table(rows: list[list[str]]) -> list[dict]:
    """从表格行生成脚本单元列表。

    同台词多行 → 合并为多 shot。
    """
    if not rows:
        return []

    header_row = find_header_row(rows)
    if header_row < 0:
        return []

    headers = rows[header_row]
    col_outline = find_column(headers, "outline")
    col_text = find_column(headers, "text")
    col_desc = find_column(headers, "description")
    col_notes = find_column(headers, "notes")
    col_duration = find_column(headers, "duration")

    units = []
    current_unit = None

    for row in rows[header_row + 1:]:
        if not row or all(not str(c).strip() for c in row):
            continue

        outline = str(row[col_outline]).strip() if col_outline >= 0 and col_outline < len(row) else ""
        text = str(row[col_text]).strip() if col_text >= 0 and col_text < len(row) else ""
        desc = str(row[col_desc]).strip() if col_desc >= 0 and col_desc < len(row) else ""
        notes = str(row[col_notes]).strip() if col_notes >= 0 and col_notes < len(row) else ""
        duration_val = str(row[col_duration]).strip() if col_duration >= 0 and col_duration < len(row) else ""

        # 同台词多行 → 合并为多 shot
        if not text and current_unit and desc:
            current_unit["shots"].append({
                "description": desc,
                "duration": parse_duration(duration_val),
                "notes": notes,
            })
            continue

        # 新建 unit
        current_unit = {
            "outline": outline or (text[:16] if text else ""),
            "text": text,
            "intent": desc or text[:30],
            "duration": parse_duration(duration_val),
            "notes": notes,
            "status": "待编辑",
            "shots": [],
        }
        if not desc and text:
            current_unit["shots"].append({
                "description": text[:30],
                "duration": parse_duration(duration_val),
                "notes": notes,
            })
        elif desc:
            current_unit["shots"].append({
                "description": desc,
                "duration": parse_duration(duration_val),
                "notes": notes,
            })
        units.append(current_unit)

    return units


def units_from_plain_text(text: str) -> list[dict]:
    """从纯文本解析脚本单元。

    解析规则：
    - 画面:/分镜:/镜头描述: 前缀 → 当前 unit 新增 shot
    - 台词:/旁白:/文案:/字幕: 前缀 → 新建 unit
    - 备注:/说明: 前缀 → 写入当前 shot.notes
    - 时长: 前缀 → 写入当前 shot.duration
    - 场景:/镜头:/段落: 前缀（短行）→ 设为 pendingOutline
    - 其他行 → appendUnit（长句拆分）
    """
    if not text or not text.strip():
        return []

    lines = text.strip().split("\n")
    units = []
    current_unit = None
    pending_outline = None

    prefixes = {
        "shot": ["画面:", "分镜:", "镜头描述:"],
        "unit": ["台词:", "旁白:", "文案:", "字幕:"],
        "notes": ["备注:", "说明:"],
        "duration": ["时长:"],
        "outline": ["场景:", "镜头:", "段落:"],
    }

    def match_prefix(line: str) -> Optional[tuple[str, str]]:
        for category, pfxs in prefixes.items():
            for pfx in pfxs:
                if line.startswith(pfx):
                    return (category, line[len(pfx):].strip())
        return None

    def append_unit(text_val: str):
        nonlocal current_unit, pending_outline
        chunks = split_long_text(text_val)
        for chunk in chunks:
            current_unit = {
                "outline": pending_outline or chunk[:16],
                "text": chunk,
                "intent": chunk[:30],
                "duration": 8,
                "notes": "",
                "status": "待编辑",
                "shots": [{
                    "description": chunk[:30],
                    "duration": 8,
                    "notes": "",
                }],
            }
            units.append(current_unit)
            pending_outline = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        matched = match_prefix(stripped)

        if matched:
            category, content = matched
            if category == "unit":
                append_unit(content)
            elif category == "shot" and current_unit:
                current_unit["shots"].append({
                    "description": content,
                    "duration": 8,
                    "notes": "",
                })
                current_unit["intent"] = content
            elif category == "notes" and current_unit and current_unit["shots"]:
                current_unit["shots"][-1]["notes"] = content
                current_unit["notes"] = content
            elif category == "duration" and current_unit and current_unit["shots"]:
                dur = parse_duration(content)
                current_unit["shots"][-1]["duration"] = dur
                current_unit["duration"] = dur
            elif category == "outline":
                pending_outline = content
        else:
            # 检测制表符/竖线分隔表格
            if "\t" in stripped or "|" in stripped:
                rows = [[c.strip() for c in line.split("\t" if "\t" in line else "|")] for line in lines]
                table_units = units_from_table(rows)
                if table_units:
                    return table_units
            # 普通文本行
            append_unit(stripped)

    return units


def parse_script_text(text: str, source_type: str = "paste") -> list[dict]:
    """解析脚本文本，返回单元列表。

    自动检测是表格还是纯文本。
    """
    if not text or not text.strip():
        return []

    if source_type == "paste":
        return units_from_plain_text(text)
    elif source_type == "spreadsheet":
        # CSV/TSV 解析
        import csv
        import io
        delimiter = "\t" if "\t" in text else ("," if "," in text else "\t")
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = [list(row) for row in reader]
        return units_from_table(rows)

    return []

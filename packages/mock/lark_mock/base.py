"""base +record-list：读调研表夹具（tests/fixtures/survey.json）。

--filter-json 用真 CLI 的 view filter 形状：
    {"logic": "and", "conditions": [["邮箱", "==", "herui@example.com"]]}
字段名两个都认：夹具的英文键（email / submitted_at）与表列的中文名（邮箱 / 提交时间），
answers 里的键直接按列名查。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import fixtures
from .envelope import Result, usage_error

ALIASES = {"邮箱": "email", "提交时间": "submitted_at"}


def _field_value(record: dict, field: str):
    key = ALIASES.get(field, field)
    if key in record:
        return record[key]
    answers = record.get("answers") or {}
    if field in answers:
        return answers[field]
    if key in answers:
        return answers[key]
    return None


def _match(record: dict, conditions: list) -> bool:
    for cond in conditions:
        if not (isinstance(cond, list) and len(cond) == 3):
            usage_error("每个条件要是三元组 [字段, 运算符, 值]", param="--filter-json")
        field, op, expected = cond
        actual = _field_value(record, field)
        if actual is None:
            return False
        if op in ("==", "intersects"):
            if isinstance(expected, list):
                pool = actual if isinstance(actual, list) else [actual]
                hit = any(v in expected for v in pool)
            else:
                hit = actual == expected
        else:
            usage_error(f"mock 只支持 == / intersects，不支持 {op!r}", param="--filter-json")
        if not hit:
            return False
    return True


def _markdown(items: list[dict]) -> str:
    if not items:
        return "(no records)"
    cols: list[str] = []
    for it in items:
        for k in it["fields"]:
            if k not in cols:
                cols.append(k)

    def cell(v) -> str:
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    lines = ["| " + " | ".join(cols) + " |",
             "| " + " | ".join("---" for _ in cols) + " |"]
    for it in items:
        lines.append("| " + " | ".join(cell(it["fields"].get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def record_list(flags: dict) -> Result:
    if not flags.get("base-token"):
        usage_error('required flag(s) "base-token" not set', param="--base-token")
    if not flags.get("table-id"):
        usage_error('required flag(s) "table-id" not set', param="--table-id")

    records = fixtures.read_json("survey.json")

    conditions: list = []
    raw = flags.get("filter-json")
    if raw:
        text = Path(raw[1:]).read_text(encoding="utf-8") if raw.startswith("@") else raw
        try:
            spec = json.loads(text)
        except json.JSONDecodeError as e:
            usage_error(f"--filter-json 不是合法 JSON: {e}", param="--filter-json")
        logic = spec.get("logic", "and")
        if logic != "and":
            usage_error(f"mock 只支持 logic=and，不支持 {logic!r}", param="--filter-json")
        conditions = spec.get("conditions") or []

    keep = [ALIASES.get(f, f) for f in flags.get("field-id") or []]

    items = []
    for i, rec in enumerate(records):
        if not _match(rec, conditions):
            continue
        fields = {k: v for k, v in rec.items() if k in keep} if keep else dict(rec)
        items.append({"record_id": f"rec-{i + 1:04d}", "fields": fields})

    total = len(items)
    offset = flags.get("offset") or 0
    limit = flags.get("limit") or 100
    page = items[offset:offset + limit]
    data = {"items": page, "total": total, "offset": offset,
            "has_more": offset + len(page) < total}
    return Result(data, table=_markdown(page))

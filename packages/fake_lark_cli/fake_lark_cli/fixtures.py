"""夹具根、形状规则与读写——「假平台」的全部知识，一份。

在 ``packages/fake_lark_cli/fake_lark_cli`` 里：

- **形状规则**：夹具记录 → 飞书负载的归一化、``list:<n>`` 切页、表记录的字段匹配
  （假 lark-cli 与资源层替身共用同一份）
- **读写**：夹具根（``LARK_MOCK_FIXTURES`` 可换）、按文件夹读邮件、按 id 找信、写 outbox

夹具形状：

    mail/<文件夹>.json     邮件：message_id / sender / recipient / subject / body / date / attachments
    attachments/<文件名>   附件原件
    group_members.json     群成员邮箱
    im/ vc/ task/ drive/   会话、会议、任务、文档（见 packages/fake_lark_cli/README.md）
    survey.json            调研表记录
    outbox/                发出去的邮件
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def root() -> Path:
    """夹具根：环境变量 LARK_MOCK_FIXTURES 可换（smoke 用它指到临时目录）。"""
    env = os.environ.get("LARK_MOCK_FIXTURES")
    return Path(env) if env else DEFAULT_ROOT


def read_json(*parts: str):
    with open(root().joinpath(*parts), encoding="utf-8") as f:
        return json.load(f)


def read_optional(*parts: str):
    """存在就读，不存在回 None——资源类夹具按「这个资源还没有数据」处理，不报错。"""
    path = root().joinpath(*parts)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def mail_folder(folder: str) -> list[dict]:
    """某个文件夹的邮件。夹具里没有这个文件夹就按空文件夹处理。"""
    return read_optional("mail", folder_file(folder)) or []


def find_messages(message_ids: list[str]) -> dict[str, dict]:
    """按 message_id 在所有邮件夹具里找（mail/ 各文件夹 + outbox/）。"""
    wanted = set(message_ids)
    found: dict[str, dict] = {}
    for path in sorted((root() / "mail").glob("*.json")):
        for rec in json.loads(path.read_text(encoding="utf-8")):
            mid = rec.get("message_id")
            if mid in wanted and mid not in found:
                found[mid] = {**rec, "_folder": path.stem}
    outbox = root() / "outbox"
    if outbox.exists():
        for path in sorted(outbox.glob("*.json")):
            rec = json.loads(path.read_text(encoding="utf-8"))
            if rec.get("message_id") in wanted:
                found.setdefault(rec["message_id"], {**rec, "_folder": "outbox"})
    return found


def slug(email: str) -> str:
    """邮箱 → 文件名片段。夹具层与资源层共用一份，同一封发信走到哪 message_id 都相同。"""
    local, _, _domain = email.partition("@")
    digest = 0
    for ch in email:
        digest = (digest * 131 + ord(ch)) % 0xFFFFFF
    return f"{local}_{digest:06x}"


def write_outbox(record: dict) -> Path:
    outbox = root() / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    path = outbox / (record["message_id"] + ".json")
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ── 形状规则（夹具记录 → 飞书负载）─────────────────────────
FOLDER_ALIASES = {"inbox": "收件箱", "INBOX": "收件箱", "spam": "Spam"}
TABLE_ALIASES = {"邮箱": "email", "提交时间": "submitted_at"}


def folder_file(folder: str) -> str:
    """文件夹名 → 夹具文件名。"""
    return re.sub(r"[^\w\u4e00-\u9fff]+", "-", folder).strip("-") + ".json"


def page_of(items: list, token: str | None, size: int) -> tuple[list, bool, str]:
    """游标切片：``list:<n>`` 表示从第 n 条起。真 CLI 的游标是服务端不透明串，
    mock 只能用位置模拟——形状对齐、语义近似（见 packages/fake_lark_cli/README.md）。"""
    start = 0
    if token:
        if not str(token).startswith("list:"):
            from .envelope import usage_error
            usage_error("mock 只实现了 list: 前缀的游标", param="--page-token")
        start = int(str(token)[len("list:"):])
    page = list(items[start:start + size])
    has_more = start + len(page) < len(items)
    return page, has_more, (f"list:{start + len(page)}" if has_more else "")


def normalize_mail(rec: dict, message_id: str, want_html: bool) -> dict:
    """夹具记录 → ``mail +messages`` 的归一化字段（见 lark-mail-message.md 字段说明）。"""
    sender = rec.get("sender", "")
    recipient = rec.get("recipient") or rec.get("to") or ""
    body = rec.get("body", "")
    date = rec.get("date", "")
    try:
        date_ms = int(datetime.strptime(date, "%Y-%m-%d").timestamp() * 1000)
    except (ValueError, TypeError):
        date_ms = 0
    sent = "sender" not in rec          # outbox 里的记录没有 sender，是发出去的
    out = {
        "message_id": message_id,
        "thread_id": f"mock-thread-{message_id}",
        "subject": rec.get("subject", ""),
        "head_from": {"mail_address": sender, "name": ""},
        "to": [{"mail_address": recipient, "name": ""}] if recipient else [],
        "date": date_ms,
        "date_formatted": date,
        "folder_id": rec.get("_folder", ""),
        "message_state": 2 if sent else 1,
        "message_state_text": "sent" if sent else "received",
        "body_plain_text": body,
        "body_preview": body[:100],
        "attachments": [
            {"id": f"{message_id}-att-{i}", "filename": name,
             "content_type": "text/plain", "attachment_type": 1, "is_inline": False}
            for i, name in enumerate(rec.get("attachments") or [])
        ],
    }
    if want_html:
        out["body_html"] = body
    return out


def value_of(record: dict, field: str):
    """表记录取字段：英文键、中文列名、answers 里的键都认。"""
    key = TABLE_ALIASES.get(field, field)
    if key in record:
        return record[key]
    answers = record.get("answers") or {}
    return answers.get(field, answers.get(key))


def match_record(record: dict, conditions: list) -> bool:
    """view filter 条件：只支持 == 与 intersects（AND）。"""
    for cond in conditions:
        if not (isinstance(cond, list) and len(cond) == 3):
            raise ValueError("每个条件要是三元组 [字段, 运算符, 值]")
        field, op, expected = cond
        actual = value_of(record, field)
        if actual is None:
            return False
        if op in ("==", "intersects"):
            if isinstance(expected, list):
                pool = actual if isinstance(actual, list) else [actual]
                hit = any(v in expected for v in pool)
            else:
                hit = actual == expected
        else:
            raise ValueError(f"mock 只支持 == / intersects，不支持 {op!r}")
        if not hit:
            return False
    return True

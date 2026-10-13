"""夹具 → 飞书负载的形状规则：一份实现，两边共用。

夹具层的两个使用者（假 lark-cli 与资源层的进程内替身）都要做同样三件事：
把夹具记录归一化成飞书字段、按 ``list:<n>`` 切页、按列名匹配表记录。规则放在这里一份，
两边 import——**改一处不会在另一处漏掉**。

（这两边都是「假平台」，所以共处一室不算作弊；真正要对照的是将来的真 lark-cli，
它走子进程，不在这个过程里。）
"""

from __future__ import annotations

import re
from datetime import datetime

from .envelope import usage_error

FOLDER_ALIASES = {"inbox": "收件箱", "INBOX": "收件箱", "spam": "Spam"}
TABLE_ALIASES = {"邮箱": "email", "提交时间": "submitted_at"}


def folder_file(folder: str) -> str:
    """文件夹名 → 夹具文件名。"""
    return re.sub(r"[^\w\u4e00-\u9fff]+", "-", folder).strip("-") + ".json"


def page_of(items: list, token: str | None, size: int) -> tuple[list, bool, str]:
    """游标切片：``list:<n>`` 表示从第 n 条起。真 CLI 的游标是服务端不透明串，
    mock 只能用位置模拟——形状对齐、语义近似（见 packages/mock/README.md）。"""
    start = 0
    if token:
        if not str(token).startswith("list:"):
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

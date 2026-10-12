"""mail 域的三条命令。输出形状对照 lark-cli skills 的 lark-mail 文档。

- ``+triage``   JSON 负载：messages[] / mailbox_id / count / has_more / page_token
                （字段名照 lark-mail-references/lark-mail-triage.md 的「输出」一节）
- ``+messages`` JSON 负载：messages[] / total / unavailable_message_ids，
                单封字段照 lark-mail-message.md 的「字段说明」
- ``+send``     草稿模式回 draft_id，--confirm-send 回 message_id / thread_id
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from . import fixtures
from .envelope import Result, usage_error


def _load_filter(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        usage_error(f"--filter 不是合法 JSON: {e}", param="--filter")
    if not isinstance(parsed, dict):
        usage_error("--filter 需要一个 JSON 对象", param="--filter")
    return parsed  # type: ignore[return-value]


def triage(flags: dict) -> Result:
    """列邮件摘要。夹具里按文件夹读，翻页游标按位置（list:<下一页起点>）。"""
    folder = "收件箱"
    f = _load_filter(flags.get("filter"))
    if f.get("folder"):
        folder = str(f["folder"])
    folder = fixtures.FOLDER_ALIASES.get(folder, folder)
    msgs = fixtures.mail_folder(folder)

    senders = f.get("from")
    if isinstance(senders, str):
        senders = [senders]
    if senders:
        wanted = {s.lower() for s in senders}
        msgs = [m for m in msgs if m.get("sender", "").lower() in wanted]
    if f.get("subject"):
        msgs = [m for m in msgs if f["subject"] in m.get("subject", "")]
    query = (flags.get("query") or "").lower()
    if query:
        msgs = [m for m in msgs
                if query in (m.get("sender", "") + m.get("subject", "")
                             + m.get("body", "")).lower()]

    token = flags.get("page-token") or ""
    start = 0
    if token:
        if not token.startswith("list:"):
            usage_error("mock 只实现了 list: 前缀的游标", param="--page-token")
        try:
            start = int(token[len("list:"):])
        except ValueError:
            usage_error(f"游标不是 list:<整数>: {token}", param="--page-token")

    limit = flags.get("page-size") or flags.get("max") or 20
    page = msgs[start:start + limit]
    has_more = start + len(page) < len(msgs)
    next_token = f"list:{start + len(page)}" if has_more else ""

    mailbox = flags.get("mailbox") or "me"
    items = [
        {
            "message_id": m["message_id"],
            "mailbox_id": mailbox,
            "date": m.get("date", ""),
            "from": m.get("sender", ""),
            "subject": m.get("subject", ""),
            "labels": folder,
        }
        for m in page
    ]
    data = {
        "messages": items,
        "mailbox_id": mailbox,
        "count": len(items),
        "has_more": has_more,
        "page_token": next_token,
    }

    lines = ["date\tfrom\tsubject\tmessage_id"]
    lines += [f"{i['date']}\t{i['from']}\t{i['subject']}\t{i['message_id']}" for i in items]
    notes = [f"{len(items)} message(s)"]
    if has_more:
        notes.append(f"next page: mail +triage --filter '{{\"folder\": \"{folder}\"}}' "
                     f"--page-token '{next_token}'")
    notes.append("tip: read full content: mail +messages --message-ids <id1>,<id2>")
    return Result(data, table="\n".join(lines), notes=notes)


def _normalize(rec: dict, message_id: str, want_html: bool) -> dict:
    """夹具记录 → +message 同款归一化字段（见 lark-mail-message.md 字段说明）。"""
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


def messages(flags: dict) -> Result:
    """按 message_id 读完整邮件；查不到的进 unavailable_message_ids（真 CLI 同此约定）。"""
    raw = flags.get("message-ids")
    if not raw:
        usage_error('required flag(s) "message-ids" not set', param="--message-ids")
    ids = [x.strip() for x in raw.split(",") if x.strip()]
    found = fixtures.find_messages(ids)
    want_html = flags.get("html") is not False

    items, missing = [], []
    for mid in ids:
        rec = found.get(mid)
        if rec is None:
            missing.append(mid)
        else:
            items.append(_normalize(rec, mid, want_html))
    return Result({"messages": items, "total": len(items),
                   "unavailable_message_ids": missing})


def send(flags: dict) -> Result:
    """发信。默认草稿模式（真 CLI 存草稿，mock 不落盘）；--confirm-send 写 outbox。"""
    to, subject = flags.get("to"), flags.get("subject")
    if not to:
        usage_error('required flag(s) "to" not set', param="--to")
    if not subject:
        usage_error('required flag(s) "subject" not set', param="--subject")
    if flags.get("body") and flags.get("body-file"):
        usage_error("--body 与 --body-file 互斥", param="--body-file")
    body = flags.get("body")
    if flags.get("body-file"):
        path = flags["body-file"]
        if not os.path.exists(path):
            usage_error(f"找不到正文文件: {path}", param="--body-file")
        with open(path, encoding="utf-8") as f:
            body = f.read()
    if body is None:
        usage_error('required flag(s) "body" not set', param="--body")

    slug = fixtures.slug(to)
    message_id = f"mock-{slug}-{subject[:12].replace(' ', '')}"
    if not flags.get("confirm-send"):
        return Result({"draft_id": f"mock-draft-{slug}",
                       "tip": "mock 不落草稿：加 --confirm-send 才写 tests/fixtures/outbox/"})

    attachments = [os.path.basename(p.strip())
                   for p in (flags.get("attach") or "").split(",") if p.strip()]
    fixtures.write_outbox({"message_id": message_id, "to": to, "subject": subject,
                           "body": body, "attachments": attachments})
    return Result({"message_id": message_id, "thread_id": f"mock-thread-{message_id}"})

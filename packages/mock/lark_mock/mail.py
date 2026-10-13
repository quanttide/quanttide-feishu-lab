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

from . import fixtures, shapes
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

    limit = flags.get("page-size") or flags.get("max") or 20
    page, has_more, next_token = shapes.page_of(msgs, flags.get("page-token"), limit)

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
    """夹具记录 → +message 归一化字段（规则在 shapes.py，一份）。"""
    return shapes.normalize_mail(rec, message_id, want_html)


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


def attachments_download(flags: dict) -> Result:
    """``mail user_mailbox.message.attachments download_url``：回附件下载地址。

    mock 不真下载：download_url 指到夹具里同名文件的 ``file://`` 地址，能力层按同一
    协议取文件——真飞书回 https 地址，取法只差一层 URL 解析。
    附件 id 与 ``+messages`` 的归一化规则一致（``<message_id>-att-<序号>``）。
    """
    mid = flags.get("message-id")
    if not mid:
        usage_error('required flag(s) "message-id" not set', param="--message-id")
    wanted = [x.strip() for x in (flags.get("attachment-ids") or "").split(",") if x.strip()]
    rec = fixtures.find_messages([mid]).get(mid)
    if rec is None:
        usage_error(f"message not found: {mid}", subtype="not_found")

    items = []
    for i, name in enumerate(rec.get("attachments") or []):
        aid = f"{mid}-att-{i}"
        if wanted and aid not in wanted:
            continue
        path = fixtures.root() / "attachments" / name
        items.append({
            "attachment_id": aid,
            "filename": name,
            "mailbox_id": flags.get("user-mailbox-id") or flags.get("mailbox") or "me",
            "download_url": path.as_uri() if path.exists() else "",
        })
    return Result({"attachments": items, "total": len(items)})

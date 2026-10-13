"""资源层测试替身：读夹具目录，按同一套路径落盘，零外部 IO。

与 ``feishu/mock.py`` 一样是**进程内测试替身**：它不替代 CLI 层假 lark-cli，
两者读同一批夹具、互相对照（``scripts/smoke_resources.py`` 逐项核两层负载一致）。

夹具（tests/fixtures/）：

    mail/<文件夹>.json           邮件：message_id / sender / recipient / subject / body / date / attachments
    attachments/<文件名>         附件原件
    group_members.json           群成员邮箱
    im/chat-<chat_id>.json       群消息
    im/p2p-<user_id>.json        单聊消息
    im/search-sender-<id>.json   按发言人搜到的消息
    im/search-at-<id>.json       被 @ 到的消息
    vc/search-<participant>.json 会议列表
    vc/meeting-<meeting_id>.json 会议详情
    task/<scope>.json            任务（my-tasks / related-tasks / tasklists）
    drive/search.json            文档变更
    drive/doc-<token>.json       文档正文
    survey.json                  调研表记录

负载形状与假 lark-cli 的 ``data`` 一致——这样「换实现不换结果」才可断言。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from ..resources import Attachment, Page
from ..resources.store import RawStore

FOLDER_ALIASES = {"inbox": "收件箱", "INBOX": "收件箱", "spam": "Spam"}
TABLE_ALIASES = {"邮箱": "email", "提交时间": "submitted_at"}
REQUEST_SEQ = 1     # 单次调用落一份响应：页序由 store 续排


def _folder_file(folder: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "-", folder).strip("-") + ".json"


def _page(items: list, token: str | None, size: int) -> tuple[list, bool, str]:
    """与假 lark-cli 的 fixtures.page_of 同一套切片语义（list:<n> 游标）。"""
    start = int(str(token)[len("list:"):]) if token else 0
    page = list(items[start:start + size])
    has_more = start + len(page) < len(items)
    return page, has_more, (f"list:{start + len(page)}" if has_more else "")


class MockResources:
    """资源层契约的夹具实现。每个动作落一份原样响应，附件落原文件。"""

    def __init__(self, store_root: str, fixtures_dir: str) -> None:
        self.store = RawStore(store_root)
        self.fixtures = Path(fixtures_dir)

    # ── 内部 ──────────────────────────────────────────────
    def _read(self, *parts: str):
        path = self.fixtures.joinpath(*parts)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _land(self, resource: str, action: str, data: dict,
              has_more: bool = False, page_token: str = "") -> Page:
        """落一份原样响应（信封 + 负载），返回 Page。写盘的是它，不是加工后的东西。"""
        raw = {"ok": True, "data": data}
        self.store.save_response(resource, action, raw)
        return Page(resource=resource, action=action, payload=data,
                    has_more=has_more, page_token=page_token, raw=raw)

    def _mail_records(self) -> list[dict]:
        records: list[dict] = []
        mail_dir = self.fixtures / "mail"
        for path in sorted(mail_dir.glob("*.json")) if mail_dir.exists() else []:
            for rec in json.loads(path.read_text(encoding="utf-8")):
                records.append({**rec, "_folder": path.stem})
        return records

    # ── mail ─────────────────────────────────────────────
    def mail_list(self, *, mailbox: str | None = None, folder: str | None = None,
                  query: str | None = None, page_size: int = 400,
                  page_token: str | None = None) -> Page:
        mailbox = mailbox or "me"
        name = FOLDER_ALIASES.get(folder or "收件箱", folder or "收件箱")
        msgs = self._read("mail", _folder_file(name)) or []
        if query:
            q = query.lower()
            msgs = [m for m in msgs
                    if q in (m.get("sender", "") + m.get("subject", "") + m.get("body", "")).lower()]
        page, has_more, token = _page(msgs, page_token, page_size)
        items = [{"message_id": m["message_id"], "mailbox_id": mailbox,
                  "date": m.get("date", ""), "from": m.get("sender", ""),
                  "subject": m.get("subject", ""), "labels": name} for m in page]
        return self._land("mail", "list", {
            "messages": items, "mailbox_id": mailbox, "count": len(items),
            "has_more": has_more, "page_token": token}, has_more, token)

    def mail_messages(self, *, message_ids: list[str], mailbox: str | None = None,
                      html: bool = True) -> Page:
        by_id = {r["message_id"]: r for r in self._mail_records()}
        items, missing = [], []
        for mid in message_ids:
            rec = by_id.get(mid)
            if rec is None:
                missing.append(mid)
            else:
                items.append(_normalize_mail(rec, mid, html))
        return self._land("mail", "messages", {
            "messages": items, "total": len(items), "unavailable_message_ids": missing})

    def mail_attachment_download(self, *, message_id: str, attachment_ids: list[str],
                                 mailbox: str | None = None) -> list[Attachment]:
        mailbox = mailbox or "me"
        rec = {r["message_id"]: r for r in self._mail_records()}.get(message_id)
        if rec is None:
            raise RuntimeError(f"邮箱 {mailbox} 里没有这封信：{message_id}")
        items, landed = [], []
        for i, name in enumerate(rec.get("attachments") or []):
            aid = f"{message_id}-att-{i}"
            if attachment_ids and aid not in attachment_ids:
                continue
            src = self.fixtures / "attachments" / name
            data = src.read_bytes() if src.exists() else b""
            path = self.store.save_attachment(aid, name, data)
            landed.append(Attachment(attachment_id=aid, filename=name, path=str(path)))
            items.append({"attachment_id": aid, "filename": name, "mailbox_id": mailbox,
                          "download_url": src.as_uri() if src.exists() else ""})
        self._land("mail", "attachments", {"attachments": items, "total": len(items)})
        return landed

    # ── im ───────────────────────────────────────────────
    def im_chat_messages(self, *, chat_id: str | None = None, user_id: str | None = None,
                         order: str = "asc", with_reactions: bool = True,
                         page_size: int = 50, page_token: str | None = None) -> Page:
        if not chat_id and not user_id:
            raise RuntimeError("im_chat_messages 需要 chat_id 或 user_id")
        name = f"chat-{chat_id}.json" if chat_id else f"p2p-{user_id}.json"
        payload = self._read("im", name) or {}
        page, has_more, token = _page(list(payload.get("messages") or []), page_token, page_size)
        if not with_reactions:
            page = [{k: v for k, v in m.items() if k != "reactions"} for m in page]
        if order == "desc":
            page = list(reversed(page))
        return self._land("im", "chat-messages", {
            "messages": page, "has_more": has_more, "page_token": token}, has_more, token)

    def im_chat_members(self, *, chat_id: str | None = None,
                        page_token: str | None = None) -> Page:
        emails = self._read("group_members.json") or []
        users = [{"member_id": e, "member_id_type": "email",
                  "name": e.partition("@")[0]} for e in emails]
        return self._land("im", "chat-members",
                          {"users": users, "bots": [], "truncations": []})

    def im_messages_search(self, *, sender: str | None = None, at_chatter: str | None = None,
                           chat_id: str | None = None, with_reactions: bool = False,
                           page_size: int = 50, page_token: str | None = None) -> Page:
        if not sender and not at_chatter:
            raise RuntimeError("im_messages_search 需要 sender 或 at_chatter")
        name = f"search-sender-{sender}.json" if sender else f"search-at-{at_chatter}.json"
        payload = self._read("im", name) or {}
        page, has_more, token = _page(list(payload.get("items") or []), page_token, page_size)
        if not with_reactions:
            page = [{k: v for k, v in m.items() if k != "reactions"} for m in page]
        return self._land("im", "messages-search", {
            "items": page, "has_more": has_more, "page_token": token}, has_more, token)

    # ── vc ───────────────────────────────────────────────
    def vc_meeting_search(self, *, participant_id: str | None = None, start: str | None = None,
                          end: str | None = None, page_size: int = 30,
                          page_token: str | None = None) -> Page:
        payload = self._read("vc", f"search-{participant_id}.json") or {}
        page, has_more, token = _page(list(payload.get("items") or []), page_token, page_size)
        return self._land("vc", "meeting-search", {
            "items": page, "has_more": has_more, "page_token": token}, has_more, token)

    def vc_meeting_get(self, *, meeting_id: str) -> Page:
        payload = self._read("vc", f"meeting-{meeting_id}.json") or {}
        return self._land("vc", "meeting-get", payload)

    # ── task ─────────────────────────────────────────────
    def task_list(self, *, scope: str = "mine", complete: bool | None = None,
                  page_size: int = 50, page_token: str | None = None) -> Page:
        filename = {"mine": "my-tasks.json", "related": "related-tasks.json",
                    "tasklists": "tasklists.json"}[scope]
        payload = self._read("task", filename) or {}
        items = list(payload.get("items") or [])
        if complete is not None:
            items = [i for i in items if bool(i.get("completed")) is complete]
        page, has_more, token = _page(items, page_token, page_size)
        return self._land("task", scope, {
            "items": page, "has_more": has_more, "page_token": token}, has_more, token)

    # ── doc ──────────────────────────────────────────────
    def drive_search(self, *, edited_since: str | None = None, created_since: str | None = None,
                     page_size: int = 20, page_token: str | None = None) -> Page:
        since = edited_since or created_since
        if not since:
            raise RuntimeError("drive_search 需要 edited_since 或 created_since")
        payload = self._read("drive", "search.json") or {}
        items = [i for i in payload.get("items") or []
                 if (i.get("edited_time") or "") >= since or (i.get("created_time") or "") >= since]
        page, has_more, token = _page(items, page_token, page_size)
        return self._land("doc", "drive-search", {
            "items": page, "has_more": has_more, "page_token": token}, has_more, token)

    def docs_fetch(self, *, doc: str, detail: str = "simple",
                   doc_format: str = "markdown") -> Page:
        payload = dict(self._read("drive", f"doc-{doc}.json") or {})
        payload["detail"] = detail
        payload["doc_format"] = doc_format
        return self._land("doc", "docs-fetch", payload)

    # ── base ─────────────────────────────────────────────
    def base_records(self, *, base_token: str | None = None, table_id: str | None = None,
                     filter_json: str | None = None, offset: int = 0,
                     limit: int = 100) -> Page:
        records = self._read("survey.json") or []
        conditions = json.loads(filter_json).get("conditions") or [] if filter_json else []
        items = []
        for i, rec in enumerate(records):
            if not _match(rec, conditions):
                continue
            items.append({"record_id": f"rec-{i + 1:04d}", "fields": dict(rec)})
        total = len(items)
        page = items[offset:offset + limit]
        return self._land("base", "record-list", {
            "items": page, "total": total, "offset": offset,
            "has_more": offset + len(page) < total})


def _normalize_mail(rec: dict, message_id: str, want_html: bool) -> dict:
    """夹具记录 → ``mail +messages`` 的归一化字段（与假 lark-cli 的 _normalize 同规则）。"""
    sender = rec.get("sender", "")
    recipient = rec.get("recipient") or rec.get("to") or ""
    body = rec.get("body", "")
    date = rec.get("date", "")
    try:
        date_ms = int(datetime.strptime(date, "%Y-%m-%d").timestamp() * 1000)
    except (ValueError, TypeError):
        date_ms = 0
    sent = "sender" not in rec
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


def _value(record: dict, field: str):
    key = TABLE_ALIASES.get(field, field)
    if key in record:
        return record[key]
    answers = record.get("answers") or {}
    return answers.get(field, answers.get(key))


def _match(record: dict, conditions: list) -> bool:
    for cond in conditions:
        if not (isinstance(cond, list) and len(cond) == 3):
            raise RuntimeError("每个条件要是三元组 [字段, 运算符, 值]")
        field, op, expected = cond
        actual = _value(record, field)
        if actual is None:
            return False
        if op in ("==", "intersects"):
            if isinstance(expected, list):
                pool = actual if isinstance(actual, list) else [actual]
                hit = any(v in expected for v in pool)
            else:
                hit = actual == expected
        else:
            raise RuntimeError(f"mock 只支持 == / intersects，不支持 {op!r}")
        if not hit:
            return False
    return True

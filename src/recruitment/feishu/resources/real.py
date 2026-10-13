"""资源层真实现：子进程调 lark-cli（canonical 实现）。

同一份代码两种活法，差别只在 PATH：

    PATH 前面放 packages/mock/bin  → 假 lark-cli，读 tests/fixtures/，离线
    PATH 里是真 lark-cli           → 打真飞书

值全部从参数与环境来，代码里不写任何邮箱、群 id、人名、关键词：

    LARK_CLI            命令名（默认 lark-cli）
    LARK_BASE_TOKEN     多维表格 base（默认 mock-base-token）
    LARK_TABLE_ID       表（默认 mock-table-id）
    LARK_CHAT_ID        群（默认 oc_mock_chat）
    LARK_MAILBOX        邮箱（默认 me）

落盘与夹具实现同一套路径（见 store.py）：每页一份原样响应，附件落原文件。
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from urllib.parse import urlparse

from ..resources import Attachment, Page
from ..resources.store import RawStore


def _extract_json(text: str) -> dict | None:
    """从输出里抠 JSON。真 lark-cli 会在 JSON 前后打进度行，直接 loads 会失败。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


class CLIResources:
    """资源层契约的 lark-cli 实现：命令只活在这里，落盘走 RawStore。"""

    def __init__(self, store_root: str, *, lark_cli: str | None = None, mailbox: str | None = None,
                 base_token: str | None = None, table_id: str | None = None,
                 chat_id: str | None = None) -> None:
        self.store = RawStore(store_root)
        self.lark_cli = lark_cli or os.environ.get("LARK_CLI", "lark-cli")
        self.mailbox = mailbox or os.environ.get("LARK_MAILBOX", "me")
        self.base_token = base_token or os.environ.get("LARK_BASE_TOKEN", "mock-base-token")
        self.table_id = table_id or os.environ.get("LARK_TABLE_ID", "mock-table-id")
        self.chat_id = chat_id or os.environ.get("LARK_CHAT_ID", "oc_mock_chat")

    # ── 内部 ──────────────────────────────────────────────
    def _run(self, *args: str) -> tuple[dict, dict]:
        """跑一条命令，回（负载, 原样信封）。信封就是你写进 raw/ 的那份东西。"""
        try:
            p = subprocess.run([self.lark_cli, *args], capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError(
                f"找不到 {self.lark_cli}：PATH 里没有。离线自测先把 packages/mock/bin 放到 PATH 前面"
            ) from None
        text = p.stdout if p.returncode == 0 else p.stderr
        payload = _extract_json(text)
        if payload is None:
            raise RuntimeError(f"{self.lark_cli} {' '.join(args)} 输出不是 JSON：{text.strip()[:200]}")
        if p.returncode != 0 or not payload.get("ok"):
            err = payload.get("error") or {}
            raise RuntimeError(f"{self.lark_cli} {' '.join(args[:2])} 失败："
                               f"{err.get('message') or text.strip()[:200]}")
        return payload.get("data") or {}, payload

    def _land(self, resource: str, action: str, raw: dict) -> Page:
        data = raw.get("data") or {}
        self.store.save_response(resource, action, raw)
        return Page(resource=resource, action=action, payload=data,
                    has_more=bool(data.get("has_more")), page_token=data.get("page_token") or "",
                    raw=raw)

    def _fetch_bytes(self, url: str) -> bytes:
        """download_url → 字节。file:// 与 https 一视同仁。"""
        parsed = urlparse(url)
        if parsed.scheme in ("", "file"):
            path = urllib.request.url2pathname(parsed.path) if parsed.scheme else url
            with open(path, "rb") as f:
                return f.read()
        with urllib.request.urlopen(url) as resp:      # noqa: S310 (平台地址来自 lark-cli)
            return resp.read()

    # ── mail ─────────────────────────────────────────────
    def mail_list(self, *, mailbox: str | None = None, folder: str | None = None,
                  query: str | None = None, page_size: int = 400,
                  page_token: str | None = None) -> Page:
        args = ["mail", "+triage", "--mailbox", mailbox or self.mailbox,
                "--max", str(page_size), "--format", "json"]
        if folder:
            args += ["--filter", json.dumps({"folder": folder}, ensure_ascii=False)]
        if query:
            args += ["--query", query]
        if page_token:
            args += ["--page-token", page_token]
        data, raw = self._run(*args)
        return self._land("mail", "list", raw)

    def mail_messages(self, *, mailbox: str | None = None, message_ids: list[str],
                      html: bool = True) -> Page:
        args = ["mail", "+messages", "--message-ids", ",".join(message_ids),
                "--mailbox", mailbox or self.mailbox, "--format", "json"]
        if not html:
            args += ["--html=false"]
        data, raw = self._run(*args)
        return self._land("mail", "messages", raw)

    def mail_attachment_download(self, *, mailbox: str | None = None, message_id: str,
                                 attachment_ids: list[str]) -> list[Attachment]:
        args = ["mail", "user_mailbox.message.attachments", "download_url",
                "--user-mailbox-id", mailbox or self.mailbox,
                "--message-id", message_id, "--format", "json"]
        if attachment_ids:
            args += ["--attachment-ids", ",".join(attachment_ids)]
        data, raw = self._run(*args)
        landed: list[Attachment] = []
        for att in data.get("attachments") or []:
            aid = att.get("attachment_id") or att.get("id") or ""
            name = att.get("filename") or aid
            url = att.get("download_url") or ""
            blob = self._fetch_bytes(url) if url else b""
            path = self.store.save_attachment(aid, name, blob)
            landed.append(Attachment(attachment_id=aid, filename=name, path=str(path)))
        # 信封也要落 —— 落的是「回了什么」，附件字节落 attachments/
        self._land("mail", "attachments", raw)
        return landed

    # ── im ───────────────────────────────────────────────
    def im_chat_messages(self, *, chat_id: str | None = None, user_id: str | None = None,
                         order: str = "asc", with_reactions: bool = True,
                         page_size: int = 50, page_token: str | None = None) -> Page:
        if not chat_id and not user_id:
            raise RuntimeError("im_chat_messages 需要 chat_id 或 user_id")
        args = ["im", "+chat-messages-list", "--page-size", str(page_size),
                "--order", order, "--format", "json"]
        if chat_id:
            args += ["--chat-id", chat_id]
        else:
            args += ["--user-id", user_id, "--as", "user"]
        if not with_reactions:
            args += ["--no-reactions"]
        if page_token:
            args += ["--page-token", page_token]
        data, raw = self._run(*args)
        return self._land("im", "chat-messages", raw)

    def im_chat_members(self, *, chat_id: str | None = None,
                        page_token: str | None = None) -> Page:
        args = ["im", "+chat-members-list", "--chat-id", chat_id or self.chat_id,
                "--page-all", "--format", "json"]
        if page_token:
            args += ["--page-token", page_token]
        data, raw = self._run(*args)
        return self._land("im", "chat-members", raw)

    def im_messages_search(self, *, sender: str | None = None, at_chatter: str | None = None,
                           chat_id: str | None = None, with_reactions: bool = False,
                           page_size: int = 50, page_token: str | None = None) -> Page:
        if not sender and not at_chatter:
            raise RuntimeError("im_messages_search 需要 sender 或 at_chatter")
        args = ["im", "+messages-search", "--as", "user",
                "--page-size", str(page_size), "--format", "json"]
        if sender:
            args += ["--sender", sender]
        if at_chatter:
            args += ["--at-chatter-ids", at_chatter]
        if chat_id:
            args += ["--chat-id", chat_id]
        if not with_reactions:
            args += ["--no-reactions"]
        if page_token:
            args += ["--page-token", page_token]
        data, raw = self._run(*args)
        return self._land("im", "messages-search", raw)

    # ── vc ───────────────────────────────────────────────
    def vc_meeting_search(self, *, participant_id: str | None = None, start: str | None = None,
                          end: str | None = None, page_size: int = 30,
                          page_token: str | None = None) -> Page:
        if not participant_id:
            raise RuntimeError("vc_meeting_search 需要 participant_id")
        args = ["vc", "+search", "--as", "user", "--participant-ids", participant_id,
                "--page-size", str(page_size), "--format", "json"]
        if start:
            args += ["--start", start]
        if end:
            args += ["--end", end]
        if page_token:
            args += ["--page-token", page_token]
        data, raw = self._run(*args)
        return self._land("vc", "meeting-search", raw)

    def vc_meeting_get(self, *, meeting_id: str) -> Page:
        data, raw = self._run("vc", "meeting", "get", "--meeting-id", meeting_id,
                              "--with-participants", "true", "--format", "json")
        return self._land("vc", "meeting-get", raw)

    # ── task ─────────────────────────────────────────────
    def task_list(self, *, scope: str = "mine", complete: bool | None = None,
                  page_size: int = 50, page_token: str | None = None) -> Page:
        if scope == "tasklists":
            args = ["task", "tasklists", "list", "--as", "user", "--page-all", "--format", "json"]
        else:
            command = "+get-my-tasks" if scope == "mine" else "+get-related-tasks"
            args = ["task", command, "--page-all", "--format", "json"]
            if complete is not None:
                args += [f"--complete={'true' if complete else 'false'}"]
        if page_token:
            args += ["--page-token", page_token]
        data, raw = self._run(*args)
        return self._land("task", scope, raw)

    # ── doc ──────────────────────────────────────────────
    def drive_search(self, *, edited_since: str | None = None, created_since: str | None = None,
                     page_size: int = 20, page_token: str | None = None) -> Page:
        if not (edited_since or created_since):
            raise RuntimeError("drive_search 需要 edited_since 或 created_since")
        args = ["drive", "+search", "--page-size", str(page_size), "--format", "json"]
        if edited_since:
            args += ["--edited-since", edited_since]
        if created_since:
            args += ["--created-since", created_since]
        if page_token:
            args += ["--page-token", page_token]
        data, raw = self._run(*args)
        return self._land("doc", "drive-search", raw)

    def docs_fetch(self, *, doc: str, detail: str = "simple",
                   doc_format: str = "markdown") -> Page:
        data, raw = self._run("docs", "+fetch", "--doc", doc, "--detail", detail,
                              "--doc-format", doc_format, "--format", "json")
        return self._land("doc", "docs-fetch", raw)

    # ── base ─────────────────────────────────────────────
    def base_records(self, *, base_token: str | None = None, table_id: str | None = None,
                     filter_json: str | None = None, offset: int = 0,
                     limit: int = 100) -> Page:
        args = ["base", "+record-list", "--base-token", base_token or self.base_token,
                "--table-id", table_id or self.table_id,
                "--offset", str(offset), "--limit", str(limit), "--format", "json"]
        if filter_json:
            args += ["--filter-json", filter_json]
        data, raw = self._run(*args)
        return self._land("base", "record-list", raw)

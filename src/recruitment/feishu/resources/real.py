"""资源层真实现：子进程调 lark-cli（canonical 实现）。

同一份代码两种活法，差别只在 PATH：

    PATH 前面放 packages/mock/bin  → 假 lark-cli，读 tests/fixtures/，离线
    PATH 里是真 lark-cli           → 打真飞书

命令只写在 ``ACTIONS`` 这张表里（动作 → 资源 / 固定命令段 / 参数名 / flag 与值的改写），
拼 argv、解信封、落盘由 ``_call`` 一次做完。加一个动作 = 表里加一行 + 契约里加一个方法。

值全部从参数与环境来，代码里不写任何邮箱、群 id、人名、关键词：

    LARK_CLI / LARK_MAILBOX / LARK_BASE_TOKEN / LARK_TABLE_ID / LARK_CHAT_ID
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from urllib.parse import urlparse

from ..resources import Attachment, Page
from ..resources.store import RawStore

# 动作表：动作名 → (资源, 落盘动作名, 固定命令段, 参数名, flag 改写, 值改写)
# 落盘动作名就是 raw/<资源>/<这个名字>/<页序>.json——短名，不与资源重复
# 值改写（没写就是原样 --<参数名，下划线换中划线>）：
#   json_folder  值包成 {"folder": <值>} 再 json       join        列表拼逗号串
#   invert       值为假才带那个否定 flag（with_reactions=False → --no-reactions）
#   bool_text    布尔渲染成 true / false 文字          user_id     带 --user-id <值> --as user
#   only_true    值为真才带（如 --page-all）
#   false_flag   值为假时带 <flag>=false（如 --html=false）   raw      原样传（如 --filter-json）
ACTIONS: dict[str, tuple] = {
    "mail_list": ("mail", "list", ("mail", "+triage"),
                  ("mailbox", "folder", "query", "page_size", "page_token"),
                  {"page_size": "--max", "folder": "--filter"}, {"folder": "json_folder"}),
    "mail_messages": ("mail", "messages", ("mail", "+messages"),
                      ("message_ids", "mailbox", "html"),
                      {"message_ids": "--message-ids"},
                      {"message_ids": "join", "html": "false_flag"}),
    "mail_send": ("mail", "send", ("mail", "+send", "--confirm-send"),
                  ("to", "subject", "body", "mailbox", "attachments"),
                  {"attachments": "--attach"}, {"attachments": "join"}),
    "im_chat_messages": ("im", "chat-messages", ("im", "+chat-messages-list"),
                         ("chat_id", "user_id", "order", "page_size", "with_reactions",
                          "page_token"),
                         {"with_reactions": "--no-reactions"},
                         {"user_id": "user_id", "with_reactions": "invert"}),
    "im_chat_members": ("im", "chat-members", ("im", "+chat-members-list", "--page-all"),
                        ("chat_id", "page_token"), {}, {}),
    "im_messages_search": ("im", "messages-search", ("im", "+messages-search", "--as", "user"),
                           ("sender", "at_chatter", "chat_id", "page_size", "with_reactions",
                            "page_token"),
                           {"at_chatter": "--at-chatter-ids", "with_reactions": "--no-reactions"},
                           {"with_reactions": "invert"}),
    "vc_meeting_search": ("vc", "meeting-search", ("vc", "+search", "--as", "user"),
                          ("participant_id", "start", "end", "page_size", "page_token"),
                          {"participant_id": "--participant-ids"}, {}),
    "vc_meeting_get": ("vc", "meeting-get", ("vc", "meeting", "get", "--with-participants", "true"),
                       ("meeting_id",), {}, {}),
    "task_list": ("task", "mine", ("task",), ("complete", "page_token"),
                  {"complete": "--complete"}, {"complete": "bool_text"}),
    "drive_search": ("doc", "drive-search", ("drive", "+search"),
                     ("edited_since", "created_since", "page_size", "page_token"), {}, {}),
    "docs_fetch": ("doc", "docs-fetch", ("docs", "+fetch"), ("doc", "detail", "doc_format"), {}, {}),
    "base_records": ("base", "record-list", ("base", "+record-list"),
                     ("base_token", "table_id", "filter_json", "offset", "limit"),
                     {}, {"filter_json": "raw"}),
    "mail_attachment_download": ("mail", "attachments", ("mail", "user_mailbox.message.attachments",
                                          "download_url"),
                                 ("mailbox", "message_id", "attachment_ids"),
                                 {"mailbox": "--user-mailbox-id"},
                                 {"attachment_ids": "join"}),
}

# task 的三种取法（我负责 / 与我相关 / 清单）——同一个动作换命令段
TASK_COMMAND = {"mine": ("task", "+get-my-tasks", "--page-all"),
                "related": ("task", "+get-related-tasks", "--page-all"),
                "tasklists": ("task", "tasklists", "list", "--as", "user", "--page-all")}


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


def _emit(args: list[str], name: str, value, flag_of: dict, mode: dict) -> None:
    """把一个参数变成 argv 片段。"""
    flag = flag_of.get(name, "--" + name.replace("_", "-"))
    how = mode.get(name)
    if how == "invert":
        if not value:
            args.append(flag)
    elif value in (None, "", []):
        return
    elif how == "user_id":
        args += ["--user-id", str(value), "--as", "user"]
    elif how == "json_folder":
        args += [flag, json.dumps({"folder": value}, ensure_ascii=False)]
    elif how == "false_flag":
        if not value:
            args.append(f"{flag}=false")
    elif how == "join":
        args += [flag, ",".join(str(v) for v in value)]
    elif how == "bool_text":
        args += [flag, "true" if value else "false"]
    else:
        args += [flag, str(value)]


class CLIResources:
    """资源层契约的 lark-cli 实现：命令在 ACTIONS 表里，落盘走 RawStore。"""

    def __init__(self, store_root: str | None = None, *, lark_cli: str | None = None,
                 mailbox: str | None = None, base_token: str | None = None,
                 table_id: str | None = None, chat_id: str | None = None) -> None:
        self.store = RawStore(store_root) if store_root else None
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
        if self.store:
            self.store.save_response(resource, action, raw)
        return Page(resource=resource, action=action, payload=data,
                    has_more=bool(data.get("has_more")), page_token=data.get("page_token") or "",
                    raw=raw)

    def _call(self, action: str, *, argv: tuple[str, ...] | None = None,
              land: str | None = None, **params) -> Page:
        """按表拼 argv：固定命令段 + 各参数 + --format json，再跑、再落盘。"""
        resource, landing, command, names, flag_of, mode = ACTIONS[action]
        args = list(argv or command)
        for name in names:
            _emit(args, name, params.get(name), flag_of, mode)
        args += ["--format", "json"]
        _, raw = self._run(*args)
        return self._land(resource, land or landing, raw)

    def _fetch_bytes(self, url: str) -> bytes:
        """download_url → 字节。file:// 与 https 一视同仁。"""
        parsed = urlparse(url)
        if parsed.scheme in ("", "file"):
            path = urllib.request.url2pathname(parsed.path) if parsed.scheme else url
            with open(path, "rb") as f:
                return f.read()
        with urllib.request.urlopen(url) as resp:      # noqa: S310 (地址来自 lark-cli)
            return resp.read()

    # ── 契约的十三个动作 ─────────────────────────────────
    def mail_list(self, *, mailbox=None, folder=None, query=None, page_size=400, page_token=None):
        return self._call("mail_list", mailbox=mailbox or self.mailbox, folder=folder,
                          query=query, page_size=page_size, page_token=page_token)

    def mail_messages(self, *, message_ids, mailbox=None, html=True):
        return self._call("mail_messages", message_ids=message_ids, mailbox=mailbox or self.mailbox,
                          html=html)

    def mail_send(self, *, to, subject, body, attachments=None, mailbox=None):
        return self._call("mail_send", to=to, subject=subject, body=body, attachments=attachments,
                          mailbox=mailbox or self.mailbox)

    def mail_attachment_download(self, *, message_id, attachment_ids, mailbox=None):
        """附件是唯一要「取字节」的动作：先取地址，再把原件落到 attachments/。"""
        page = self._call("mail_attachment_download", mailbox=mailbox or self.mailbox,
                          message_id=message_id, attachment_ids=attachment_ids)
        landed: list[Attachment] = []
        for att in page.payload.get("attachments") or []:
            aid = att.get("attachment_id") or att.get("id") or ""
            name = att.get("filename") or aid
            url = att.get("download_url") or ""
            blob = self._fetch_bytes(url) if url else b""
            path = self.store.save_attachment(aid, name, blob) if self.store else ""
            landed.append(Attachment(attachment_id=aid, filename=name, path=str(path)))
        return landed

    def im_chat_messages(self, *, chat_id=None, user_id=None, order="asc",
                         with_reactions=True, page_size=50, page_token=None):
        if not chat_id and not user_id:
            raise RuntimeError("im_chat_messages 需要 chat_id 或 user_id")
        return self._call("im_chat_messages", chat_id=chat_id, user_id=user_id, order=order,
                          page_size=page_size, with_reactions=with_reactions, page_token=page_token)

    def im_chat_members(self, *, chat_id=None, page_token=None):
        return self._call("im_chat_members", chat_id=chat_id or self.chat_id, page_token=page_token)

    def im_messages_search(self, *, sender=None, at_chatter=None, chat_id=None,
                           with_reactions=False, page_size=50, page_token=None):
        if not sender and not at_chatter:
            raise RuntimeError("im_messages_search 需要 sender 或 at_chatter")
        return self._call("im_messages_search", sender=sender, at_chatter=at_chatter,
                          chat_id=chat_id, page_size=page_size, with_reactions=with_reactions,
                          page_token=page_token)

    def vc_meeting_search(self, *, participant_id=None, start=None, end=None, page_size=30,
                          page_token=None):
        if not participant_id:
            raise RuntimeError("vc_meeting_search 需要 participant_id")
        return self._call("vc_meeting_search", participant_id=participant_id, start=start, end=end,
                          page_size=page_size, page_token=page_token)

    def vc_meeting_get(self, *, meeting_id):
        return self._call("vc_meeting_get", meeting_id=meeting_id)

    def task_list(self, *, scope="mine", complete=None, page_size=50, page_token=None):
        return self._call("task_list", argv=TASK_COMMAND[scope], land=scope,
                          complete=complete, page_token=page_token)

    def drive_search(self, *, edited_since=None, created_since=None, page_size=20, page_token=None):
        if not (edited_since or created_since):
            raise RuntimeError("drive_search 需要 edited_since 或 created_since")
        return self._call("drive_search", edited_since=edited_since, created_since=created_since,
                          page_size=page_size, page_token=page_token)

    def docs_fetch(self, *, doc, detail="simple", doc_format="markdown"):
        return self._call("docs_fetch", doc=doc, detail=detail, doc_format=doc_format)

    def base_records(self, *, base_token=None, table_id=None, filter_json=None, offset=0, limit=100):
        return self._call("base_records", base_token=base_token or self.base_token,
                          table_id=table_id or self.table_id, filter_json=filter_json,
                          offset=offset, limit=limit)

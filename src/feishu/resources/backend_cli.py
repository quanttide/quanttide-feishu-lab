"""资源层后端一：子进程调 lark-cli（canonical 实现）。

同一份代码两种活法，差别只在 PATH：

    PATH 前面放 packages/fake_lark_cli/bin  → 假 lark-cli，读 tests/fixtures/，离线
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
from .actions import ACTIONS, TASK_COMMAND, emit_arg
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


class CLIBackend:
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
                f"找不到 {self.lark_cli}：PATH 里没有。离线自测先把 packages/fake_lark_cli/bin 放到 PATH 前面"
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
        unknown = set(params) - set(names)
        if unknown:
            raise TypeError(f"{action} 不认识这些参数：{sorted(unknown)}")
        # 资源位置没给就用本实例的（构造参数或环境变量）——缺省值不进代码
        for key, fallback in (("mailbox", self.mailbox), ("chat_id", self.chat_id),
                              ("base_token", self.base_token), ("table_id", self.table_id)):
            if key in names and params.get(key) is None:
                params[key] = fallback
        args = list(argv or command)
        for name in names:
            emit_arg(args, name, params.get(name), flag_of, mode)
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

    # ── 契约的十三个动作（签名与默认值见 resources/__init__.py 的契约）──
    def mail_list(self, **kw):
        return self._call("mail_list", **kw)

    def mail_messages(self, **kw):
        return self._call("mail_messages", **kw)

    def mail_send(self, **kw):
        return self._call("mail_send", **kw)

    def im_chat_messages(self, **kw):
        if not (kw.get("chat_id") or kw.get("user_id")):
            raise RuntimeError("im_chat_messages 需要 chat_id 或 user_id")
        return self._call("im_chat_messages", **kw)

    def im_chat_members(self, **kw):
        return self._call("im_chat_members", **kw)

    def im_messages_search(self, **kw):
        if not (kw.get("sender") or kw.get("at_chatter")):
            raise RuntimeError("im_messages_search 需要 sender 或 at_chatter")
        kw.setdefault("with_reactions", False)     # 契约默认：搜索不去表情
        return self._call("im_messages_search", **kw)

    def vc_meeting_search(self, **kw):
        if not kw.get("participant_id"):
            raise RuntimeError("vc_meeting_search 需要 participant_id")
        return self._call("vc_meeting_search", **kw)

    def vc_meeting_get(self, **kw):
        return self._call("vc_meeting_get", **kw)

    def task_list(self, scope="mine", **kw):
        """三种取法共用一条动作，命令段按 scope 换、落盘目录也按 scope 分。"""
        return self._call("task_list", argv=TASK_COMMAND[scope], land=scope, **kw)

    def drive_search(self, **kw):
        if not (kw.get("edited_since") or kw.get("created_since")):
            raise RuntimeError("drive_search 需要 edited_since 或 created_since")
        return self._call("drive_search", **kw)

    def docs_fetch(self, **kw):
        return self._call("docs_fetch", **kw)

    def base_records(self, **kw):
        return self._call("base_records", **kw)

    def mail_attachment_download(self, **kw):
        """附件是唯一要「取字节」的动作：先取地址，再把原件落到 attachments/。"""
        page = self._call("mail_attachment_download", **kw)
        landed: list[Attachment] = []
        for att in page.payload.get("attachments") or []:
            aid = att.get("attachment_id") or att.get("id") or ""
            name = att.get("filename") or aid
            blob = self._fetch_bytes(att["download_url"]) if att.get("download_url") else b""
            path = self.store.save_attachment(aid, name, blob) if self.store else ""
            landed.append(Attachment(attachment_id=aid, filename=name, path=str(path)))
        return landed

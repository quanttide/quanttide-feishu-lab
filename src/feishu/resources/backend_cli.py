"""资源层后端一：子进程调 lark-cli（canonical 实现）。

同一份代码两种活法，差别只在 PATH：

    PATH 前面放 tests/fake_lark_cli/bin  → 假 lark-cli，读 tests/fixtures/，离线
    PATH 里是真 lark-cli                 → 打真飞书

命令怎么写只由各资源的登记决定（``mail.py`` / ``im.py`` / …）：拼 argv、跑子进程、解信封、
落盘由 ``_call`` 一次做完。十三个动作不在这里逐一写转发——**动作名即方法名**（``__getattr__``
按登记生成），加一个动作只改它所属的资源文件。

值全部从参数与环境来，代码里不写任何邮箱、群 id、人名、关键词：

    LARK_CLI / LARK_MAILBOX / LARK_BASE_TOKEN / LARK_TABLE_ID / LARK_CHAT_ID
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from urllib.parse import urlparse

from . import ACTIONS
from .action import Attachment, Page
from .store import RawStore

# 资源位置参数：调用方没给就用本实例的（构造参数或环境变量）——缺省值不进代码
LOCATION = {"mailbox": "LARK_MAILBOX", "chat_id": "LARK_CHAT_ID",
            "base_token": "LARK_BASE_TOKEN", "table_id": "LARK_TABLE_ID"}


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
    """资源层契约的 lark-cli 实现：命令在各资源的登记里，落盘走 RawStore。"""

    def __init__(self, store_root: str | None = None, *, lark_cli: str | None = None,
                 mailbox: str | None = None, base_token: str | None = None,
                 table_id: str | None = None, chat_id: str | None = None) -> None:
        self.store = RawStore(store_root) if store_root else None
        self.lark_cli = lark_cli or os.environ.get("LARK_CLI", "lark-cli")
        self.lark_mailbox = mailbox or os.environ.get("LARK_MAILBOX", "me")
        self.lark_base_token = base_token or os.environ.get("LARK_BASE_TOKEN", "mock-base-token")
        self.lark_table_id = table_id or os.environ.get("LARK_TABLE_ID", "mock-table-id")
        self.lark_chat_id = chat_id or os.environ.get("LARK_CHAT_ID", "oc_mock_chat")

    # ── 动作名即方法名 ────────────────────────────────────
    def __getattr__(self, name: str):
        """登记里有的动作才有方法：十三个都不逐一写转发。"""
        action = ACTIONS.get(name)
        if action is None:
            raise AttributeError(name)

        def call(**params) -> Page:
            return self._call(name, **params)

        return call

    def location(self, name: str) -> str:
        """本实例给这个资源位置参数的值。"""
        return getattr(self, f"lark_{name}")

    # ── 内部 ──────────────────────────────────────────────
    def _run(self, *args: str) -> tuple[dict, dict]:
        """跑一条命令，回（负载, 原样信封）。信封就是你写进 raw/ 的那份东西。"""
        try:
            p = subprocess.run([self.lark_cli, *args], capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError(
                f"找不到 {self.lark_cli}：PATH 里没有。离线自测先把 tests/fake_lark_cli/bin 放到 PATH 前面"
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

    def _call(self, name: str, **params) -> Page | list[Attachment]:
        """校验参数 → 拼 argv → 跑 → 落盘。附件那类动作再往下取字节。"""
        action = ACTIONS[name]
        allowed = set(action.params) | ({action.variant_param} if action.variant_param else set())
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise TypeError(f"{name} 不认识这些参数：{unknown}")
        if action.needs_any and not any(params.get(k) for k in action.needs_any):
            raise RuntimeError(f"{name} 需要 {' 或 '.join(action.needs_any)}")
        for key in LOCATION:
            if key in action.params and params.get(key) is None:
                params[key] = self.location(key)
        for key, value in action.defaults.items():
            params.setdefault(key, value)
        argv, landed = action.argv(params)
        _, raw = self._run(*argv)
        page = self._land(action.resource, landed, raw)
        return self._download(page) if action.kind == "files" else page

    def _fetch_bytes(self, url: str) -> bytes:
        """download_url → 字节。file:// 与 https 一视同仁。"""
        parsed = urlparse(url)
        if parsed.scheme in ("", "file"):
            path = urllib.request.url2pathname(parsed.path) if parsed.scheme else url
            with open(path, "rb") as f:
                return f.read()
        with urllib.request.urlopen(url) as resp:      # noqa: S310 (地址来自 lark-cli)
            return resp.read()

    def _download(self, page: Page) -> list[Attachment]:
        """取附件原件：先取地址，再把字节落到 attachments/。"""
        landed: list[Attachment] = []
        for att in page.payload.get("attachments") or []:
            aid = att.get("attachment_id") or att.get("id") or ""
            name = att.get("filename") or aid
            blob = self._fetch_bytes(att["download_url"]) if att.get("download_url") else b""
            path = self.store.save_attachment(aid, name, blob) if self.store else ""
            landed.append(Attachment(attachment_id=aid, filename=name, path=str(path)))
        return landed

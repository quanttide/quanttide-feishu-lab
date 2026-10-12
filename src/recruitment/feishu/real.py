"""真飞书客户端：子进程调 lark-cli（canonical 实现）。

同一份代码两种活法，差别只在 PATH：

    PATH 前面放 packages/mock/bin  → 假 lark-cli，读 tests/fixtures/，离线
    PATH 里是真 lark-cli           → 打真飞书

资源位置不进模型：邮箱由流程的「收集.邮箱」给（cli.py 传入）；其余 id 用
环境变量给真值，缺省是占位符——够 mock 用，打真飞书会明确报错，不会静默：

    LARK_CLI          命令名（默认 lark-cli）
    LARK_BASE_TOKEN   问卷表所在 base（默认 mock-base-token）
    LARK_TABLE_ID     调研表（默认 mock-table-id）
    LARK_CHAT_ID      实训基地群（默认 oc_mock_chat）
"""

from __future__ import annotations

import json
import os
import subprocess

from . import Mail, SurveyRecord


def _extract_json(text: str) -> dict | None:
    """从输出里抠出 JSON 对象。真 lark-cli 会在 JSON 前后打进度行（如
    "[page 1] fetching..."），直接 json.loads 会失败。"""
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


class CLIFeishu:
    """FeishuClient 的 lark-cli 子进程实现：命令只活在这里。"""

    def __init__(self, lark_cli: str | None = None, *, mailbox: str = "me",
                 base_token: str | None = None, table_id: str | None = None,
                 chat_id: str | None = None, attachments_dir: str = "") -> None:
        self.lark_cli = lark_cli or os.environ.get("LARK_CLI", "lark-cli")
        self.mailbox = mailbox
        self.base_token = base_token or os.environ.get("LARK_BASE_TOKEN", "mock-base-token")
        self.table_id = table_id or os.environ.get("LARK_TABLE_ID", "mock-table-id")
        self.chat_id = chat_id or os.environ.get("LARK_CHAT_ID", "oc_mock_chat")
        self.attachments_dir = attachments_dir

    # ── 内部 ──────────────────────────────────────────────
    def _run(self, *args: str) -> dict:
        """跑一条 lark-cli 命令，解开 {"ok": true, "data": ...} 信封。

        失败（exit 2 + stderr 里的 {"ok": false, "error": {...}}）→ RuntimeError。
        """
        try:
            p = subprocess.run([self.lark_cli, *args], capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError(
                f"找不到 {self.lark_cli}：PATH 里没有。离线自测先把 packages/mock/bin 放到 PATH 前面"
            ) from None
        text = p.stdout if p.returncode == 0 else p.stderr
        payload = _extract_json(text)
        if payload is None:
            raise RuntimeError(
                f"{self.lark_cli} {' '.join(args)} 输出不是 JSON：{text.strip()[:200]}"
            )
        if p.returncode != 0 or not payload.get("ok"):
            err = payload.get("error") or {}
            raise RuntimeError(
                f"{self.lark_cli} {' '.join(args[:2])} 失败："
                f"{err.get('message') or text.strip()[:200]}"
            )
        return payload.get("data") or {}

    def _resolve(self, name: str) -> str:
        """附件名 → 路径：本来就是路径就用它，否则到附件目录里找。"""
        if os.path.isabs(name) or os.path.sep in name or os.path.exists(name):
            return name
        return os.path.join(self.attachments_dir, name)

    # ── 飞书能力 ──────────────────────────────────────────
    def read_mail(self, folder: str, cursor: str | None = None) -> tuple[list[Mail], str]:
        """读某个文件夹：+triage 列摘要，+messages 取正文与附件，游标语义与夹具层一致。"""
        summaries = self._run(
            "mail", "+triage",
            "--filter", json.dumps({"folder": folder}, ensure_ascii=False),
            "--mailbox", self.mailbox, "--max", "400", "--format", "json",
        ).get("messages") or []
        ids = [s["message_id"] for s in summaries]
        full: dict[str, dict] = {}
        if ids:
            full = {m["message_id"]: m for m in self._run(
                "mail", "+messages", "--message-ids", ",".join(ids),
                "--mailbox", self.mailbox).get("messages") or []}

        mails: list[Mail] = []
        for s in summaries:
            m = full.get(s["message_id"])
            if m is None:
                continue
            to = m.get("to") or []
            mails.append(Mail(
                message_id=s["message_id"],
                folder=folder,
                sender=(m.get("head_from") or {}).get("mail_address", ""),
                recipient=to[0].get("mail_address", "") if to else "",
                subject=m.get("subject", ""),
                body=m.get("body_plain_text", ""),
                date=(m.get("date_formatted") or s.get("date") or "")[:10],
                attachments=[a.get("filename", "") for a in m.get("attachments") or []],
            ))
        if cursor:
            mails = [m for m in mails if m.date > cursor]
        new_cursor = max((m.date for m in mails), default=cursor or "")
        return mails, new_cursor

    def read_survey(self, emails: list[str]) -> dict[str, SurveyRecord]:
        """按邮箱查调研表：+record-list，中文列名与夹具的英文键都认。"""
        if not emails:
            return {}
        spec = {"logic": "and", "conditions": [["邮箱", "intersects", list(emails)]]}
        items = self._run(
            "base", "+record-list",
            "--base-token", self.base_token, "--table-id", self.table_id,
            "--filter-json", json.dumps(spec, ensure_ascii=False),
            "--format", "json",
        ).get("items") or []
        out: dict[str, SurveyRecord] = {}
        for item in items:
            fields = item.get("fields") or {}
            email = fields.get("email") or fields.get("邮箱")
            if not email:
                continue
            answers = fields.get("answers")
            if not isinstance(answers, dict):
                skip = {"email", "邮箱", "submitted_at", "提交时间"}
                answers = {k: v for k, v in fields.items() if k not in skip}
            out[email] = SurveyRecord(
                email=email,
                submitted_at=fields.get("submitted_at") or fields.get("提交时间") or "",
                answers=answers,
            )
        return out

    def read_group_members(self) -> set[str]:
        """读群成员：+chat-members-list，返回邮箱集合。"""
        users = self._run("im", "+chat-members-list",
                          "--chat-id", self.chat_id).get("users") or []
        return {u["member_id"].lower() for u in users if u.get("member_id")}

    def send_mail(self, to: str, subject: str, body: str,
                  attachments: list[str] | None = None) -> str:
        """发一封邮件：+send 带 --confirm-send，返回 message_id。

        注意：PATH 里是真 lark-cli 时这封信会真发出去（能力层要 message_id，
        只能走发送模式）；实验室里靠 --cli 显式开启来把住这道门。
        """
        args = ["mail", "+send", "--to", to, "--subject", subject, "--body", body,
                "--mailbox", self.mailbox, "--confirm-send"]
        if attachments:
            args += ["--attach", ",".join(self._resolve(a) for a in attachments)]
        return self._run(*args).get("message_id") or ""

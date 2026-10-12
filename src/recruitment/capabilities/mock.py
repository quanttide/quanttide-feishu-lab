"""夹具实现：把能力表的三列换成夹具那一列。

夹具目录的形状：

    tests/fixtures/
      mail/
        收件箱.json          每封：message_id / sender / subject / body / date / attachments
        已发送问卷.json
        Spam.json
        沟通面试中.json
      survey.json            调研表记录：[{email, submitted_at, answers}, …]
      group_members.json     群成员邮箱：[…]
      outbox/                发出去的邮件（本实现写入；每封一个 .json）

发信写进 outbox/ 而不是真发；读信只读夹具。所以同一份 YAML 在这里跑出来的
结果完全由夹具决定——可重复，可断言。
"""

from __future__ import annotations

import json
import os
import re

from . import Mail, SurveyRecord


def _slug(email: str) -> str:
    """邮箱 → 文件名片段：本地名 + 域名的短哈希，保证唯一且可读。"""
    local, _, domain = email.partition("@")
    digest = 0
    for ch in email:
        digest = (digest * 131 + ord(ch)) % 0xFFFFFF
    return f"{local}_{digest:06x}"


class MockCapabilities:
    def __init__(self, fixtures_dir: str) -> None:
        self.root = os.path.abspath(fixtures_dir)
        self.outbox = os.path.join(self.root, "outbox")
        os.makedirs(self.outbox, exist_ok=True)

    # ── 内部 ──────────────────────────────────────────────
    def _read_json(self, *parts: str):
        path = os.path.join(self.root, *parts)
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _folder_file(folder: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "-", folder).strip("-") + ".json"

    # ── 四种能力 ──────────────────────────────────────────
    def read_mail(self, folder: str, cursor: str | None = None):
        """读夹具里某个文件夹的邮件。游标按日期过滤：只返回比游标新的。"""
        raw = self._read_json("mail", self._folder_file(folder))
        mails = [
            Mail(
                message_id=m["message_id"],
                folder=folder,
                sender=m.get("sender", ""),
                recipient=m.get("recipient", ""),
                subject=m.get("subject", ""),
                body=m.get("body", ""),
                date=m["date"],
                attachments=list(m.get("attachments", [])),
            )
            for m in raw
        ]
        if cursor:
            mails = [m for m in mails if m.date > cursor]
        new_cursor = max((m.date for m in mails), default=cursor or "")
        return mails, new_cursor

    def read_survey(self, emails: list[str]) -> dict[str, SurveyRecord]:
        wanted = {e.lower() for e in emails}
        out: dict[str, SurveyRecord] = {}
        for rec in self._read_json("survey.json"):
            if rec["email"].lower() in wanted:
                out[rec["email"]] = SurveyRecord(
                    email=rec["email"],
                    submitted_at=rec["submitted_at"],
                    answers=dict(rec.get("answers", {})),
                )
        return out

    def read_group_members(self) -> set[str]:
        return {e.lower() for e in self._read_json("group_members.json")}

    def send_mail(self, to: str, subject: str, body: str,
                  attachments: list[str] | None = None) -> str:
        message_id = "mock-" + _slug(to) + "-" + subject[:12].replace(" ", "")
        record = {
            "message_id": message_id,
            "to": to,
            "subject": subject,
            "body": body,
            "attachments": list(attachments or []),
        }
        path = os.path.join(self.outbox, message_id + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return message_id

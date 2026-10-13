"""流程能力层的契约：四个动作 + 流程用的数据类 + 负载映射。

契约只认流程的词汇（文件夹、候选人邮箱、群）；平台词汇（命令、flag、folder id）
活在资源层与它下面的后端里。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Mail:
    """一封飞书邮件。folder 是它在飞书里所在的文件夹（收件箱 / 已发送问卷 / Spam…）。"""
    message_id: str
    folder: str
    sender: str          # 发件人邮箱（收件箱侧）
    recipient: str       # 收件人邮箱（已发送侧）
    subject: str
    body: str
    date: str            # YYYY-MM-DD
    attachments: list[str] = field(default_factory=list)   # 附件文件名


@dataclass
class SurveyRecord:
    """飞书多维表格「调研」表里的一条记录。"""
    email: str
    submitted_at: str
    answers: dict[str, str]


class FeishuClient(Protocol):
    """流程要用到的飞书能力。参数与返回值都用普通数据，不给调用方任何
    业务（招聘）概念——但「飞书」是显式的，方法名即飞书操作。"""

    def read_mail(self, folder: str, cursor: str | None = None) -> tuple[list[Mail], str]:
        """读某个飞书文件夹的邮件，返回（邮件列表，新游标）。

        cursor 为空表示从头拉；返回的游标供下次增量使用。
        """
        ...

    def read_survey(self, emails: list[str]) -> dict[str, SurveyRecord]:
        """按邮箱查飞书多维表格「调研」记录：只返回查到的那些。"""
        ...

    def read_group_members(self) -> set[str]:
        """读飞书群成员，返回邮箱集合。"""
        ...

    def send_mail(self, to: str, subject: str, body: str,
                  attachments: list[str] | None = None) -> str:
        """发一封飞书邮件，返回它的 message_id。"""
        ...



# ── 负载 → 流程数据类（两个实现共用，避免各写一份映射）──
def to_mail(payload: dict, folder: str) -> Mail:
    """资源层的邮件负载 → 流程的 Mail。"""
    to = payload.get("to") or []
    return Mail(
        message_id=payload["message_id"],
        folder=folder,
        sender=(payload.get("head_from") or {}).get("mail_address", ""),
        recipient=to[0].get("mail_address", "") if to else "",
        subject=payload.get("subject", ""),
        body=payload.get("body_plain_text", ""),
        date=(payload.get("date_formatted") or "")[:10],
        attachments=[a.get("filename", "") for a in payload.get("attachments") or []],
    )


def since(mails: list[Mail], cursor: str | None) -> tuple[list[Mail], str]:
    """游标语义：只留比游标新的，新游标取其中最新的日期。两个实现一致。"""
    if cursor:
        mails = [m for m in mails if m.date > cursor]
    return mails, max((m.date for m in mails), default=cursor or "")


def to_survey(items: list[dict]) -> dict[str, SurveyRecord]:
    """资源层的表记录 → 流程的 SurveyRecord（中文列名与英文键都认）。"""
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

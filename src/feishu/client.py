"""流程能力层：四个动作的契约与实现，一处写清。

契约只认流程的词汇（文件夹、候选人邮箱、群）；平台词汇（命令、flag、folder id）活在资源层。
这一层只做两件事，所以契约与实现不分成两个文件：

1. **坐标映射**：流程的词汇 → 资源层的坐标（mailbox、chat_id…）
2. **数据类映射**：资源层的负载 → 流程用的 ``Mail`` / ``SurveyRecord``（``to_mail`` / ``to_survey``）

四个动作：``read_mail`` / ``read_survey`` / ``read_group_members`` / ``send_mail``——
方法名即飞书操作，参数与返回值都是普通数据，不给调用方任何招聘概念。
「夹具实现」与「lark-cli 实现」共用这一个类，换实现 = 换它包的那个资源层客户端
（见 ``__init__.py`` 的 ``mock()`` / ``real()``）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

PAGE_SIZE = 400


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


class Feishu:
    """流程能力层：把一个资源层客户端包成流程要用的四个动作。"""

    def __init__(self, resources, *, mailbox: str = "me", attachments_dir: str = "") -> None:
        self.res = resources
        self.mailbox = mailbox
        self.attachments_dir = attachments_dir

    def _resolve(self, name: str) -> str:
        """附件名 → 路径：本来就是路径就用它，否则到附件目录里找。"""
        if os.path.isabs(name) or os.path.sep in name or os.path.exists(name):
            return name
        return os.path.join(self.attachments_dir, name)

    # ── 流程要用的四个动作 ────────────────────────────────
    def read_mail(self, folder: str, cursor: str | None = None) -> tuple[list[Mail], str]:
        """读某个飞书文件夹的邮件，返回（邮件列表，新游标）。

        cursor 为空表示从头拉；返回的游标供下次增量使用。
        +triage 列摘要、+messages 取正文（资源层两步），再映射成 Mail。
        """
        summaries = self.res.mail_list(folder=folder, mailbox=self.mailbox,
                                       page_size=PAGE_SIZE).payload.get("messages") or []
        ids = [s["message_id"] for s in summaries]
        full: dict[str, dict] = {}
        if ids:
            full = {m["message_id"]: m for m in self.res.mail_messages(
                message_ids=ids, mailbox=self.mailbox).payload.get("messages") or []}
        mails = [to_mail(full[s["message_id"]], folder)
                 for s in summaries if s["message_id"] in full]
        return since(mails, cursor)

    def read_survey(self, emails: list[str]) -> dict[str, SurveyRecord]:
        """按邮箱查飞书多维表格「调研」记录：只返回查到的那些。"""
        if not emails:
            return {}
        spec = {"logic": "and", "conditions": [["邮箱", "intersects", list(emails)]]}
        items = self.res.base_records(
            filter_json=json.dumps(spec, ensure_ascii=False)).payload.get("items") or []
        wanted = {e.lower() for e in emails}
        return {k: v for k, v in to_survey(items).items() if k.lower() in wanted}

    def read_group_members(self) -> set[str]:
        """读飞书群成员，返回邮箱集合。"""
        users = self.res.im_chat_members().payload.get("users") or []
        return {u["member_id"].lower() for u in users if u.get("member_id")}

    def send_mail(self, to: str, subject: str, body: str,
                  attachments: list[str] | None = None) -> str:
        """发一封飞书邮件，返回它的 message_id。

        注意：PATH 里是真 lark-cli 时这封信会真发出去（能力层要 message_id，只能走发送模式）；
        实验室里靠 ``--cli`` 显式开启来把住这道门。
        """
        page = self.res.mail_send(to=to, subject=subject, body=body, mailbox=self.mailbox,
                                  attachments=[self._resolve(a) for a in attachments or []])
        return page.payload.get("message_id") or ""

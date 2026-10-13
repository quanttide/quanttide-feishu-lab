"""飞书适配层（port / adapter）：流程与外部位（飞书）之间的接缝。

这个平台的核心定位就是**绑定飞书**，所以这里不是「平台无关的通用接口」，
而是**显式的飞书适配层**——方法名直接对应飞书的操作
（某个飞书邮箱文件夹、某张多维表格的「调研」表、某个飞书群）。

取数与落盘规则都在资源层（``feishu/resources/``）；这里只做两件事：把流程的词汇
（文件夹、候选人邮箱、群）翻成资源层的坐标，再把资源层的负载映射成流程的数据类。

两类实现，二者都是飞书客户端，不是「两套平台」：

  - ``mock`` ：进程内**测试替身**，读夹具目录，零外部 IO，用于确定性自测与断言。
  - ``real`` ：**真飞书客户端**，子进程调 lark-cli（canonical 实现）。
              PATH 前面放 ``packages/mock/bin`` 即离线走假 lark-cli；
              放真 lark-cli 即打真飞书——同一份代码，两种活法。

执行器（runner）只认 ``FeishuClient`` 这个契约，不认具体实现；换实现 = 换工厂，
流程与执行器代码一行不动。但「飞书」是这个产品的本体：能力层隔离的是
**飞书 API 的易变细节**（鉴权、命令、字段、限流），不是「飞书」这个概念本身。
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

def mock(fixtures_dir: str) -> FeishuClient:
    """测试替身：资源层走夹具，读写都不碰外网，确定性、可断言。"""
    from .client import Feishu
    from .resources.mock import MockResources

    return Feishu(MockResources(None, fixtures_dir))


def real(*, mailbox: str = "me", attachments_dir: str = "", **ids) -> FeishuClient:
    """真飞书客户端：资源层子进程调 lark-cli（canonical 实现）。

    资源 id 由 ``mailbox`` 与 ``ids`` 给（缺省走环境变量），缺省值是占位符——
    够 mock 用，打真飞书会明确报错，不会静默。
    """
    from .client import Feishu
    from .resources.real import CLIResources

    res = CLIResources(None, mailbox=None, **ids)
    return Feishu(res, mailbox=mailbox or res.mailbox, attachments_dir=attachments_dir)

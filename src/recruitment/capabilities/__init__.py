"""能力层：流程对外的需求清单。

YAML 里只出现能力名，不出现任何 lark-cli 命令——命令只活在真实实现里。
mock 就是把这张表的实现换一份：同一份 YAML，--mock 走夹具，关掉打真飞书。

四个能力是跑通最小闭环（投递 → 问卷 → 进群）需要的；写回等接了真数据再加。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Mail:
    """一封邮件。folder 是它在飞书里所在的文件夹（收件箱 / 已发送问卷 / Spam…）。"""
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
    """调研表里的一条记录。"""
    email: str
    submitted_at: str
    answers: dict[str, str]


class Capabilities(Protocol):
    """流程要用到的四种能力。参数与返回值都用普通数据，不给调用方任何平台概念。"""

    def read_mail(self, folder: str, cursor: str | None = None) -> tuple[list[Mail], str]:
        """读某个文件夹的邮件，返回（邮件列表，新游标）。

        cursor 为空表示从头拉；返回的游标供下次增量使用。
        """
        ...

    def read_survey(self, emails: list[str]) -> dict[str, SurveyRecord]:
        """按邮箱查调研表记录：只返回查到的那些。"""
        ...

    def read_group_members(self) -> set[str]:
        """读群成员，返回邮箱集合。"""
        ...

    def send_mail(self, to: str, subject: str, body: str,
                  attachments: list[str] | None = None) -> str:
        """发一封邮件，返回它的 message_id。"""
        ...


def mock(fixtures_dir: str) -> Capabilities:
    """夹具实现：读写夹具目录，不打任何外部接口。"""
    from .mock import MockCapabilities
    return MockCapabilities(fixtures_dir)


def real(*args, **kwargs) -> Capabilities:
    """真实实现：接本地 lark-cli。暂未实现——先让流程在夹具上跑通。"""
    raise NotImplementedError(
        "真实能力尚未实现：先跑 --mock 把流程走通，再接 lark-cli"
    )

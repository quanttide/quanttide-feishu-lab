"""飞书适配层（port / adapter）：流程与外部位（飞书）之间的接缝。

这个平台的核心定位就是**绑定飞书**，所以这里不是「平台无关的通用接口」，
而是**显式的飞书适配层**——方法名直接对应飞书的操作
（某个飞书邮箱文件夹、某张多维表格的「调研」表、某个飞书群）。

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


def mock(fixtures_dir: str) -> FeishuClient:
    """测试替身：读写夹具目录，确定性、可断言、不碰外网。"""
    from .mock import MockFeishu
    return MockFeishu(fixtures_dir)


def real(*args, **kwargs) -> FeishuClient:
    """真飞书客户端：子进程调 lark-cli（canonical 实现）。"""
    from .real import CLIFeishu
    return CLIFeishu(*args, **kwargs)

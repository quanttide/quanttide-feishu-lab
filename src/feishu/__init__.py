"""飞书能力层（主线）：流程要用的四个飞书动作，一个契约两种后端。

    contract.py   契约：FeishuClient（读邮件 / 读调研表 / 读群成员 / 发邮件）+ 数据类
    client.py     实现：包一个资源层后端，只做坐标映射与数据类映射
    resources/    资源层：六资源十三动作 + 原样落盘

这里的 ``mock()`` / ``real()`` 换的是**资源层后端**（同进程假 CLI / lark-cli 子进程），
流程与执行器代码一行不动。
"""

from __future__ import annotations

from .contract import Mail, SurveyRecord, FeishuClient, since, to_mail, to_survey  # noqa: F401

__all__ = ["Mail", "SurveyRecord", "FeishuClient", "since", "to_mail", "to_survey",
           "mock", "real"]


def mock(fixtures_dir: str) -> FeishuClient:
    """测试替身：资源层走夹具，读写都不碰外网，确定性、可断言。"""
    from .client import Feishu
    from .resources.backend_inprocess import InProcessBackend

    return Feishu(InProcessBackend(None, fixtures_dir))


def real(*, mailbox: str = "me", attachments_dir: str = "", **ids) -> FeishuClient:
    """真飞书客户端：资源层子进程调 lark-cli（canonical 实现）。

    资源 id 由 ``mailbox`` 与 ``ids`` 给（缺省走环境变量），缺省值是占位符——
    够 mock 用，打真飞书会明确报错，不会静默。
    """
    from .client import Feishu
    from .resources.backend_cli import CLIBackend

    res = CLIBackend(None, mailbox=None, **ids)
    return Feishu(res, mailbox=mailbox or res.mailbox, attachments_dir=attachments_dir)

"""飞书能力层（主线）：流程要用的四个飞书动作，一处契约两种后端。

    client.py     契约与实现：Mail / SurveyRecord / Feishu（四个动作）+ 负载映射
    resources/    资源层：六资源十三动作 + 原样落盘——动作登记就是契约，按飞书资源分文件

这里的 ``mock()`` / ``real()`` 换的是**资源层后端**（同进程假 CLI / lark-cli 子进程），
流程与执行器代码一行不动。
"""

from __future__ import annotations

from .client import Feishu, Mail, SurveyRecord, since, to_mail, to_survey  # noqa: F401

__all__ = ["Feishu", "Mail", "SurveyRecord", "since", "to_mail", "to_survey", "mock", "real"]


def mock(fixtures_dir: str) -> Feishu:
    """测试替身：资源层走夹具，读写都不碰外网，确定性、可断言。"""
    from .client import Feishu
    from .resources.backend_inprocess import InProcessBackend

    return Feishu(InProcessBackend(None, fixtures_dir))


def real(*, mailbox: str = "me", attachments_dir: str = "", **ids) -> Feishu:
    """真飞书客户端：资源层子进程调 lark-cli（canonical 实现）。

    资源 id 由 ``mailbox`` 与 ``ids`` 给（缺省走环境变量），缺省值是占位符——
    够 mock 用，打真飞书会明确报错，不会静默。
    """
    from .client import Feishu
    from .resources.backend_cli import CLIBackend

    res = CLIBackend(None, mailbox=None, **ids)
    return Feishu(res, mailbox=mailbox or res.location("mailbox"), attachments_dir=attachments_dir)

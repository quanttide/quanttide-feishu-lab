"""飞书能力：基础单元 + 串联器。两样东西，各说各的话。

    resources/    基础单元：六资源十三个动作——飞书有什么、怎么取、怎么原样落盘
    engine.py     串联器：读定义（配置），把定义展开成一串基础单元的活动
    store.py / backend_cli.py / backend_inprocess.py   落盘与两个后端

定义（我们的话 → 一串飞书活动）与流程（状态、迁移）都是配置，放在用它的场景那一侧
（见 ``examples/qtrecurit/``）：这里不认识招聘、也不认识任何业务。

``mock_backend()`` / ``real_backend()`` 只换**基础单元的后端**：同一条定义，换成假 CLI
或真 lark-cli，跑出来的形状一样。
"""

from __future__ import annotations

from . import engine, resources  # noqa: F401
from .engine import Definition, Engine, Outcome  # noqa: F401
from .resources import ACTIONS, Action, Attachment, Page, pull  # noqa: F401

__all__ = ["Engine", "Definition", "Outcome", "load_definitions", "mock_backend", "real_backend",
           "resources", "engine", "ACTIONS", "Action", "Attachment", "Page", "pull"]


def load_definitions(path: str) -> dict[str, Definition]:
    """读定义表（我们的话 → 一串飞书活动）。"""
    return engine.load(path)


def mock_backend(fixtures_dir: str):
    """基础单元的测试后端：同进程跑假 CLI，读写都不碰外网，确定性、可断言。"""
    from .resources.backend_inprocess import InProcessBackend

    return InProcessBackend(None, fixtures_dir)


def real_backend(**ids):
    """基础单元的真后端：子进程调 lark-cli。

    资源位置（邮箱、群、表格）由 ``ids`` 或环境变量给（``LARK_MAILBOX`` / ``LARK_CHAT_ID`` /
    ``LARK_BASE_TOKEN`` / ``LARK_TABLE_ID``）；缺省值是占位符——够 mock 用，打真飞书会明确报错。
    """
    from .resources.backend_cli import CLIBackend

    return CLIBackend(None, **ids)

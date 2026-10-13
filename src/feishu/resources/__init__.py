"""资源层（门面）：六资源十四个动作——动作登记就是契约，按飞书资源分文件。

    mail.py / im.py / vc.py / task.py / doc.py / base.py   各资源的动作登记（命令、参数、必填、落盘名）
    action.py         登记的形状：Action + Page / Attachment + 参数 → argv
    backend_cli.py    后端一：子进程调 lark-cli（canonical）
    backend_inprocess.py  后端二：同进程跑假 lark-cli（离线、不依赖 PATH）
    store.py          落盘契约：raw/<资源>/<动作>/<页序>.json + 游标 + 附件

十四个动作的名字与参数只写在这些登记里——没有第二处签名，两个后端也不逐一写方法
（动作名即方法名）。加一个动作 = 改它所属的那个资源文件。
"""

from __future__ import annotations

from dataclasses import replace

from . import base, doc, im, mail, task, vc
from .action import Action, Attachment, Page

_MODULES = (mail, im, vc, task, doc, base)
ACTIONS: dict[str, Action] = {name: replace(action, resource=module.RESOURCE)
                              for module in _MODULES for name, action in module.ACTIONS.items()}

assert len(ACTIONS) == sum(len(m.ACTIONS) for m in _MODULES), "动作名重了：一张表只该有一个名字"

__all__ = ["ACTIONS", "Action", "Attachment", "Page", "pull", "cli_backend", "inprocess_backend"]


# ── 分页：一份实现 ────────────────────────────────────────
def pull(client, action: str, *, cursor_key: str | None = None,
         max_pages: int = 100, **kwargs) -> list[Page]:
    """把某个动作拉到底：一页一页取，每页已由实现落盘，最后推游标。

    ``cursor_key`` 给了才动游标（列表类动作用资源名当键）；整段拉完才前进，
    中途异常不推——下次还能从断点续。
    """
    method = getattr(client, action)
    pages: list[Page] = []
    token = kwargs.pop("page_token", None)
    while True:
        page = method(page_token=token, **kwargs)
        pages.append(page)
        if not page.has_more or not page.page_token or len(pages) >= max_pages:
            break
        token = page.page_token
    if cursor_key and pages and client.store:
        client.store.set_cursor(cursor_key, pages[-1].page_token or "")
    return pages


def inprocess_backend(store_root: str | None, fixtures_dir: str):
    """同进程假 lark-cli：离线、不 fork、不依赖 PATH，落盘路径与真后端同一套。"""
    from .backend_inprocess import InProcessBackend
    return InProcessBackend(store_root, fixtures_dir)


def cli_backend(store_root: str | None = None, **ids):
    """子进程调 lark-cli（canonical 实现）。"""
    from .backend_cli import CLIBackend
    return CLIBackend(store_root, **ids)

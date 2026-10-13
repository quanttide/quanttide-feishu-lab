"""资源层（门面）：六资源十三动作，两个后端换来换去都是它。

    contract.py            契约：Resources（十三个动作）+ Page / Attachment
    actions.py             动作表：动作 → 资源 / 命令段 / 参数 / flag 改写
    backend_cli.py         后端一：子进程调 lark-cli（canonical）
    backend_inprocess.py   后端二：同进程跑假 lark-cli（离线、不依赖 PATH）
    store.py               落盘：raw/<资源>/<动作>/<页序>.json + 游标 + 附件

载荷、命令、信封、字段归一化、落盘路径都只在这里与它的三个邻居里各写一遍；
上层（``feishu/``）只调动作名。
"""

from __future__ import annotations

from .contract import Attachment, Page, Resources

__all__ = ["Attachment", "Page", "Resources", "pull", "cli_backend", "inprocess_backend"]

# ── 分页：一份实现 ────────────────────────────────────────
def pull(client: Resources, action: str, *, cursor_key: str | None = None,
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


def inprocess_backend(store_root: str | None, fixtures_dir: str) -> Resources:
    """同进程假 lark-cli：离线、不 fork、不依赖 PATH，落盘路径与真后端同一套。"""
    from .backend_inprocess import InProcessBackend
    return InProcessBackend(store_root, fixtures_dir)


def cli_backend(store_root: str | None = None, **ids) -> Resources:
    """子进程调 lark-cli（canonical 实现）。"""
    from .backend_cli import CLIBackend
    return CLIBackend(store_root, **ids)

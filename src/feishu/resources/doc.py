"""doc 域：找文档与取正文，两个动作。

    drive_search    drive +search     按编辑时间或创建时间找（写一个就够）
    docs_fetch      docs +fetch       按文档 token 导出正文（detail / doc_format 决定格式）
"""

from __future__ import annotations

from .action import Action

RESOURCE = "doc"

ACTIONS: dict[str, Action] = {
    "drive_search": Action(
        command=("drive", "+search"), landed="drive-search",
        needs_any=("edited_since", "created_since"),
        params={"edited_since": "--edited-since", "created_since": "--created-since",
                "page_size": "--page-size", "page_token": "--page-token"},
    ),
    "docs_fetch": Action(
        command=("docs", "+fetch"), landed="docs-fetch",
        params={"doc": "--doc", "detail": "--detail", "doc_format": "--doc-format"},
    ),
}

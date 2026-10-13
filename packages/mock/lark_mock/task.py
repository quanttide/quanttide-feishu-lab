"""task 域：``+get-my-tasks`` / ``+get-related-tasks`` / ``tasklists list``。

夹具（tests/fixtures/task/）：

    my-tasks.json        {"items": [{guid, summary, completed, due, creator, assignee}], …}
    related-tasks.json   同形
    tasklists.json       {"items": [{guid, name}], …}

``--complete=false`` 只回未完成的（真 CLI 的语义），``--complete`` 只回已完成的。
"""

from __future__ import annotations

from . import fixtures
from .envelope import Result, usage_error

SCOPE_FIXTURE = {"mine": "my-tasks.json", "related": "related-tasks.json",
                 "tasklists": "tasklists.json"}


def _scope(flags: dict, command: str) -> str:
    if command == "+get-related-tasks":
        return "related"
    if command == "tasklists list":
        return "tasklists"
    return "mine"


def list_tasks(flags: dict, *, command: str = "+get-my-tasks") -> Result:
    if command == "tasklists list" and (flags.get("as") or "auto") not in ("user", "auto"):
        usage_error("mock 的 tasklists 只认 --as user", param="--as")
    payload = fixtures.read_json("task", SCOPE_FIXTURE[_scope(flags, command)])
    items = list(payload.get("items") or [])
    complete = None
    raw = flags.get("complete")
    if isinstance(raw, str):
        complete = raw.lower() not in ("false", "0", "no")
    elif raw is True:
        complete = True
    if complete is not None:
        items = [i for i in items if bool(i.get("completed")) is complete]

    page, has_more, token = fixtures.page_of(items, flags.get("page-token"),
                                             flags.get("page-size") or 50)
    data = {"items": page, "has_more": has_more, "page_token": token}
    lines = ["guid\tsummary\tcompleted"]
    lines += [f"{i.get('guid','')}\t{i.get('summary','')}\t{i.get('completed','')}"
              for i in page]
    return Result(data, table="\n".join(lines))

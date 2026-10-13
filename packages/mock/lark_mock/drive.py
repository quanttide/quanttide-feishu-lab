"""drive 域 ``+search`` 与 docs 域 ``+fetch``：文档变更列表与正文导出。

夹具（tests/fixtures/drive/）：

    search.json            {"items": [{token, name, type, edited_time, created_time, url}], …}
    doc-<token>.json       {"token": …, "doc_type": …, "content": "…（markdown）"}

真 CLI 的形状：``drive +search --edited-since <日期>`` 列变更、``docs +fetch --doc <token>
--doc-format markdown`` 导出正文。mock 按夹具把两者串起来——先列、再导，与真 CLI 同一用法。
"""

from __future__ import annotations

from . import fixtures, shapes
from .envelope import Result, usage_error


def search(flags: dict) -> Result:
    since = flags.get("edited-since") or flags.get("created-since")
    if not since:
        usage_error('required flag(s) "edited-since" or "created-since" not set',
                    param="--edited-since")
    payload = fixtures.read_json("drive", "search.json")
    items = [i for i in payload.get("items") or []
             if (i.get("edited_time") or "") >= since or (i.get("created_time") or "") >= since]
    page, has_more, token = shapes.page_of(items, flags.get("page-token"),
                                             flags.get("page-size") or 20)
    data = {"items": page, "has_more": has_more, "page_token": token}
    lines = ["token\tname\tedited_time"]
    lines += [f"{i.get('token','')}\t{i.get('name','')}\t{i.get('edited_time','')}"
              for i in page]
    return Result(data, table="\n".join(lines))


def fetch(flags: dict) -> Result:
    doc = flags.get("doc")
    if not doc:
        usage_error('required flag(s) "doc" not set', param="--doc")
    payload = fixtures.read_json("drive", f"doc-{doc}.json")
    data = dict(payload)
    data["detail"] = flags.get("detail") or "simple"
    data["doc_format"] = flags.get("doc-format") or "markdown"
    return Result(data, table=str(payload.get("content", "")))

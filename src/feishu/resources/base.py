"""base 域：多维表格的记录，一个动作。

    base_records    base +record-list    按 base_token + table_id 列表；filter_json 给字典或 JSON 串
"""

from __future__ import annotations

import json

from .action import Action

RESOURCE = "base"

ACTIONS: dict[str, Action] = {
    "base_records": Action(
        command=("base", "+record-list"), landed="record-list",
        params={"base_token": "--base-token", "table_id": "--table-id", "offset": "--offset",
                "limit": "--limit",
                # 查询条件可以写成字典（配置里就是这样），也可以给现成的 JSON 串
                "filter_json": lambda v: ["--filter-json",
                                          v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)]},
    ),
}

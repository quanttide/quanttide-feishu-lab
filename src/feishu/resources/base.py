"""base 域：多维表格的记录，一个动作。

    base_records    base +record-list    按 base_token + table_id 列表；filter_json 原样传
"""

from __future__ import annotations

from .action import Action

RESOURCE = "base"

ACTIONS: dict[str, Action] = {
    "base_records": Action(
        command=("base", "+record-list"), landed="record-list",
        params={"base_token": "--base-token", "table_id": "--table-id",
                "filter_json": "--filter-json", "offset": "--offset", "limit": "--limit"},
    ),
}

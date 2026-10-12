"""im +chat-members-list：读群成员夹具（tests/fixtures/group_members.json）。

已知差距：真 CLI 返回 open_id，mock 只有邮箱，member_id 直接放邮箱并标
member_id_type=email——接真飞书时能力层要补一步 open_id → 邮箱解析。
"""

from __future__ import annotations

from . import fixtures
from .envelope import Result, usage_error


def chat_members_list(flags: dict) -> Result:
    if not flags.get("chat-id"):
        usage_error('required flag(s) "chat-id" not set', param="--chat-id")
    emails = fixtures.read_json("group_members.json")

    want = [t.strip() for t in (flags.get("member-types") or "user,bot").split(",") if t.strip()]
    users = []
    if "user" in want:
        users = [{"member_id": e, "member_id_type": "email",
                  "name": e.partition("@")[0]} for e in emails]

    data = {"users": users, "bots": [], "truncations": []}   # 夹具里没有机器人
    lines = ["member_id\tname"] + [f"{u['member_id']}\t{u['name']}" for u in users]
    return Result(data, table="\n".join(lines))

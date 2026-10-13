"""im 域：``+chat-members-list`` 读群成员、``+chat-messages-list`` 读会话消息、
``+messages-search`` 搜索消息。

成员夹具是 ``tests/fixtures/group_members.json``（邮箱列表）；
会话与搜索夹具在 ``tests/fixtures/im/``：

    chat-<chat_id>.json        群消息：{"messages": [...], "has_more": …, "page_token": …}
    p2p-<user_id>.json         单聊消息，同形
    search-sender-<open_id>.json   某人发出的消息：{"items": [...]}
    search-at-<open_id>.json       被 @ 到的消息，同形

已知差距：真 CLI 返回 open_id，成员 mock 只有邮箱，member_id 直接放邮箱并标
member_id_type=email——接真飞书时能力层要补一步 open_id → 邮箱解析。
"""

from __future__ import annotations

from . import fixtures
from .envelope import Result, usage_error


def _paged(items: list, flags: dict, *, key: str = "messages") -> Result:
    """按 page-size / page-token 切页；--no-reactions 去掉表情回复；--order desc 反序。"""
    size = flags.get("page-size") or 50
    page, has_more, token = fixtures.page_of(items, flags.get("page-token"), size)
    if flags.get("no-reactions"):
        page = [{k: v for k, v in m.items() if k != "reactions"} for m in page]
    if (flags.get("order") or "asc") == "desc":
        page = list(reversed(page))
    data = {key: page, "has_more": has_more, "page_token": token}
    return Result(data, table=f"{len(page)} message(s)")


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


def chat_messages_list(flags: dict) -> Result:
    """群按 --chat-id，单聊按 --user-id（真 CLI 单聊要 --as user，mock 不看身份）。"""
    chat_id, user_id = flags.get("chat-id"), flags.get("user-id")
    if not chat_id and not user_id:
        usage_error('required flag(s) "chat-id" or "user-id" not set', param="--chat-id")
    name = f"chat-{chat_id}.json" if chat_id else f"p2p-{user_id}.json"
    payload = fixtures.read_optional("im", name) or {}
    return _paged(list(payload.get("messages") or []), flags)


def messages_search(flags: dict) -> Result:
    """按发言人（--sender）或被 @ 的人（--at-chatter-ids）搜消息，夹具按人存一份。"""
    sender, at = flags.get("sender"), flags.get("at-chatter-ids")
    if not sender and not at:
        usage_error('required flag(s) "sender" or "at-chatter-ids" not set', param="--sender")
    who = (sender or at).split(",")[0].strip()
    name = f"search-sender-{who}.json" if sender else f"search-at-{who}.json"
    payload = fixtures.read_optional("im", name) or {}
    return _paged(list(payload.get("items") or []), flags, key="items")


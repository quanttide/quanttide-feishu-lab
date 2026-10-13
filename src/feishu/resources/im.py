"""im 域：群/单聊的消息、成员与群链接，四个动作。

    im_chat_messages      im +chat-messages-list    群按 chat_id、单聊按 user_id（写一个就够）
    im_chat_members       im +chat-members-list     群成员
    im_messages_search    im +messages-search       按发言人 / 被 @ 人搜（用户身份拉）
    im_chat_link          im chats link             取群分享链接（填进邀请信）

``with_reactions`` 是反向 flag：只有明确写 False 才带 ``--no-reactions``；不给就随平台默认。
搜索这条命令的契约默认是不带表情（``defaults``）。

``im_chat_link`` 的边界（实测）：调用者得是群成员；**外部群机器人身份取不到**
（API 232033「机器人无权管理外部群」），要么用用户身份，要么别拿机器人试。
``validity_period`` 是写进请求体（``--data``）的：``week`` / ``year`` / ``permanently``，
不给就用群自己的设置。
"""

from __future__ import annotations

import json

from .action import Action

RESOURCE = "im"

_NO_REACTIONS = lambda v: ["--no-reactions"] if v is False else []      # noqa: E731

ACTIONS: dict[str, Action] = {
    "im_chat_messages": Action(
        command=("im", "+chat-messages-list"), landed="chat-messages",
        needs_any=("chat_id", "user_id"),
        params={"chat_id": "--chat-id", "page_size": "--page-size", "page_token": "--page-token",
                "order": "--order", "with_reactions": _NO_REACTIONS,
                "user_id": lambda v: ["--user-id", str(v), "--as", "user"]},
    ),
    "im_chat_members": Action(
        command=("im", "+chat-members-list", "--page-all"), landed="chat-members",
        params={"chat_id": "--chat-id", "page_token": "--page-token"},
    ),
    "im_chat_link": Action(
        command=("im", "chats", "link"), landed="chat-link",
        params={"chat_id": "--chat-id",
                "validity_period": lambda v: ["--data",
                                              json.dumps({"validity_period": v}, ensure_ascii=False)]},
    ),
    "im_messages_search": Action(
        command=("im", "+messages-search", "--as", "user"), landed="messages-search",
        needs_any=("sender", "at_chatter"), defaults={"with_reactions": False},
        params={"sender": "--sender", "at_chatter": "--at-chatter-ids", "chat_id": "--chat-id",
                "page_size": "--page-size", "page_token": "--page-token",
                "with_reactions": _NO_REACTIONS},
    ),
}

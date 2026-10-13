"""im 域：群/单聊的消息与成员，三个动作。

    im_chat_messages      im +chat-messages-list    群按 chat_id、单聊按 user_id（写一个就够）
    im_chat_members       im +chat-members-list     群成员
    im_messages_search    im +messages-search       按发言人 / 被 @ 人搜（用户身份拉）

``with_reactions`` 是反向 flag：只有明确写 False 才带 ``--no-reactions``；不给就随平台默认。
搜索这条命令的契约默认是不带表情（``defaults``）。
"""

from __future__ import annotations

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
    "im_messages_search": Action(
        command=("im", "+messages-search", "--as", "user"), landed="messages-search",
        needs_any=("sender", "at_chatter"), defaults={"with_reactions": False},
        params={"sender": "--sender", "at_chatter": "--at-chatter-ids", "chat_id": "--chat-id",
                "page_size": "--page-size", "page_token": "--page-token",
                "with_reactions": _NO_REACTIONS},
    ),
}

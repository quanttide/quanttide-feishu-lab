"""资源动作表：参数名 → 平台 flag 的那一份知识，两个实现共用。

真实现（``real.py``）用它拼 lark-cli 的 argv；夹具实现（``mock.py``）用同一条路径把
argv 交给同进程的假 CLI。**加一个动作只改这张表 + 契约里的一个方法**；参数名怎么变成
flag、哪些值是"假才带"的否定 flag，只在这里写一遍。
"""

from __future__ import annotations

import json

# 动作表：动作名 → (资源, 落盘动作名, 固定命令段, 参数名, flag 改写, 值改写)
# 落盘动作名就是 raw/<资源>/<这个名字>/<页序>.json——短名，不与资源重复
# 值改写（没写就是原样 --<参数名，下划线换中划线>）：
#   json_folder  值包成 {"folder": <值>} 再 json       join        列表拼逗号串
#   invert       值明确为假才带那个否定 flag（with_reactions=False → --no-reactions）
#   bool_text    布尔渲染成 true / false 文字          user_id     带 --user-id <值> --as user
#   only_true    值为真才带（如 --page-all）
#   false_flag   值明确为假时带 <flag>=false（如 --html=false） raw     原样传（如 --filter-json）
ACTIONS: dict[str, tuple] = {
    "mail_list": ("mail", "list", ("mail", "+triage"),
                  ("mailbox", "folder", "query", "page_size", "page_token"),
                  {"page_size": "--max", "folder": "--filter"}, {"folder": "json_folder"}),
    "mail_messages": ("mail", "messages", ("mail", "+messages"),
                      ("message_ids", "mailbox", "html"),
                      {"message_ids": "--message-ids"},
                      {"message_ids": "join", "html": "false_flag"}),
    "mail_send": ("mail", "send", ("mail", "+send", "--confirm-send"),
                  ("to", "subject", "body", "mailbox", "attachments"),
                  {"attachments": "--attach"}, {"attachments": "join"}),
    "im_chat_messages": ("im", "chat-messages", ("im", "+chat-messages-list"),
                         ("chat_id", "user_id", "order", "page_size", "with_reactions",
                          "page_token"),
                         {"with_reactions": "--no-reactions"},
                         {"user_id": "user_id", "with_reactions": "invert"}),
    "im_chat_members": ("im", "chat-members", ("im", "+chat-members-list", "--page-all"),
                        ("chat_id", "page_token"), {}, {}),
    "im_messages_search": ("im", "messages-search", ("im", "+messages-search", "--as", "user"),
                           ("sender", "at_chatter", "chat_id", "page_size", "with_reactions",
                            "page_token"),
                           {"at_chatter": "--at-chatter-ids", "with_reactions": "--no-reactions"},
                           {"with_reactions": "invert"}),
    "vc_meeting_search": ("vc", "meeting-search", ("vc", "+search", "--as", "user"),
                          ("participant_id", "start", "end", "page_size", "page_token"),
                          {"participant_id": "--participant-ids"}, {}),
    "vc_meeting_get": ("vc", "meeting-get", ("vc", "meeting", "get", "--with-participants", "true"),
                       ("meeting_id",), {}, {}),
    "task_list": ("task", "mine", ("task",), ("complete", "page_token"),
                  {"complete": "--complete"}, {"complete": "bool_text"}),
    "drive_search": ("doc", "drive-search", ("drive", "+search"),
                     ("edited_since", "created_since", "page_size", "page_token"), {}, {}),
    "docs_fetch": ("doc", "docs-fetch", ("docs", "+fetch"), ("doc", "detail", "doc_format"), {}, {}),
    "base_records": ("base", "record-list", ("base", "+record-list"),
                     ("base_token", "table_id", "filter_json", "offset", "limit"),
                     {}, {"filter_json": "raw"}),
    "mail_attachment_download": ("mail", "attachments", ("mail", "user_mailbox.message.attachments",
                                          "download_url"),
                                 ("mailbox", "message_id", "attachment_ids"),
                                 {"mailbox": "--user-mailbox-id"},
                                 {"attachment_ids": "join"}),
}

# task 的三种取法（我负责 / 与我相关 / 清单）——同一个动作换命令段
TASK_COMMAND = {"mine": ("task", "+get-my-tasks", "--page-all"),
                "related": ("task", "+get-related-tasks", "--page-all"),
                "tasklists": ("task", "tasklists", "list", "--as", "user", "--page-all")}


def emit_arg(args: list[str], name: str, value, flag_of: dict, mode: dict) -> None:
    """把一个参数变成 argv 片段。"""
    flag = flag_of.get(name, "--" + name.replace("_", "-"))
    how = mode.get(name)
    if how == "invert":
        if value is False:          # 只有明确要求"不要"才带否定 flag；没给就按平台默认
            args.append(flag)
    elif value in (None, "", []):
        return
    elif how == "user_id":
        args += ["--user-id", str(value), "--as", "user"]
    elif how == "json_folder":
        args += [flag, json.dumps({"folder": value}, ensure_ascii=False)]
    elif how == "false_flag":
        if value is False:
            args.append(f"{flag}=false")
    elif how == "join":
        args += [flag, ",".join(str(v) for v in value)]
    elif how == "bool_text":
        args += [flag, "true" if value else "false"]
    else:
        args += [flag, str(value)]



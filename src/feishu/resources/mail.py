"""mail 域：列摘要、取正文、发信、下附件——四个动作，只有发信是写。

落盘：``raw/mail/<动作>/<页序>.json``；附件原件另落 ``raw/mail/attachments/<附件id>/<原文件名>``。

    mail_list                  mail +triage         按文件夹（收件箱 / Spam …）列摘要
    mail_messages              mail +messages       按 message_id 取正文
    mail_attachment_download    mail user_mailbox.message.attachments download_url
    mail_send                  mail +send --confirm-send

两条命令怪癖写在这里，不往共用处加名字：``folder`` 要包成 ``{"folder": …}`` 的 JSON 给
``--filter``；``html=false`` 才是「不要 HTML 正文」，给 true 不带这个 flag。
"""

from __future__ import annotations

import json

from .action import Action

RESOURCE = "mail"

ACTIONS: dict[str, Action] = {
    "mail_list": Action(
        command=("mail", "+triage"), landed="list",
        params={"mailbox": "--mailbox", "query": "--query", "page_size": "--max",
                "page_token": "--page-token",
                "folder": lambda v: ["--filter", json.dumps({"folder": v}, ensure_ascii=False)]},
    ),
    "mail_messages": Action(
        command=("mail", "+messages"), landed="messages",
        params={"mailbox": "--mailbox",
                "message_ids": lambda v: ["--message-ids", ",".join(map(str, v))],
                "html": lambda v: ["--html=false"] if v is False else []},
    ),
    "mail_send": Action(
        command=("mail", "+send", "--confirm-send"), landed="send",
        params={"to": "--to", "subject": "--subject", "body": "--body", "mailbox": "--mailbox",
                "attachments": lambda v: ["--attach", ",".join(map(str, v))]},
    ),
    "mail_attachment_download": Action(
        command=("mail", "user_mailbox.message.attachments", "download_url"), landed="attachments",
        kind="files",
        params={"mailbox": "--user-mailbox-id", "message_id": "--message-id",
                "attachment_ids": lambda v: ["--attachment-ids", ",".join(map(str, v))]},
    ),
}

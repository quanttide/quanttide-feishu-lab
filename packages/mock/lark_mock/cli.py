"""mock lark-cli 的 argv 分发：只实现流程要用的五条命令。

其余命令面与真 CLI 一致地回 validation 错误（stderr + exit 2）——
缺哪条命令，就是能力层真实要用而 mock 还没接的信号，不假装有。
"""

from __future__ import annotations

import sys

from . import base as base_mod
from . import drive as drive_mod
from . import fixtures
from . import im as im_mod
from . import mail as mail_mod
from . import task as task_mod
from . import vc as vc_mod
from .envelope import Result, emit, usage_error

USAGE = """\
lark-cli (mock) — 实验室假 lark-cli：读 tests/fixtures/，不打真飞书。

用法:
  lark-cli <域> <命令> [flags]

已实现的命令:
  mail +triage           列邮件摘要（tests/fixtures/mail/<文件夹>.json）
  mail +messages         按 message_id 读完整邮件
  mail +send             发信（--confirm-send 写 tests/fixtures/outbox/）
  mail user_mailbox.message.attachments download_url
                         回附件下载地址（tests/fixtures/attachments/）
  base +record-list      读调研表（tests/fixtures/survey.json）
  im +chat-members-list  读群成员（tests/fixtures/group_members.json）
  im +chat-messages-list 读群聊 / 单聊消息（tests/fixtures/im/）
  im +messages-search    按发言人或被 @ 的人搜消息（tests/fixtures/im/）
  vc +search             列会议（tests/fixtures/vc/search-<participant>.json）
  vc meeting get         读会议详情（tests/fixtures/vc/meeting-<id>.json）
  task +get-my-tasks     列我负责的任务（tests/fixtures/task/my-tasks.json）
  task +get-related-tasks 列与我相关的任务
  task tasklists list    列任务清单
  drive +search          列文档变更（tests/fixtures/drive/search.json）
  docs +fetch            导出文档正文（tests/fixtures/drive/doc-<token>.json）

环境变量:
  LARK_MOCK_FIXTURES     换夹具目录（smoke 用它指到临时目录）

PATH 遮蔽真 CLI 的用法:
  PATH=<实验室>/packages/mock/bin:$PATH lark-cli mail +triage --format json
"""

HELP = {
    "mail +triage": """\
用法:
  lark-cli mail +triage [flags]

列邮件摘要（mock：读 tests/fixtures/mail/<文件夹>.json，游标按位置翻页）。

flags（与真 CLI 同名同义，完整语义见真 CLI 的 --help）:
  --filter string    筛选 JSON：folder / from / subject
  --query string     全文关键词
  --max int          最大返回条数（默认 20）
  --page-token string  翻页游标（mock 形如 list:3）
  --format string    table（默认）| json | data
  --mailbox string   邮箱（默认 me）
  --jq string        用 jq 过滤 JSON 输出
  --dry-run          只回 argv 与夹具根，不读夹具""",
    "mail +messages": """\
用法:
  lark-cli mail +messages --message-ids <id1>,<id2> [flags]

按 message_id 读完整邮件（mock：在 tests/fixtures/mail/ 与 outbox/ 里找）。

flags:
  --message-ids string  必填，逗号分隔
  --html=false          省略 body_html
  --format string       json（默认）| pretty | ndjson
  --jq string / --dry-run""",
    "mail +send": """\
用法:
  lark-cli mail +send --to <addr> --subject <s> --body <b> [--confirm-send]

发信。默认草稿模式（真 CLI 存草稿，mock 不落盘）；--confirm-send 才写
tests/fixtures/outbox/<message_id>.json，message_id 与 Python 层 mock 同算法。

flags:
  --to / --subject / --body（或 --body-file）
  --attach string       附件路径，逗号分隔（mock 只记文件名）
  --confirm-send        真发（写 outbox）
  --format string / --jq string / --dry-run""",
    "base +record-list": """\
用法:
  lark-cli base +record-list --base-token <t> --table-id <t> [flags]

读调研表（mock：tests/fixtures/survey.json）。

flags:
  --filter-json string  view filter 形状：{"logic":"and","conditions":[[字段,==,值]]}
                        字段认 email / submitted_at 与中文别名 邮箱 / 提交时间，
                        answers 里的键也按列名查；支持 @file
  --field-id string     字段投影，可重复
  --offset / --limit    分页
  --format string       markdown（默认）| json
  --jq string / --dry-run""",
    "im +chat-members-list": """\
用法:
  lark-cli im +chat-members-list --chat-id <oc_xxx> [flags]

读群成员（mock：tests/fixtures/group_members.json）。
mock 的 member_id 直接是邮箱（member_id_type=email）；真 CLI 是 open_id。

flags:
  --chat-id string      必填
  --member-types string user,bot（默认全要）
  --format string       json（默认）| table
  --jq string / --dry-run""",
    "mail user_mailbox.message.attachments download_url": """\
用法:
  lark-cli mail user_mailbox.message.attachments download_url \
--user-mailbox-id <邮箱> --message-id <id> --attachment-ids <aid> [flags]

回附件下载地址（mock：tests/fixtures/attachments/<文件名> 的 file:// 地址）。
附件 id 与 +messages 的归一化规则一致：<message_id>-att-<序号>。

flags:
  --user-mailbox-id string / --mailbox string
  --message-id string   必填
  --attachment-ids string 逗号分隔，缺省全要
  --format string / --jq string / --dry-run""",
    "im +chat-messages-list": """\
用法:
  lark-cli im +chat-messages-list [--chat-id <oc_xxx> | --user-id <ou_xxx>] [flags]

读会话消息（mock：tests/fixtures/im/chat-<chat_id>.json 或 p2p-<user_id>.json）。
群按 --chat-id，单聊按 --user-id（真 CLI 单聊要 --as user）。

flags:
  --chat-id / --user-id
  --order string        asc（默认）| desc
  --page-size int       默认 50
  --page-token string   mock 形如 list:50
  --no-reactions        去掉表情回复
  --format string / --jq string / --dry-run""",
    "im +messages-search": """\
用法:
  lark-cli im +messages-search [--sender <ou_xxx> | --at-chatter-ids <ou_xxx>] [flags]

搜消息（mock：tests/fixtures/im/search-sender-<id>.json / search-at-<id>.json）。

flags:
  --sender string       某人发出的消息
  --at-chatter-ids string  被 @ 到的消息
  --page-all / --page-size / --page-token / --no-reactions
  --format string / --jq string / --dry-run""",
    "vc +search": """\
用法:
  lark-cli vc +search --participant-ids <ou_xxx> [--start <日期> --end <日期>] [flags]

列会议（mock：tests/fixtures/vc/search-<participant_id>.json）。
真 CLI 要 --as user（按参会人搜自己的会议）。

flags:
  --participant-ids string  必填，逗号分隔
  --start / --end       日期范围
  --page-size int / --page-token string
  --format string / --jq string / --dry-run""",
    "vc meeting get": """\
用法:
  lark-cli vc meeting get --meeting-id <id> [--with-participants true] [flags]

读会议详情（mock：tests/fixtures/vc/meeting-<meeting_id>.json），带参会人名单。

flags:
  --meeting-id string   必填
  --with-participants string  true / false
  --format string / --jq string / --dry-run""",
    "task +get-my-tasks": """\
用法:
  lark-cli task +get-my-tasks [--page-all] [--complete[=false]] [flags]

列我负责的任务（mock：tests/fixtures/task/my-tasks.json）。
--complete 只回已完成，--complete=false 只回未完成，不写都回。

flags:
  --page-all / --page-size / --page-token
  --complete string      true | false
  --format string / --jq string / --dry-run""",
    "task +get-related-tasks": """\
用法:
  lark-cli task +get-related-tasks [--page-all] [flags]

列与我相关的任务（mock：tests/fixtures/task/related-tasks.json）。""",
    "task tasklists list": """\
用法:
  lark-cli task tasklists list [--as user] [--page-all] [flags]

列任务清单（mock：tests/fixtures/task/tasklists.json）。""",
    "drive +search": """\
用法:
  lark-cli drive +search [--edited-since <日期> | --created-since <日期>] [flags]

列文档变更（mock：tests/fixtures/drive/search.json）。
两个 since 至少要给一个；mock 按 edited_time / created_time 字符串比。

flags:
  --edited-since / --created-since string
  --page-size int / --page-token string
  --format string / --jq string / --dry-run""",
    "docs +fetch": """\
用法:
  lark-cli docs +fetch --doc <token> [--detail simple] [--doc-format markdown] [flags]

导出文档正文（mock：tests/fixtures/drive/doc-<token>.json）。

flags:
  --doc string          必填（docx / wiki token）
  --detail string       simple（默认）| full
  --doc-format string   markdown（默认）
  --format string / --jq string / --dry-run""",
}

# flag 表：名字 → (类型, 默认值)。类型：str / bool / int / list（可重复）
COMMON = {"as": ("str", "auto"), "jq": ("str", None),
          "dry-run": ("bool", False), "json": ("bool", False)}

SPECS: dict[str, dict] = {
    "mail +triage": {**COMMON,
                     "filter": ("str", None), "query": ("str", None),
                     "format": ("str", "table"), "max": ("int", 20),
                     "page-size": ("int", None), "page-token": ("str", None),
                     "mailbox": ("str", "me"), "labels": ("bool", False)},
    "mail +messages": {**COMMON,
                       "message-ids": ("str", None), "mailbox": ("str", "me"),
                       "html": ("bool", True), "format": ("str", "json")},
    "mail +send": {**COMMON,
                   "to": ("str", None), "subject": ("str", None),
                   "body": ("str", None), "body-file": ("str", None),
                   "attach": ("str", None), "from": ("str", None),
                   "mailbox": ("str", None), "confirm-send": ("bool", False),
                   "no-signature": ("bool", False), "format": ("str", "json")},
    "base +record-list": {**COMMON,
                          "base-token": ("str", None), "table-id": ("str", None),
                          "field-id": ("list", None), "view-id": ("str", None),
                          "filter-json": ("str", None), "sort-json": ("str", None),
                          "offset": ("int", 0), "limit": ("int", 100),
                          "format": ("str", "markdown")},
    "im +chat-members-list": {**COMMON,
                              "chat-id": ("str", None), "member-types": ("str", None),
                              "member-id-type": ("str", "open_id"),
                              "page-all": ("bool", False), "page-size": ("int", 20),
                              "page-token": ("str", None), "format": ("str", "json")},
    "mail user_mailbox.message.attachments download_url": {**COMMON,
                              "user-mailbox-id": ("str", None), "mailbox": ("str", None),
                              "message-id": ("str", None), "attachment-ids": ("str", None),
                              "format": ("str", "json")},
    "im +chat-messages-list": {**COMMON,
                               "chat-id": ("str", None), "user-id": ("str", None),
                               "order": ("str", "asc"), "page-size": ("int", 50),
                               "page-token": ("str", None), "no-reactions": ("bool", False),
                               "format": ("str", "json")},
    "im +messages-search": {**COMMON,
                            "sender": ("str", None), "at-chatter-ids": ("str", None),
                            "chat-id": ("str", None), "page-all": ("bool", False),
                            "page-limit": ("int", None), "page-size": ("int", 50),
                            "page-token": ("str", None), "no-reactions": ("bool", False),
                            "format": ("str", "json")},
    "vc +search": {**COMMON,
                   "participant-ids": ("str", None), "participant-id": ("str", None),
                   "start": ("str", None), "end": ("str", None),
                   "page-size": ("int", 30), "page-token": ("str", None),
                   "format": ("str", "json")},
    "vc meeting get": {**COMMON,
                       "meeting-id": ("str", None), "with-participants": ("str", None),
                       "format": ("str", "json")},
    "task +get-my-tasks": {**COMMON,
                           "page-all": ("bool", False), "page-size": ("int", 50),
                           "page-token": ("str", None), "complete": ("str", None),
                           "format": ("str", "json")},
    "task +get-related-tasks": {**COMMON,
                                "page-all": ("bool", False), "page-size": ("int", 50),
                                "page-token": ("str", None), "format": ("str", "json")},
    "task tasklists list": {**COMMON,
                            "page-all": ("bool", False), "page-size": ("int", 50),
                            "page-token": ("str", None), "format": ("str", "json")},
    "drive +search": {**COMMON,
                      "edited-since": ("str", None), "created-since": ("str", None),
                      "page-size": ("int", 20), "page-token": ("str", None),
                      "format": ("str", "json")},
    "docs +fetch": {**COMMON,
                    "doc": ("str", None), "detail": ("str", "simple"),
                    "doc-format": ("str", "markdown"), "format": ("str", "json")},
}

HANDLERS = {
    "mail +triage": mail_mod.triage,
    "mail +messages": mail_mod.messages,
    "mail +send": mail_mod.send,
    "mail user_mailbox.message.attachments download_url": mail_mod.attachments_download,
    "base +record-list": base_mod.record_list,
    "im +chat-members-list": im_mod.chat_members_list,
    "im +chat-messages-list": im_mod.chat_messages_list,
    "im +messages-search": im_mod.messages_search,
    "vc +search": vc_mod.search,
    "vc meeting get": vc_mod.meeting_get,
    "task +get-my-tasks": task_mod.list_tasks,
    "task +get-related-tasks": lambda flags: task_mod.list_tasks(flags, command="+get-related-tasks"),
    "task tasklists list": lambda flags: task_mod.list_tasks(flags, command="tasklists list"),
    "drive +search": drive_mod.search,
    "docs +fetch": drive_mod.fetch,
}

DOMAINS = ("mail", "base", "im", "vc", "task", "drive", "docs")

# 多段命令：域名后面的前几段一起才是命令名（真 CLI 的形状）
MULTI_PART = {
    ("mail", "user_mailbox.message.attachments"): "download_url",
    ("vc", "meeting"): "get",
    ("task", "tasklists"): "list",
}


def _command_of(domain: str, rest: list[str]) -> tuple[str, list[str]]:
    """把 argv 的前几段拼成命令名，回（命令名，剩下的 flag 段）。

    mail 的附件命令是 ``mail user_mailbox.message.attachments download_url``——
    段数不固定，所以不能一律取 rest[0]。
    """
    for (dom, prefix), action in MULTI_PART.items():
        if dom == domain and rest and rest[0] == prefix:
            if len(rest) < 2 or rest[1] != action:
                usage_error(f"unknown command: {domain} {prefix} {rest[1] if len(rest) > 1 else ''}",
                            hint=f"用法: lark-cli {domain} {prefix} {action} …")
            return f"{domain} {prefix} {action}", rest[2:]
    return f"{domain} {rest[0]}", rest[1:]


def _parse(spec: dict, argv: list[str], command: str) -> dict:
    flags = {name: default for name, (_, default) in spec.items()}
    for name, (kind, _) in spec.items():
        if kind == "list" and flags[name] is None:
            flags[name] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if not tok.startswith("-"):
            usage_error(f"unknown argument: {tok}", hint=f"Run `lark-cli {command} --help`")
        body = tok[1:] if not tok.startswith("--") else tok[2:]
        if "=" in body:
            key, explicit = body.split("=", 1)
        else:
            key, explicit = body, None
        if key == "q":                      # -q 是 --jq 的简写
            key = "jq"
        if key not in spec:
            usage_error(f"unknown flag: --{key}",
                        hint=f"Run `lark-cli {command} --help`")
        kind, _ = spec[key]
        if kind == "bool":
            flags[key] = True if explicit is None else explicit.lower() not in ("false", "0", "no")
            i += 1
            continue
        if explicit is None:
            if i + 1 >= len(argv):
                usage_error(f"flag needs an argument: --{key}", param=f"--{key}")
            value, i = argv[i + 1], i + 2
        else:
            value, i = explicit, i + 1
        if kind == "int":
            try:
                value = int(value)
            except ValueError:
                usage_error(f"--{key} 需要整数，收到 {value!r}", param=f"--{key}")
        if kind == "list":
            flags[key].append(value)
        else:
            flags[key] = value
    return flags


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if argv[0] == "--version":
        print("mock lark-cli (packages/mock)")
        return 0

    domain, rest = argv[0], argv[1:]
    if domain not in DOMAINS:
        usage_error(f"unknown domain: {domain}",
                    hint=f"mock 实现了 {' / '.join(DOMAINS)} 域，见 packages/mock/README.md")
    if not rest:
        usage_error(f"missing command: lark-cli {domain} <command>",
                    hint=f"Run `lark-cli {domain} --help`")
    if rest[0] in ("-h", "--help"):
        print(USAGE)
        return 0

    command, tail = _command_of(domain, rest)
    if command not in SPECS:
        usage_error(f"unknown command: {command}",
                    hint="mock 实现的命令与夹具映射见 packages/mock/README.md")
    if any(a in ("-h", "--help") for a in tail):
        print(HELP[command])
        return 0

    flags = _parse(SPECS[command], tail, command)
    if flags["dry-run"]:
        emit(Result({"command": [command, *rest[1:]], "fixtures": str(fixtures.root())}),
             flags, command, top={"identity": "user", "dry_run": True})
        return 0
    emit(HANDLERS[command](flags), flags, command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

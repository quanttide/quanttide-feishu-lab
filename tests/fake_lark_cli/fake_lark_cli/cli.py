"""mock lark-cli 的 argv 分发：一份命令声明表，生成其余一切。

``COMMANDS`` 是唯一的声明处（命令名、一句摘要、用法行、flag 表、谁来处理），
``USAGE``（命令目录）、``HELP``（每条命令的用法）、``SPECS``（解析用的 flag 表）、
``HANDLERS`` 与 ``MULTI_PART``（多段命令）全部由它生成。加一条命令只改一处，
不会出现「帮助里写了、解析器不认」。

其余命令面与真 CLI 一致地回 validation 错误（stderr + exit 2）——缺哪条命令，
就是能力层真实要用而 mock 还没接的信号，不假装有。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from . import base as base_mod
from . import drive as drive_mod
from . import fixtures
from . import im as im_mod
from . import mail as mail_mod
from . import task as task_mod
from . import vc as vc_mod
from .envelope import Result, emit, usage_error

KIND_LABEL = {"str": "string", "bool": "bool", "int": "int", "list": "string(可重复)"}


@dataclass(frozen=True)
class Flag:
    """一个 flag：类型 / 缺省 / 一句说明。说明进 HELP，类型与缺省进解析器。"""

    kind: str
    default: Any = None
    help: str = ""

    def label(self) -> str:
        text = KIND_LABEL.get(self.kind, self.kind)
        if self.kind == "bool" or self.default in (None, False):
            return text
        return f"{text}，默认 {self.default}"


@dataclass(frozen=True)
class Command:
    """一条命令：用法行、一句摘要、flag 表、处理器、补充说明。"""

    usage: str
    summary: str
    handler: Callable[[dict], Result]
    flags: dict[str, Flag] = field(default_factory=dict)
    notes: str = ""


COMMON = {
    "as": Flag("str", "auto", "身份：auto / user / bot"),
    "jq": Flag("str", None, "用 jq 过滤 JSON 输出"),
    "dry-run": Flag("bool", False, "只回 argv 与夹具根，不读夹具"),
    "json": Flag("bool", False, "--format=json 的简写"),
}

TASK_PAGING = {
    "page-all": Flag("bool", False, "一次拉完"),
    "page-size": Flag("int", 50, "每页条数"),
    "page-token": Flag("str", None, "翻页游标"),
}


def _flags(**own: Flag) -> dict[str, Flag]:
    """命令自己的 flag + 共用 flag（--as / --jq / --dry-run / --json）。"""
    return {**COMMON, **own}


COMMANDS: dict[str, Command] = {
    "mail +triage": Command(
        "mail +triage [flags]",
        "列邮件摘要（tests/fixtures/mail/<文件夹>.json）",
        mail_mod.triage,
        _flags(**{

            "filter": Flag("str", None, "筛选 JSON：folder / from / subject"),
            "query": Flag("str", None, "全文关键词"), "max": Flag("int", 20, "最大返回条数"),
            "page-size": Flag("int", None, "每页条数（优先于 --max）"),
            "page-token": Flag("str", None, "翻页游标（mock 形如 list:3）"),
            "mailbox": Flag("str", "me", "邮箱"), "labels": Flag("bool", False, "附带标签"),
            "format": Flag("str", "table", "table（默认）| json | data"),

        }),
        "mock 读 tests/fixtures/mail/<文件夹>.json，游标按位置翻页。",
    ),
    "mail +messages": Command(
        "mail +messages --message-ids <id1>,<id2> [flags]",
        "按 message_id 读完整邮件",
        mail_mod.messages,
        _flags(**{

            "message-ids": Flag("str", None, "必填，逗号分隔"), "mailbox": Flag("str", "me", "邮箱"),
            "html": Flag("bool", True, "带 body_html（--html=false 省略）"),
            "format": Flag("str", "json", "json（默认）| pretty | ndjson"),

        }),
        "mock 在 tests/fixtures/mail/ 与 outbox/ 里按 message_id 找。",
    ),
    "mail +send": Command(
        "mail +send --to <addr> --subject <s> --body <b> [--confirm-send]",
        "发信（--confirm-send 写 tests/fixtures/outbox/）",
        mail_mod.send,
        _flags(**{

            "to": Flag("str", None, "收件人，必填"), "subject": Flag("str", None, "主题，必填"),
            "body": Flag("str", None, "正文（或用 --body-file）"),
            "body-file": Flag("str", None, "从文件读正文，与 --body 互斥"),
            "attach": Flag("str", None, "附件路径，逗号分隔（mock 只记文件名）"),
            "from": Flag("str", None, "发件地址"), "mailbox": Flag("str", None, "邮箱"),
            "confirm-send": Flag("bool", False, "真发（写 outbox）；不给是草稿模式"),
            "no-signature": Flag("bool", False, "不带签名"), "format": Flag("str", "json", "json"),

        }),
        "默认草稿模式；--confirm-send 才写 tests/fixtures/outbox/<message_id>.json，"
        "message_id 与 Python 层 mock 同算法。",
    ),
    "mail user_mailbox.message.attachments download_url": Command(
        "mail user_mailbox.message.attachments download_url "
        "--user-mailbox-id <邮箱> --message-id <id> [--attachment-ids <aid>] [flags]",
        "回附件下载地址（tests/fixtures/attachments/）",
        mail_mod.attachments_download,
        _flags(**{

            "user-mailbox-id": Flag("str", None, "邮箱"),
            "mailbox": Flag("str", None, "邮箱（--user-mailbox-id 的别名）"),
            "message-id": Flag("str", None, "必填"),
            "attachment-ids": Flag("str", None, "附件 id，逗号分隔，缺省全要"),
            "format": Flag("str", "json", "json"),

        }),
        "mock 回 tests/fixtures/attachments/<文件名> 的 file:// 地址；附件 id 与 +messages "
        "的归一化规则一致（<message_id>-att-<序号>）。",
    ),
    "base +record-list": Command(
        "base +record-list --base-token <t> --table-id <t> [flags]",
        "读调研表（tests/fixtures/survey.json）",
        base_mod.record_list,
        _flags(**{

            "base-token": Flag("str", None, "必填"), "table-id": Flag("str", None, "必填"),
            "field-id": Flag("list", None, "字段投影，可重复"), "view-id": Flag("str", None, "视图"),
            "filter-json": Flag("str", None, "view filter 形状，支持 @file"),
            "sort-json": Flag("str", None, "排序"), "offset": Flag("int", 0, "起始位置"),
            "limit": Flag("int", 100, "每页条数"),
            "format": Flag("str", "markdown", "markdown（默认）| json"),

        }),
        "字段认 email / submitted_at 与中文别名 邮箱 / 提交时间，answers 里的键也按列名查。",
    ),
    "im +chat-members-list": Command(
        "im +chat-members-list --chat-id <oc_xxx> [flags]",
        "读群成员（tests/fixtures/group_members.json）",
        im_mod.chat_members_list,
        _flags(**{

            "chat-id": Flag("str", None, "必填"),
            "member-types": Flag("str", None, "user,bot（默认全要）"),
            "member-id-type": Flag("str", "open_id", "id 类型"),
            "page-all": Flag("bool", False, "一次拉完"), "page-size": Flag("int", 20, "每页条数"),
            "page-token": Flag("str", None, "翻页游标"),
            "format": Flag("str", "json", "json（默认）| table"),

        }),
        "mock 的 member_id 直接是邮箱（member_id_type=email）；真 CLI 是 open_id。",
    ),
    "im chats link": Command(
        "im chats link --chat-id <oc_xxx> [flags]",
        "取群分享链接（tests/fixtures/im/chat-link.json）",
        im_mod.chats_link,
        _flags(**{

            "chat-id": Flag("str", None, "必填"),
            "data": Flag("str", None, "请求体 JSON，如 {\"validity_period\": \"permanently\"}"),
            "as": Flag("str", "user", "身份 user | bot（mock 不看身份）"),
            "format": Flag("str", "json", "json（默认）| table"),

        }),
        "mock 回一份夹具链接；真 CLI 要用户身份，外部群机器人身份会被拒（232033）。",
    ),
    "im +chat-messages-list": Command(
        "im +chat-messages-list [--chat-id <oc_xxx> | --user-id <ou_xxx>] [flags]",
        "读群聊 / 单聊消息（tests/fixtures/im/）",
        im_mod.chat_messages_list,
        _flags(**{

            "chat-id": Flag("str", None, "群 id"),
            "user-id": Flag("str", None, "单聊对端 open_id（真 CLI 单聊要 --as user）"),
            "order": Flag("str", "asc", "asc（默认）| desc"), "page-size": Flag("int", 50, "每页条数"),
            "page-token": Flag("str", None, "翻页游标（mock 形如 list:50）"),
            "no-reactions": Flag("bool", False, "去掉表情回复"), "format": Flag("str", "json", "json"),

        }),
        "mock 读 tests/fixtures/im/chat-<chat_id>.json 或 p2p-<user_id>.json。",
    ),
    "im +messages-search": Command(
        "im +messages-search [--sender <ou_xxx> | --at-chatter-ids <ou_xxx>] [flags]",
        "按发言人或被 @ 的人搜消息（tests/fixtures/im/）",
        im_mod.messages_search,
        _flags(**{

            "sender": Flag("str", None, "某人发出的消息"),
            "at-chatter-ids": Flag("str", None, "被 @ 到的消息"), "chat-id": Flag("str", None, "限定会话"),
            "page-all": Flag("bool", False, "一次拉完"), "page-limit": Flag("int", None, "翻页上限"),
            "page-size": Flag("int", 50, "每页条数"), "page-token": Flag("str", None, "翻页游标"),
            "no-reactions": Flag("bool", False, "去掉表情回复"), "format": Flag("str", "json", "json"),

        }),
        "mock 读 tests/fixtures/im/search-sender-<id>.json / search-at-<id>.json。",
    ),
    "vc +search": Command(
        "vc +search --participant-ids <ou_xxx> [--start <日期> --end <日期>] [flags]",
        "列会议（tests/fixtures/vc/search-<participant>.json）",
        vc_mod.search,
        _flags(**{

            "participant-ids": Flag("str", None, "必填，逗号分隔"),
            "participant-id": Flag("str", None, "单个参会人 id"), "start": Flag("str", None, "起始日期"),
            "end": Flag("str", None, "结束日期"), "page-size": Flag("int", 30, "每页条数"),
            "page-token": Flag("str", None, "翻页游标"), "format": Flag("str", "json", "json"),

        }),
        "真 CLI 要 --as user（按参会人搜自己的会议）。",
    ),
    "vc meeting get": Command(
        "vc meeting get --meeting-id <id> [--with-participants true] [flags]",
        "读会议详情（tests/fixtures/vc/meeting-<id>.json）",
        vc_mod.meeting_get,
        _flags(**{

            "meeting-id": Flag("str", None, "必填"),
            "with-participants": Flag("str", None, "true / false"),
            "format": Flag("str", "json", "json"),

        }),
        "mock 回的详情带参会人名单。",
    ),
    "task +get-my-tasks": Command(
        "task +get-my-tasks [--page-all] [--complete[=false]] [flags]",
        "列我负责的任务（tests/fixtures/task/my-tasks.json）",
        task_mod.list_tasks,
        _flags(**{**TASK_PAGING,
                  "complete": Flag("str", None, "true | false，不写都回"),
                  "format": Flag("str", "json", "json")}),
        "--complete 只回已完成，--complete=false 只回未完成。",
    ),
    "task +get-related-tasks": Command(
        "task +get-related-tasks [--page-all] [flags]",
        "列与我相关的任务（tests/fixtures/task/related-tasks.json）",
        lambda flags: task_mod.list_tasks(flags, command="+get-related-tasks"),
        _flags(**{**TASK_PAGING, "format": Flag("str", "json", "json")}),
    ),
    "task tasklists list": Command(
        "task tasklists list [--as user] [--page-all] [flags]",
        "列任务清单（tests/fixtures/task/tasklists.json）",
        lambda flags: task_mod.list_tasks(flags, command="tasklists list"),
        _flags(**{**TASK_PAGING, "format": Flag("str", "json", "json")}),
        "mock 只认 --as user。",
    ),
    "drive +search": Command(
        "drive +search [--edited-since <日期> | --created-since <日期>] [flags]",
        "列文档变更（tests/fixtures/drive/search.json）",
        drive_mod.search,
        _flags(**{

            "edited-since": Flag("str", None, "编辑时间下限"),
            "created-since": Flag("str", None, "创建时间下限"), "page-size": Flag("int", 20, "每页条数"),
            "page-token": Flag("str", None, "翻页游标"), "format": Flag("str", "json", "json"),

        }),
        "两个 since 至少要给一个；mock 按 edited_time / created_time 字符串比。",
    ),
    "docs +fetch": Command(
        "docs +fetch --doc <token> [--detail simple] [--doc-format markdown] [flags]",
        "导出文档正文（tests/fixtures/drive/doc-<token>.json）",
        drive_mod.fetch,
        _flags(**{

            "doc": Flag("str", None, "必填（docx / wiki token）"),
            "detail": Flag("str", "simple", "simple（默认）| full"),
            "doc-format": Flag("str", "markdown", "markdown（默认）"),
            "format": Flag("str", "json", "json"),

        }),
    ),
}

# ── 由声明生成：其余四样 ─────────────────────────────────
DOMAINS = tuple(sorted({name.split()[0] for name in COMMANDS}))
SPECS = {name: {k: (f.kind, f.default) for k, f in cmd.flags.items()}
         for name, cmd in COMMANDS.items()}
HANDLERS = {name: cmd.handler for name, cmd in COMMANDS.items()}
# 多段命令：域名与动作之间还有段（如 vc meeting get / task tasklists list）
MULTI_PART = {(parts[0], " ".join(parts[1:-1])): parts[-1]
              for parts in (name.split() for name in COMMANDS)
              if len(parts) > 2}

_NAME_COL = max(len(name) for name in COMMANDS) + 2


def _usage_doc() -> str:
    rows = "\n".join(f"  {name:<{_NAME_COL}}{cmd.summary}" for name, cmd in COMMANDS.items())
    return f"""\
lark-cli (mock) — 实验室假 lark-cli：读 tests/fixtures/，不打真飞书。

用法:
  lark-cli <域> <命令> [flags]

已实现的命令（{len(COMMANDS)} 条，{len(DOMAINS)} 个域）:
{rows}

环境变量:
  LARK_MOCK_FIXTURES     换夹具目录（smoke 用它指到临时目录）

PATH 遮蔽真 CLI 的用法:
  PATH=<实验室>/tests/fake_lark_cli/bin:$PATH lark-cli mail +triage --format json
"""


def _help_doc(cmd: Command) -> str:
    flags = "\n".join(f"  --{name:<22}{flag.label():<20}{flag.help}"
                      for name, flag in cmd.flags.items())
    notes = f"\n{cmd.notes}\n" if cmd.notes else ""
    return f"用法:\n  lark-cli {cmd.usage}\n{notes}\nflags（与真 CLI 同名同义，完整语义见真 CLI 的 --help）:\n{flags}"


USAGE = _usage_doc()
HELP = {name: _help_doc(cmd) for name, cmd in COMMANDS.items()}


def _command_of(domain: str, rest: list[str]) -> tuple[str, list[str]]:
    """把 argv 的前几段拼成命令名，回（命令名，剩下的 flag 段）。

    多段命令（``vc meeting get``、``task tasklists list``、
    ``mail user_mailbox.message.attachments download_url``）段数不固定，
    不能一律取 rest[0]。
    """
    for (dom, prefix), action in MULTI_PART.items():
        if dom == domain and rest and rest[0] == prefix:
            if len(rest) < 2 or rest[1] != action:
                got = rest[1] if len(rest) > 1 else ""
                usage_error(f"unknown command: {domain} {prefix} {got}",
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
            usage_error(f"unknown flag: --{key}", param=f"--{key}",
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
        print("mock lark-cli (tests/fake_lark_cli)")
        return 0

    domain, rest = argv[0], argv[1:]
    if domain not in DOMAINS:
        usage_error(f"unknown domain: {domain}",
                    hint=f"mock 实现了 {' / '.join(DOMAINS)} 域，见 tests/fake_lark_cli/README.md")
    if not rest:
        usage_error(f"missing command: lark-cli {domain} <command>",
                    hint=f"Run `lark-cli {domain} --help`")
    if rest[0] in ("-h", "--help"):
        print(USAGE)
        return 0

    command, tail = _command_of(domain, rest)
    if command not in COMMANDS:
        usage_error(f"unknown command: {command}",
                    hint="mock 实现的命令与夹具映射见 tests/fake_lark_cli/README.md")
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

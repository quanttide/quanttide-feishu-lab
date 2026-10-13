"""资源层的形状与规矩：一个动作登记什么、参数怎么变成命令行、取回来的东西长什么样。

**表就是契约**——这层的十四个动作没有第二处签名：每个动作长什么样写在它所属的资源文件里
（``mail.py`` / ``im.py`` / ``vc.py`` / ``task.py`` / ``doc.py`` / ``base.py``），
这里只提供登记用的形状与共用的转换。两个后端都不逐一写方法：动作名即方法名。

一个动作登记五件事：

    command      固定命令段，如 ``("mail", "+triage")``；带值的写法原样写在这里
    params       参数名 → flag；值需要改写的参数给一个函数（值 → argv 片段）
    needs_any    必填参数（写一个就够的那些，如 chat_id / user_id）
    landed       落盘目录名：``raw/<资源>/<这个名字>/<页序>.json``；留空则用动作名
    kind         ``page``＝一页负载；``files``＝一批原件（只有取附件是这一类）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# 值 → argv 片段：给函数的参数自己写清楚这条命令要什么形状。
Rewrite = Callable[[object], list[str]]


@dataclass
class Page:
    """一页响应：原样负载 + 翻页信息 + 未解信封的完整响应（落盘的就是它）。"""

    resource: str
    action: str
    payload: dict
    has_more: bool = False
    page_token: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class Attachment:
    """落盘的附件原件：飞书给的 id + 原文件名 + 本机路径。"""

    attachment_id: str
    filename: str
    path: str


@dataclass(frozen=True)
class Action:
    """一个飞书动作的登记。字段含义见本文件开头。"""

    command: tuple[str, ...]
    resource: str = ""                                    # 所属飞书资源（落盘目录的第一段）
    params: dict[str, str | Rewrite] = field(default_factory=dict)
    needs_any: tuple[str, ...] = ()
    landed: str = ""
    kind: str = "page"
    defaults: dict = field(default_factory=dict)          # 调用方没给时的契约默认值
    variants: dict[str, tuple[tuple[str, ...], str]] = field(default_factory=dict)
    variant_param: str = ""                               # 挑变体的那个参数（不变成 flag）

    def argv(self, values: dict) -> tuple[list[str], str]:
        """参数 → （argv, 落盘目录名）。参数名与必填由后端先校验。"""
        values = dict(values)
        command, landed = self.command, self.landed
        if self.variants:
            key = values.pop(self.variant_param, "") or next(iter(self.variants))
            command, landed = self.variants[key]
        args = list(command)
        for name, spec in self.params.items():
            value = values.get(name)
            if value is None or value == "" or value == []:
                continue                    # 没给就不带这个 flag——缺省值由平台说了算
            if callable(spec):
                args += spec(value)
            else:
                args += [spec, str(value)]
        return args + ["--format", "json"], landed or ""

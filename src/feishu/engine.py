"""串联器：读定义（配置），把定义展开成一串基础单元的活动，一步步做完。

定义说的是我们的话（读投递邮件 / 看谁进群了 / 发问卷调研），基础单元说的是飞书的话
（``mail +triage`` / ``base +record-list``）。这一层只干两件事：**翻译**与**串联**——
把参数模板换成真值、把上一步的产出喂给下一步、按定义声明把产出起成我们的名字。

    defs = engine.load("examples/qtrecurit/定义.yaml")
    eng = engine.Engine(backend, defs)                 # backend = 基础单元的客户端
    out = eng.call("读投递邮件", 邮箱="hr@…", 文件夹="收件箱", 游标=上次的游标)
    out.rows        # 按「出」表起过名的行：[{"发件人": …, "日期": …, "附件": [...]}]
    out.cursor      # 增量：这批里最新的那个值（下次当游标传回来）
    out.values      # 所有行里所有字段的值（给「包含某邮箱」这类判断用）

一个定义 = 有序的步骤 + 一张「出」表（可选）+ 一条增量声明（可选）：

    步骤   一步 = 一个基础单元的动作 + 参数，参数里可以写 ``{{选择器}}``；
           ``as:`` 给这一步的产出起名，后面的步骤就能取用（``{{摘要.messages[].message_id}}``）
    出     ``行:`` 说哪一段是行，``字段:`` 说每行按什么起名——左边是我们的话，右边是飞书的字段
    增量   ``比: 日期``——只留比游标新的行，新游标取这批里最新的值；游标由调用方保管

上下文里的东西：调用方给的变量（邮箱、文件夹、候选人…）、各步骤的产出（按 ``as`` 起的名），
以及保留名 ``游标``（增量用）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

PLACEHOLDER = re.compile(r"\{\{([^{}]+)\}\}")
CURSOR = "游标"          # 增量的上下文变量名：调用方给、调用方存


def pick(context: Any, path: str) -> Any:
    """从上下文里取一个值：``a.b`` 逐层取；``a[].b`` 把 a 的每个元素都取一遍；
    ``a.英文|a.中文`` 取第一个取得到的（表列名两种写法都认）。"""
    for alternative in path.split("|"):
        value = _walk(context, alternative.strip())
        if value not in (None, "", []):
            return value
    return None


def _walk(value: Any, path: str) -> Any:
    if not path:
        return value
    head, _, rest = path.partition(".")
    pluck = head.endswith("[]")
    key = head[:-2] if pluck else head
    current = value.get(key) if isinstance(value, dict) else getattr(value, key, None)
    if pluck:
        items = current if isinstance(current, (list, tuple)) else []
        return [_walk(item, rest) for item in items]
    return _walk(current, rest)


def resolve(value: Any, context: dict) -> Any:
    """把参数里的 ``{{…}}`` 换成真值。整串就是一个占位符的，保持原类型（列表还是列表）。"""
    if isinstance(value, str):
        whole = PLACEHOLDER.fullmatch(value.strip())
        if whole:
            return pick(context, whole.group(1))
        return PLACEHOLDER.sub(lambda m: str(pick(context, m.group(1))), value)
    if isinstance(value, list):
        return [resolve(v, context) for v in value]
    if isinstance(value, dict):
        return {k: resolve(v, context) for k, v in value.items()}
    return value


@dataclass
class Step:
    """一步：基础单元的一个动作 + 参数；起个名，后面的步骤能取用它的产出。"""

    action: str
    params: dict = field(default_factory=dict)
    as_name: str = ""


@dataclass
class Definition:
    name: str
    steps: list[Step]
    rows_from: str = ""                            # 「出」的行：从哪一段算行
    fields: dict = field(default_factory=dict)     # 每行按什么起名（我们的话 ← 飞书的字段）
    increment_by: str = ""                         # 增量：按哪个字段跟游标比
    note: str = ""


@dataclass
class Outcome:
    """一次定义的产出。"""

    rows: list[dict] = field(default_factory=list)
    single: dict = field(default_factory=dict)
    cursor: str | None = None
    steps: dict = field(default_factory=dict)      # 各步骤的原样产出（调试用）

    @property
    def values(self) -> list[str]:
        """所有行里所有字段的值——「包含某邮箱」「非空」这类判断看它。"""
        return [str(v) for row in self.rows for v in row.values() if v not in (None, "", [])]

    def first(self, key: str, default: Any = "") -> Any:
        return self.rows[0].get(key, default) if self.rows else default


def parse(raw: list[dict]) -> dict[str, Definition]:
    """配置 → 定义表（键是定义名，就是我们的话）。"""
    definitions: dict[str, Definition] = {}
    for item in raw or []:
        out = item.get("出") or {}
        definitions[item["名称"]] = Definition(
            name=item["名称"],
            note=item.get("说明", ""),
            steps=[Step(action=s["动作"], params=dict(s.get("参数") or {}), as_name=s.get("as", ""))
                   for s in item.get("步骤") or []],
            rows_from=out.get("行", ""),
            fields=dict(out.get("字段") or {}),
            increment_by=(item.get("增量") or {}).get("比", ""),
        )
    return definitions


def load(path: str) -> dict[str, Definition]:
    with open(path, encoding="utf-8") as f:
        return parse(yaml.safe_load(f).get("定义"))


class Engine:
    """一个基础单元客户端 + 一批定义。定义里的动作名就是基础单元的动作名。"""

    def __init__(self, backend, definitions: dict[str, Definition]) -> None:
        self.backend = backend
        self.defs = definitions

    def call(self, name: str, **context) -> Outcome:
        """跑一个定义：一步接一步，最后按「出」表起名、按增量声明筛一遍。"""
        definition = self.defs[name]
        ctx = dict(context)
        steps: dict[str, Any] = {}
        for step in definition.steps:
            params = {k: resolve(v, ctx) for k, v in step.params.items()}
            result = getattr(self.backend, step.action)(**params)
            payload = getattr(result, "payload", result)       # 一页响应 → 取负载
            steps[step.as_name or step.action] = payload
            if step.as_name:
                ctx[step.as_name] = payload
        out = Outcome(steps=steps)
        if definition.rows_from:
            rows = pick(ctx, definition.rows_from) or []
            out.rows = [{our: pick(row, sel) for our, sel in definition.fields.items()}
                        for row in rows]
        else:
            last = next(reversed(steps.values()), {}) if steps else {}
            out.single = ({our: pick(last, sel) for our, sel in definition.fields.items()}
                          if definition.fields else dict(last))
        if definition.increment_by:
            key = definition.increment_by
            cursor_in = str(context.get(CURSOR) or "")
            if cursor_in:
                out.rows = [r for r in out.rows if str(r.get(key) or "") > cursor_in]
            out.cursor = max((str(r.get(key) or "") for r in out.rows), default=cursor_in) or None
        return out

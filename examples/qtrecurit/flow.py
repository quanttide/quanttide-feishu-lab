"""招聘流程：把流程读成数据、把人推到下一格、把状态落在本地。

一个示例该有的东西就这三件，所以放在一个文件里——它演示的是怎么用基础单元与定义，
不是要长成第二个项目。设计由来见 `docs/runner.md`。

**流程 = YAML**（`recruitment.yaml`）：状态、迁移、触发、执行者、检查、动作。
流程写的是检查与动作的**名字**（`看谁进群了`、`发群二维码`）——这些名字是
`定义.yaml` 里的定义，定义才认识飞书；流程不认识飞书。

**推格规则**：执行者是「系统」且检查成立才推；动作先做，失败不挪格；人 / 半自动只记待办。
**状态**：落在本地文件，可从飞书侧重建——本地是缓存，事实在飞书那边。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import yaml


# ── 流程模型 ─────────────────────────────────────────────
@dataclass
class Check:
    """一段机器可判的条件，两类互斥：定义检查（跑一条定义后判）与时间检查（纯领域逻辑）。"""

    definition: str | None = None
    holds: str | None = None               # 非空 / 为空 / 包含…
    timing: dict[str, Any] | None = None   # {成立: 超过天数, 天数: N}

    @staticmethod
    def parse(raw: dict[str, Any] | None) -> "Check | None":
        if not raw:
            return None
        return Check(definition=raw.get("定义"), holds=raw.get("成立"), timing=raw.get("计时"))


@dataclass
class Action:
    """推这条迁移之前要跑的定义（一条一串飞书活动）；失败就不挪格。"""

    definition: str

    @staticmethod
    def parse(raw: dict[str, Any] | None) -> "Action | None":
        if not raw:
            return None
        return Action(definition=raw["定义"])


@dataclass
class Migration:
    from_state: str
    to_state: str
    trigger: str
    executor: str                          # 人 / 系统 / 半自动
    check: Check | None = None
    effect: str = ""
    action: Action | None = None

    @property
    def automatic(self) -> bool:
        """只有「系统」执行的迁移，执行器才代劳；人做的是待办。"""
        return self.executor == "系统"


@dataclass
class Flow:
    name: str
    source: str
    version: str
    collect: dict[str, Any]
    states: list[str]
    migrations: list[Migration]

    def from_state(self, state: str) -> list[Migration]:
        return [m for m in self.migrations if m.from_state == state]


def load(path: str) -> Flow:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Flow(
        name=raw["流程"], source=raw.get("来源", ""), version=str(raw.get("版本", "")),
        collect=dict(raw.get("收集") or {}), states=list(raw.get("状态") or []),
        migrations=[Migration(from_state=m["从"], to_state=m["到"], trigger=m.get("触发", ""),
                              executor=m.get("执行者", ""), check=Check.parse(m.get("检查")),
                              effect=m.get("副作用", ""), action=Action.parse(m.get("动作")))
                    for m in raw.get("迁移", [])])


# ── 状态（本地缓存，可从飞书侧重建）──────────────────────
def load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def since_days(entry: dict, today: str) -> int:
    try:
        y, m, d = (int(x) for x in entry.get("since", "").split("-"))
        ty, tm, td = (int(x) for x in today.split("-"))
        return (date(ty, tm, td) - date(y, m, d)).days
    except Exception:
        return 0


def context_of(flow: Flow, engine_context: dict | None = None) -> dict:
    """调用方给的定义上下文 + 流程收集节里的东西（邮箱）。群、表格这类留空由基础单元取环境变量。"""
    ctx = dict(engine_context or {})
    if flow.collect.get("邮箱"):
        ctx.setdefault("邮箱", flow.collect["邮箱"])
    return ctx


def derive(engine, flow: Flow, context: dict, today: str | None = None) -> dict:
    """从飞书侧重建每人现在在哪一格：进人只看收件箱，群成员只用来升级状态。

    「进人」与「群成员」各用哪条定义写在流程的收集节里——定义名是流程的话，
    执行器只照着调，不自己认名字。
    """
    today = today or date.today().isoformat()
    entry, member_def = flow.collect.get("进人"), flow.collect.get("群成员")
    if not entry or not member_def:
        raise RuntimeError("流程的收集节要写「进人」与「群成员」各用哪条定义")
    members = {str(r.get("邮箱") or "").lower() for r in engine.call(member_def, **context).rows}
    applied: dict[str, str] = {}
    for folder in (flow.collect.get("范围") or []):
        if folder != "收件箱":
            continue                    # 漂移 / Spam 是补拉范围，进人仍以收件箱为准
        out = engine.call(entry, 文件夹=folder, **context)
        for row in out.rows:
            who = str(row.get("发件人") or "").lower()
            if who and "@" in who:
                applied.setdefault(who, str(row.get("日期") or ""))
    state: dict = {}
    for who in sorted(applied):
        joined = who in members
        where = "已进群" if joined else flow.states[0]
        state[who] = {"state": where, "since": today if joined else applied[who],
                      "trail": [where]}
    return state


# ── 推格：一轮一跑 ───────────────────────────────────────
@dataclass
class Advance:
    who: str
    from_state: str
    to_state: str
    effect: str


@dataclass
class Todo:
    who: str
    state: str
    migration_to: str
    trigger: str
    executor: str


@dataclass
class Report:
    advanced: list[Advance] = field(default_factory=list)
    todos: list[Todo] = field(default_factory=list)
    waiting: list[tuple[str, str, str]] = field(default_factory=list)   # 谁 / 哪条 / 为什么

    @property
    def empty(self) -> bool:
        return not (self.advanced or self.todos or self.waiting)


def _holds(engine, mig: Migration, who: str, entry: dict, today: str, context: dict) -> bool:
    check = mig.check
    if check is None:
        return True                              # 没写检查 = 无条件
    if check.timing is not None:                 # 纯时间检查：不碰飞书
        return since_days(entry, today) >= (check.timing.get("天数") or 0)
    out = engine.call(check.definition, 候选人={"邮箱": who}, **context)
    values = {v.lower() for v in out.values}
    if check.holds == "非空":
        return bool(out.values or out.rows)
    if check.holds == "为空":
        return not (out.values or out.rows)
    if check.holds and check.holds.startswith("包含"):   # 如「包含该候选人邮箱」
        return who.lower() in values
    return False


def _perform(engine, mig: Migration, who: str, context: dict) -> str:
    out = engine.call(mig.action.definition, 候选人={"邮箱": who}, **context)
    if out.single:
        return "，".join(str(v) for v in out.single.values() if v)
    return "，".join(out.values)


def advance(engine, flow: Flow, state: dict, context: dict, today: str | None = None,
            step_only: bool = False) -> Report:
    """推一轮：系统执行且检查成立的推过去（动作先做，失败不挪格），人/半自动记待办。"""
    today = today or date.today().isoformat()
    report = Report()
    for who in sorted(state):
        entry = state[who]
        for mig in flow.from_state(entry["state"]):
            if not mig.automatic:
                report.todos.append(Todo(who, entry["state"], mig.to_state, mig.trigger,
                                         mig.executor))
                continue
            if not _holds(engine, mig, who, entry, today, context):
                label = (mig.check.definition or ("计时" if mig.check.timing else "无检查")
                         if mig.check else "无检查")
                report.waiting.append((who, f"{mig.from_state}→{mig.to_state}",
                                       f"检查不成立（{label}）"))
                continue
            result = _perform(engine, mig, who, context)
            entry["state"], entry["since"] = mig.to_state, today
            entry.setdefault("trail", []).append(mig.to_state)
            effect = f"{mig.effect}：{result}" if (mig.effect and result) else \
                (mig.effect or str(result or ""))
            report.advanced.append(Advance(who, mig.from_state, mig.to_state, effect))
            if step_only:
                return report
    return report

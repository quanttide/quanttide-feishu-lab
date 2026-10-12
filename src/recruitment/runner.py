"""推进流程：一轮一跑，跑完退出。

对每个人、每条从他当前状态出发的迁移：
  - 执行者是「系统」且检查成立 → 推过去，记一笔
  - 执行者是「系统」但检查不成立 → 这轮跳过，等条件起来
  - 执行者是人或半自动 → 执行器不代劳，记成待办

不做常驻服务、不连数据库：一轮一跑，看清楚了再跑下一轮。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import state as st


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
    waiting: list[tuple[str, str, str]] = field(default_factory=list)   # 谁 / 哪条 / 为什么不成立

    @property
    def empty(self) -> bool:
        return not (self.advanced or self.todos or self.waiting)


def _render(value, email: str):
    """把参数里的 {{候选人.邮箱}} 换成这个人。参数可以是字符串也可以是列表。"""
    if isinstance(value, str):
        return value.replace("{{候选人.邮箱}}", email)
    if isinstance(value, list):
        return [_render(v, email) for v in value]
    if isinstance(value, dict):
        return {k: _render(v, email) for k, v in value.items()}
    return value


def _holds(cap, mig, email: str, entry: dict, today: str) -> bool:
    c = mig.check
    if c is None:
        return True                     # 没写检查 = 无条件：人这一格就该推
    if c.capability == "_since":
        return st.since_days(entry, today) >= (c.days or 0)
    fn = getattr(cap, c.capability, None)
    if fn is None:
        return False
    params = {k: _render(v, email) for k, v in c.params.items()}
    result = fn(**params)
    if c.holds == "非空":
        return bool(result)
    if c.holds == "为空":
        return not result
    if c.holds and c.holds.startswith("包含"):   # 如「包含该候选人邮箱」
        return email.lower() in {str(x).lower() for x in result}
    return False


def _perform(cap, mig, email: str):
    """执行迁移的动作：调能力，返回它的返回值（没有动作返回 None）。"""
    a = mig.action
    if a is None:
        return None
    fn = getattr(cap, a.capability, None)
    if fn is None:
        raise RuntimeError(f"迁移 {mig.from_state}→{mig.to_state} 的动作里没有能力「{a.capability}」")
    params = {k: _render(v, email) for k, v in a.params.items()}
    return fn(**params)


def advance(cap, flow, state: dict, today: str | None = None,
            step_only: bool = False) -> Report:
    today = today or date.today().isoformat()
    report = Report()
    for who in sorted(state):
        entry = state[who]
        for mig in flow.from_state(entry["state"]):
            if not mig.automatic:
                report.todos.append(Todo(who, entry["state"], mig.to_state,
                                         mig.trigger, mig.executor))
                continue
            if not _holds(cap, mig, who, entry, today):
                report.waiting.append((who, f'{mig.from_state}→{mig.to_state}',
                                       f'检查不成立（{mig.check.capability if mig.check else "无检查"}）'))
                continue
            result = _perform(cap, mig, who)    # 动作先做：失败就不挪格
            entry["state"] = mig.to_state
            entry["since"] = today
            entry.setdefault("trail", []).append(mig.to_state)
            effect = mig.effect
            if result:
                effect = f"{effect}：{result}" if effect else str(result)
            report.advanced.append(Advance(who, mig.from_state, mig.to_state, effect))
            if step_only:
                return report
    return report

"""本地状态：一个候选人现在在哪一格。

三条规矩（见 docs/runner.md）：落在本地文件；位置由参数给，不进模型；
可从飞书侧的原始数据重建——本地是缓存，事实在飞书那边。
"""

from __future__ import annotations

import json
import os
from datetime import date

EMPTY = ""


def load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def derive(cap, flow, today: str | None = None) -> dict:
    """从飞书侧的原始数据重建每人当前在哪一格。缺省状态由流程的第二个状态起步。"""
    today = today or date.today().isoformat()
    first, second = flow.states[0], flow.states[1]
    members = cap.read_group_members()

    applied: dict[str, str] = {}      # 邮箱 → 投递日
    invited: dict[str, str] = {}      # 邮箱 → 问卷发出日
    for folder in (flow.collect.get("范围") or []):
        mails, _ = cap.read_mail(folder)
        for m in mails:
            who = (m.sender if folder == "收件箱" else m.recipient).lower()
            if not who or "@" not in who:
                continue
            if folder == "收件箱":
                applied.setdefault(who, m.date)
            elif folder == "已发送问卷":
                invited.setdefault(who, m.date)

    # 群里还有员工，不是候选人：候选人从投递与已发问卷两侧来，群成员只用来升级状态
    people = sorted(set(applied) | set(invited))
    records = cap.read_survey(people)

    state: dict = {}
    for who in people:
        if who in members:
            where, since = flow.states[4], today          # 已进群
        elif who in records:
            where, since = flow.states[2], records[who].submitted_at   # 问卷已交
        elif who in invited:
            where, since = second, invited[who]           # 问卷已发
        else:
            where, since = first, applied.get(who, today)  # 投递
        state[who] = {"state": where, "since": since, "trail": [where]}
    return state


def since_days(entry: dict, today: str) -> int:
    try:
        y, m, d = (int(x) for x in entry.get("since", "").split("-"))
        ty, tm, td = (int(x) for x in today.split("-"))
        return (date(ty, tm, td) - date(y, m, d)).days
    except Exception:
        return 0

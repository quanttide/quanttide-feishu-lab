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
    """从飞书侧的原始数据重建每人当前在哪一格。缺省状态由流程的第一个状态起步。"""
    today = today or date.today().isoformat()
    members = cap.read_group_members()

    applied: dict[str, str] = {}      # 邮箱 → 投递日
    for folder in (flow.collect.get("范围") or []):
        if folder != "收件箱":
            continue              # 漂移 / Spam 是补拉范围：进人仍以收件箱为准（见流程「待定」）
        mails, _ = cap.read_mail(folder)
        for m in mails:
            who = m.sender.lower()
            if who and "@" in who:
                applied.setdefault(who, m.date)

    # 群里还有员工，不是候选人：候选人从投递来，群成员只用来升级状态
    state: dict = {}
    for who in sorted(applied):
        if who in members:
            where, since = "已进群", today          # 扫码进过群的，重建时直接算已进群
        else:
            where, since = flow.states[0], applied[who]
        state[who] = {"state": where, "since": since, "trail": [where]}
    return state


def since_days(entry: dict, today: str) -> int:
    try:
        y, m, d = (int(x) for x in entry.get("since", "").split("-"))
        ty, tm, td = (int(x) for x in today.split("-"))
        return (date(ty, tm, td) - date(y, m, d)).days
    except Exception:
        return 0

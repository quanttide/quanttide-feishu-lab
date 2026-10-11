"""读流程定义：把 flows/*.yaml 读成结构，不给它任何平台与业务概念。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class Check:
    """一段机器可判的条件。能力名对能力层的函数名；成立是判据。"""
    capability: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    holds: str | None = None      # 非空 / 为空 / 超过天数
    days: int | None = None       # 与「超过天数」配套

    @staticmethod
    def parse(raw: dict[str, Any] | None) -> "Check | None":
        if not raw:
            return None
        return Check(
            capability=raw.get("能力"),
            params=dict(raw.get("参数") or {}),
            holds=raw.get("成立"),
            days=raw.get("天数"),
        )


@dataclass
class Migration:
    from_state: str
    to_state: str
    trigger: str
    executor: str                 # 人 / 系统 / 半自动
    check: Check | None = None
    effect: str = ""

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
    migrations = [
        Migration(
            from_state=m["从"],
            to_state=m["到"],
            trigger=m.get("触发", ""),
            executor=m.get("执行者", ""),
            check=Check.parse(m.get("检查")),
            effect=m.get("副作用", ""),
        )
        for m in raw.get("迁移", [])
    ]
    return Flow(
        name=raw["流程"],
        source=raw.get("来源", ""),
        version=str(raw.get("版本", "")),
        collect=dict(raw.get("收集") or {}),
        states=list(raw.get("状态") or []),
        migrations=migrations,
    )


def default_path(lab_root: str) -> str:
    return os.path.join(lab_root, "flows", "recruitment.yaml")

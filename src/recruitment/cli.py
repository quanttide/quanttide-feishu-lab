"""命令行入口：一轮一跑，命令形态对齐 qtcloud-work task 的手感。

    python -m recruitment.cli run     [--mock] [--fixtures DIR] [--state FILE] [--drain]
    python -m recruitment.cli status  ...
"""

from __future__ import annotations

import argparse
import os
import sys

from . import capabilities as cap
from . import flow as flow_mod
from . import runner
from . import state as st

LAB_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recruitment", description="招聘流程调度器")
    p.add_argument("command", choices=["run", "status"])
    p.add_argument("--mock", action="store_true", help="走夹具，不打真飞书")
    p.add_argument("--fixtures", default=os.path.join(LAB_ROOT, "fixtures"))
    p.add_argument("--state", default=os.path.join(LAB_ROOT, "state", "recruitment.json"))
    p.add_argument("--flow", default=flow_mod.default_path(LAB_ROOT))
    p.add_argument("--drain", action="store_true", help="把能推的都推完（缺省只推一步）")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.mock:
        print("真实能力尚未实现：先跑 --mock。", file=sys.stderr)
        return 2

    flow = flow_mod.load(args.flow)
    capabilities = cap.mock(args.fixtures)

    state = st.load(args.state)
    rebuilt = False
    if not state:
        state = st.derive(capabilities, flow)
        rebuilt = True
    if rebuilt:
        print(f"本地无状态：从飞书侧原始数据重建（{len(state)} 人）")

    if args.command == "status":
        for who in sorted(state):
            e = state[who]
            print(f"  {who:26s} {e['state']}（{e['since']} 起）")
        return 0

    report = runner.advance(capabilities, flow, state, step_only=not args.drain)
    st.save(args.state, state)

    print(f"推进 {len(report.advanced)} 条")
    for a in report.advanced:
        print(f"  ✓ {a.who}：{a.from_state} → {a.to_state}（{a.effect}）")
    print(f"待办 {len(report.todos)} 条（执行者是人或半自动，执行器不代劳）")
    for t in report.todos:
        print(f"  · {t.who} 停在「{t.state}」：{t.trigger}（{t.executor}）")
    if report.waiting:
        print(f"等条件 {len(report.waiting)} 条")
        for who, mig, why in report.waiting:
            print(f"  ⋯ {who}：{mig} {why}")
    print(f"状态已落盘：{args.state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

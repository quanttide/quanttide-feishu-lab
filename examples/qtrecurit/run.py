"""跑一轮招聘流程（示例入口）。

    PYTHONPATH=src python3 examples/qtrecurit/run.py status --mock          # 看谁在哪一格
    PYTHONPATH=src python3 examples/qtrecurit/run.py run --mock [--step]    # 推一轮

``--mock`` 走同进程的假 lark-cli（离线）；``--cli`` 走子进程调 lark-cli——
PATH 前面放 ``tests/fake_lark_cli/bin`` 就是离线的假 CLI，放真 lark-cli 就打真飞书
（资源 id 由 ``LARK_CHAT_ID`` 等环境变量给）。两个都不给会明确报错。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
sys.path.insert(0, str(LAB / "src"))
sys.path.insert(0, str(HERE))          # 本示例的 flow 模块

import flow as flow_mod  # noqa: E402
from feishu import mock as feishu_mock, real as feishu_real  # noqa: E402

DEFAULT_STATE = "state/recruitment.json"


def _client(args, flow):
    if args.mock:
        return feishu_mock(str(args.fixtures))
    if not args.cli:
        raise SystemExit("要么 --mock（离线夹具），要么 --cli（子进程调 lark-cli）")
    return feishu_real(mailbox=flow.collect.get("邮箱") or "me",
                       attachments_dir=str(Path(args.fixtures) / "attachments"))


def main() -> int:
    p = argparse.ArgumentParser(prog="qtrecurit", description="招聘流程示例：读流程、推格、看状态")
    p.add_argument("command", choices=["run", "status"])
    p.add_argument("--mock", action="store_true", help="走同进程假 lark-cli（离线）")
    p.add_argument("--cli", action="store_true", help="走子进程调 lark-cli")
    p.add_argument("--fixtures", default=str(LAB / "tests" / "fixtures"), help="夹具目录")
    p.add_argument("--flow", default=str(HERE / "recruitment.yaml"), help="流程定义")
    p.add_argument("--state", default=DEFAULT_STATE, help="状态文件")
    p.add_argument("--step", action="store_true", help="只推一步")
    args = p.parse_args()

    flow = flow_mod.load(args.flow)
    client = _client(args, flow)

    state = flow_mod.load_state(args.state)
    if not state:
        state = flow_mod.derive(client, flow)
        print(f"本地无状态：从飞书侧原始数据重建（{len(state)} 人）")

    if args.command == "status":
        for who in sorted(state):
            print(f"  {who:26s} {state[who]['state']}（{state[who]['since']} 起）")
        return 0

    report = flow_mod.advance(client, flow, state, step_only=args.step)
    for a in report.advanced:
        print(f"  ✓ {a.who:26s} {a.from_state} → {a.to_state}（{a.effect or '已推'}）")
    for who, mig, why in report.waiting:
        print(f"  ⋯ {who:26s} {mig} {why}")
    for t in report.todos:
        print(f"  ☐ {t.who:26s} {t.state} → {t.migration_to}｜{t.trigger}（{t.executor}）")
    if report.empty:
        print("  这一轮没有可推的迁移")
    flow_mod.save_state(args.state, state)
    print(f"状态已落盘：{os.path.abspath(args.state)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# qtrecurit 示例：招聘流程

演示能力层怎么用：**流程写成数据**（`recruitment.yaml`：状态、迁移、触发、执行者、检查、动作），
一个执行器读它推格；换成假 lark-cli 或真 lark-cli，流程与执行器一行不改。

```bash
PYTHONPATH=src python3 examples/qtrecurit/run.py status --mock         # 看谁在哪一格
PYTHONPATH=src python3 examples/qtrecurit/run.py run --mock --step     # 推一步
PATH=$PWD/packages/fake_lark_cli/bin:$PATH PYTHONPATH=src \
  python3 examples/qtrecurit/run.py status --cli                       # 子进程走假 CLI
```

| 文件 | 是什么 |
| :-- | :-- |
| `recruitment.yaml` | 流程定义（改流程 = 改这份文件，代码零改动） |
| `flow.py` | 流程模型 + 状态 + 推格：读 YAML、从飞书侧重建、一轮一跑 |
| `run.py` | 示例入口：`run` / `status`，`--mock` / `--cli` |

设计由来（为什么触发要从「话」变成「条件」、检查与动作各是什么）见 [`docs/runner.md`](../../docs/runner.md)。
状态默认落在 `state/recruitment.json`（不入库），可从飞书侧原始数据重建——本地是缓存，事实在飞书那边。

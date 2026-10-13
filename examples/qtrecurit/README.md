# qtrecurit 示例：招聘流程

演示怎么用基础单元与串联器：**两样东西都写成数据**——

- `定义.yaml`：**定义**（我们的话 → 一串飞书活动）。比如「看谁进群了」就是一步
  `im_chat_members`；「读投递邮件」是 `mail_list` 拿 id、再 `mail_messages` 取正文两步。
- `recruitment.yaml`：**流程**（状态、迁移、触发、执行者、检查、动作）。检查与动作写的是
  定义的名字——流程不认识飞书，只认识定义。

一个执行器（`flow.py`）读这两份配置推格；换成假 lark-cli 或真 lark-cli，定义、流程与执行器一行不改。

```bash
PYTHONPATH=src python3 examples/qtrecurit/run.py status --mock         # 看谁在哪一格
PYTHONPATH=src python3 examples/qtrecurit/run.py run --mock --step     # 推一步
PATH=$PWD/tests/fake_lark_cli/bin:$PATH PYTHONPATH=src \
  python3 examples/qtrecurit/run.py status --cli                       # 子进程走假 CLI
```

| 文件 | 是什么 |
| :-- | :-- |
| `定义.yaml` | 定义：我们的话 → 一串飞书活动（改定义 = 改这份文件，代码零改动） |
| `recruitment.yaml` | 流程：状态、迁移、检查、动作（写的是定义的名字） |
| `flow.py` | 流程模型 + 状态 + 推格：读 YAML、从飞书侧重建、一轮一跑 |
| `run.py` | 入口：`run` / `status`，`--mock` / `--cli`；`--definitions` / `--flow` / `--attachments` |

设计由来（为什么触发要从「话」变成「条件」、检查与动作各是什么）见 [`docs/runner.md`](../../docs/runner.md)。
状态默认落在 `state/recruitment.json`（不入库），可从飞书侧原始数据重建——本地是缓存，事实在飞书那边。

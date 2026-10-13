# 量潮飞书适配实验室

飞书适配的实验原型：验证信息架构与接口假设。

实验室里是**两个项目，一主一副**：

- **主线：飞书能力层（`src/feishu/`）**——按飞书资源读写（六资源十三动作：邮件 / 会话 / 会议 /
  任务 / 文档 / 表），每取一页落一份**原样响应**，路径里只有资源名、动作名与飞书 id。
  抓取与落盘只写一遍，场景各自去读同一份数据。清单与落盘契约见 `docs/capabilities.md`。
- **示例：`examples/qtrecurit/`**——招聘流程。流程写成配置文件（`recruitment.yaml`），
  一个执行器读它推格，代替原来写死在 `qtrecurit-cli` 里的流程；它是能力层的**第一个消费者**，
  也是"换后端不换流程"的现场证明。设计见 `docs/runner.md`。

## 怎么跑

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt

PYTHONPATH=src python3 scripts/smoke.py            # 一份冒烟：能力层 + 流程原型 + 假 CLI 的 CLI 面

PYTHONPATH=src .venv/bin/python examples/qtrecurit/run.py status --mock   # 示例：看谁在哪一格
PYTHONPATH=src .venv/bin/python examples/qtrecurit/run.py run --mock      # 示例：推一轮
```

示例里 `--mock` 走同进程的假 lark-cli（离线）；`--cli` 走子进程调 `lark-cli`——
PATH 前面放 `packages/fake_lark_cli/bin` 就是离线的假 CLI（读同一批 `tests/fixtures/`），
放真 `lark-cli` 就打真飞书（资源 id 用 `LARK_CHAT_ID` 等环境变量给真值）。两个都不给会明确报错，
不会偷偷打出去。冒烟的 `--record` 重新录制能力层的负载快照。

## 目录

| 路径 | 是什么 |
| :-- | :-- |
| `src/feishu/` | **主线**：飞书能力层。`contract.py` 契约（四个动作）、`client.py` 实现（包一个资源层后端） |
| `src/feishu/resources/` | 资源层：`contract.py` 十三个动作的契约、`actions.py` 动作表、`backend_cli.py` / `backend_inprocess.py` 两个后端、`store.py` 落盘 |
| `examples/qtrecurit/` | **示例**：招聘流程——`recruitment.yaml` 流程定义、`flow.py` 模型+状态+推格、`run.py` 入口 |
| `tests/fixtures/` | 测试样例：虚构候选人、邮件文件夹、会话 / 会议 / 任务 / 文档、调研表、群成员、附件、流程定义；`snapshots/` 是能力层的录制负载；`state/` 运行时落盘，不入库 |
| `packages/fake_lark_cli/` | 假 `lark-cli`：读同一批夹具，遮蔽真 CLI（`bin/lark-cli` + `fake_lark_cli/`） |
| `scripts/smoke.py` | 唯一的冒烟入口：能力层 13 动作 × 录制负载 + 落盘契约 + 流程最小闭环 + 假 CLI 的 CLI 面 |
| `docs/capabilities.md` | 主线：能力清单与落盘契约（逐字对应 `resources/actions.py`） |
| `docs/runner.md` | 示例的设计由来：流程为什么要写成数据、检查与动作各是什么 |

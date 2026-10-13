# 量潮飞书适配实验室

飞书适配的实验原型：验证信息架构与接口假设。

实验室里是**两样东西，各说各的话**：

- **`src/feishu/`：基础单元 + 串联器。** 基础单元就是飞书有的东西（邮件 / 会话 / 会议 / 任务 /
  文档 / 表，共十三个动作），按资源读写、每取一页落一份**原样响应**，路径里只有资源名、动作名与
  飞书 id；串联器读**定义**（配置），把定义展开成一串基础单元的活动，一步步做完。
  清单与落盘契约见 `docs/capabilities.md`。
- **`examples/qtrecurit/`：一个场景。** 招聘流程写成两份配置——`recruitment.yaml`（流程：状态、
  迁移、检查、动作）与 `定义.yaml`（定义：我们的话 → 一串飞书活动），一个执行器读它们推格，
  代替原来写死在 `qtrecurit-cli` 里的流程。流程不认识飞书，只认识定义；定义才认识飞书。
  设计见 `docs/runner.md`。

## 怎么跑

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt

PYTHONPATH=src .venv/bin/python tests/smoke.py      # 一份冒烟：基础单元 + 定义 + 示例 + 假 CLI

PYTHONPATH=src .venv/bin/python examples/qtrecurit/run.py status --mock   # 示例：看谁在哪一格
PYTHONPATH=src .venv/bin/python examples/qtrecurit/run.py run --mock      # 示例：推一轮
```

示例里 `--mock` 走同进程的假 lark-cli（离线）；`--cli` 走子进程调 `lark-cli`——
PATH 前面放 `tests/fake_lark_cli/bin` 就是离线的假 CLI（读同一批 `tests/fixtures/`），
放真 `lark-cli` 就打真飞书（资源 id 用 `LARK_CHAT_ID` 等环境变量给真值）。两个都不给会明确报错，
不会偷偷打出去。冒烟的 `--record` 重新录制基础单元的负载快照。

## 目录

| 路径 | 是什么 |
| :-- | :-- |
| `src/feishu/` | 基础单元 + 串联器：`engine.py`（读定义、串活动）、`__init__.py` 门面（`mock_backend()` / `real_backend()`） |
| `src/feishu/resources/` | 基础单元：按飞书资源分文件的动作登记（`mail.py` / `im.py` / `vc.py` / `task.py` / `doc.py` / `base.py`）、`action.py` 登记的形状、`backend_cli.py` / `backend_inprocess.py` 两个后端、`store.py` 落盘 |
| `examples/qtrecurit/` | **场景**：招聘——`recruitment.yaml` 流程、`定义.yaml` 定义（我们的话 → 飞书活动）、`flow.py` 模型+状态+推格、`run.py` 入口 |
| `tests/` | **测试设施**：`fixtures/` 夹具与录制负载、`fake_lark_cli/` 假 `lark-cli`（遮蔽真 CLI）、`smoke.py` 唯一冒烟入口（89 项） |
| `docs/capabilities.md` | 基础单元：能力清单与落盘契约（逐字对应 `resources/` 里六个资源文件的登记） |
| `docs/runner.md` | 场景的设计由来：定义与流程为什么要写成数据、检查与动作各是什么 |

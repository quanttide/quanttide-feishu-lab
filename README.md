# 量潮飞书适配实验室

飞书适配的实验原型：验证信息架构与接口假设。

第一个项目：**招聘流程调度器**——流程写成配置文件（`tests/fixtures/flows/recruitment.yaml`），
一个执行器读它跑，代替原来写死在 `qtrecurit-cli` 里的流程。设计见 `docs/runner.md`。

第二个项目：**资源层**——按飞书资源读写（六资源十三动作：邮件 / 会话 / 会议 / 任务 / 文档 / 表），
每取一页落一份**原样响应**，路径里只有资源名、动作名与飞书 id。抓取与落盘只写一遍，
场景各自去读同一份数据，不再每个场景一套抓取脚本。清单与落盘契约见 `docs/capabilities.md`。

## 怎么跑

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt

PYTHONPATH=src .venv/bin/python -m recruitment.cli run --mock     # 走夹具推一步
PYTHONPATH=src .venv/bin/python -m recruitment.cli status --mock  # 看谁在哪一格
PYTHONPATH=src scripts/smoke.py                                   # 飞书适配层冒烟：夹具 + CLI 两层
PYTHONPATH=src python3 scripts/smoke_resources.py                 # 资源层冒烟：十三动作 × 两层 + 落盘契约
PATH=$PWD/packages/mock/bin:$PATH PYTHONPATH=src \
  .venv/bin/python -m recruitment.cli status --cli                # 子进程走假 lark-cli
```

`--mock` 走 Python 层夹具；`--cli` 走子进程调 `lark-cli`——PATH 前面放 `packages/mock/bin` 就是离线的
假 CLI（读同一批 `tests/fixtures/`，六个虚构候选人），放真 `lark-cli` 就打真飞书（资源 id 用
`LARK_CHAT_ID` 等环境变量给真值）。两个都不给会明确报错，不会偷偷打出去。

## 目录

| 路径 | 是什么 |
| :-- | :-- |
| `tests/fixtures/flows/recruitment.yaml` | 流程定义：状态、迁移、触发、执行者、检查、副作用 |
| `src/recruitment/feishu/` | 流程能力层：契约（`__init__.py`）+ 实现（`client.py` 包一个资源层客户端） |
| `src/recruitment/feishu/resources/` | 资源层：六资源十三动作 + 原样落盘（`store.py`），两种实现同上；清单见 `docs/capabilities.md` |
| `src/recruitment/{flow,state,runner,cli}.py` | 执行器：读流程、落状态、推一步、命令行 |
| `tests/fixtures/` | 测试样例：虚构候选人、邮件文件夹、会话 / 会议 / 任务 / 文档、调研表、群成员、附件、流程定义；`state/` 运行时落盘，不入库 |
| `packages/mock/` | 假 lark-cli：读同一批夹具，遮蔽真 CLI，供真实能力（子进程路径）离线自测 |
| `scripts/smoke.py` | 飞书适配层冒烟：不推流程，只验夹具撑不撑得起 |
| `scripts/smoke_resources.py` | 资源层冒烟：十三动作 × 两层一致 + 落盘契约 + 值不在代码里 |

# 量潮飞书适配实验室

飞书适配的实验原型：验证信息架构与接口假设。

第一个项目：**招聘流程调度器**——流程写成配置文件（`tests/fixtures/flows/recruitment.yaml`），
一个执行器读它跑，代替原来写死在 `qtrecurit-cli` 里的流程。设计见 `docs/runner.md`。

## 怎么跑

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt

PYTHONPATH=src .venv/bin/python -m recruitment.cli run --mock     # 走夹具推一步
PYTHONPATH=src .venv/bin/python -m recruitment.cli status --mock  # 看谁在哪一格
PYTHONPATH=src scripts/smoke.py                                   # 只跑能力层，不推流程
```

`--mock` 走 `tests/fixtures/`（六个虚构候选人），不打真飞书；真实能力接本地 `lark-cli`，尚未实现。
去掉 `--mock` 会明确报「先跑 --mock」，不会偷偷打出去。

## 目录

| 路径 | 是什么 |
| :-- | :-- |
| `tests/fixtures/flows/recruitment.yaml` | 流程定义：状态、迁移、触发、执行者、检查、副作用 |
| `src/recruitment/capabilities/` | 能力层：流程要用到的四种能力，两种实现（夹具 / 真实） |
| `src/recruitment/{flow,state,runner,cli}.py` | 执行器：读流程、落状态、推一步、命令行 |
| `tests/fixtures/` | 测试样例：虚构候选人、邮件文件夹、调研表、群成员、附件、流程定义、状态 |
| `packages/mock/` | 假 lark-cli：读同一批夹具，遮蔽真 CLI，供真实能力（子进程路径）离线自测 |
| `scripts/smoke.py` | 能力层冒烟：不推流程，只验夹具撑不撑得起 |

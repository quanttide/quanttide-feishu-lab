# CHANGELOG

## [Unreleased]

### Added

- **基础单元**（`src/feishu/resources/`）：六资源十三动作（mail / im / vc / task / doc / base），
  两个后端（同进程假 CLI、lark-cli 子进程），按飞书资源分文件，动作登记就是契约——
  命令、参数、必填、落盘名各写一处
- **落盘契约**（`resources/store.py`）：`raw/<资源>/<动作>/<页序>.json` 原样响应（含 ok/data 信封）、
  `raw/mail/attachments/<附件id>/<原文件名>`、`cursor/<资源>.json` 游标（整段拉完才前进）
- **串联器**（`src/feishu/engine.py`）：读定义（配置），把定义展开成一串基础单元的活动——
  参数模板（含「上一步的输出喂给下一步」）、按定义把产出起成我们的话、增量游标
- 假 `lark-cli`（`tests/fake_lark_cli/`，15 条命令）与夹具；基础单元负载的录制快照
  （`tests/fixtures/snapshots/resources.json`）
- 冒烟一份入口（`tests/smoke.py`，95 项）：基础单元 × 录制负载、落盘契约、定义端到端、
  示例跑通、假 CLI 的 CLI 面；重新录制负载用 `--record`
- 示例 `examples/qtrecurit/`：招聘场景的两份配置（`recruitment.yaml` 流程、`定义.yaml` 定义）
  加执行器（`flow.py` / `run.py`）
- 能力清单与落盘契约文档 —— `docs/capabilities.md`

### Changed

- 流程的收集节多两行：`进人` / `群成员` 各用哪条定义——执行器不再自己认定义名，定义名由流程说
  （一份配置，实验室与正式平台 CLI 都读它）

- 定义（我们的话 → 一串飞书活动）与流程（状态、迁移）都写成配置，放在用它的场景那一侧；
  `src/` 只剩两样：基础单元与串联器
- 三层各说各的话：流程只认定义名，定义才认飞书动作，基础单元只认飞书坐标——换后端
  （夹具 ↔ 真飞书）不动定义与流程，改流程不动代码
- 基础单元按其资源分文件、动作登记就是契约：没有第二处签名，两个后端不逐一写方法（动作名即方法名）；
  命令怪癖（folder 包 JSON、`--no-reactions`、`html=false`）写在需要它的那个资源文件里
- 两个后端按「跑在哪」命名（`backend_cli` 子进程 / `backend_inprocess` 同进程），
  由 `mock_backend()` / `real_backend()` 交给串联器
- 测试设施收进 `tests/`：夹具、假 `lark-cli`、冒烟

## [0.0.1] - 2026-10-11

初始版本。

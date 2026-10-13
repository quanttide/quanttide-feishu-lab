# CHANGELOG

## [Unreleased]

### Added

- 资源层：六资源十三动作（mail / im / vc / task / doc / base），两个后端（同进程假 CLI、lark-cli
  子进程），每取一页落一份原样响应 —— `src/feishu/resources/`
- 落盘契约：`raw/<资源>/<动作>/<页序>.json` 原样响应、`raw/mail/attachments/<附件id>/<原文件名>`、
  `cursor/<资源>.json` 游标（整段拉完才前进）—— `resources/store.py`
- 冒烟：一份入口 `scripts/smoke.py`（能力层 13 动作 × 录制负载、落盘契约、示例端到端、假 CLI 的
  CLI 面），89 项；重新录制负载用 `--record`
- 假 lark-cli 扩到 15 条命令（im / vc / task / drive / docs / 附件下载），表输出收成一份渲染
  （`envelope.table_of`），并补上 `--format markdown`
- 夹具：`im/`、`vc/`、`task/`、`drive/` 四类资源夹具 + `snapshots/resources.json` 录制负载
- 能力清单与落盘契约文档 —— `docs/capabilities.md`

### Changed

- 主线独立：能力层成 `src/feishu/`（契约 `contract.py` / 实现 `client.py` / 资源层 `resources/`）；
  契约与门面分开；两个后端按边界命名（`backend_cli.py` 子进程 / `backend_inprocess.py` 同进程）；
  假 CLI 包改名 `packages/fake_lark_cli/`（名字自证是假 CLI）
- 招聘流程收成**示例** `examples/qtrecurit/`：流程定义 `recruitment.yaml`、模型+状态+推格 `flow.py`、
  入口 `run.py`——四个模块合成两个，不再与能力层同层；端到端对照（换后端不换流程）挂在冒烟第 7 段
- 精简重复：命令声明表生成 USAGE / HELP / SPECS、夹具形状规则一份（`fake_lark_cli/fixtures.py`）、
  能力层实现收成一个类、资源层动作表驱动两个后端、三处冒烟入口合成一处

## [0.0.1] - 2026-10-11

初始版本。

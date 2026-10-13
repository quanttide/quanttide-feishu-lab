# CHANGELOG

## [Unreleased]

### Added

- 资源层：六资源十三动作（mail / im / vc / task / doc / base），两种实现（进程内夹具替身、
  lark-cli 子进程），每取一页落一份原样响应 —— `src/feishu/resources/`
- 落盘契约：`raw/<资源>/<动作>/<页序>.json` 原样响应、`raw/mail/attachments/<附件id>/<原文件名>`、
  `cursor/<资源>.json` 游标（整段拉完才前进）—— `resources/store.py`
- 冒烟：资源层十三动作 × 录制负载 + 落盘契约 + 流程能力层最小闭环，合并进一份 —— `scripts/smoke.py`
- 假 lark-cli 扩到 15 条命令：补 `im +chat-messages-list` / `im +messages-search` /
  `mail user_mailbox.message.attachments download_url` / `vc +search` / `vc meeting get` /
  `task +get-my-tasks` / `task +get-related-tasks` / `task tasklists list` / `drive +search` / `docs +fetch`
- 夹具：`im/`、`vc/`、`task/`、`drive/` 四类资源夹具
- 能力清单与落盘契约文档 —— `docs/capabilities.md`

### Changed

- 整理结构（不是精简）：能力层独立成 `src/feishu/`（主线），招聘流程原型留在 `src/recruitment/`
  （副线，能力层的第一个消费者）；契约与门面分开（`contract.py` / `__init__.py`）；两个后端按边界
  命名（`backend_cli.py` 子进程 / `backend_inprocess.py` 同进程）；假 CLI 包改名
  `packages/fake_lark_cli/`；三处冒烟入口合成 `scripts/smoke.py` 一份（89 项）

- 精简：删掉重复的三张帮助表（`cli.py` 改成一份命令声明表生成 USAGE / HELP / SPECS）、
  夹具形状规则并进 `fake_lark_cli/fixtures.py`、流程能力层由两个实现收成一个类（`feishu/client.py`）、
  资源层夹具实现改为「同进程假 CLI」（负载只有一处来源）、三个冒烟合成一份（`scripts/smoke.py`）、
  资源层 lark-cli 实现改成动作表——`git ls-files '*.py'` 从 3105 行降到 2750 行左右，判据一项未减

## [0.0.1] - 2026-10-11

初始版本。

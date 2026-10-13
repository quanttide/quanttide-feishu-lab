# CHANGELOG

## [Unreleased]

### Added

- 资源层：六资源十二动作（mail / im / vc / task / doc / base），两种实现（进程内夹具替身、
  lark-cli 子进程），每取一页落一份原样响应 —— `src/recruitment/feishu/resources/`
- 落盘契约：`raw/<资源>/<动作>/<页序>.json` 原样响应、`raw/mail/attachments/<附件id>/<原文件名>`、
  `cursor/<资源>.json` 游标（整段拉完才前进）—— `resources/store.py`
- 资源层冒烟：十二动作 × 两层负载一致、落盘契约、源码里无具体值，41 项 —— `scripts/smoke_resources.py`
- 假 lark-cli 扩到 15 条命令：补 `im +chat-messages-list` / `im +messages-search` /
  `mail user_mailbox.message.attachments download_url` / `vc +search` / `vc meeting get` /
  `task +get-my-tasks` / `task +get-related-tasks` / `task tasklists list` / `drive +search` / `docs +fetch`
- 夹具：`im/`、`vc/`、`task/`、`drive/` 四类资源夹具
- 能力清单与落盘契约文档 —— `docs/capabilities.md`

## [0.0.1] - 2026-10-11

初始版本。

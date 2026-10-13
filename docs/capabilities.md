# 基础单元：六资源十三动作（设计与契约）

这一页定两件事：**能力清单**（飞书有哪些东西、按什么拿）与**落盘契约**（拿回来的东西怎么写下来）。
基础单元是这一层的说法——飞书有什么就有什么；至于"一句话怎么变成一串基础单元的动作"，
是上一层**定义**的事（写在用它的场景里，见 `examples/qtrecurit/定义.yaml`）。
判据全部可跑：`PYTHONPATH=src .venv/bin/python tests/smoke.py`（95 项：基础单元 63 + 定义 14 + 示例 5 + 假 CLI 的 CLI 面 13）。

## 一、为什么要单独一层

定义（`定义.yaml`：读投递邮件、看谁进群了、发群二维码…）说的是**我们的话**——一句话里带着
我们的需求；基础单元说的是**飞书有什么**，只有飞书坐标。分开的好处是：抓取与落盘只写一遍，
业务场景（招聘、治理、财务）各自去读同一份数据，不再各写一套抓取脚本。

| 层 | 说什么 | 参数里有什么 | 谁用 |
| :-- | :-- | :-- | :-- |
| 定义 | 我们的话（一句话 → 一串活动） | 我们的概念（候选人邮箱、文件夹、群） | 串联器 |
| **基础单元** | 飞书有什么 | 只有飞书坐标（mailbox、chat_id、meeting_id、since） | 定义 |

## 二、能力清单（十三动作）

| 资源 | 动作 | 参数（全部由调用方给） | lark-cli 命令 |
| :-- | :-- | :-- | :-- |
| mail | `mail_list` | mailbox, folder, query, page_size, page_token | `mail +triage` |
| mail | `mail_messages` | message_ids, mailbox, html | `mail +messages` |
| mail | `mail_attachment_download` | message_id, attachment_ids, mailbox | `mail user_mailbox.message.attachments download_url` |
| mail | `mail_send` | to, subject, body, attachments, mailbox | `mail +send --confirm-send`（写） |
| im | `im_chat_messages` | chat_id 或 user_id, order, with_reactions, page_size | `im +chat-messages-list` |
| im | `im_chat_members` | chat_id | `im +chat-members-list` |
| im | `im_messages_search` | sender 或 at_chatter, chat_id, with_reactions | `im +messages-search` |
| vc | `vc_meeting_search` | participant_id, start, end, page_size | `vc +search` |
| vc | `vc_meeting_get` | meeting_id | `vc meeting get --with-participants true` |
| task | `task_list` | scope（mine / related / tasklists）, complete | `task +get-my-tasks` / `+get-related-tasks` / `tasklists list` |
| doc | `drive_search` | edited_since 或 created_since, page_size | `drive +search` |
| doc | `docs_fetch` | doc, detail, doc_format | `docs +fetch` |
| base | `base_records` | base_token, table_id, filter_json, offset, limit | `base +record-list` |

这张表与 `src/feishu/resources/` 里的登记逐字对应（表里一行 = 一个资源文件里的一条 `Action`）；
每一行的命令、参数、必填、落盘名都写在**它所属的那个资源文件**里（`mail.py` / `im.py` / `vc.py` /
`task.py` / `doc.py` / `base.py`）——登记就是契约，没有第二处签名，两个后端也不逐一写方法；
要加一个动作只改它所属的资源文件。
十三个动作覆盖现有私有脚本对 lark-cli 的全部调用面（只有 `mail_send` 是写）；**不在这张表里的能力，需要时再补**——
补的姿势是加一个动作，不是在场景脚本里自己拼命令。

## 三、落盘契约

```
<store>/                                    启动参数给（缺省在当前目录下）
  raw/<资源>/<动作>/<页序>.json              飞书原样响应（含 ok / data 信封），一页一份
  raw/mail/attachments/<附件id>/<原文件名>    附件原件
  cursor/<资源>.json                        {"cursor": …, "updated_at": …}
```

三条规矩：

1. **原样**：写进 `raw/` 的是平台回的那份负载，不解信封、不拆数组、不聚合、不按月切。
   要什么形状在读取时算——写的时候加工，就分不出哪份是事实。
2. **无业务名**：路径里只有资源名、动作名、飞书 id 与页序。没有邮箱、人名、来源仓库名。
3. **游标只在整段拉完后前进**：`pull()` 在 `has_more=false` 时才写 `cursor/`；中途失败不推游标，
   下次从断点续。

分页只有一份实现（`resources/__init__.py: pull`）：各实现只管把一页取回来，翻页、落盘、
游标推进都在这里。

## 四、值从哪来

资源层的代码里不出现任何具体值，全部走参数与环境变量：

| 环境变量 | 是什么 | 缺省（够 mock 用，打真飞书会明确报错） |
| :-- | :-- | :-- |
| `LARK_CLI` | 命令名 | `lark-cli` |
| `LARK_MAILBOX` | 邮箱 | `me` |
| `LARK_BASE_TOKEN` | 多维表格 base | `mock-base-token` |
| `LARK_TABLE_ID` | 表 | `mock-table-id` |
| `LARK_CHAT_ID` | 群 | `oc_mock_chat` |

判据：`tests/smoke.py` 的资源层第 4 段直接 grep 源码——没有 `oc_/ou_/om_` 开头的具体 id、
没有邮箱字面量，才通过。

## 五、两个后端

| 实现 | 形态 | 怎么用 |
| :-- | :-- | :-- |
| `resources/backend_inprocess.py` | 同进程跑假 `lark-cli`（不 fork、不依赖 PATH） | 定义与示例的 `--mock`：确定性自测与断言 |
| `resources/backend_cli.py` | 子进程调 `lark-cli` | `PATH` 前面放 `tests/fake_lark_cli/bin` 即离线；放真 CLI 即打真飞书 |
| `__init__.py` 的 `mock_backend()` / `real_backend()` | 造上面两个后端 | 场景把后端交给串联器：`Engine(backend, 定义)` |

负载对着**录制快照**（`tests/fixtures/snapshots/resources.json`）比，两条路都要对上；改坏形状就红。
重新录制：`PYTHONPATH=src .venv/bin/python tests/smoke.py --record`。

## 六、不做什么

- 不聚合、不分类、不按月切、不删字段（`--no-reactions` 这类取舍由调用方显式要求）。
- 不在资源层写业务判断：谁是候选人、哪封信是投递，是场景的事。
- 不为每个场景写一套抓取脚本：场景读 `raw/`，或把这几条动作用定义串起来。

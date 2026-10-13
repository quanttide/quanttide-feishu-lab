# packages/mock — lark-cli 的 mock

假 `lark-cli`：读同一批 `tests/fixtures/`，按真 CLI 的信封回话，不打真飞书。

## 为什么要有它

飞书适配层有两种实现（`src/recruitment/feishu/`）：

| 实现 | 形态 | 给谁用 | 现状 |
| :-- | :-- | :-- | :-- |
| Python 层 mock（`feishu/mock.py`） | 飞书能力接口直读夹具 | runner | 已跑通 |
| 真实能力 | **子进程调 `lark-cli`**（`feishu/real.py`） | runner（`--cli`） | 已实现；真飞书侧 scope 未开通、要授权，仍打不通 |

真实能力已经就是子进程调 `lark-cli`：把本包的 `bin/lark-cli` 顶到 PATH 最前面遮蔽真 CLI，
它**一行不改**就能离线跑通——`scripts/smoke.py` 的 CLI 段逐项核对两层结果一致。
这也是 runner.md 判据「换实现不换流程」在本地兑现的地方。

两层 mock 并存，读同一批 `tests/fixtures/`，不互相取代。

## 命令面

流程要用的五条 + 资源层要用的十条（`docs/capabilities.md` 的六资源十二动作）：

| 命令 | 读 / 写 | 关键 flags | `data` 负载 |
| :-- | :-- | :-- | :-- |
| `mail +triage` | `tests/fixtures/mail/<文件夹>.json` | `--filter`（folder/from/subject）、`--query`、`--max`、`--page-token`、`--format` | `messages[]` / `count` / `has_more` / `page_token` |
| `mail +messages` | `mail/` + `outbox/` 按 message_id 找 | `--message-ids`、`--html` | `messages[]` / `total` / `unavailable_message_ids` |
| `mail +send` | 写 `tests/fixtures/outbox/` | `--to`、`--subject`、`--body`、`--attach`、`--confirm-send` | 草稿模式 `draft_id`；发送 `message_id` / `thread_id` |
| `mail user_mailbox.message.attachments download_url` | `tests/fixtures/attachments/` | `--user-mailbox-id`、`--message-id`、`--attachment-ids` | `attachments[]`（含 `download_url`，指向夹具文件的 `file://` 地址）/ `total` |
| `base +record-list` | `tests/fixtures/survey.json` | `--base-token`、`--table-id`、`--filter-json`、`--field-id`、`--offset`、`--limit` | `items[]` / `total` / `has_more` |
| `im +chat-members-list` | `tests/fixtures/group_members.json` | `--chat-id`、`--member-types` | `users[]` / `bots[]` / `truncations[]` |
| `im +chat-messages-list` | `tests/fixtures/im/chat-<chat_id>.json`、`p2p-<user_id>.json` | `--chat-id` / `--user-id`、`--order`、`--page-size`、`--page-token`、`--no-reactions` | `messages[]` / `has_more` / `page_token` |
| `im +messages-search` | `tests/fixtures/im/search-sender-<id>.json`、`search-at-<id>.json` | `--sender` / `--at-chatter-ids`、`--page-all`、`--no-reactions` | `items[]` / `has_more` / `page_token` |
| `vc +search` | `tests/fixtures/vc/search-<participant>.json` | `--participant-ids`、`--start`、`--end`、`--page-size` | `items[]` / `has_more` / `page_token` |
| `vc meeting get` | `tests/fixtures/vc/meeting-<id>.json` | `--meeting-id`、`--with-participants` | `meeting` |
| `task +get-my-tasks` | `tests/fixtures/task/my-tasks.json` | `--page-all`、`--complete[=false]` | `items[]` / `has_more` / `page_token` |
| `task +get-related-tasks` | `tests/fixtures/task/related-tasks.json` | `--page-all` | 同上 |
| `task tasklists list` | `tests/fixtures/task/tasklists.json` | `--as user`、`--page-all` | 同上 |
| `drive +search` | `tests/fixtures/drive/search.json` | `--edited-since` / `--created-since`、`--page-size` | `items[]` / `has_more` / `page_token` |
| `docs +fetch` | `tests/fixtures/drive/doc-<token>.json` | `--doc`、`--detail`、`--doc-format` | `token` / `doc_type` / `content` / `detail` / `doc_format` |

多段命令（`vc meeting get`、`task tasklists list`、`mail user_mailbox.message.attachments download_url`）
按真 CLI 的形状分段拼命令名，见 `cli.py` 的 `MULTI_PART`。

## 输出契约（照真 CLI）

- 成功：`{"ok": true, "data": {...}}` → stdout，exit 0
- 失败：`{"ok": false, "error": {type, subtype, message, hint?, param?}}` → **stderr，exit 2**
- `--format`：`json` / `data` / `pretty` / `ndjson` / `table`（按命令的真 CLI 默认值，如 triage 默认 table、record-list 默认 markdown）；`--json` 是简写
- `--jq <expr>`：走本机 `jq` 过滤输出；给了 `--jq` 一律按 json 走
- `--dry-run`：回 argv 与夹具根，**不编 API 路径**
- 未实现的域 / 命令 / flag：回同款 validation 错误——缺什么就是接真 CLI 时要补什么，不假装有

依据：本机 `lark-cli` 实测（错误信封、exit 2、`--dry-run` 形状）＋
`lark-cli skills read lark-mail` 的字段文档（triage / messages / send 的负载与字段名）。

## 夹具映射

| 命令 | 夹具 |
| :-- | :-- |
| `mail +triage --filter '{"folder":"收件箱"}'` | `tests/fixtures/mail/收件箱.json`（`inbox`→收件箱、`spam`→Spam 两个别名） |
| `mail +messages` | 遍历 `mail/*.json` + `outbox/*.json` 按 `message_id` 找 |
| `mail +send --confirm-send` | 写 `tests/fixtures/outbox/<message_id>.json`（message_id 与 Python 层 mock 同算法） |
| `base +record-list` | `tests/fixtures/survey.json`，`--filter-json` 认 `email`/`submitted_at` 与中文别名 `邮箱`/`提交时间`，`answers` 里的键按列名查 |
| `im +chat-members-list` | `tests/fixtures/group_members.json` |
| `im +chat-messages-list --chat-id` / `--user-id` | `tests/fixtures/im/chat-<id>.json` / `p2p-<user_id>.json` |
| `im +messages-search --sender` / `--at-chatter-ids` | `tests/fixtures/im/search-sender-<id>.json` / `search-at-<id>.json` |
| `vc +search --participant-ids <id>` | `tests/fixtures/vc/search-<id>.json` |
| `vc meeting get --meeting-id <id>` | `tests/fixtures/vc/meeting-<id>.json` |
| `task +get-my-tasks` / `+get-related-tasks` / `tasklists list` | `tests/fixtures/task/my-tasks.json` / `related-tasks.json` / `tasklists.json` |
| `drive +search` | `tests/fixtures/drive/search.json`（按 `edited_time` / `created_time` 与 since 字符串比） |
| `docs +fetch --doc <token>` | `tests/fixtures/drive/doc-<token>.json` |
| `mail user_mailbox.message.attachments download_url` | `tests/fixtures/attachments/<文件名>`（`download_url` 是它的 `file://` 地址） |

夹具目录默认取实验室根的 `tests/fixtures/`，环境变量 `LARK_MOCK_FIXTURES` 可换。

## 怎么用

```bash
# 遮蔽真 CLI（哪个先在 PATH 里，哪个说了算）
PATH=$PWD/packages/mock/bin:$PATH lark-cli mail +triage --format json

# 自检：五条命令 + 错误面 + 信封，夹具拷到临时目录跑，不碰仓库
python3 packages/mock/smoke.py
```

## 已知差距（接真 CLI 时要处理）

| 差距 | 说明 |
| :-- | :-- |
| base / im 的 `data` 形状 | mail 三条对照过 skill 文档；base / im 是按飞书 API 通用形状近似——本机 lark-cli 缺 scope 打不出成功输出，接真时逐字段核 |
| 群成员邮箱 | 真 CLI 回 `open_id`，mock 直接回邮箱（`member_id_type=email`）——真实能力要补一步 open_id → 邮箱解析 |
| 草稿 | 真 CLI 存草稿可取回，mock 只回 `draft_id` 不落盘 |
| 翻页游标 | mock 是**按位置**的 `list:<n>`，真 CLI 是服务端不透明游标——形状对齐、语义近似；`task` 三条用 `--page-all`，一次给全量、不再翻页 |
| 文档 / 会议 / 任务字段 | `drive` / `vc` / `task` 的 `data` 形状是按飞书 API 通用形状近似（本机 lark-cli 缺 scope 打不出成功输出）——接真时逐字段核 |
| `docs +fetch` 的回显 | 真 CLI 只回正文；mock 多回 `detail` / `doc_format` 两个字段，方便断言调用参数传对了 |
| `mail … attachments download_url` | mock 回 `file://` 地址（能力层按同一协议取文件）；真 CLI 回 https 地址，取法只差 URL 解析 |
| 文件夹 | mock 按文件夹名找夹具文件；真 CLI 是 `folder` / `folder_id` 体系 |
| 错误面 | 只有 validation 一类，不模拟授权失败、限流 |

## 不做什么

- 不模拟网络延迟、分页上限、`truncations[]`
- 不真发邮件、不写真表——写只落到 `tests/fixtures/outbox/`
- 不被 import：runner 默认走 Python 层 mock；`--cli` 才经子进程走到本包，自检在 `scripts/smoke.py` 的 CLI 段

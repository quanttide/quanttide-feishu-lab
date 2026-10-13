"""资源层契约：按飞书资源读写，动作只有三种——列、读、取附件。

与 ``feishu/__init__.py`` 的「流程能力」分工：

| 层 | 说什么 | 参数里有什么 | 谁用 |
| :-- | :-- | :-- | :-- |
| 流程能力（`read_mail` / `send_mail` …） | 流程要用到什么 | 业务概念（候选人邮箱、群） | 执行器（runner） |
| 资源层（`mail_list` / `im_chat_messages` …） | 飞书有什么 | 只有飞书坐标（mailbox、chat_id、meeting_id、since） | 收集与场景脚本 |

资源层不认候选人、不认阶段、不认「招聘」——它只把飞书的东西按原样取回来。每个动作
取到的每一页都落一份原样响应（见 ``store.py``），所以「数据」与「加工」天然分开：
``raw/`` 里只有飞书的事实，要聚合要分类另行去建目录。

资源与动作（六资源十三动作，覆盖现有脚本对 lark-cli 的全部调用面；只有 mail_send 是写，
其余都是读）：

| 资源 | 动作 | 对应的 lark-cli 命令 |
| :-- | :-- | :-- |
| mail | `mail_list` | `mail +triage` |
| mail | `mail_messages` | `mail +messages` |
| mail | `mail_attachment_download` | `mail user_mailbox.message.attachments download_url` |
| mail | `mail_send` | `mail +send --confirm-send` |
| im | `im_chat_messages` | `im +chat-messages-list`（群按 chat-id，单聊按 user-id） |
| im | `im_chat_members` | `im +chat-members-list` |
| im | `im_messages_search` | `im +messages-search`（按发言人 / 被 @ 人） |
| vc | `vc_meeting_search` | `vc +search` |
| vc | `vc_meeting_get` | `vc meeting get` |
| task | `task_list` | `task +get-my-tasks` / `+get-related-tasks` / `tasklists list` |
| doc | `drive_search` | `drive +search`（按编辑时间 / 创建时间） |
| doc | `docs_fetch` | `docs +fetch`（导出正文） |
| base | `base_records` | `base +record-list` |

分页只有一份实现（``pull``）：各实现只管把一页取回来，翻页、落盘、游标推进都在这里。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .store import RawStore


@dataclass
class Page:
    """一页响应：原样负载 + 翻页信息 + 未解信封的完整响应（落盘的就是它）。"""

    resource: str
    action: str
    payload: dict
    has_more: bool = False
    page_token: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class Attachment:
    """落盘的附件原件：飞书给的 id + 原文件名 + 本机路径。"""

    attachment_id: str
    filename: str
    path: str


class Resources(Protocol):
    """资源层契约。所有参数都是飞书坐标，返回值都是原样负载。"""

    store: RawStore | None      # 给了才落盘：流程能力层只读，不需要留档

    # mail
    def mail_list(self, *, mailbox: str | None = None, folder: str | None = None,
                  query: str | None = None, page_size: int = 400,
                  page_token: str | None = None) -> Page: ...

    def mail_messages(self, *, message_ids: list[str], mailbox: str | None = None,
                      html: bool = True) -> Page: ...

    def mail_attachment_download(self, *, message_id: str, attachment_ids: list[str],
                                 mailbox: str | None = None) -> list[Attachment]: ...

    def mail_send(self, *, to: str, subject: str, body: str,
                  attachments: list[str] | None = None, mailbox: str | None = None) -> Page: ...

    # im
    def im_chat_messages(self, *, chat_id: str | None = None, user_id: str | None = None,
                         order: str = "asc", with_reactions: bool = True,
                         page_size: int = 50, page_token: str | None = None) -> Page: ...

    def im_chat_members(self, *, chat_id: str | None = None,
                        page_token: str | None = None) -> Page: ...

    def im_messages_search(self, *, sender: str | None = None, at_chatter: str | None = None,
                           chat_id: str | None = None, with_reactions: bool = False,
                           page_size: int = 50, page_token: str | None = None) -> Page: ...

    # vc
    def vc_meeting_search(self, *, participant_id: str | None = None, start: str | None = None,
                          end: str | None = None, page_size: int = 30,
                          page_token: str | None = None) -> Page: ...

    def vc_meeting_get(self, *, meeting_id: str) -> Page: ...

    # task
    def task_list(self, *, scope: str = "mine", complete: bool | None = None,
                  page_size: int = 50, page_token: str | None = None) -> Page: ...

    # doc
    def drive_search(self, *, edited_since: str | None = None, created_since: str | None = None,
                     page_size: int = 20, page_token: str | None = None) -> Page: ...

    def docs_fetch(self, *, doc: str, detail: str = "simple",
                   doc_format: str = "markdown") -> Page: ...

    # base
    def base_records(self, *, base_token: str | None = None, table_id: str | None = None,
                     filter_json: str | None = None, offset: int = 0,
                     limit: int = 100) -> Page: ...

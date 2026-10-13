"""流程能力层的实现：包一个资源层客户端，只做两种映射。

取数、命令、信封、字段归一化都在资源层（``resources/``）；这一层只做：

1. **坐标映射**：流程的词汇（文件夹、候选人邮箱、群）→ 资源层的坐标（mailbox、chat_id…）
2. **数据类映射**：资源层的负载 → 流程用的 ``Mail`` / ``SurveyRecord``（``to_mail`` / ``to_survey``）

所以「夹具实现」与「lark-cli 实现」共用一个类，换实现 = 换它包的那个资源层客户端，
不换这层代码（见 ``__init__.py`` 的 ``mock()`` / ``real()``）。
"""

from __future__ import annotations

import json
import os

from .contract import Mail, SurveyRecord, since, to_mail, to_survey

PAGE_SIZE = 400


class Feishu:
    """流程能力层：把一个资源层客户端包成流程要用的四个动作。"""

    def __init__(self, resources, *, mailbox: str = "me", attachments_dir: str = "") -> None:
        self.res = resources
        self.mailbox = mailbox
        self.attachments_dir = attachments_dir

    def _resolve(self, name: str) -> str:
        """附件名 → 路径：本来就是路径就用它，否则到附件目录里找。"""
        if os.path.isabs(name) or os.path.sep in name or os.path.exists(name):
            return name
        return os.path.join(self.attachments_dir, name)

    # ── 流程要用的四个动作 ────────────────────────────────
    def read_mail(self, folder: str, cursor: str | None = None) -> tuple[list[Mail], str]:
        """读某个文件夹：+triage 列摘要、+messages 取正文（资源层两步），再映射成 Mail。"""
        summaries = self.res.mail_list(folder=folder, mailbox=self.mailbox,
                                       page_size=PAGE_SIZE).payload.get("messages") or []
        ids = [s["message_id"] for s in summaries]
        full: dict[str, dict] = {}
        if ids:
            full = {m["message_id"]: m for m in self.res.mail_messages(
                message_ids=ids, mailbox=self.mailbox).payload.get("messages") or []}
        mails = [to_mail(full[s["message_id"]], folder)
                 for s in summaries if s["message_id"] in full]
        return since(mails, cursor)

    def read_survey(self, emails: list[str]) -> dict[str, SurveyRecord]:
        """按邮箱查调研表（资源层的 base_records），只返回查到的那些。"""
        if not emails:
            return {}
        spec = {"logic": "and", "conditions": [["邮箱", "intersects", list(emails)]]}
        items = self.res.base_records(
            filter_json=json.dumps(spec, ensure_ascii=False)).payload.get("items") or []
        wanted = {e.lower() for e in emails}
        return {k: v for k, v in to_survey(items).items() if k.lower() in wanted}

    def read_group_members(self) -> set[str]:
        """读群成员（资源层的 im_chat_members），返回邮箱集合。"""
        users = self.res.im_chat_members().payload.get("users") or []
        return {u["member_id"].lower() for u in users if u.get("member_id")}

    def send_mail(self, to: str, subject: str, body: str,
                  attachments: list[str] | None = None) -> str:
        """发一封邮件，返回 message_id。

        注意：PATH 里是真 lark-cli 时这封信会真发出去（能力层要 message_id，只能走发送模式）；
        实验室里靠 ``--cli`` 显式开启来把住这道门。
        """
        page = self.res.mail_send(to=to, subject=subject, body=body, mailbox=self.mailbox,
                                  attachments=[self._resolve(a) for a in attachments or []])
        return page.payload.get("message_id") or ""

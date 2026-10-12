"""夹具根与读写。

默认取实验室的 ``fixtures/``（与 Python 层 mock 共用同一批数据）；
环境变量 ``LARK_MOCK_FIXTURES`` 可换目录——smoke 用它把输出引到临时目录，
不污染仓库里的 ``fixtures/outbox/``。

夹具形状见 ``src/recruitment/capabilities/mock.py`` 的模块说明：
    fixtures/mail/<文件夹>.json   每封：message_id / sender / subject / body / date / attachments
    fixtures/survey.json          调研表记录
    fixtures/group_members.json   群成员邮箱
    fixtures/outbox/              发出去的邮件（mail +send 写这里）
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures"

# 系统文件夹名 → 夹具文件夹名（其余名字原样用，找不到文件当空文件夹）
FOLDER_ALIASES = {"inbox": "收件箱", "INBOX": "收件箱", "spam": "Spam"}


def root() -> Path:
    env = os.environ.get("LARK_MOCK_FIXTURES")
    return Path(env) if env else DEFAULT_ROOT


def folder_file(folder: str) -> str:
    """文件夹名 → 夹具文件名。与 capabilities/mock.py 的规则一致。"""
    return re.sub(r"[^\w一-鿿]+", "-", folder).strip("-") + ".json"


def read_json(*parts: str):
    with open(root().joinpath(*parts), encoding="utf-8") as f:
        return json.load(f)


def mail_folder(folder: str) -> list[dict]:
    """某个文件夹的邮件。夹具里没有这个文件夹就按空文件夹处理。"""
    path = root() / "mail" / folder_file(folder)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_messages(message_ids: list[str]) -> dict[str, dict]:
    """按 message_id 在所有邮件夹具里找（mail/ 各文件夹 + outbox/）。"""
    wanted = set(message_ids)
    found: dict[str, dict] = {}
    mail_dir = root() / "mail"
    for path in sorted(mail_dir.glob("*.json")):
        for rec in json.loads(path.read_text(encoding="utf-8")):
            mid = rec.get("message_id")
            if mid in wanted and mid not in found:
                found[mid] = {**rec, "_folder": path.stem}
    outbox = root() / "outbox"
    if outbox.exists():
        for path in sorted(outbox.glob("*.json")):
            rec = json.loads(path.read_text(encoding="utf-8"))
            mid = rec.get("message_id")
            if mid in wanted and mid not in found:
                found[mid] = {**rec, "_folder": "outbox"}
    return found


def slug(email: str) -> str:
    """邮箱 → 文件名片段。与 capabilities/mock.py 的 _slug 保持一致，
    同一封发信无论走 Python 层 mock 还是 CLI 层 mock，message_id 都相同。"""
    local, _, domain = email.partition("@")
    digest = 0
    for ch in email:
        digest = (digest * 131 + ord(ch)) % 0xFFFFFF
    return f"{local}_{digest:06x}"


def write_outbox(record: dict) -> Path:
    outbox = root() / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    path = outbox / (record["message_id"] + ".json")
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

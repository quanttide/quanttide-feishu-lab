"""落盘契约：一份响应一个文件，路径只由资源、动作与页序决定。

    <root>/
      raw/<资源>/<动作>/<页序>.json             飞书原样响应（含 ok/data 信封）
      raw/mail/attachments/<附件id>/<原文件名>   附件原件
      cursor/<资源>.json                        {"cursor": …, "updated_at": …}

三条规矩（这一层存在的全部理由）：

1. **原样**：写进 ``raw/`` 的是平台回的那份负载，不解信封、不拆数组、不聚合、不按月切。
   要什么形状，读的时候再算——写的时候不许加工，加工的东西一旦混进来就分不出哪份是事实。
2. **无业务名**：路径里只有资源名、动作名、飞书 id 与页序。不出现邮箱、人名、来源仓库名——
   那些是调用方的参数，不是飞书的坐标。
3. **游标只在整段拉完后前进**：``set_cursor`` 由 ``pull()`` 在 ``has_more=false`` 时调用，
   中途失败不会把游标推过没拉到的数据。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

# 页序固定四位：raw/<资源>/<动作>/0001.json
SEQ_WIDTH = 4


class RawStore:
    """原样落盘。只认资源名与动作名，不认识任何业务概念。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # ── 路径 ──────────────────────────────────────────────
    def raw_dir(self, resource: str, action: str) -> Path:
        return self.root / "raw" / resource / action

    def response_path(self, resource: str, action: str, seq: int) -> Path:
        return self.raw_dir(resource, action) / f"{seq:0{SEQ_WIDTH}d}.json"

    def attachment_path(self, attachment_id: str, filename: str) -> Path:
        return self.root / "raw" / "mail" / "attachments" / attachment_id / filename

    def cursor_path(self, resource: str) -> Path:
        return self.root / "cursor" / f"{resource}.json"

    # ── 写 ────────────────────────────────────────────────
    def next_seq(self, resource: str, action: str) -> int:
        """下一个页序：接着已有文件往下排，重跑同一次调用不会覆盖历史页。"""
        dirpath = self.raw_dir(resource, action)
        if not dirpath.exists():
            return 1
        return len(list(dirpath.glob("*.json"))) + 1

    def save_response(self, resource: str, action: str, raw: dict,
                      seq: int | None = None) -> Path:
        """把一份原样响应写成一个文件。返回落盘路径。"""
        seq = self.next_seq(resource, action) if seq is None else seq
        path = self.response_path(resource, action, seq)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def save_attachment(self, attachment_id: str, filename: str, data: bytes) -> Path:
        path = self.attachment_path(attachment_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def set_cursor(self, resource: str, cursor: str) -> Path:
        path = self.cursor_path(resource)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"cursor": cursor, "updated_at": datetime.now().isoformat(timespec="seconds")},
            ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    # ── 读 ────────────────────────────────────────────────
    def cursor(self, resource: str) -> str:
        path = self.cursor_path(resource)
        if not path.exists():
            return ""
        return json.loads(path.read_text(encoding="utf-8")).get("cursor", "")

    def responses(self, resource: str, action: str | None = None) -> list[dict]:
        """读回某个资源（或某个动作）已落盘的原样响应，按页序排。"""
        base = self.root / "raw" / resource
        paths = sorted(base.glob("*/[0-9]*.json")) if action is None \
            else sorted(self.raw_dir(resource, action).glob("[0-9]*.json"))
        return [json.loads(p.read_text(encoding="utf-8")) for p in paths]

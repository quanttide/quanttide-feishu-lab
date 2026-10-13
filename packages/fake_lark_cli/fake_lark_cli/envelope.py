"""输出信封：与真 lark-cli 同形。

成功: ``{"ok": true, "data": {...}}``        → stdout，exit 0
失败: ``{"ok": false, "error": {...}}``      → stderr，exit 2

依据（对照过真 CLI / 官方 skill 文档）：
- 错误信封与 exit 2：本机 lark-cli 实测（``unknown flag`` / ``required flag(s) not set``）
- 成功信封 ``{"ok": true, "data": ...}``：lark-mail skill 文档「所有 JSON 输出统一包裹」
- ``--dry-run`` 信封带 ``identity``：本机 lark-cli 实测
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field


def usage_error(message: str, *, hint: str | None = None,
                param: str | None = None, subtype: str = "invalid_argument") -> None:
    """以真 CLI 的错误信封退出：stderr + exit 2。"""
    err: dict = {"type": "validation", "subtype": subtype, "message": message}
    if hint:
        err["hint"] = hint
    if param:
        err["param"] = param
    sys.stderr.write(json.dumps({"ok": False, "error": err},
                                ensure_ascii=False, indent=2) + "\n")
    sys.exit(2)


@dataclass
class Result:
    """一条命令跑完的结果：data 是 JSON 负载，table 是 --format=table 的正文，
    notes 是 table 模式下打到 stderr 的提示行（真 CLI 也是这个习惯）。"""

    data: dict
    table: str | None = None
    notes: list[str] = field(default_factory=list)


def _write(text: str, jq: str | None) -> None:
    if jq is None:
        sys.stdout.write(text + "\n")
        return
    try:
        proc = subprocess.run(["jq", jq], input=text, capture_output=True, text=True)
    except FileNotFoundError:
        usage_error("--jq 需要本机装有 jq", param="--jq")
    if proc.returncode != 0:
        usage_error((proc.stderr or "jq 执行失败").strip(), param="--jq")
    sys.stdout.write(proc.stdout)


def emit(result: Result, flags: dict, command: str, *, top: dict | None = None) -> None:
    """按 --format / --jq 输出。--json 是 --format=json 的简写；给了 --jq 一律按 json 走。
    top 是顶层附加字段（--dry-run 信封用它放 identity / dry_run）。"""
    fmt = flags.get("format") or "json"
    if flags.get("json") or flags.get("jq"):
        fmt = "json"
    payload = {"ok": True, **(top or {}), "data": result.data}

    if fmt in ("json", "data", "pretty"):
        _write(json.dumps(payload, ensure_ascii=False, indent=2), flags.get("jq"))
    elif fmt == "ndjson":
        _write(json.dumps(payload, ensure_ascii=False), flags.get("jq"))
    elif fmt == "table":
        if result.table is None:
            usage_error(f"mock 未实现 {command} 的 --format=table",
                        hint="改用 --format json")
        sys.stdout.write(result.table + "\n")
        for note in result.notes:
            sys.stderr.write(note + "\n")
    else:
        usage_error(f"mock 未实现 --format={fmt}",
                    hint="mock 支持 json / data / pretty / ndjson / table",
                    param="--format")

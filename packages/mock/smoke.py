"""packages/mock 自检：五条命令各走一遍，全部经 PATH 遮蔽调用假 lark-cli。

跑法（实验室根目录）：

    python3 packages/mock/smoke.py

夹具整份拷进临时目录、LARK_MOCK_FIXTURES 指过去再跑：
发信写进临时目录，不碰仓库里的 tests/fixtures/outbox/。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parent
LAB = PKG.parents[1]                      # packages/mock → packages → 实验室根
BIN = PKG / "bin"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✓' if ok else '✗'} {name}")
    if not ok:
        failures.append(f"{name}｜{detail[:300]}")


def sh(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["lark-cli", *args], capture_output=True, text=True, env=env)


def payload(p: subprocess.CompletedProcess) -> dict:
    """成功走 stdout，失败走 stderr——与真 CLI 一致。"""
    return json.loads(p.stdout if p.returncode == 0 else p.stderr)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="lark-mock-"))
    try:
        shutil.copytree(LAB / "tests" / "fixtures", tmp / "fixtures")
        env = os.environ.copy()
        env["PATH"] = f"{BIN}{os.pathsep}{env['PATH']}"
        env["LARK_MOCK_FIXTURES"] = str(tmp / "fixtures")

        print("── PATH 遮蔽")
        which = shutil.which("lark-cli", path=env["PATH"])
        check("which lark-cli 指向 mock", which == str(BIN / "lark-cli"), str(which))

        print("── mail +triage")
        p = sh(env, "mail", "+triage", "--filter", '{"folder":"收件箱"}', "--format", "json")
        d = payload(p)
        check("收件箱 4 封", d["data"]["count"] == 4, p.stderr)
        p = sh(env, "mail", "+triage", "--filter", '{"folder":"inbox"}', "--format", "json")
        check("folder=inbox 别名 → 收件箱", payload(p)["data"]["count"] == 4)
        p = sh(env, "mail", "+triage", "--filter", '{"folder":"Spam"}', "--format", "json")
        check("Spam 1 封", payload(p)["data"]["count"] == 1)

        p = sh(env, "mail", "+triage", "--max", "2", "--format", "json")
        d = payload(p)["data"]
        token = d["page_token"]
        check("翻页第一页：count=2 / has_more / 游标", d["count"] == 2 and d["has_more"]
              and token.startswith("list:"), json.dumps(d, ensure_ascii=False))
        p = sh(env, "mail", "+triage", "--max", "2", "--page-token", token, "--format", "json")
        d = payload(p)["data"]
        check("翻页第二页：剩 2 封、无游标", d["count"] == 2 and not d["has_more"],
              json.dumps(d, ensure_ascii=False))

        print("── mail +messages")
        p = sh(env, "mail", "+messages", "--message-ids", "m-001,m-999")
        d = payload(p)["data"]
        check("命中 1 封，m-999 进 unavailable", d["total"] == 1
              and d["unavailable_message_ids"] == ["m-999"], json.dumps(d, ensure_ascii=False))
        m = d["messages"][0]
        check("归一化字段（正文 / 文件夹 / 附件）",
              "简历" in m["body_plain_text"] and m["folder_id"] == "收件箱"
              and m["attachments"][0]["filename"] == "陈默-简历.txt",
              json.dumps(m, ensure_ascii=False))

        print("── mail +send")
        p = sh(env, "mail", "+send", "--to", "smoke@example.com",
               "--subject", "冒烟", "--body", "…")
        d = payload(p)
        check("默认草稿模式（不落盘）", "draft_id" in d["data"], p.stderr)
        p = sh(env, "mail", "+send", "--confirm-send", "--to", "smoke@example.com",
               "--subject", "冒烟", "--body", "…")
        d = payload(p)
        mid = d["data"].get("message_id", "")
        check("--confirm-send 写 outbox", mid != ""
              and (tmp / "fixtures" / "outbox" / (mid + ".json")).exists(),
              json.dumps(d, ensure_ascii=False))

        print("── base +record-list")
        p = sh(env, "base", "+record-list", "--base-token", "b", "--table-id", "tbl1",
               "--format", "json")
        check("全表 2 条", payload(p)["data"]["total"] == 2, p.stderr)
        p = sh(env, "base", "+record-list", "--base-token", "b", "--table-id", "tbl1",
               "--filter-json",
               '{"logic":"and","conditions":[["邮箱","==","herui@example.com"]]}',
               "--format", "json")
        check("过滤（中文别名 邮箱）1 条", payload(p)["data"]["total"] == 1, p.stderr)

        print("── im +chat-members-list")
        p = sh(env, "im", "+chat-members-list", "--chat-id", "oc_mock")
        d = payload(p)["data"]
        check("群成员 3 人且 member_id 是邮箱", len(d["users"]) == 3
              and d["users"][0]["member_id_type"] == "email", json.dumps(d, ensure_ascii=False))

        print("── 信封与错误面")
        p = sh(env, "mail", "+reply")
        err = payload(p)
        check("未实现命令 → exit 2 + ok:false",
              p.returncode == 2 and err["ok"] is False, p.stderr)
        p = sh(env, "mail", "+triage", "--nope", "1")
        err = payload(p)
        check("未知 flag → exit 2 + param",
              p.returncode == 2 and err["error"].get("param") == "--nope"
              or err["error"]["message"].startswith("unknown flag"), p.stderr)
        p = sh(env, "mail", "+triage", "--filter", '{"folder":"收件箱"}',
               "--jq", ".data.count")
        check("--jq '.data.count' → 4", p.stdout.strip() == "4", p.stdout + p.stderr)
        p = sh(env, "im", "+chat-members-list", "--chat-id", "oc_mock", "--dry-run")
        d = payload(p)
        check("--dry-run 信封带 identity/dry_run",
              d["ok"] and d["dry_run"] is True and d["identity"] == "user", p.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print(f"\n✗ {len(failures)} 项未过：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nmock lark-cli 自检全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

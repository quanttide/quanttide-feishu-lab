"""实验室冒烟：资源层 + 流程能力层 + 假 lark-cli，一份脚本跑完。

跑法（在实验室根目录）：

    PYTHONPATH=src python3 tests/smoke.py            # 两段都跑
    PYTHONPATH=src python3 tests/smoke.py --record   # 重新录制资源层负载快照

三段判据，全部可跑：

1. **资源层**：六资源十三动作取得到东西；负载与录制快照（``tests/fixtures/snapshots/resources.json``）
   一致——同进程假 CLI 与子进程假 CLI 两条路都要对上；落盘契约成立；源码里没有具体值。
2. **能力层**：四个动作取得到东西（漂移与 Spam 两处卡点也算得出来）；换成子进程后端结果一致。
3. **示例 `examples/qtrecurit`**：流程写成 YAML，端到端跑通（重建状态、推一步、缺凭据明确报错）。
4. **假 lark-cli 的 CLI 面**：经 PATH 遮蔽调它，核信封、退出码、翻页、``--jq`` / ``--dry-run``。

落盘写在临时目录，跑完即删，不碰仓库。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import feishu as cap  # noqa: E402
from feishu.resources import pull  # noqa: E402
from feishu.resources.backend_inprocess import InProcessBackend  # noqa: E402
from feishu.resources.backend_cli import CLIBackend  # noqa: E402
from feishu.resources.store import RawStore  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
MOCK_BIN = ROOT / "tests" / "fake_lark_cli" / "bin"
PYTHON = ROOT / ".venv" / "bin" / "python"
SNAPSHOT = FIXTURES / "snapshots" / "resources.json"
FOLDERS = ["收件箱", "已发送问卷", "沟通面试中", "Spam"]     # 对齐 flows/recruitment.yaml 的收集节

# 值全部由调用方给：能力层不认识这些是什么
CHAT, PEER, MEETING, MAILBOX = "oc_mock_chat", "ou_mock_peer", "7654321098765432109", "hr@example.com"
DOC, MAIL_ID = "docxmock0001", "m-001"

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS += ok
    FAIL += not ok
    print(f"  {'✓' if ok else '✗'} {name}")
    if not ok and detail:
        print(f"      {detail}")


def calls(client) -> dict:
    """十三个动作的调用清单：录制与比对共用同一份，不许各写一套。"""
    pages = lambda action, **kw: [p.payload for p in pull(client, action, **kw)]
    return {
        "mail_list": pages("mail_list", folder="收件箱", mailbox=MAILBOX, page_size=2),
        "mail_messages": [client.mail_messages(message_ids=[MAIL_ID], mailbox=MAILBOX).payload],
        "mail_attachment_download": [a.filename for a in client.mail_attachment_download(
            message_id=MAIL_ID, attachment_ids=[], mailbox=MAILBOX)],
        "mail_send": [client.mail_send(to="new@example.com", subject="群二维码", body="扫码进群",
                                       attachments=["群二维码.png"], mailbox=MAILBOX).payload],
        "im_chat_messages": pages("im_chat_messages", chat_id=CHAT, page_size=2),
        "im_chat_members": [client.im_chat_members(chat_id=CHAT).payload],
        "im_messages_search": [client.im_messages_search(sender=PEER).payload],
        "vc_meeting_search": [client.vc_meeting_search(participant_id=PEER).payload],
        "vc_meeting_get": [client.vc_meeting_get(meeting_id=MEETING).payload],
        "task_list_mine": [client.task_list(scope="mine", complete=False).payload],
        "task_list_related": [client.task_list(scope="related").payload],
        "task_list_tasklists": [client.task_list(scope="tasklists").payload],
        "drive_search": [client.drive_search(edited_since="2026-10-01").payload],
        "docs_fetch": [client.docs_fetch(doc=DOC).payload],
        "base_records": [client.base_records(base_token="t", table_id="t", filter_json=json.dumps(
            {"logic": "and", "conditions": [["邮箱", "intersects", ["herui@example.com"]]]},
            ensure_ascii=False)).payload],
    }


def smoke_resources(store_dir: Path) -> None:
    """资源层：十三动作 + 录制负载 + 落盘契约 + 值不在代码里。"""
    mock, cli = InProcessBackend(None, str(FIXTURES)), CLIBackend(str(store_dir), mailbox=MAILBOX,
                                                                 chat_id=CHAT)
    if "--record" in sys.argv:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(calls(mock), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已录制 {SNAPSHOT.relative_to(ROOT)}（{len(calls(mock))} 项）")
        return
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    print("── 1. 资源层：十三个动作")
    for name, value in calls(mock).items():
        check(name, bool(value) or value == [], f"{name} 空结果")

    print("\n── 2. 资源层：与录制负载一致（同进程假 CLI / 子进程假 CLI 都要对上）")
    for impl, layer in ((mock, "夹具层"), (cli, "子进程层")):
        got = calls(impl)
        for key, expected in snapshot.items():
            check(f"{layer} {key}", got.get(key) == expected,
                  f"实际 {str(got.get(key))[:120]}\n      期望 {str(expected)[:120]}")

    print("\n── 3. 资源层：落盘契约")
    raws = sorted((store_dir / "raw").glob("*/*/[0-9]*.json"))
    check("raw 下有原样响应", bool(raws), f"{len(raws)} 份")
    unenveloped = [p for p in raws
                   if json.loads(p.read_text(encoding="utf-8")).get("ok") is not True
                   or not isinstance(json.loads(p.read_text(encoding="utf-8")).get("data"),
                                     (dict, list))]
    check('每份顶层都是未解信封的 {"ok": true, "data": …}', not unenveloped, str(unenveloped[:3]))
    mail_pages = sorted((store_dir / "raw" / "mail" / "list").glob("[0-9]*.json"))
    check("翻页每页一个文件、页序四位", 2 <= len(mail_pages) and mail_pages[0].name == "0001.json",
          f"{len(mail_pages)} 个文件")
    check("没拉到底之前不写游标", not (store_dir / "cursor").exists())
    pull(cli, "mail_list", cursor_key="mail", folder="收件箱", mailbox=MAILBOX, page_size=2)
    cursor = json.loads((store_dir / "cursor" / "mail.json").read_text(encoding="utf-8"))
    check("整段拉完后游标才写", cursor["cursor"] in ("", "list:2"), str(cursor))
    landed = sorted((store_dir / "raw" / "mail" / "attachments").glob("*/*"))
    check("附件落在 <附件id>/<原文件名>，字节与夹具一致",
          bool(landed) and landed[0].parent.name == f"{MAIL_ID}-att-0"
          and landed[0].read_bytes() == (FIXTURES / "attachments" / landed[0].name).read_bytes(),
          str(landed[:1]))
    bad_paths = [str(p) for p in (store_dir / "raw").rglob("*")
                 if re.search(r"(候选人|qt[a-z]+-private|journal|report)", str(p))]
    check("路径里没有业务名 / 来源仓名", not bad_paths, str(bad_paths[:3]))

    print("\n── 4. 资源层：值全在调用方（源码里不该有具体值）")
    for path in sorted((ROOT / "src" / "feishu" / "resources").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        hard_id = re.search(r'"(oc|ou|om|cli|tbl|bas)[A-Za-z0-9]{8,}"', text)
        hard_mail = re.search(r"[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        check(f"{path.name} 无硬编码 id / 邮箱", not hard_id and not hard_mail,
              f"{hard_id and hard_id.group(0)} {hard_mail and hard_mail.group(0)}")


def smoke_capability_layer() -> None:
    """能力层：四个动作取得到东西（含漂移与 Spam 两处卡点）+ 换成子进程后端结果一致。"""
    c = cap.mock(str(FIXTURES))
    print("\n── 5. 能力层：读邮件（按文件夹，带游标）")
    applications: dict[str, str] = {}
    drift: list[str] = []
    spammy: list[str] = []
    for folder in FOLDERS:
        mails, cursor = c.read_mail(folder)
        mails2, _ = c.read_mail(folder, cursor)          # 游标再拉一次应无新件
        check(f"{folder}: {len(mails)} 封，再拉 {len(mails2)} 封", not mails2)
        for m in mails:
            if not m.sender:
                continue
            if folder == "收件箱":
                applications.setdefault(m.sender.lower(), m.date)
            elif folder == "沟通面试中":
                drift.append(m.sender.lower())
            elif folder == "Spam":
                spammy.append(m.sender.lower())
    check(f"漂移（只出现在沟通面试中）：{drift}；误判（在 Spam）：{spammy}", bool(drift) and bool(spammy))

    people = sorted(set(list(applications) + drift + spammy))
    records, members = c.read_survey(people), c.read_group_members()
    qr_to, qr_subject = "chenmo@example.com", "量潮实训基地 · 群二维码"
    qr_body, qr_attach = "你好，扫码直接进群（群二维码见附件）。", ["群二维码.png"]
    mid = c.send_mail(qr_to, qr_subject, qr_body, qr_attach)
    check(f"调研表命中 {len(records)} 人 / 群成员 {len(members)} 人 / 发出群二维码 {bool(mid)}",
          bool(records) and bool(members) and bool(mid))

    cli_cap = cap.real(attachments_dir=str(FIXTURES / "attachments"))
    print("\n── 6. 能力层：换成子进程后端，结果一致")
    for folder in FOLDERS:
        check(f"read_mail({folder})", c.read_mail(folder) == cli_cap.read_mail(folder))
    check("read_survey", records == cli_cap.read_survey(people))
    check("read_group_members", members == cli_cap.read_group_members())
    check("send_mail", mid == cli_cap.send_mail(qr_to, qr_subject, qr_body, qr_attach))


def smoke_example() -> None:
    """示例 examples/qtrecurit：流程写成数据、一轮一跑，端到端跑通。

    状态文件指向临时目录——不然上一轮跑出来的状态会让这一轮的结果不一样。
    """
    print("\n── 7. 示例 examples/qtrecurit（流程 = YAML，执行器读它推格）")
    py = PYTHON if PYTHON.exists() else Path(sys.executable)     # 示例要 pyyaml
    state = Path(tempfile.mkdtemp(prefix="feishu-example-")) / "recruitment.json"

    def run_example(env: dict, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(py), str(ROOT / "examples/qtrecurit/run.py"),
                               *args, "--state", str(state)],
                              capture_output=True, text=True, env=env, cwd=str(ROOT))

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    status = run_example(env, "status", "--mock")
    states = dict(re.findall(r"(\S+@\S+)\s+(\S+?)（", status.stdout))
    check("status --mock：从飞书侧重建（进人只看收件箱，四人在册）",
          len(states) == 4 and all("无响应" not in v for v in states.values()), status.stdout)
    check("重建出来的格子：投递 3 人 + 已进群 1 人",
          sorted(states.values()) == ["已进群", "投递", "投递", "投递"], str(states))

    step = run_example(env, "run", "--mock", "--step")
    check("run --mock --step：只推一步（一条 ✓）",
          step.stdout.count("✓") == 1, step.stdout + step.stderr)
    after = dict(re.findall(r"(\S+@\S+)\s+(\S+?)（", run_example(env, "status", "--mock").stdout))
    check("推完这一步后状态落盘：有一人格子变了",
          after != states and sum(1 for k in after if after[k] != states.get(k)) == 1,
          f"{states} → {after}")

    bad = run_example(env, "status")
    check("既不给 --mock 也不给 --cli：明确报错、不偷偷打出去",
          bad.returncode != 0 and "--mock" in (bad.stdout + bad.stderr), bad.stdout + bad.stderr)


def smoke_cli_surface() -> None:
    """假 lark-cli 的 CLI 面：信封（成功 stdout / 失败 stderr + exit 2）、翻页、--jq、--dry-run。

    夹具整份拷进临时目录再跑，发信写在那里，不动仓库里的 tests/fixtures/。
    """
    tmp = Path(tempfile.mkdtemp(prefix="feishu-cli-surface-"))
    try:
        shutil.copytree(FIXTURES, tmp / "fixtures")
        env = os.environ.copy()
        env["PATH"] = f"{MOCK_BIN}{os.pathsep}{env['PATH']}"
        env["LARK_MOCK_FIXTURES"] = str(tmp / "fixtures")

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(["lark-cli", *args], capture_output=True, text=True, env=env)

        def payload(p: subprocess.CompletedProcess) -> dict:
            return json.loads(p.stdout if p.returncode == 0 else p.stderr)

        print("\n── 8. 假 lark-cli 的 CLI 面（PATH 遮蔽）")
        check("which lark-cli 指向假 CLI",
              shutil.which("lark-cli", path=env["PATH"]) == str(MOCK_BIN / "lark-cli"))

        d = payload(run("mail", "+triage", "--filter", '{"folder":"收件箱"}', "--format", "json"))["data"]
        check("收件箱 4 封 / folder=inbox 别名 / Spam 1 封",
              d["count"] == 4
              and payload(run("mail", "+triage", "--filter", '{"folder":"inbox"}',
                              "--format", "json"))["data"]["count"] == 4
              and payload(run("mail", "+triage", "--filter", '{"folder":"Spam"}',
                              "--format", "json"))["data"]["count"] == 1)
        d = payload(run("mail", "+triage", "--max", "2", "--format", "json"))["data"]
        token = d["page_token"]
        check("翻页第一页 count=2 / has_more / 游标", d["count"] == 2 and d["has_more"]
              and token.startswith("list:"), json.dumps(d, ensure_ascii=False))
        d = payload(run("mail", "+triage", "--max", "2", "--page-token", token,
                        "--format", "json"))["data"]
        check("翻页第二页剩 2 封、无游标", d["count"] == 2 and not d["has_more"])

        d = payload(run("mail", "+messages", "--message-ids", "m-001,m-999"))["data"]
        m = d["messages"][0] if d["messages"] else {}
        check("+messages 命中 1 封、m-999 进 unavailable、字段归一化",
              d["total"] == 1 and d["unavailable_message_ids"] == ["m-999"]
              and "简历" in m.get("body_plain_text", "") and m.get("folder_id") == "收件箱"
              and m["attachments"][0]["filename"] == "陈默-简历.txt")

        check("+send 默认草稿模式（不落盘）",
              "draft_id" in payload(run("mail", "+send", "--to", "smoke@example.com",
                                        "--subject", "冒烟", "--body", "…"))["data"])
        mid = payload(run("mail", "+send", "--confirm-send", "--to", "smoke@example.com",
                          "--subject", "冒烟", "--body", "…"))["data"].get("message_id", "")
        check("+send --confirm-send 写 outbox",
              bool(mid) and (tmp / "fixtures" / "outbox" / f"{mid}.json").exists())

        check("base +record-list 全表 2 条 / 过滤（中文别名 邮箱）1 条",
              payload(run("base", "+record-list", "--base-token", "b", "--table-id", "tbl1",
                          "--format", "json"))["data"]["total"] == 2
              and payload(run("base", "+record-list", "--base-token", "b", "--table-id", "tbl1",
                              "--filter-json", '{"logic":"and","conditions":'
                              '[["邮箱","==","herui@example.com"]]}', "--format", "json")
                          )["data"]["total"] == 1)
        d = payload(run("im", "+chat-members-list", "--chat-id", "oc_mock"))["data"]
        check("im +chat-members-list 3 人且 member_id 是邮箱",
              len(d["users"]) == 3 and d["users"][0]["member_id_type"] == "email")

        p = run("mail", "+reply")
        check("未实现命令 → exit 2 + ok:false",
              p.returncode == 2 and payload(p)["ok"] is False)
        p = run("mail", "+triage", "--nope", "1")
        check("未知 flag → exit 2 + param",
              p.returncode == 2 and payload(p)["error"].get("param") == "--nope")
        p = run("mail", "+triage", "--filter", '{"folder":"收件箱"}', "--jq", ".data.count")
        check("--jq '.data.count' → 4", p.stdout.strip() == "4", p.stdout + p.stderr)
        d = payload(run("im", "+chat-members-list", "--chat-id", "oc_mock", "--dry-run"))
        check("--dry-run 信封带 identity / dry_run",
              d["ok"] and d["dry_run"] is True and d["identity"] == "user")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    store_dir = Path(tempfile.mkdtemp(prefix="feishu-smoke-"))
    os.environ["PATH"] = str(MOCK_BIN) + os.pathsep + os.environ["PATH"]
    try:
        smoke_resources(store_dir)
        if "--record" not in sys.argv:
            smoke_capability_layer()
            smoke_example()
            smoke_cli_surface()
        print(f"\n通过 {PASS}，失败 {FAIL}")
        return 0 if FAIL == 0 else 1
    finally:
        shutil.rmtree(store_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

"""实验室冒烟：资源层 + 流程能力层 + 假 lark-cli，一份脚本跑完。

跑法（在实验室根目录）：

    PYTHONPATH=src python3 scripts/smoke.py            # 两段都跑
    PYTHONPATH=src python3 scripts/smoke.py --record   # 重新录制资源层负载快照

三段判据，全部可跑：

1. **资源层**：六资源十三动作取得到东西；负载与录制快照（``tests/fixtures/snapshots/resources.json``）
   一致——同进程假 CLI 与子进程假 CLI 两条路都要对上；落盘契约成立；源码里没有具体值。
2. **流程能力层**：夹具撑得起招聘最小闭环——六位虚构候选人落在投递 / 二维码已发 / 已进群三格，
   其中两位分别躺在 Spam 与被移走的文件夹里（两处卡点）；换成子进程假 CLI 结果一致。
3. **假 lark-cli**：信封、退出码、翻页、``--jq`` / ``--dry-run`` 自检（见 packages/mock/README.md）。

落盘写在临时目录，跑完即删，不碰仓库。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import recruitment.feishu as cap  # noqa: E402
from recruitment.feishu.resources import pull  # noqa: E402
from recruitment.feishu.resources.mock import MockResources  # noqa: E402
from recruitment.feishu.resources.real import CLIResources  # noqa: E402
from recruitment.feishu.resources.store import RawStore  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
MOCK_BIN = ROOT / "packages" / "mock" / "bin"
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
    mock, cli = MockResources(None, str(FIXTURES)), CLIResources(str(store_dir), mailbox=MAILBOX,
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
    for path in sorted((ROOT / "src" / "recruitment" / "feishu" / "resources").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        hard_id = re.search(r'"(oc|ou|om|cli|tbl|bas)[A-Za-z0-9]{8,}"', text)
        hard_mail = re.search(r"[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        check(f"{path.name} 无硬编码 id / 邮箱", not hard_id and not hard_mail,
              f"{hard_id and hard_id.group(0)} {hard_mail and hard_mail.group(0)}")


def smoke_flow() -> None:
    """流程能力层：夹具撑不撑得起最小闭环 + 换实现不换结果。"""
    c = cap.mock(str(FIXTURES))
    print("\n── 5. 流程能力层：读邮件（按文件夹，带游标）")
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

    people = sorted(set(list(applications) + drift + spammy))
    records, members = c.read_survey(people), c.read_group_members()
    qr_to, qr_subject = "chenmo@example.com", "量潮实训基地 · 群二维码"
    qr_body, qr_attach = "你好，扫码直接进群（群二维码见附件）。", ["群二维码.png"]
    mid = c.send_mail(qr_to, qr_subject, qr_body, qr_attach)
    check(f"调研表命中 {len(records)} 人 / 群成员 {len(members)} 人 / 发出群二维码 {bool(mid)}",
          bool(records) and bool(members) and bool(mid))

    cli_cap = cap.real(attachments_dir=str(FIXTURES / "attachments"))
    print("\n── 6. 流程能力层：换成子进程假 CLI，结果一致")
    for folder in FOLDERS:
        check(f"read_mail({folder})", c.read_mail(folder) == cli_cap.read_mail(folder))
    check("read_survey", records == cli_cap.read_survey(people))
    check("read_group_members", members == cli_cap.read_group_members())
    check("send_mail", mid == cli_cap.send_mail(qr_to, qr_subject, qr_body, qr_attach))

    print("\n── 7. 每人现在在哪一格（runner 的活儿，这里先手推一遍）")
    expect = {
        "chenmo@example.com": "二维码已发",
        "linyizhou@example.com": "投递",
        "suxiao@example.com": "投递",
        "herui@example.com": "已进群",
        "zhouyan@example.com": "投递（在 Spam 里，要先捞回）",
        "zhengnan@example.com": "投递（被移出收件箱，靠补拉找回）",
    }
    for email in people:
        state = "已进群" if email in members else ("二维码已发" if email == qr_to else "投递")
        if email in spammy:
            state += "（在 Spam 里，要先捞回）"
        if email in drift:
            state += "（被移出收件箱，靠补拉找回）"
        want = expect.get(email, "?")
        check(f"{email:26s} {state}", state.startswith(want), f"期望 {want}")


def main() -> int:
    store_dir = Path(tempfile.mkdtemp(prefix="feishu-smoke-"))
    os.environ["PATH"] = str(MOCK_BIN) + os.pathsep + os.environ["PATH"]
    try:
        smoke_resources(store_dir)
        if "--record" not in sys.argv:
            smoke_flow()
        print(f"\n通过 {PASS}，失败 {FAIL}")
        return 0 if FAIL == 0 else 1
    finally:
        shutil.rmtree(store_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

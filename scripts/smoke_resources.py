"""资源层冒烟：十二个动作走两层实现，并核落盘契约。

跑法（在实验室根目录）：

    PYTHONPATH=src python3 scripts/smoke_resources.py

它回答四个问题，每个都有可跑判据：

1. **十二动作都能取到东西**：六资源十二动作各跑一遍，夹具撑不撑得起来。
2. **换实现不换结果**：同一批夹具，进程内替身与假 lark-cli（子进程）负载逐项一致。
3. **落盘契约成立**：``raw/`` 一份响应一个文件、顶层是**未解信封**的原样响应；
   翻页每页一份文件；游标只在整段拉完后写；附件按 ``<附件id>/<原文件名>`` 落盘，
   字节与夹具一致。
4. **值全在调用方**：资源层源码里 grep 不到任何飞书 id、邮箱、人名、关键词——
   也就是「公开仓只收能力，具体值留私有配置」这条能不能兑现。

落盘全部写在临时目录，跑完即删，不碰仓库。
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

from recruitment.feishu.resources import pull  # noqa: E402
from recruitment.feishu.resources.mock import MockResources  # noqa: E402
from recruitment.feishu.resources.real import CLIResources  # noqa: E402
from recruitment.feishu.resources.store import RawStore  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
MOCK_BIN = ROOT / "packages" / "mock" / "bin"
CHAT = "oc_mock_chat"
PEER = "ou_mock_peer"
MAILBOX = "hr@example.com"          # 值由调用方给：能力层不认识它是什么邮箱

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS += ok
    FAIL += not ok
    print(f"  {'✓' if ok else '✗'} {name}")
    if not ok and detail:
        print(f"      {detail}")


def main() -> int:
    store_dir = Path(tempfile.mkdtemp(prefix="feishu-resources-"))
    fixture_store = Path(tempfile.mkdtemp(prefix="feishu-resources-mock-"))
    os.environ["PATH"] = str(MOCK_BIN) + os.pathsep + os.environ["PATH"]
    try:
        c_mock = MockResources(str(fixture_store), str(FIXTURES))
        c_cli = CLIResources(str(store_dir), mailbox=MAILBOX, chat_id=CHAT)

        print("── 1. 十二个动作（夹具层）")
        mail_pages = pull(c_mock, "mail_list", folder="收件箱", mailbox=MAILBOX, page_size=2)
        mail_ids = [m["message_id"] for p in mail_pages for m in p.payload["messages"]]
        check("mail_list 翻页", len(mail_pages) >= 2 and len(mail_ids) == len(set(mail_ids)),
              f"{len(mail_pages)} 页 / {len(mail_ids)} 封")
        full = c_mock.mail_messages(message_ids=mail_ids[:2], mailbox=MAILBOX)
        check("mail_messages", len(full.payload["messages"]) == 2
              and not full.payload["unavailable_message_ids"])
        atts = c_mock.mail_attachment_download(message_id=mail_ids[0], attachment_ids=[],
                                               mailbox=MAILBOX)
        check("mail_attachment_download", bool(atts), f"{len(atts)} 个附件")
        im = pull(c_mock, "im_chat_messages", chat_id=CHAT, page_size=2)
        check("im_chat_messages 翻页", len(im) >= 2, f"{len(im)} 页")
        p2p = c_mock.im_chat_messages(user_id=PEER, with_reactions=False)
        check("im_chat_messages(单聊, 去表情)", all("reactions" not in m
                                                  for m in p2p.payload["messages"]))
        members = c_mock.im_chat_members(chat_id=CHAT)
        check("im_chat_members", len(members.payload["users"]) > 0)
        search = c_mock.im_messages_search(sender=PEER)
        check("im_messages_search", len(search.payload["items"]) > 0)
        vcs = c_mock.vc_meeting_search(participant_id=PEER)
        check("vc_meeting_search", len(vcs.payload["items"]) > 0)
        mid = vcs.payload["items"][0]["meeting_id"]
        detail = c_mock.vc_meeting_get(meeting_id=mid)
        check("vc_meeting_get", "meeting" in detail.payload)
        tasks = c_mock.task_list(scope="mine", complete=False)
        check("task_list(--complete=false)", all(not i["completed"] for i in tasks.payload["items"]))
        check("task_list(related)", len(c_mock.task_list(scope="related").payload["items"]) > 0)
        check("task_list(tasklists)", len(c_mock.task_list(scope="tasklists").payload["items"]) > 0)
        docs = c_mock.drive_search(edited_since="2026-10-01")
        check("drive_search", len(docs.payload["items"]) > 0)
        check("docs_fetch", bool(c_mock.docs_fetch(doc="docxmock0001").payload.get("content")))
        recs = c_mock.base_records(base_token="t", table_id="t",
                                   filter_json=json.dumps({"logic": "and", "conditions":
                                                           [["邮箱", "intersects", ["herui@example.com"]]]},
                                                          ensure_ascii=False))
        check("base_records(filter)", len(recs.payload["items"]) == 1)

        print("\n── 2. 换实现不换结果（夹具层 vs 假 lark-cli）")
        pairs = [
            ("mail_list", lambda c: pull(c, "mail_list", folder="收件箱", mailbox=MAILBOX, page_size=2)),
            ("mail_messages", lambda c: [c.mail_messages(message_ids=mail_ids[:2], mailbox=MAILBOX)]),
            ("im_chat_messages", lambda c: pull(c, "im_chat_messages", chat_id=CHAT, page_size=2)),
            ("im_chat_members", lambda c: [c.im_chat_members(chat_id=CHAT)]),
            ("im_messages_search", lambda c: [c.im_messages_search(sender=PEER)]),
            ("vc_meeting_search", lambda c: [c.vc_meeting_search(participant_id=PEER)]),
            ("vc_meeting_get", lambda c: [c.vc_meeting_get(meeting_id=mid)]),
            ("task_list(mine)", lambda c: [c.task_list(scope="mine", complete=False)]),
            ("task_list(related)", lambda c: [c.task_list(scope="related")]),
            ("task_list(tasklists)", lambda c: [c.task_list(scope="tasklists")]),
            ("drive_search", lambda c: [c.drive_search(edited_since="2026-10-01")]),
            ("docs_fetch", lambda c: [c.docs_fetch(doc="docxmock0001")]),
            ("base_records", lambda c: [c.base_records(
                base_token="t", table_id="t",
                filter_json=json.dumps({"logic": "and", "conditions": [["邮箱", "intersects",
                                                                        ["herui@example.com"]]]},
                                       ensure_ascii=False))]),
        ]
        for name, run in pairs:
            a = [p.payload for p in run(c_mock)]
            b = [p.payload for p in run(c_cli)]
            check(f"{name} 两层一致", a == b)
        atts_cli = c_cli.mail_attachment_download(message_id=mail_ids[0], attachment_ids=[],
                                                 mailbox=MAILBOX)
        check("mail_attachment_download 两层一致（文件名与字节）",
              [a.filename for a in atts] == [a.filename for a in atts_cli]
              and all(Path(a.path).read_bytes() == Path(b.path).read_bytes()
                      for a, b in zip(atts, atts_cli)))

        print("\n── 3. 落盘契约")
        store = RawStore(str(store_dir))
        raws = sorted((store_dir / "raw").glob("*/*/[0-9]*.json"))
        check("raw 下有原样响应", len(raws) > 0, f"{len(raws)} 份")
        unenveloped = [p for p in raws
                       if not (json.loads(p.read_text(encoding="utf-8")).get("ok") is True
                               and isinstance(json.loads(p.read_text(encoding="utf-8")).get("data"),
                                              (dict, list)))]
        check("每份顶层都是未解信封的 {\"ok\": true, \"data\": …}", not unenveloped,
              str(unenveloped[:3]))
        mail_files = sorted((store_dir / "raw" / "mail" / "list").glob("[0-9]*.json"))
        check("翻页每页一个文件", len(mail_files) == len(mail_pages),
              f"{len(mail_files)} 文件 / {len(mail_pages)} 页")
        check("页序四位、从 0001 起", [p.name for p in mail_files][:1] == ["0001.json"])

        # 游标：一次性动作不写游标；pull 的列表动作写
        c_cli2 = CLIResources(str(store_dir), mailbox=MAILBOX, chat_id=CHAT)
        check("落盘前没有游标", not (store_dir / "cursor").exists()
              or list((store_dir / "cursor").glob("*.json")) == [])
        pull(c_cli2, "mail_list", cursor_key="mail", folder="收件箱", mailbox=MAILBOX, page_size=2)
        cur = json.loads((store_dir / "cursor" / "mail.json").read_text(encoding="utf-8"))
        check("整段拉完后游标才写", cur["cursor"] == "" or cur["cursor"].startswith("list:"))

        landed = sorted((store_dir / "raw" / "mail" / "attachments").glob("*/*"))
        check("附件落在 <附件id>/<原文件名>", bool(landed) and landed[0].parent.name.startswith("m-"),
              str(landed[:2]))

        # 路径里不许出现业务名与来源仓名
        bad = [str(p) for p in (store_dir / "raw").rglob("*")
               if re.search(r"(候选人|qt[a-z]+-private|journal|report)", str(p))]
        check("路径里没有业务名 / 来源仓名", not bad, str(bad[:3]))

        print("\n── 4. 值全在调用方（资源层源码里不该有具体值）")
        for path in sorted((ROOT / "src" / "recruitment" / "feishu" / "resources").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            hard_id = re.search(r"\"(oc|ou|om|cli|tbl|bas)[A-Za-z0-9]{8,}\"", text)
            hard_mail = re.search(r"[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
            check(f"{path.name} 无硬编码 id / 邮箱", not hard_id and not hard_mail,
                  f"{hard_id.group(0) if hard_id else ''} {hard_mail.group(0) if hard_mail else ''}")

        print(f"\n通过 {PASS}，失败 {FAIL}")
        return 0 if FAIL == 0 else 1
    finally:
        shutil.rmtree(store_dir, ignore_errors=True)
        shutil.rmtree(fixture_store, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

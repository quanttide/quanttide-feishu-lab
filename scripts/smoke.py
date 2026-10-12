"""夹具冒烟：把四种能力都跑一遍，看夹具能不能撑起最小闭环。

跑法（在实验室根目录）：

    PYTHONPATH=src python3 scripts/smoke.py

它不推进流程，只回答一个问题：**光靠夹具里的数据，一个候选人「现在在哪一格」推得出来吗？**
六位虚构候选人应当落在投递、二维码已发、已进群三格，
其中两位分别躺在 Spam 与被移走的文件夹里（两处卡点）。

后半段把同样四种能力换成子进程走 packages/mock 的假 lark-cli（CLI 层），
逐项核两层结果一致——同一批夹具，换实现不换结果。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import recruitment.feishu as cap  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests", "fixtures")

# 收集范围：收件箱 + 漂移的两个文件夹 + Spam（对齐 tests/fixtures/flows/recruitment.yaml 的收集节）
FOLDERS = ["收件箱", "已发送问卷", "沟通面试中", "Spam"]


def main() -> int:
    c = cap.mock(FIXTURES)

    print("── 读邮件（按文件夹，带游标）")
    applications: dict[str, str] = {}     # 邮箱 → 首次投递日期
    drift: list[str] = []
    spammy: list[str] = []
    for folder in FOLDERS:
        mails, cursor = c.read_mail(folder)
        mails2, cursor2 = c.read_mail(folder, cursor)   # 游标再拉一次应无新件
        print(f"  {folder}: {len(mails)} 封，游标 {cursor or '(空)'}；再拉一次 {len(mails2)} 封")
        for m in mails:
            if folder == "收件箱" and m.sender:
                applications.setdefault(m.sender.lower(), m.date)
            elif folder == "沟通面试中" and m.sender:
                drift.append(m.sender.lower())
            elif folder == "Spam" and m.sender:
                spammy.append(m.sender.lower())

    print(f"  收件箱得到的投递：{sorted(applications)}")
    print(f"  只出现在「沟通面试中」（漂移）：{drift}")
    print(f"  只出现在 Spam（误判）：{spammy}")

    print("\n── 读问卷记录 / 读群成员 / 发群二维码")
    people = sorted(set(list(applications) + drift + spammy))
    records = c.read_survey(people)
    members = c.read_group_members()
    print(f"  调研表命中：{sorted(records)}")
    print(f"  群成员：{sorted(members)}")
    qr_to, qr_subject = "chenmo@example.com", "量潮实训基地 · 群二维码"
    qr_body, qr_attach = "你好，扫码直接进群（群二维码见附件）。", ["群二维码.png"]
    mid = c.send_mail(qr_to, qr_subject, qr_body, qr_attach)
    print(f"  发出一封群二维码（写进 tests/fixtures/outbox/）：{mid}")

    print("\n── CLI 层：子进程走 packages/mock 的假 lark-cli（同一批夹具，两层应当一致）")
    mock_bin = os.path.abspath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "packages", "mock", "bin"))
    os.environ["PATH"] = mock_bin + os.pathsep + os.environ["PATH"]
    cli_cap = cap.real(attachments_dir=os.path.join(FIXTURES, "attachments"))

    cli_same = cli_total = 0

    def same(name: str, a, b) -> None:
        nonlocal cli_same, cli_total
        cli_total += 1
        ok = a == b
        cli_same += ok
        print(f"  {'✓' if ok else '✗'} {name}")
        if not ok:
            print(f"      夹具层：{a!r}")
            print(f"      CLI 层：{b!r}")

    for folder in FOLDERS:
        same(f"read_mail({folder})", c.read_mail(folder), cli_cap.read_mail(folder))
    same("read_survey", records, cli_cap.read_survey(people))
    same("read_group_members", members, cli_cap.read_group_members())
    same("send_mail", mid, cli_cap.send_mail(qr_to, qr_subject, qr_body, qr_attach))

    print("\n── 每人现在在哪一格（runner 的活儿，这里先手推一遍）")
    sent_qr = {qr_to}                       # 上面刚给他发过群二维码
    expect = {
        "chenmo@example.com": "二维码已发",
        "linyizhou@example.com": "投递",
        "suxiao@example.com": "投递",
        "herui@example.com": "已进群",
        "zhouyan@example.com": "投递（在 Spam 里，要先捞回）",
        "zhengnan@example.com": "投递（被移出收件箱，靠补拉找回）",
    }
    passed = total = 0
    for email in people:
        if email in members:
            state = "已进群"
        elif email in sent_qr:
            state = "二维码已发"
        else:
            state = "投递"
        if email in spammy:
            state += "（在 Spam 里，要先捞回）"
        if email in drift:
            state += "（被移出收件箱，靠补拉找回）"
        want = expect.get(email, "?")
        good = state.startswith(want)
        passed += good
        total += 1
        print(f"  {'✓' if good else '✗'} {email:26s} {state}（期望 {want}）")

    print(f"\n状态推对 {passed}/{total}")
    print("夹具覆盖 投递/二维码已发/已进群：", "是 ✓" if passed == total else "否 ✗")
    print(f"CLI 层对齐 {cli_same}/{cli_total}")
    return 0 if (passed == total and cli_same == cli_total) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""vc 域：``+search`` 列会议、``meeting get`` 读会议详情。

夹具（tests/fixtures/vc/）：

    search-<participant_id>.json   {"items": [{meeting_id, topic, start_time, end_time, …}], "has_more": …, "page_token": …}
    meeting-<meeting_id>.json      {"meeting": {meeting_id, topic, participants: [...]}}

真 CLI 的会议详情用 ``--with-participants true`` 才带参会人；mock 一律带，
因为「参会人名单」正是能力层要的东西（对齐 export_chat_data.py 的调用）。
"""

from __future__ import annotations

from . import fixtures
from .envelope import Result, usage_error


def search(flags: dict) -> Result:
    raw = flags.get("participant-ids") or flags.get("participant-id")
    if not raw:
        usage_error('required flag(s) "participant-ids" not set', param="--participant-ids")
    who = raw.split(",")[0].strip()
    payload = fixtures.read_json("vc", f"search-{who}.json")
    items, has_more, token = fixtures.page_of(
        payload.get("items") or [], flags.get("page-token"), flags.get("page-size") or 30)

    data = {"items": items, "has_more": has_more, "page_token": token}
    lines = ["meeting_id\ttopic\tstart_time"]
    lines += [f"{i.get('meeting_id','')}\t{i.get('topic','')}\t{i.get('start_time','')}"
              for i in items]
    return Result(data, table="\n".join(lines))


def meeting_get(flags: dict) -> Result:
    mid = flags.get("meeting-id")
    if not mid:
        usage_error('required flag(s) "meeting-id" not set', param="--meeting-id")
    payload = fixtures.read_json("vc", f"meeting-{mid}.json")
    return Result(payload)

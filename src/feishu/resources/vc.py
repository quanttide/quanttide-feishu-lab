"""vc 域：会议搜索与单场会议详情，两个动作。

    vc_meeting_search    vc +search --as user        按参与人 + 时间范围找会议
    vc_meeting_get       vc meeting get              按会议 id 取详情（带参会人）
"""

from __future__ import annotations

from .action import Action

RESOURCE = "vc"

ACTIONS: dict[str, Action] = {
    "vc_meeting_search": Action(
        command=("vc", "+search", "--as", "user"), landed="meeting-search",
        needs_any=("participant_id",),
        params={"participant_id": "--participant-ids", "start": "--start", "end": "--end",
                "page_size": "--page-size", "page_token": "--page-token"},
    ),
    "vc_meeting_get": Action(
        command=("vc", "meeting", "get", "--with-participants", "true"), landed="meeting-get",
        params={"meeting_id": "--meeting-id"},
    ),
}

"""task 域：一条动作三种取法——我负责 / 与我相关 / 清单。

    task_list(scope="mine")        task +get-my-tasks --page-all
    task_list(scope="related")     task +get-related-tasks --page-all
    task_list(scope="tasklists")   task tasklists list --as user --page-all

命令段与落盘目录都按 scope 分（``raw/task/mine/…``）；``complete`` 是文字 true/false 而非 flag。
"""

from __future__ import annotations

from .action import Action

RESOURCE = "task"

ACTIONS: dict[str, Action] = {
    "task_list": Action(
        command=("task",), landed="mine", variant_param="scope",
        variants={"mine": (("task", "+get-my-tasks", "--page-all"), "mine"),
                  "related": (("task", "+get-related-tasks", "--page-all"), "related"),
                  "tasklists": (("task", "tasklists", "list", "--as", "user", "--page-all"),
                                "tasklists")},
        params={"complete": lambda v: ["--complete", "true" if v else "false"],
                "page_token": "--page-token"},
    ),
}

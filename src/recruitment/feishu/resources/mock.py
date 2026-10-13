"""资源层夹具实现：把 lark-cli 换成**同进程的假 CLI**。

它不自己造负载，也不另写一套取数逻辑：拼 argv 用与真实现同一张表（``actions.py``），
跑的是同一个假平台（``packages/mock``），落盘是同一个 ``RawStore``。与真实现的唯一差别
是"子进程"换成"同进程调用"——不 fork，跑得快，且不依赖 PATH。

负载长什么样因此只有一处来源（假 lark-cli 的 handler）；改坏形状由
``tests/fixtures/snapshots/resources.json``（录制负载）与冒烟脚本发现。
"""

from __future__ import annotations

import contextlib
import json
import io
import os
import sys
from pathlib import Path

from .real import CLIResources

# 假 lark-cli 在 packages/mock 里，与 src 是两个 PYTHONPATH 根：按本文件位置显式挂上
_MOCK_PKG = Path(__file__).resolve().parents[4] / "packages" / "mock"
if str(_MOCK_PKG) not in sys.path:
    sys.path.insert(0, str(_MOCK_PKG))

from lark_mock import cli as fake_cli  # noqa: E402


class MockResources(CLIResources):
    """资源层契约的夹具实现：同进程假 CLI + 同一套落盘。"""

    def __init__(self, store_root: str | None, fixtures_dir: str) -> None:
        super().__init__(store_root)
        os.environ["LARK_MOCK_FIXTURES"] = str(fixtures_dir)

    def _run(self, *args: str) -> tuple[dict, dict]:
        """跑假 CLI：捕获它的 stdout，按真实现的规矩解信封。"""
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                fake_cli.main(list(args))
        except SystemExit as exc:                      # 假 CLI 用 exit 2 报 validation 错误
            raise RuntimeError(f"lark-cli(假) {' '.join(args)} 失败：{err.getvalue().strip()[:200]}") from exc
        text = out.getvalue()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"lark-cli(假) {' '.join(args)} 输出不是 JSON：{text[:200]}") from None
        return payload.get("data") or {}, payload

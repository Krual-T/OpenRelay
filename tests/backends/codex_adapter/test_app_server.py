from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from openrelay.backends.codex_adapter.app_server import CodexAppServerClient


def make_client(tmp_path: Path) -> CodexAppServerClient:
    return CodexAppServerClient(
        codex_path="codex",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "sqlite",
        model="gpt-test",
        safety_mode="workspace-write",
    )


@pytest.mark.asyncio
async def test_stdout_reader_accepts_large_jsonrpc_line(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    reader = asyncio.StreamReader()
    large_text = "x" * (1024 * 1024)
    reader.feed_data((f'{{"id":1,"result":{{"text":"{large_text}"}}}}\n').encode())
    reader.feed_eof()
    client.process = SimpleNamespace(stdout=reader)
    future = asyncio.get_running_loop().create_future()
    client.pending_requests[1] = future

    await client._read_stdout()

    assert future.result()["text"] == large_text


@pytest.mark.asyncio
async def test_stdout_reader_failure_fails_pending_requests(tmp_path: Path) -> None:
    class BrokenStdout:
        async def read(self, _limit: int) -> bytes:
            raise ValueError("broken stdout")

        async def readline(self) -> bytes:
            raise ValueError("broken stdout")

    class FakeProcess:
        stdout = BrokenStdout()
        stdin = None

        def terminate(self) -> None:
            return

        async def wait(self) -> int:
            return 1

    client = make_client(tmp_path)
    client.process = FakeProcess()
    future = asyncio.get_running_loop().create_future()
    client.pending_requests[1] = future

    await client._read_stdout()

    assert future.done()
    with pytest.raises(RuntimeError, match="stdout reader failed"):
        future.result()

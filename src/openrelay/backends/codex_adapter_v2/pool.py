"""
ConnectionPool — Codex CLI 子进程连接池。

管理 v2 session 的生命周期：
- 上限通过 CODEX_MAX_CONNECTIONS 环境变量配置（默认 5）
- LRU 淘汰：按最后活动时间排序，池满时淘汰最旧空闲连接
- 定期回收：空闲超过 CODEX_IDLE_TIMEOUT 秒（默认 600）自动关闭
- 池满且全部活跃 → 返回 PoolFullError
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .session import CodexV2Session

LOGGER = logging.getLogger("openrelay.backends.codex_adapter_v2.pool")

DEFAULT_MAX_CONNECTIONS = 5
DEFAULT_IDLE_TIMEOUT = 600.0  # 10 分钟
CLEANUP_INTERVAL = 60.0  # 每分钟检查一次


class PoolFullError(Exception):
    """连接池已满且所有连接都在活跃 turn 中。"""


@dataclass(slots=True)
class _PoolEntry:
    session: CodexV2Session
    thread_id: str
    last_active_at: float = 0.0


@dataclass(slots=True)
class ConnectionPool:
    """Codex CLI 连接池。"""

    max_size: int = DEFAULT_MAX_CONNECTIONS
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT
    _entries: dict[str, _PoolEntry] = field(default_factory=dict)
    _cleanup_task: asyncio.Task[None] | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @classmethod
    def from_env(cls) -> ConnectionPool:
        """从环境变量构建连接池。"""
        max_size = int(os.environ.get("CODEX_MAX_CONNECTIONS", str(DEFAULT_MAX_CONNECTIONS)))
        idle_timeout = float(os.environ.get("CODEX_IDLE_TIMEOUT", str(DEFAULT_IDLE_TIMEOUT)))
        return cls(max_size=max_size, idle_timeout=idle_timeout)

    async def get_or_create(
        self,
        thread_id: str,
        *,
        codex_path: str,
        workspace_root: Path,
        model: str = "",
        safety_mode: str = "workspace-write",
        sqlite_home: Path | None = None,
    ) -> CodexV2Session:
        """获取或创建 session。

        1. 如果 thread_id 已在池中 → 更新 last_active_at，返回现有 session
        2. 如果池未满 → 创建新 session
        3. 如果池已满 → 淘汰最旧空闲连接，创建新 session
        4. 如果全部活跃 → raise PoolFullError
        """
        async with self._lock:
            # 1. 已存在 → 复用
            if thread_id in self._entries:
                entry = self._entries[thread_id]
                entry.last_active_at = time.monotonic()
                entry.session.client.touch()
                self._ensure_cleanup()
                return entry.session

            # 2. 池未满 → 创建
            if len(self._entries) < self.max_size:
                return await self._create_and_add(
                    thread_id,
                    codex_path=codex_path,
                    workspace_root=workspace_root,
                    model=model,
                    safety_mode=safety_mode,
                    sqlite_home=sqlite_home,
                )

            # 3. 池已满 → 找空闲连接淘汰
            idle_entries = [
                entry
                for entry in self._entries.values()
                if not entry.session.is_running
            ]
            if idle_entries:
                idle_entries.sort(key=lambda e: e.last_active_at)
                victim = idle_entries[0]
                LOGGER.info(
                    "pool full evicting idle thread_id=%s last_active=%.0fs ago",
                    victim.thread_id,
                    time.monotonic() - victim.last_active_at,
                )
                await self._remove(victim.thread_id)
                return await self._create_and_add(
                    thread_id,
                    codex_path=codex_path,
                    workspace_root=workspace_root,
                    model=model,
                    safety_mode=safety_mode,
                    sqlite_home=sqlite_home,
                )

            # 4. 全部活跃
            raise PoolFullError(
                f"connection pool full ({len(self._entries)}/{self.max_size}), "
                f"all connections have active turns"
            )

    async def remove(self, thread_id: str) -> None:
        """主动移除并关闭一个连接。"""
        async with self._lock:
            await self._remove(thread_id)

    async def touch(self, thread_id: str) -> None:
        """更新连接的活动时间。"""
        entry = self._entries.get(thread_id)
        if entry is not None:
            entry.last_active_at = time.monotonic()
            entry.session.client.touch()

    async def shutdown(self) -> None:
        """关闭所有连接，停止清理任务。"""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        async with self._lock:
            for thread_id in list(self._entries):
                await self._remove(thread_id)

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def active_count(self) -> int:
        return sum(1 for e in self._entries.values() if e.session.is_running)

    # ---- internal ----

    async def _create_and_add(
        self,
        thread_id: str,
        *,
        codex_path: str,
        workspace_root: Path,
        model: str,
        safety_mode: str,
        sqlite_home: Path | None,
    ) -> CodexV2Session:
        session = await CodexV2Session.create(
            codex_path=codex_path,
            workspace_root=workspace_root,
            model=model,
            safety_mode=safety_mode,
            sqlite_home=sqlite_home,
        )
        # 使用 server 返回的真实 thread_id
        actual_id = session.thread_id or thread_id
        self._entries[actual_id] = _PoolEntry(
            session=session,
            thread_id=actual_id,
            last_active_at=time.monotonic(),
        )
        self._ensure_cleanup()
        LOGGER.info("pool added thread_id=%s size=%s", actual_id, len(self._entries))
        return session

    async def _remove(self, thread_id: str) -> None:
        entry = self._entries.pop(thread_id, None)
        if entry is None:
            return
        try:
            await entry.session.shutdown()
        except Exception:
            LOGGER.exception("pool removal shutdown failed thread_id=%s", thread_id)
        LOGGER.info("pool removed thread_id=%s size=%s", thread_id, len(self._entries))

    def _ensure_cleanup(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_idle())

    async def _cleanup_idle(self) -> None:
        """定期扫描并回收空闲超时的连接。"""
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL)
            now = time.monotonic()
            async with self._lock:
                to_remove: list[str] = []
                for thread_id, entry in self._entries.items():
                    if not entry.session.is_running and (now - entry.last_active_at) > self.idle_timeout:
                        to_remove.append(thread_id)
                for thread_id in to_remove:
                    LOGGER.info(
                        "pool idle cleanup thread_id=%s idle=%.0fs",
                        thread_id,
                        now - self._entries[thread_id].last_active_at,
                    )
                    await self._remove(thread_id)
                if not self._entries:
                    self._cleanup_task = None
                    return

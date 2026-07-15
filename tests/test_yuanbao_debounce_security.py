"""Security bounds for Yuanbao inbound debounce buffering."""

from __future__ import annotations

import asyncio

import pytest

from gateway.platforms.yuanbao import ConnectionManager


class _Pipeline:
    def __init__(self) -> None:
        self.frames: list[list[bytes]] = []

    async def execute(self, ctx) -> None:
        self.frames.append(ctx.raw_frames)


class _Adapter:
    name = "yuanbao-test"

    def __init__(self) -> None:
        self._inbound_pipeline = _Pipeline()
        self.tasks: list[asyncio.Task] = []

    def _track_task(self, task: asyncio.Task) -> None:
        self.tasks.append(task)


async def _settle(adapter: _Adapter) -> None:
    if adapter.tasks:
        await asyncio.gather(*adapter.tasks)


@pytest.mark.asyncio
async def test_frame_limit_flushes_before_buffer_can_grow_unbounded() -> None:
    adapter = _Adapter()
    manager = ConnectionManager(adapter)
    manager._extract_sender_key = lambda _raw: "sender"  # type: ignore[method-assign]
    manager._DEBOUNCE_MAX_FRAMES_PER_KEY = 2

    manager._push_to_inbound(b"one")
    manager._push_to_inbound(b"two")
    manager._push_to_inbound(b"three")
    await _settle(adapter)

    assert adapter._inbound_pipeline.frames == [[b"one", b"two"]]
    assert manager._inbound_buffer["sender"] == [b"three"]
    manager._flush_inbound_buffer("sender")
    await _settle(adapter)


@pytest.mark.asyncio
async def test_byte_limit_flushes_existing_frames() -> None:
    adapter = _Adapter()
    manager = ConnectionManager(adapter)
    manager._extract_sender_key = lambda _raw: "sender"  # type: ignore[method-assign]
    manager._DEBOUNCE_MAX_BYTES_PER_KEY = 5

    manager._push_to_inbound(b"1234")
    manager._push_to_inbound(b"56")
    await _settle(adapter)

    assert adapter._inbound_pipeline.frames == [[b"1234"]]
    assert manager._inbound_bytes["sender"] == 2
    manager._flush_inbound_buffer("sender")
    await _settle(adapter)


@pytest.mark.asyncio
async def test_key_limit_flushes_oldest_sender() -> None:
    adapter = _Adapter()
    manager = ConnectionManager(adapter)
    manager._extract_sender_key = lambda raw: raw.decode()  # type: ignore[method-assign]
    manager._DEBOUNCE_MAX_KEYS = 2

    manager._push_to_inbound(b"a")
    manager._push_to_inbound(b"b")
    manager._push_to_inbound(b"c")
    await _settle(adapter)

    assert adapter._inbound_pipeline.frames == [[b"a"]]
    assert set(manager._inbound_buffer) == {"b", "c"}
    manager._flush_inbound_buffer("b")
    manager._flush_inbound_buffer("c")
    await _settle(adapter)


@pytest.mark.asyncio
async def test_timer_deadline_is_capped_by_maximum_age() -> None:
    adapter = _Adapter()
    manager = ConnectionManager(adapter)
    manager._extract_sender_key = lambda _raw: "sender"  # type: ignore[method-assign]
    manager._DEBOUNCE_WINDOW = 60.0
    manager._DEBOUNCE_MAX_AGE = 0.05

    manager._push_to_inbound(b"one")
    first_seen = manager._inbound_first_seen["sender"]
    timer = manager._inbound_timers["sender"]

    assert timer.when() <= first_seen + manager._DEBOUNCE_MAX_AGE + 0.01
    manager._flush_inbound_buffer("sender")
    await _settle(adapter)

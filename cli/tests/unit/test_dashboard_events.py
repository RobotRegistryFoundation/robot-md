from __future__ import annotations

import asyncio
import gzip
import json
import os
import time
from pathlib import Path

import pytest

from robot_md.dashboard.events import Event, EventLog, EventPublisher


def _event(kind="heartbeat", data=None, ts=None) -> Event:
    return Event(kind=kind, ts=ts or time.time(), data=data or {"joints": {"shoulder_pan": 2048}})


def test_event_jsonl_roundtrip_all_kinds():
    kinds = ["heartbeat", "tool.call", "tool.result", "estop.set", "estop.cleared", "frame"]
    for k in kinds:
        e = _event(kind=k, data={"x": 1, "y": [2, 3]})
        line = e.to_jsonl()
        assert line.endswith("\n")
        e2 = Event.from_jsonl(line)
        assert e2.kind == e.kind
        assert e2.ts == e.ts
        assert e2.data == e.data


def test_publisher_writes_jsonl(tmp_path):
    p = tmp_path / "events.jsonl"
    pub = EventPublisher(jsonl_path=p, ws_port=None)
    pub.start()
    try:
        pub.publish("heartbeat", {"joints": {"shoulder_pan": 2048}, "estop": False})
        pub.publish("estop.set", {"set": True})
        time.sleep(0.2)
    finally:
        pub.stop()
    lines = p.read_text().splitlines()
    assert len(lines) == 2
    e0 = Event.from_jsonl(lines[0] + "\n")
    assert e0.kind == "heartbeat"
    assert e0.data["estop"] is False


def test_publisher_no_ws_still_writes_jsonl(tmp_path):
    p = tmp_path / "events.jsonl"
    pub = EventPublisher(jsonl_path=p, ws_port=None)
    pub.start()
    try:
        pub.publish("heartbeat", {})
        time.sleep(0.2)
    finally:
        pub.stop()
    assert p.exists()
    assert len(p.read_text().splitlines()) == 1


def test_publisher_rotates_at_size_limit(tmp_path, monkeypatch):
    p = tmp_path / "events.jsonl"
    monkeypatch.setattr("robot_md.dashboard.events.ROTATE_BYTES", 1024)
    pub = EventPublisher(jsonl_path=p, ws_port=None)
    pub.start()
    try:
        big_data = {"x": "a" * 200}
        for _ in range(20):
            pub.publish("heartbeat", big_data)
        time.sleep(0.5)
    finally:
        pub.stop()
    rotated = tmp_path / "events.1.jsonl.gz"
    assert rotated.exists(), f"expected rotation, saw: {list(tmp_path.iterdir())}"
    with gzip.open(rotated, "rt") as f:
        assert any("heartbeat" in line for line in f)


def test_publisher_frame_rate_limit(tmp_path, monkeypatch):
    p = tmp_path / "events.jsonl"
    monkeypatch.setattr("robot_md.dashboard.events.FRAME_MIN_INTERVAL_S", 0.5)
    pub = EventPublisher(jsonl_path=p, ws_port=None)
    pub.start()
    try:
        for _ in range(5):
            pub.publish("frame", {"png_b64": "xxx", "width": 1, "height": 1})
        time.sleep(0.2)
    finally:
        pub.stop()
    lines = p.read_text().splitlines()
    assert len([l for l in lines if '"kind": "frame"' in l]) == 1


def test_publisher_non_frame_not_rate_limited(tmp_path):
    p = tmp_path / "events.jsonl"
    pub = EventPublisher(jsonl_path=p, ws_port=None)
    pub.start()
    try:
        for _ in range(5):
            pub.publish("heartbeat", {"joints": {}})
        time.sleep(0.2)
    finally:
        pub.stop()
    lines = p.read_text().splitlines()
    assert len(lines) == 5


@pytest.mark.asyncio
async def test_eventlog_snapshot_reads_last_n(tmp_path):
    p = tmp_path / "events.jsonl"
    with p.open("w") as f:
        for i in range(10):
            f.write(Event(kind="heartbeat", ts=float(i), data={"i": i}).to_jsonl())
    log = EventLog(jsonl_path=p, ws_url=None)
    snap = await log.snapshot(n=5)
    assert len(snap) == 5
    assert [e.data["i"] for e in snap] == [5, 6, 7, 8, 9]


@pytest.mark.asyncio
async def test_eventlog_snapshot_crosses_rotation(tmp_path):
    p = tmp_path / "events.jsonl"
    rotated = tmp_path / "events.1.jsonl.gz"
    with gzip.open(rotated, "wt") as f:
        for i in range(10):
            f.write(Event(kind="heartbeat", ts=float(i), data={"i": i}).to_jsonl())
    with p.open("w") as f:
        for i in range(10, 15):
            f.write(Event(kind="heartbeat", ts=float(i), data={"i": i}).to_jsonl())
    log = EventLog(jsonl_path=p, ws_url=None)
    snap = await log.snapshot(n=12)
    assert [e.data["i"] for e in snap] == [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]


@pytest.mark.asyncio
async def test_eventlog_tail_yields_live(tmp_path):
    p = tmp_path / "events.jsonl"
    pub = EventPublisher(jsonl_path=p, ws_port=None)
    pub.start()
    log = EventLog(jsonl_path=p, ws_url=None, poll_interval_s=0.05)
    received: list[Event] = []

    async def collect():
        async for e in log.tail():
            received.append(e)
            if len(received) >= 3:
                return

    task = asyncio.create_task(collect())
    try:
        await asyncio.sleep(0.1)
        pub.publish("heartbeat", {"i": 0})
        pub.publish("heartbeat", {"i": 1})
        pub.publish("heartbeat", {"i": 2})
        await asyncio.wait_for(task, timeout=3.0)
    finally:
        pub.stop()
    assert len(received) == 3
    assert received[0].data["i"] == 0


def test_publisher_survives_slow_ws_client(tmp_path):
    """If a WS client is slow, publish() must not block; events still land in JSONL."""
    p = tmp_path / "events.jsonl"
    pub = EventPublisher(jsonl_path=p, ws_port=0)  # port 0 → OS picks
    pub.start()
    try:
        t0 = time.time()
        for _ in range(50):
            pub.publish("heartbeat", {"j": 1})
        dt = time.time() - t0
        time.sleep(0.2)
    finally:
        pub.stop()
    assert dt < 1.0, f"publish blocked: {dt:.2f}s"
    assert len(p.read_text().splitlines()) == 50

# SP-AN — Hot-Plug Announce + Confirm Surfaces Implementation Plan (v1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship SP-AN v1 — the operator-facing announce + confirm layer over SP-HP's queue. v1 has two surfaces only: (a) Claude chat, driven by `notifications/resources/updated` for the new `robot-md://hotplug/pending` MCP resource + skill-text in `using-robot-md.SKILL.md` that turns those updates into announce / review / confirm flows, and (b) audio onboarding via Claude's existing voice mode (no new TTS code). **Pendant integration is deferred to SP-AN v2** — v1's queue contract (resolution race semantics: pending → resolved (bind|reject|expired), single writer = daemon, first-acting channel wins) is shape-correct so v2 plugs in without queue-shape changes.

**Architecture:** SP-AN ships as additions to existing components — no new long-running processes. The MCP server gains one resource (`robot-md://hotplug/pending`) emitting `notifications/resources/updated` whenever SP-HP's daemon nudges the socket or the file-poll detects a queue change. Skill-text additions to the canonical `using-robot-md.SKILL.md` (per SP1 simplification-revisions Revision 7: edited only in `~/robot-md-mcp/skills/using-robot-md/SKILL.md`; sync script propagates to `cli/src/robot_md/skills/using-robot-md.SKILL.md`) instruct Claude on the announce-on-HIGH, surface-on-MEDIUM, undo-within-30s, and resolved-elsewhere flows. A sandboxed Claude harness exercises the skill-text contracts without a live model.

**Tech Stack:** Python 3.10+, FastMCP (`mcp.server.fastmcp`), the existing `using-robot-md` skill text infrastructure + sync script (Revision 7), `pytest`, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-27-sp-an-announce-confirm-design.md`

**Depends on:** SP-HP — the queue + daemon socket + manifest merge live there. SP-AN consumes them read-only via the resource + writes resolution records via `hotplug_confirm` (defined in SP-HP).

---

## File Structure

**MCP-server-side resource:**
- `cli/src/robot_md/mcp/resources/__init__.py` — NEW (only if the directory doesn't already exist).
- `cli/src/robot_md/mcp/resources/hotplug_pending.py` — NEW. Reads pending records from `EventQueue`; surfaces them as a single resource document. Emits `notifications/resources/updated` on subscribed clients when the daemon's socket nudge fires (Linux) or when the periodic file-poll detects a queue change (macOS / Windows).
- `cli/src/robot_md/mcp/server.py` — MODIFY. Register the resource + wire the socket subscriber + start the file-poll fallback timer.
- `cli/src/robot_md/mcp/resource_subscribers.py` — NEW. Tracks subscribed clients, emits `notifications/resources/updated`.

**Skill text:**
- `~/robot-md-mcp/skills/using-robot-md/SKILL.md` (canonical, lives in the npm-published mcp-server repo) — MODIFY. Add three new sections: "Reacting to hot-plug events", "Modality hierarchy", "Resolved-elsewhere handling".
- `cli/src/robot_md/skills/using-robot-md.SKILL.md` (CLI-shipped mirror) — REGENERATED via the sync script.
- `cli/scripts/sync-skill.sh` (or wherever the existing Revision 7 sync script lives) — VERIFY it still copies cleanly after the additions.

**Sandboxed harness tests:**
- `cli/tests/hotplug_an/__init__.py` — NEW.
- `cli/tests/hotplug_an/conftest.py` — NEW. Skill-text fixture loader.
- `cli/tests/hotplug_an/test_skill_announce_high_tier_in_voice_mode.py` — NEW.
- `cli/tests/hotplug_an/test_skill_undo_within_window_calls_reject.py` — NEW.
- `cli/tests/hotplug_an/test_skill_undo_after_window_warns_manifest_bound.py` — NEW.
- `cli/tests/hotplug_an/test_skill_medium_tier_surfaces_alternatives.py` — NEW.
- `cli/tests/hotplug_an/test_skill_resolved_elsewhere_acknowledges.py` — NEW.

**Resource subscription tests:**
- `cli/tests/hotplug_an/test_hotplug_pending_resource_lists_pending.py` — NEW.
- `cli/tests/hotplug_an/test_hotplug_pending_resource_emits_updated_on_nudge.py` — NEW.
- `cli/tests/hotplug_an/test_hotplug_pending_resource_emits_updated_on_file_poll.py` — NEW.
- `cli/tests/hotplug_an/test_hotplug_pending_resource_subscribers_only_get_changes.py` — NEW.

**Manual smoke checklist:**
- `cli/tests/manual/span_smoke.md` — NEW.

**Documentation (called out as v1 limitation):**
- `cli/docs/hotplug-roadmap.md` — NEW. Single page listing v2 follow-ups (pendant surface, web UI, manifest unbind tool, persistent operator preferences).

---

## Phase A — `robot-md://hotplug/pending` resource

### Task 1: Resource read returns pending events from `EventQueue`

**Files:**
- Create: `cli/src/robot_md/mcp/resources/__init__.py`, `cli/src/robot_md/mcp/resources/hotplug_pending.py`
- Test: `cli/tests/hotplug_an/test_hotplug_pending_resource_lists_pending.py`

- [ ] **Step 1: Inspect existing resource patterns**

```bash
grep -rn "@server.resource\|server.resource(" cli/src/robot_md/mcp/ 2>/dev/null | head -10
```

Note the existing FastMCP resource registration pattern. Match it.

- [ ] **Step 2: Write the resource-read test**

```python
# cli/tests/hotplug_an/test_hotplug_pending_resource_lists_pending.py
from __future__ import annotations

import json
from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue
from robot_md.mcp.resources.hotplug_pending import build_pending_payload


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_payload_lists_only_pending_events(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    p1 = q.append_pending(_evt(), Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None))
    p2 = q.append_pending(_evt(), Decision(tier="LOW", unambiguous=False, bind_proposal=None))
    q.append_resolution(ref_id=p1.id, resolution="bind", by="cli", outcome={})

    payload = build_pending_payload(_queue=q)
    pending_ids = {p["event_id"] for p in payload["pending"]}
    assert p2.id in pending_ids
    assert p1.id not in pending_ids


def test_payload_is_json_serializable(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    q.append_pending(_evt(), Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None))
    payload = build_pending_payload(_queue=q)
    json.dumps(payload)  # must not raise
```

- [ ] **Step 3: Run test (expect FAIL — module missing)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/hotplug_an/test_hotplug_pending_resource_lists_pending.py -v
```

- [ ] **Step 4: Implement `hotplug_pending.py`**

Create `cli/src/robot_md/mcp/resources/__init__.py`:

```python
"""MCP resources — readable URIs that emit notifications/resources/updated."""
```

Create `cli/src/robot_md/mcp/resources/hotplug_pending.py`:

```python
"""robot-md://hotplug/pending — read-only view over SP-HP's pending events.

Subscribers receive notifications/resources/updated on socket-nudge (Linux)
or file-poll-detected change (macOS / Windows).
"""

from __future__ import annotations

import json

from robot_md.hotplug.queue import EventQueue


URI = "robot-md://hotplug/pending"


def build_pending_payload(*, _queue: EventQueue | None = None) -> dict:
    q = _queue or EventQueue()
    if not q.path.exists():
        return {"pending": []}
    records: list[dict] = []
    for line in q.path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    pending_ids = {r["id"] for r in records if r.get("kind") == "pending"}
    resolved_refs = {r["ref"] for r in records if r.get("kind") == "resolved" and r.get("ref")}

    out = []
    for r in records:
        if r.get("kind") == "pending" and r["id"] in (pending_ids - resolved_refs):
            out.append({
                "event_id": r["id"],
                "tier": r["decision"]["tier"],
                "device": r["event"],
                "decision": r["decision"],
            })
    return {"pending": out}
```

- [ ] **Step 5: Run test (expect PASS 2/2)**

- [ ] **Step 6: Commit (Task 1)**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/mcp/resources/__init__.py cli/src/robot_md/mcp/resources/hotplug_pending.py cli/tests/hotplug_an/test_hotplug_pending_resource_lists_pending.py
git commit -m "$(cat <<'EOF'
feat(span): build_pending_payload — read-only view over SP-HP queue

Filters resolved events out, surfaces only currently-pending records
with tier + device metadata + decision blob. JSON-serializable for the
MCP resource at robot-md://hotplug/pending. Resource registration +
notifications wiring follow in Tasks 2-4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Register the resource on the MCP server + emit on subscribe

**Files:**
- Modify: `cli/src/robot_md/mcp/server.py` (register `@server.resource(URI)`)
- Test: extend `cli/tests/hotplug_an/test_hotplug_pending_resource_lists_pending.py` with a server-roundtrip test, OR add a new `test_hotplug_pending_resource_registered.py`

- [ ] **Step 1: Write the resource-registration test**

```python
# cli/tests/hotplug_an/test_hotplug_pending_resource_registered.py
from __future__ import annotations


def test_resource_uri_appears_in_server_list_resources() -> None:
    from robot_md.mcp.server import server  # adjust to actual symbol
    from robot_md.mcp.resources.hotplug_pending import URI
    resources = list(server.list_resources())
    uris = {r.uri for r in resources}
    assert URI in uris, f"{URI} not registered; got {uris!r}"
```

(If `server.list_resources()` returns differently in this project's FastMCP version, adapt — the goal is to confirm the URI is registered.)

- [ ] **Step 2: Run test (expect FAIL — not registered)**

- [ ] **Step 3: Register in `server.py`**

In `cli/src/robot_md/mcp/server.py`, alongside existing `@server.tool()` registrations, add:

```python
    from robot_md.mcp.resources.hotplug_pending import URI as _HOTPLUG_URI

    @server.resource(_HOTPLUG_URI)
    def hotplug_pending_resource() -> dict:
        """Currently-pending hot-plug events awaiting operator confirmation."""
        from robot_md.mcp.resources.hotplug_pending import build_pending_payload
        return build_pending_payload()
```

- [ ] **Step 4: Run test (expect PASS)**

- [ ] **Step 5: Commit (Task 2)**

```bash
git add cli/src/robot_md/mcp/server.py cli/tests/hotplug_an/test_hotplug_pending_resource_registered.py
git commit -m "feat(span): register robot-md://hotplug/pending MCP resource"
```

---

### Task 3: Emit `notifications/resources/updated` on socket-nudge (Linux)

**Files:**
- Create: `cli/src/robot_md/mcp/resource_subscribers.py`
- Modify: `cli/src/robot_md/mcp/server.py` (start a socket subscriber on connect)
- Test: `cli/tests/hotplug_an/test_hotplug_pending_resource_emits_updated_on_nudge.py`

- [ ] **Step 1: Write the on-nudge test**

```python
# cli/tests/hotplug_an/test_hotplug_pending_resource_emits_updated_on_nudge.py
from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

import pytest

from robot_md.mcp.resource_subscribers import HotplugResourceSubscriber


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Unix socket — Linux primary")


def test_subscriber_emits_updated_on_socket_nudge(tmp_path: Path) -> None:
    received: list = []
    sock_path = tmp_path / "nudge.sock"

    # Pre-bind a fake daemon socket.
    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(str(sock_path))
    server_sock.listen(1)

    subscriber = HotplugResourceSubscriber(
        socket_path=sock_path,
        on_change=lambda: received.append(1),
    )

    async def main():
        await subscriber.start()
        # Connect + send 1-byte nudge.
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(sock_path))
        client.sendall(b"\x01")
        client.close()
        await asyncio.sleep(0.1)
        await subscriber.stop()

    try:
        asyncio.run(main())
    finally:
        server_sock.close()
        sock_path.unlink(missing_ok=True)

    assert received == [1]
```

(Note: this test as written wires the subscriber as a CLIENT of the daemon's socket. Adjust the implementation accordingly — the subscriber connects to the daemon's pre-bound socket and reads incoming nudge bytes.)

- [ ] **Step 2: Implement `resource_subscribers.py`**

```python
# cli/src/robot_md/mcp/resource_subscribers.py
"""Linux-only Unix-socket subscriber for SP-HP daemon nudges.

Connects to /run/user/$UID/robot-md-hotplug.sock and reads nudge bytes;
each byte received triggers on_change().
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Callable

_DEFAULT_PATH = Path(f"/run/user/{os.getuid()}/robot-md-hotplug.sock") if hasattr(os, "getuid") else None


class HotplugResourceSubscriber:
    def __init__(self, *, socket_path: Path | None = None, on_change: Callable[[], None]) -> None:
        self.socket_path = socket_path or _DEFAULT_PATH
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._on_change = on_change

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        if self.socket_path is None or not self.socket_path.exists():
            return
        try:
            reader, writer = await asyncio.open_unix_connection(str(self.socket_path))
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            return
        try:
            while not self._stop.is_set():
                data = await reader.read(1)
                if not data:
                    break
                self._on_change()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
```

- [ ] **Step 3: Wire into `server.py`**

In `cli/src/robot_md/mcp/server.py`, add startup hook (typical FastMCP shape — adapt to project convention):

```python
    # On connect: start the hotplug subscriber. on_change emits
    # notifications/resources/updated for the pending resource.
    @server.on_connect
    async def _start_hotplug_subscriber():
        from robot_md.mcp.resource_subscribers import HotplugResourceSubscriber
        from robot_md.mcp.resources.hotplug_pending import URI as _HOTPLUG_URI

        async def _emit():
            await server.send_resource_updated(_HOTPLUG_URI)

        sub = HotplugResourceSubscriber(on_change=lambda: asyncio.create_task(_emit()))
        await sub.start()
        # Stash on the server context so disconnect can stop it.
        server.state["_hotplug_subscriber"] = sub

    @server.on_disconnect
    async def _stop_hotplug_subscriber():
        sub = server.state.pop("_hotplug_subscriber", None)
        if sub is not None:
            await sub.stop()
```

(`@server.on_connect` / `@server.on_disconnect` / `server.send_resource_updated` are illustrative names matching MCP-spec semantics. Adapt to the actual FastMCP API shipped with this project — if those hooks aren't named that way, look at how the existing `tools/list_changed` notification is emitted on backend reload (Task 17 of SP-HP plan) and follow that pattern.)

- [ ] **Step 4: Run test (expect PASS)**

- [ ] **Step 5: Commit (Task 3)**

```bash
git add cli/src/robot_md/mcp/resource_subscribers.py cli/src/robot_md/mcp/server.py cli/tests/hotplug_an/test_hotplug_pending_resource_emits_updated_on_nudge.py
git commit -m "feat(span): Linux socket subscriber emits notifications/resources/updated"
```

---

### Task 4: File-poll fallback for macOS / Windows + subscriber-only-changes guard

**Files:**
- Modify: `cli/src/robot_md/mcp/resource_subscribers.py` (add `FilePollFallback`)
- Modify: `cli/src/robot_md/mcp/server.py` (start poll on platforms without working socket)
- Test: `cli/tests/hotplug_an/test_hotplug_pending_resource_emits_updated_on_file_poll.py`, `test_hotplug_pending_resource_subscribers_only_get_changes.py`

- [ ] **Step 1: Write the file-poll test**

```python
# cli/tests/hotplug_an/test_hotplug_pending_resource_emits_updated_on_file_poll.py
from __future__ import annotations

import asyncio
from pathlib import Path

from robot_md.mcp.resource_subscribers import FilePollFallback


def test_poll_fires_on_file_mtime_change(tmp_path: Path) -> None:
    queue_path = tmp_path / "q.jsonl"
    queue_path.write_text("")
    received: list = []

    poller = FilePollFallback(queue_path=queue_path, on_change=lambda: received.append(1), interval=0.05)

    async def main():
        await poller.start()
        await asyncio.sleep(0.1)
        # Simulate a daemon write.
        queue_path.write_text('{"id":"evt_1","kind":"pending"}\n')
        await asyncio.sleep(0.2)
        await poller.stop()

    asyncio.run(main())
    assert received, "FilePollFallback did not fire on mtime change"
```

- [ ] **Step 2: Write the no-self-loop test**

```python
# cli/tests/hotplug_an/test_hotplug_pending_resource_subscribers_only_get_changes.py
from __future__ import annotations

import asyncio
from pathlib import Path

from robot_md.mcp.resource_subscribers import FilePollFallback


def test_no_change_no_event(tmp_path: Path) -> None:
    queue_path = tmp_path / "q.jsonl"
    queue_path.write_text("seed\n")
    received: list = []
    poller = FilePollFallback(queue_path=queue_path, on_change=lambda: received.append(1), interval=0.02)

    async def main():
        await poller.start()
        # No writes — poller should NOT fire.
        await asyncio.sleep(0.15)
        await poller.stop()

    asyncio.run(main())
    assert received == []
```

- [ ] **Step 3: Implement `FilePollFallback`**

Append to `cli/src/robot_md/mcp/resource_subscribers.py`:

```python
class FilePollFallback:
    def __init__(self, *, queue_path: Path, on_change: Callable[[], None], interval: float = 2.0) -> None:
        self.queue_path = queue_path
        self._on_change = on_change
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        last_mtime = self._mtime()
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
                return
            except asyncio.TimeoutError:
                pass
            current = self._mtime()
            if current is not None and current != last_mtime:
                last_mtime = current
                self._on_change()

    def _mtime(self) -> float | None:
        try:
            return self.queue_path.stat().st_mtime
        except FileNotFoundError:
            return None
```

Wire into `server.py`'s on-connect handler — start `FilePollFallback` on macOS / Windows (or any platform where the socket subscriber's `_run` returned without binding). Easiest: always start the poller; the socket subscriber is a low-latency optimization on top of it. If both fire on the same change, MCP clients gracefully ignore duplicate `notifications/resources/updated` (the resource is read on demand; the notification is just a hint).

- [ ] **Step 4: Run tests (expect PASS 2/2)**

- [ ] **Step 5: Commit (Task 4)**

```bash
git add cli/src/robot_md/mcp/resource_subscribers.py cli/src/robot_md/mcp/server.py cli/tests/hotplug_an/test_hotplug_pending_resource_emits_updated_on_file_poll.py cli/tests/hotplug_an/test_hotplug_pending_resource_subscribers_only_get_changes.py
git commit -m "feat(span): file-poll fallback for non-Linux + no-spurious-event guard"
```

---

## Phase B — Skill text additions

### Task 5: Add three new sections to `using-robot-md.SKILL.md`

**Files:**
- Modify: `~/robot-md-mcp/skills/using-robot-md/SKILL.md` (canonical) — assume worktree contains a checkout or has the path mounted; if not, write to a draft path here and the implementer copies into the npm repo.
- Modify: `cli/src/robot_md/skills/using-robot-md.SKILL.md` (regenerated mirror).
- Run: existing Revision 7 sync script.
- Test: drift check + content presence.

- [ ] **Step 1: Locate the canonical skill file**

```bash
ls ~/robot-md-mcp/skills/using-robot-md/SKILL.md 2>/dev/null && echo "canonical found"
ls cli/src/robot_md/skills/using-robot-md.SKILL.md 2>/dev/null && echo "mirror found"
```

If the canonical npm-side repo isn't checked out alongside this worktree, the implementer either (a) clones it adjacent and proceeds, or (b) edits the CLI-mirror directly and files a follow-up PR against the npm repo to sync. Either path: the new sections eventually live in the canonical file per Revision 7.

- [ ] **Step 2: Write the content-presence test**

```python
# cli/tests/hotplug_an/test_skill_text_has_hotplug_sections.py
from __future__ import annotations

from pathlib import Path


_MIRROR = Path(__file__).parents[2] / "src" / "robot_md" / "skills" / "using-robot-md.SKILL.md"


def test_mirror_contains_three_new_sections() -> None:
    text = _MIRROR.read_text()
    assert "## Reacting to hot-plug events" in text
    assert "## Modality hierarchy" in text
    assert "## Resolved-elsewhere handling" in text


def test_mirror_announces_30s_undo_window() -> None:
    text = _MIRROR.read_text()
    assert "30 s" in text or "30 seconds" in text


def test_mirror_describes_hotplug_review_and_confirm_calls() -> None:
    text = _MIRROR.read_text()
    assert "hotplug_review" in text
    assert "hotplug_confirm" in text
```

- [ ] **Step 3: Run test (expect FAIL — sections missing)**

- [ ] **Step 4: Add the three sections**

Edit the canonical `using-robot-md.SKILL.md` (or, in the fallback path, the mirror). Append:

```markdown
## Reacting to hot-plug events

The MCP server emits `notifications/resources/updated` for
`robot-md://hotplug/pending` whenever new hardware is detected.

When you receive that notification:

1. Call `hotplug_review`.
2. For HIGH-tier events that already resolved (`bind`):
   - **Announce to the operator** — say or write:
     "Found a {preset_name} on {port}. I bound it as the {driver_id} driver
      using the {backend_name} backend. Say 'undo' to reject."
   - If the operator says undo / reject within 30 s of the announce,
     call `hotplug_confirm({event_id}, "reject")`. The daemon will append
     a rejection record; the manifest stays bound but the audit trail
     captures the operator's intent. (Manifest unbinding is out of scope
     for v1 — call this out and offer to help edit ROBOT.md by hand.)
3. For MEDIUM/LOW-tier pending events:
   - Surface the event with its alternatives.
   - Ask the operator: "Want me to bind this as {top_candidate}, pick
     a different option, or reject?"
   - Call `hotplug_confirm` with their answer.

## Modality hierarchy

If the operator is in voice mode, **announce by voice first**, then mirror
the same text to the chat. If the operator is in text mode, write to the
chat only.

## Resolved-elsewhere handling

If you call `hotplug_confirm` and get back `already_resolved`, the
operator confirmed it via another path (e.g., `robot-md hotplug confirm`
from a terminal, or — in the future — a pendant). Tell them you saw it
("Got it — I see {decision} happened from the terminal.") and move on.
```

- [ ] **Step 5: Run the existing Revision 7 sync script**

```bash
# Whatever the existing invocation is — examples:
~/robot-md/scripts/sync-skill.sh
# OR
bash cli/scripts/sync-skill.sh
```

If the script doesn't exist (drift since SP1): file a follow-up to add it, but for v1 hand-copy the canonical content into the mirror.

- [ ] **Step 6: Run tests (expect PASS 3/3)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/hotplug_an/test_skill_text_has_hotplug_sections.py -v
```

- [ ] **Step 7: Commit (Task 5)**

```bash
git add cli/src/robot_md/skills/using-robot-md.SKILL.md cli/tests/hotplug_an/test_skill_text_has_hotplug_sections.py
# If editing the npm-side repo, that commit lands separately.
git commit -m "$(cat <<'EOF'
docs(span): skill-text additions for hot-plug announce + confirm

Three new sections in using-robot-md.SKILL.md:
  1. Reacting to hot-plug events — review on resource update; announce
     HIGH-tier auto-binds; surface MEDIUM/LOW alternatives; pass operator
     answers to hotplug_confirm.
  2. Modality hierarchy — voice-first when operator is in voice mode;
     text-only otherwise.
  3. Resolved-elsewhere handling — acknowledge already_resolved cleanly.

Per simplification-revisions Rev 7, the canonical file is
~/robot-md-mcp/skills/using-robot-md/SKILL.md; the CLI mirror in
cli/src/robot_md/skills/ is regenerated by the existing sync script.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase C — Sandboxed Claude harness tests

These tests don't call a live model. They simulate the MCP-side message flow that a Claude session experiences (resource update, tool calls, tool responses) and assert the skill-text contract — i.e., that "given resource X arrives in state Y, the next operator-visible action is Z." The harness is a small Python helper that loads the skill text + scripts the conversation deterministically.

### Task 6: Skill-text harness fixture

**Files:**
- Create: `cli/tests/hotplug_an/conftest.py`

- [ ] **Step 1: Create the harness fixture**

```python
# cli/tests/hotplug_an/conftest.py
"""Sandboxed harness for skill-text contract tests.

Provides a SkillTextHarness that loads the canonical SKILL.md, exposes
helpers to assert the operator-visible behavior given a fixed sequence
of MCP messages, and simulates 'voice mode' / 'text mode' rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_SKILL_PATH = Path(__file__).parents[2] / "src" / "robot_md" / "skills" / "using-robot-md.SKILL.md"


@dataclass
class HarnessTranscript:
    voice_lines: list[str] = field(default_factory=list)
    text_lines: list[str] = field(default_factory=list)
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)


@dataclass
class SkillTextHarness:
    """Minimal contract-checker. Tests inspect the skill text + assert that
    rules described in it are present (regex-level checks). For full
    end-to-end behavior a live model is required; that is the manual
    smoke step in Task 12."""
    skill_text: str

    def has_rule(self, *substrings: str) -> bool:
        return all(s in self.skill_text for s in substrings)


@pytest.fixture
def harness() -> SkillTextHarness:
    return SkillTextHarness(skill_text=_SKILL_PATH.read_text())
```

- [ ] **Step 2: Commit (Task 6)**

```bash
git add cli/tests/hotplug_an/__init__.py cli/tests/hotplug_an/conftest.py
git commit -m "feat(span): skill-text harness fixture"
```

---

### Task 7: Announce-HIGH-in-voice-mode contract

**Files:**
- Test: `cli/tests/hotplug_an/test_skill_announce_high_tier_in_voice_mode.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/hotplug_an/test_skill_announce_high_tier_in_voice_mode.py
from __future__ import annotations


def test_skill_text_describes_high_tier_announce(harness) -> None:
    assert harness.has_rule(
        "HIGH-tier events that already resolved",
        'I bound it as the {driver_id} driver',
        "Say 'undo' to reject",
    )


def test_skill_text_announces_voice_first(harness) -> None:
    assert harness.has_rule(
        "voice mode",
        "announce by voice first",
        "mirror the same text to the chat",
    )
```

- [ ] **Step 2: Run test (expect PASS — Task 5 already added the content)**

- [ ] **Step 3: Commit (Task 7)**

```bash
git add cli/tests/hotplug_an/test_skill_announce_high_tier_in_voice_mode.py
git commit -m "test(span): lock skill-text HIGH-tier voice-announce contract"
```

---

### Task 8: Undo-within-30s contract

**Files:**
- Test: `cli/tests/hotplug_an/test_skill_undo_within_window_calls_reject.py`, `test_skill_undo_after_window_warns_manifest_bound.py`

- [ ] **Step 1: Write both undo tests**

```python
# cli/tests/hotplug_an/test_skill_undo_within_window_calls_reject.py
from __future__ import annotations


def test_skill_text_pulls_undo_through_to_hotplug_confirm_reject(harness) -> None:
    assert harness.has_rule(
        "operator says undo",
        'hotplug_confirm({event_id}, "reject")',
    )


def test_skill_text_mentions_30s_window(harness) -> None:
    assert harness.has_rule("within 30 s")
```

```python
# cli/tests/hotplug_an/test_skill_undo_after_window_warns_manifest_bound.py
from __future__ import annotations


def test_skill_text_warns_that_manifest_stays_bound(harness) -> None:
    assert harness.has_rule(
        "manifest stays bound",
        "Manifest unbinding is out of scope",
        "help edit ROBOT.md by hand",
    )
```

- [ ] **Step 2: Run tests (expect PASS — Task 5 added content)**

- [ ] **Step 3: Commit (Task 8)**

```bash
git add cli/tests/hotplug_an/test_skill_undo_*.py
git commit -m "test(span): lock skill-text undo / manifest-stays-bound contracts"
```

---

### Task 9: MEDIUM-tier alternatives surfacing

**Files:**
- Test: `cli/tests/hotplug_an/test_skill_medium_tier_surfaces_alternatives.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/hotplug_an/test_skill_medium_tier_surfaces_alternatives.py
from __future__ import annotations


def test_skill_text_describes_medium_tier_alternatives(harness) -> None:
    assert harness.has_rule(
        "MEDIUM/LOW-tier pending events",
        "Surface the event with its alternatives",
        "pick a different option, or reject",
        "Call `hotplug_confirm` with their answer",
    )
```

- [ ] **Step 2: Run test (expect PASS)**

- [ ] **Step 3: Commit (Task 9)**

```bash
git add cli/tests/hotplug_an/test_skill_medium_tier_surfaces_alternatives.py
git commit -m "test(span): lock skill-text MEDIUM-tier alternatives contract"
```

---

### Task 10: Resolved-elsewhere acknowledgement

**Files:**
- Test: `cli/tests/hotplug_an/test_skill_resolved_elsewhere_acknowledges.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/hotplug_an/test_skill_resolved_elsewhere_acknowledges.py
from __future__ import annotations


def test_skill_text_handles_already_resolved(harness) -> None:
    assert harness.has_rule(
        "already_resolved",
        "operator confirmed it via another path",
        "happened from the terminal",
    )
```

- [ ] **Step 2: Run test (expect PASS)**

- [ ] **Step 3: Commit (Task 10)**

```bash
git add cli/tests/hotplug_an/test_skill_resolved_elsewhere_acknowledges.py
git commit -m "test(span): lock skill-text resolved-elsewhere acknowledgement contract"
```

---

## Phase D — Documentation + manual smoke

### Task 11: `cli/docs/hotplug-roadmap.md` — v2 follow-ups

**Files:**
- Create: `cli/docs/hotplug-roadmap.md`

- [ ] **Step 1: Write the roadmap page**

```markdown
# Hot-plug roadmap (v2 and beyond)

SP-AN v1 ships Claude chat + voice-mode audio. The following items are
explicitly deferred and tracked here so v2 work has a starting point:

## v2 — pendant screen surface

- pendant-mcp gains `pendant_set_pending_panel(events)` tool. Skill text
  calls it whenever new pending events appear; pendantd's existing
  status renderer shows a "NEW HARDWARE" panel + Confirm/Reject/Skip
  button bindings.
- pendant-mcp depends on the separate
  `2026-04-25-voice-host-audio-design.md` spec landing first.
- Pendant hardware bring-up must unblock (BOOT button issue).

## v2 — pendant independent subscriber

- pendantd hosts its own Linux Unix-socket subscriber (mirroring the
  MCP server's path). Removes the v1 limitation that pendant requires
  an active Claude session to see real-time events.

## v2 — manifest unbind tool (`hotplug_unbind`)

- Complement to `hotplug_confirm`. Takes an existing driver_id; removes
  it from `drivers[]` after safety checks (no kinematics referencing,
  no in-flight execution).
- Driver-dependency + safety semantics designed during the v2 plan.

## v3+ — web UI surface

- Out of scope for v2; tracked here so the queue contract design choices
  (pending → resolved single-writer, hash-chained) hold the line on what
  surfaces are addable without queue-shape changes.

## v3+ — operator preferences

- Per-RRN `~/.robot-md/hotplug-preferences.toml`: "always confirm even on
  HIGH" / "never bind backend X" / etc. v1 uses SP-HP's tier policy as-is.
```

- [ ] **Step 2: Commit (Task 11)**

```bash
git add cli/docs/hotplug-roadmap.md
git commit -m "docs(span): hotplug v2 roadmap (pendant + unbind tool + web UI + prefs)"
```

---

### Task 12: Manual smoke checklist

**Files:**
- Create: `cli/tests/manual/span_smoke.md`

- [ ] **Step 1: Write the manual smoke**

```markdown
# SP-AN v1 smoke — manual checks on bob

Pre-requisites: SP-HP daemon running. Claude session open in either
voice or text mode. Worktree `pip install -e cli[hardware]` complete.

1. **Voice-mode HIGH-tier auto-bind.** With operator in Claude voice
   mode, replug the SO-ARM101 USB cable on bob. Within 5 s of the plug
   click, Claude announces by voice: "Found an SO-ARM101 on
   /dev/ttyACM0. I bound it as arm_servos using lerobot. Say 'undo' to
   reject." Confirm the announce text appears in chat too.

2. **Voice-mode undo within window.** Same as #1 but the operator says
   "undo" within 30 s. Confirm: a `resolution: reject` record appears
   in `~/.robot-md/hotplug-events.jsonl` for that event_id; the
   manifest still has the driver (manifest unbind is v2).

3. **Voice-mode undo after window.** Same as #1 but the operator says
   "undo" 60 s later. Claude still calls `hotplug_confirm({event_id},
   "reject")`. Claude warns: "the manifest is already bound; want me
   to help unbind by hand?"

4. **Text-mode MEDIUM event.** With operator in text mode (no voice),
   plug a generic CH340 dongle. Claude surfaces the alternatives in
   chat. Operator picks one. Claude passes the choice to
   `hotplug_confirm` with `choice_index`. Manifest gets the driver.

5. **No-Claude-session durability.** Close the Claude session. Plug a
   device. Reopen Claude. The event surfaces in the next interaction
   via the resource update.

6. **Resolved-elsewhere via terminal CLI.** With Claude session open,
   from a separate shell: `robot-md hotplug confirm <event_id> --bind`.
   Claude's next interaction acknowledges: "Got it — I see bind
   happened from the terminal."
```

- [ ] **Step 2: Commit (Task 12)**

```bash
git add cli/tests/manual/span_smoke.md
git commit -m "docs(span): manual smoke checklist (6 items)"
```

---

## Implementation Order Summary

```
Phase A — robot-md://hotplug/pending resource
  1. build_pending_payload — read-only view over EventQueue
  2. Register the resource on the MCP server
  3. Linux socket subscriber emits notifications/resources/updated
  4. File-poll fallback for non-Linux + no-self-loop guard

Phase B — skill text
  5. Three new sections in using-robot-md.SKILL.md (synced canonical → mirror)

Phase C — sandboxed harness contract tests
  6. SkillTextHarness fixture
  7. HIGH-tier voice-announce contract
  8. undo-within / after-window contracts
  9. MEDIUM-tier alternatives contract
 10. resolved-elsewhere acknowledgement contract

Phase D — docs + smoke
 11. cli/docs/hotplug-roadmap.md (v2 follow-ups)
 12. cli/tests/manual/span_smoke.md (6-item checklist)
```

---

## Success Criteria

SP-AN v1 is done when:

- [ ] All 12 tasks merged.
- [ ] `robot-md://hotplug/pending` resource lists pending events; resource updates fire on socket-nudge (Linux) and file-poll (macOS / Windows).
- [ ] Skill-text additions live in the canonical `using-robot-md.SKILL.md` and propagate to the CLI mirror via the existing sync script.
- [ ] All resource-subscription unit tests pass on Linux (the socket-nudge tests skip cleanly on macOS / Windows; file-poll tests run on all three).
- [ ] All skill-text harness tests pass (5/5 contract checks).
- [ ] Manual smoke checklist (`cli/tests/manual/span_smoke.md`) passes 6/6 on bob.
- [ ] `cli/docs/hotplug-roadmap.md` documents the v2 follow-ups (pendant surface, manifest unbind tool, operator preferences) so future SP-AN v2 work has a starting page.
- [ ] Demo dry-run: operator in voice mode, no display attached on bob; replug SO-ARM101; Claude announces the bind audibly within 5 s; operator says "looks good"; conversation continues.

---

## Notes for the implementer

- **No live model required for v1 contract tests.** The skill-text harness in Task 6 is regex-level — it asserts the rules are present in the skill file, not that Claude follows them. Real-model behavior is verified in the manual smoke (Task 12). If your shop has a Claude-powered integration harness (some superpowers projects do), you can extend `SkillTextHarness` to actually drive a model.
- **Canonical / mirror skill-file editing** depends on whether the npm-side `robot-md-mcp` repo is checked out adjacent to this worktree. If yes, edit canonical first, run sync. If no, edit the CLI mirror, file a follow-up PR against the npm repo, and let CI's drift check catch divergence.
- **The Linux socket subscriber connects as a CLIENT to the daemon's pre-bound socket.** Don't bind a second socket from the MCP server — that would conflict with SP-HP's daemon. The socket is one-way: daemon writes 1-byte nudges; subscriber reads them.
- **`server.send_resource_updated(URI)` is illustrative.** The actual FastMCP API may differ; if it does, follow the same pattern the SP-HP plan's `notifications/tools/list_changed` emission uses (Task 17 in SP-HP plan) — those land first and establish the project convention.
- **Each task ends with a commit.** Plan execution is incremental.

# SP-HP — Runtime Hot-Plug Detection Daemon

**Date:** 2026-04-27
**Status:** Design — pending implementation plan
**Sub-project:** Companion to SP3 (not numbered in the SP1-5 sequence)
**Depends on:** SP3 capability-metadata addendum (`Capability`, `describe_capabilities`, `enumerate_capabilities`)
**Paired with:** `2026-04-27-sp-an-announce-confirm-design.md` (operator-facing surfaces)

## Problem

Once SP3 ships, an operator with `robot-md` installed can plug in any vendor's arm and *if they re-run* `robot-md init`, autodetect picks up the change. The "headless auto-onboard" demo moment — *robot reboots, no screen, just audio I/O, and Claude's like "I see a new arm, want me to bind it?"* — does NOT work today. Two specific gaps:

1. **No runtime device watcher.** `robot-md init` only runs when the operator invokes it.
2. **No durable event surface.** Even if `init` ran on every boot, there's no place to queue "I detected an arm, but I need confirmation" so an operator (via Claude, terminal CLI, or — in the future — pendant) can answer it later.

For the Anthropic acquisition demo, the auto-onboard moment is a strong reveal — *it just works the way you'd want a robot to work*. Without SP-HP, that moment requires manual operator intervention (re-run init), which weakens the demo.

## Scope

**In scope:**
- A persistent OS-level service (`robot-md hotplug-daemon`) that watches for USB / serial device hot-plug events, matches them to presets + backends, and emits a durable, hash-chained event stream.
- Cross-platform device detection from v1: Linux (`pyudev`, real-time, <50 ms), macOS (`ioreg` polling + `pyserial.tools.list_ports`, 1–2 s), Windows (`pywin32` `WM_DEVICECHANGE` + polling fallback, 1–2 s).
- Tier-based confirmation policy: HIGH → auto-bind manifest + emit announce event; MEDIUM/LOW → queue `awaiting_confirm` event, no manifest write.
- Durable event queue at `~/.robot-md/hotplug-events.jsonl`, hash-chained for audit.
- Hash-chained per-RRN audit log at `~/.robot-md/audit/<rrn>.jsonl` capturing every bind/queue/reject decision.
- Hybrid daemon ↔ MCP-server communication: files for durable state, optional Linux-only Unix socket at `/run/user/$UID/robot-md-hotplug.sock` for low-latency wake-up nudges. Graceful fallback to file-poll if the socket is unavailable.
- MCP server changes: inotify watch on `ROBOT.md` + manifest reload + `notifications/tools/list_changed` emission; socket subscriber on connect; two new tools (`hotplug_review`, `hotplug_confirm`).
- CLI: `robot-md hotplug-daemon start|stop|status`, `robot-md hotplug review`, `robot-md hotplug confirm`, `robot-md hotplug install-service` (writes systemd user unit on Linux, launchd plist on macOS, scheduled task on Windows).

**Out of scope** (called out as v1 limitations or follow-ups):
- **Hot-unplug (device removal) graceful handling** — daemon emits a `device_removed` audit-log entry but does NOT auto-unbind the manifest. Removed-then-replugged behaves like a fresh hot-plug.
- **Multi-host robot rigs.** Single host assumed; cross-host event sync is out of scope.
- **Automatic driver download from a registry.** The matching backend's pip extra must already be installed; if no backend matches the device's protocol, the event lands as LOW with a `missing_backend_extra` hint.
- **Backend hot-uninstall mid-session.** Manifest stays bound to the named backend even if `pip uninstall` removed the entry-point. Runtime fails with a clean error on next call.
- **Pendant integration.** Originally co-scoped, **deferred to SP-AN v2** because the pendant repo is in early bring-up. SP-HP's queue contract is shape-correct for any future surface; pendant slots in without queue-shape changes. (Tracked in SP-AN.)

## Design

### Architecture

Six in-process components plus the OS service wrapper:

1. **`cli/src/robot_md/hotplug/daemon.py`** — Long-running event loop. Composes the cross-platform watcher + matcher + queue writer. Owns the socket listener.
2. **`cli/src/robot_md/hotplug/{linux,macos,windows}.py`** — Per-platform implementations of a single `watch_devices()` interface. All emit the same `DeviceEvent` shape.
3. **`cli/src/robot_md/hotplug/matcher.py`** — Given a `DeviceEvent`, walks installed presets + `BackendRegistry` to compute a tier (HIGH/MEDIUM/LOW) and a candidate `bind_proposal`.
4. **`cli/src/robot_md/hotplug/queue.py`** — Hash-chained append-only writer for `~/.robot-md/hotplug-events.jsonl`. Resolution operations (`bind`, `reject`, `expired`) append a new chained record; original `pending` is never edited.
5. **`cli/src/robot_md/hotplug/audit.py`** — Hash-chained per-RRN audit logger. Mirrors RRF's audit-trail conventions.
6. **`cli/src/robot_md/hotplug/manifest.py`** — Manifest merge logic. Validates BEFORE writing; refuses non-validating writes and queues a `merge_failed` event instead.

OS service wrappers (created by `robot-md hotplug install-service`):
- `~/.config/systemd/user/robot-md-hotplug.service` (Linux)
- `~/Library/LaunchAgents/dev.robotmd.hotplug.plist` (macOS)
- Scheduled Task via `pywin32` install helper (Windows)

The MCP server (`robot-md mcp`) is **not** a peer of the daemon — it's a subscriber. Specifically:

- The daemon is the single writer of `hotplug-events.jsonl` and the audit log. (Concurrency: even if two daemons race-started, only one binds the socket; the other fails fast with `EADDRINUSE` and exits with a clear error.)
- The MCP server reads-only the queue + watches the manifest. No writes from the MCP server side.
- Why split? Per-session lifecycle is the wrong shape for hot-plug — the daemon must outlive any one Claude session. Embedding the daemon inside the MCP server would tie hot-plug detection to "an operator has Claude open right now."

**Design principles preserved:**
- Backend resolution via SP3 entry-points + `try_resolve` — daemon reuses, doesn't re-implement.
- Manifest schema validation gates every write. No "best-effort write then fix later."
- Audit log is append-only and hash-chained — same shape as RRF's compliance trail.

### Components

#### 1. `hotplug/daemon.py` — service entry point

```python
# robot_md/hotplug/daemon.py

import asyncio, signal
from robot_md.hotplug import linux, macos, windows
from robot_md.hotplug.matcher import classify
from robot_md.hotplug.queue import EventQueue
from robot_md.hotplug.audit import AuditLog

PLATFORM_WATCHERS = {"linux": linux.watch_devices,
                     "darwin": macos.watch_devices,
                     "win32": windows.watch_devices}

async def run(rrn: str | None) -> int:
    queue = EventQueue.open()
    audit = AuditLog.open(rrn=rrn)
    socket_listener = _maybe_open_socket()  # Linux-only; None elsewhere

    watcher = PLATFORM_WATCHERS[sys.platform]
    async for evt in watcher():
        decision = classify(evt)
        record = queue.append_pending(evt, decision)
        audit.append("hotplug_event", record)
        if decision.tier == "HIGH" and decision.unambiguous:
            outcome = manifest.merge(decision.bind_proposal)
            queue.append_resolution(record.id, outcome)
            audit.append("hotplug_bind", outcome)
            if socket_listener: socket_listener.nudge_subscribers()
        else:
            if socket_listener: socket_listener.nudge_subscribers()
    return 0
```

**Why structured:** every hot-plug becomes a queue record. Resolution is a separate appended record referencing the original — never an in-place edit. This is what makes the queue hash-chainable.

#### 2. Per-platform `watch_devices()`

```python
# robot_md/hotplug/linux.py
async def watch_devices() -> AsyncIterator[DeviceEvent]:
    """pyudev real-time monitor. <50ms latency."""
    import pyudev
    ctx = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(ctx)
    monitor.filter_by(subsystem="usb")
    monitor.filter_by(subsystem="tty")
    monitor.start()
    for action, device in monitor:
        if action == "add":
            yield DeviceEvent.from_pyudev(device)

# robot_md/hotplug/macos.py
async def watch_devices() -> AsyncIterator[DeviceEvent]:
    """ioreg + pyserial polling. 1-2s latency."""
    seen = set()
    while True:
        await asyncio.sleep(1.5)
        current = _enumerate_macos()  # parses `ioreg -p IOUSB -l` + list_ports.comports()
        for evt in (current - seen):
            yield evt
        seen = current

# robot_md/hotplug/windows.py
async def watch_devices() -> AsyncIterator[DeviceEvent]:
    """WM_DEVICECHANGE message pump + polling fallback. 1-2s latency."""
    # See Implementation Notes for details on win32 message-loop integration.
    ...
```

Single shape:

```python
@dataclass(frozen=True)
class DeviceEvent:
    kind: Literal["usb_added", "tty_added"]
    vid: str | None              # e.g. "1a86"
    pid: str | None              # e.g. "7523"
    serial: str | None           # device serial number, if exposed
    path: str                    # /dev/ttyACM0, /dev/cu.usbmodem*, COM3
    transport: Literal["feetech", "dynamixel", "realsense", "uvc", "unknown"]
    raw_metadata: dict[str, Any] # platform-specific extras
    detected_at: str             # ISO-8601 UTC
```

`transport` is heuristically derived from VID:PID lookup table + tty class hints. "unknown" lands in LOW tier.

#### 3. `matcher.py` — tier classification

```python
# robot_md/hotplug/matcher.py

@dataclass(frozen=True)
class BindProposal:
    rrn: str | None              # if a manifest already exists in cwd
    driver_id_suggestion: str    # e.g. "arm_servos"
    backend_name: str            # resolved entry-point name
    preset_name: str | None      # e.g. "so_arm101"
    capability_preview: list[Capability]   # via SP3 enumerate_capabilities()
    inferred_fields: dict        # protocol, port, baud, etc.

@dataclass(frozen=True)
class Decision:
    tier: Literal["HIGH", "MEDIUM", "LOW"]
    unambiguous: bool
    bind_proposal: BindProposal | None
    alternatives: list[BindProposal]
    reasons: list[str]           # human-readable; surfaced to operator

def classify(evt: DeviceEvent) -> Decision:
    """Match a hot-plug event to preset + backend.

    Tier criteria:
      HIGH:   VID:PID:serial triple matches a preset that declares this exact
              hardware AND exactly one matching backend installed. Auto-bind.
      MEDIUM: VID:PID matches a preset family OR multiple eligible
              presets/backends. Top-1 candidate + alternatives surfaced; queued.
      LOW:    Only protocol/transport detected, no preset match. Queued with a
              "name this device" prompt.
    """
    ...
```

Tier thresholds are deliberately stricter than SP2's init-time tiers — SP2 has the operator's full attention; SP-HP HIGH must justify writing the manifest unattended.

#### 4. `queue.py` — hash-chained event log

```jsonl
# ~/.robot-md/hotplug-events.jsonl (one record per line)
{"id":"evt_01H...","ts":"2026-04-27T19:30:11Z","kind":"pending","event":{...DeviceEvent...},"decision":{...Decision...},"prev_hash":"sha256:0000...","this_hash":"sha256:abcd..."}
{"id":"evt_01H...","ts":"2026-04-27T19:30:12Z","kind":"resolved","ref":"evt_01H...","resolution":"bind","by":"daemon_auto","outcome":{...},"prev_hash":"sha256:abcd...","this_hash":"sha256:beef..."}
{"id":"evt_01H...","ts":"2026-04-27T19:31:05Z","kind":"pending","event":{...},"decision":{...},"prev_hash":"sha256:beef...","this_hash":"sha256:cafe..."}
```

**State model:** every `pending` record is in one of three terminal states: `bind | reject | expired`. The terminal state is a separate `kind: "resolved"` record referencing the original by `id` — first writer wins. In v1 the resolution channels are the MCP server (when subscribed) and the terminal CLI (`robot-md hotplug confirm`); each calls `hotplug_confirm` independently; both go through the daemon's socket-or-file API; the daemon serializes resolution writes (see Concurrency below). v2 surfaces (pendant, web UI) plug into the same path.

**TTL:** pending events expire after **7 days** (configurable via `~/.robot-md/hotplug.toml` key `pending_ttl_days`). The daemon scans the queue on start and once an hour, appending `resolution: "expired"` for any pending older than the TTL.

**Hash chain:** `this_hash = sha256(prev_hash || canonical_json(record_minus_hash))`. Same shape as RRF's compliance audit trail; tooling reusable.

**Concurrency:** queue file is opened with `O_APPEND`; appends are atomic on POSIX. Resolution races are handled by the daemon serializing writes — both `hotplug_confirm` callers nudge the daemon over the socket, which checks the queue under a fcntl lock and writes the first `resolved` record; subsequent callers get back "already resolved" with the resolver name.

#### 5. `audit.py` — per-RRN audit log

Same hash-chained shape as queue; one file per `RRN-*` value. Records every:
- `hotplug_event` (raw DeviceEvent + Decision)
- `hotplug_bind` (manifest merge outcome)
- `hotplug_reject` (operator-driven via `hotplug confirm --reject`)
- `hotplug_expired` (TTL elapsed)
- `merge_failed` (manifest validation failed)

Rolls into the existing `~/.robot-md/audit/` directory used by SP1/SP2's compliance trail.

#### 6. `manifest.py` — schema-gated merge

```python
def merge(proposal: BindProposal, *, manifest_path: Path) -> MergeOutcome:
    """Append a new drivers[] entry. Preserves all other fields. Sets
    backend: from resolved entry-point.

    Schema validation BEFORE write — daemon refuses to write a non-validating
    manifest; operator gets a queued event with status: "merge_failed" and
    the validator's error.
    """
    spec = parse_robot_md(manifest_path)
    new_spec = spec.with_appended_driver(proposal.to_driver_entry())
    validate_against_schema(new_spec)  # raises on violation
    write_atomic(manifest_path, render(new_spec))
    return MergeOutcome.success(rrn=spec.rrn, driver_id=proposal.driver_id_suggestion)
```

Existing `drivers[]` entries are NEVER modified — auto-bind is strictly additive.

#### MCP server changes

- **inotify watch on the active `ROBOT.md`** (Linux; `kqueue` on macOS via `watchdog`; `ReadDirectoryChangesW` on Windows). On change: reload `RobotSpec`, refresh `BackendRegistry`'s in-memory mapping, emit `notifications/tools/list_changed` so Claude sees newly-bound capabilities without a session restart.
- **Socket subscriber on connect** (Linux only): connect to `/run/user/$UID/robot-md-hotplug.sock`. On any 1-byte nudge, drain the queue and update the in-memory pending list. If the socket is missing or fails to connect, fall back to polling the queue file every 2 s.
- **Two new tools** (registered alongside SP3's tools):
  - `hotplug_review()` — returns `[{event_id, tier, bind_proposal, alternatives, reasons}, ...]` for all pending events.
  - `hotplug_confirm(event_id, decision: "bind" | "reject", choice_index?: int)` — calls back to the daemon which appends the resolution record.

#### Cross-platform commitments

| Platform | Watcher | Latency | Socket nudge | Service wrapper |
|---|---|---|---|---|
| Linux | `pyudev` netlink monitor | <50 ms | yes (Unix domain socket at `/run/user/$UID/robot-md-hotplug.sock`) | systemd user unit |
| macOS | `ioreg` + `pyserial.tools.list_ports` polling, 1.5 s tick | 1–2 s | **no** (file-poll only) | launchd plist |
| Windows | `pywin32` `WM_DEVICECHANGE` + polling fallback | 1–2 s | **no** (file-poll only) | Scheduled Task |

The Linux socket is a **performance optimization** — it cuts MCP-server-side detection-to-surface from 2 s (file poll cadence) to <100 ms (kernel wakeup). The architecture stays correct without it; macOS and Windows users see the same UX with a 1–2 s caveat. This is documented to operators.

### Data Flow

#### HIGH-tier auto-bind (the headline demo moment)

```
Operator                                State
─────────────────────────────────────────────────────────────────
(Robot rebooting, no display, audio
 only. Claude session is open
 elsewhere on the operator's laptop.)

(USB plug click)                  →   Linux: pyudev fires <50ms
                                      DeviceEvent(vid=1a86, pid=7523,
                                                  serial=AB12,
                                                  transport=feetech,
                                                  path=/dev/ttyACM0)

                                      matcher.classify():
                                        VID:PID:serial → so_arm101 preset
                                        Backends installed: lerobot only
                                        unambiguous=True, tier=HIGH

                                      manifest.merge() validates + writes:
                                        ROBOT.md gains new drivers[]:
                                          - id: arm_servos
                                            protocol: feetech
                                            backend: lerobot
                                            port: /dev/ttyACM0

                                      queue.append_pending → resolved (bind)
                                      audit.append(hotplug_bind, ...)

                                      socket_listener.nudge_subscribers()

(MCP server in Claude session     →   inotify fires on ROBOT.md change.
 wakes up)                            Reload RobotSpec; refresh
                                      BackendRegistry.
                                      Emit notifications/tools/list_changed.

(SP-AN takes over from here.)     →   See SP-AN spec for the audio
                                      announcement + Claude-chat surface.
```

#### MEDIUM-tier queued event

```
(USB plug, but VID:PID maps to    →   matcher.classify():
 a generic feetech-bus chip that      VID:PID matches multiple presets
 multiple presets share)              (so_arm101, koch_arm, custom_feetech)
                                      Backends installed: lerobot,
                                                          feetech_depthai
                                      tier=MEDIUM, unambiguous=False

                                      queue.append_pending (no merge)
                                      audit.append(hotplug_event, ...)
                                      socket nudge

(Operator's Claude chat session   →   hotplug_review() →
 or terminal CLI)
 chat session)                          [{event_id, tier=MEDIUM,
                                          bind_proposal: {preset=so_arm101,
                                                          backend=lerobot},
                                          alternatives: [koch_arm/lerobot,
                                                         so_arm101/feetech_depthai,
                                                         ...],
                                          reasons: ["VID:PID matches 3 presets",
                                                    "2 backends could drive this"]}]

(Operator answers via Claude:     →   hotplug_confirm(event_id,
 "yes, the SO-ARM101 with lerobot")     decision="bind", choice_index=0)
                                      Daemon merges manifest, appends
                                      resolution=bind to queue, appends
                                      hotplug_bind to audit.
                                      socket nudge → MCP reloads spec.
```

#### LOW-tier queued event (unknown hardware)

```
(USB plug, VID:PID not in any      →   matcher.classify():
 preset table)                          transport=unknown OR no preset match
                                       tier=LOW

                                       queue.append_pending with reasons:
                                         ["No preset matches VID:PID 1234:5678",
                                          "Hint: this looks like a feetech bus,
                                           try `pip install robot-md[hardware]`
                                           if you don't have it yet"]

(Operator answers via Claude:      →   Two paths:
 "name this 'left arm' and use         (a) hotplug_confirm + manual driver_id
  the lerobot backend")                (b) trigger SP4 author-backend flow
                                          if no backend can drive it
```

#### No active channel — durable replay

```
(Robot reboots, daemon restarts.    →   Queue file persists; daemon doesn't
 No Claude session is running.)         lose state across restarts.
                                        HIGH-tier still auto-binds (no
                                        operator dependency).
                                        MEDIUM/LOW pending records persist.

(Operator opens Claude later)        →  MCP server connects, drains queue
                                        via socket nudge (Linux) or file
                                        poll (macOS/Windows), surfaces all
                                        pending events to Claude.
```

#### State summary

| Hot-plug case | Tier | Auto-bind? | Manifest write? | Queue record |
|---|---|---|---|---|
| Exact preset + single backend match | HIGH | yes | yes | pending → resolved (bind, by=daemon_auto) |
| Multi-preset / multi-backend | MEDIUM | no | no | pending until operator confirms |
| Unknown VID:PID | LOW | no | no | pending with naming prompt |
| Daemon already saw this device | (any) | no-op | no | not re-emitted (deduped on VID:PID:serial:path) |
| Manifest validation fails on HIGH-tier merge | HIGH | aborted | no | pending → resolved (merge_failed) |
| TTL elapsed (7d) on pending | (any) | no | no | pending → resolved (expired) |

### Error Handling

#### (a) Caught — structured handling

| Failure | Where caught | Operator/author sees |
|---|---|---|
| `pyudev` import fails (Linux without USB perms) | daemon startup | Logs `udev_unavailable`; daemon falls back to polling at 2 s tick. Operator sees a warning at `robot-md hotplug-daemon status`. |
| Socket bind fails (file exists, no other daemon) | daemon startup | Logs `stale_socket`; unlinks + retries once; if still fails, runs without socket (file-poll only on the MCP-server side). |
| Two daemons race-start | second daemon | `EADDRINUSE` on socket bind → exits with status 2 + clear message. systemd's `Restart=on-failure` won't re-trigger because exit-code 2 is in `RestartPreventExitStatus`. |
| Manifest validation fails on HIGH-tier merge | `manifest.merge()` | Append `resolution: merge_failed` with validator output; do NOT write the manifest. Operator surfaces the error via `hotplug_review`. |
| Queue file corruption (truncated last record) | `EventQueue.open()` | Log `queue_truncated_record_dropped`; rebuild hash chain from prior valid record; emit a one-time alert via the queue itself (`{"kind":"daemon_alert","msg":"queue tail truncated"}`). |
| MCP server's inotify drops events under load | `watchdog` callback | Worst-case: tool list goes stale until next manifest change. SP-AN's surfaces also poll the queue on a 5 s cadence as a backstop. |
| Socket-unavailable on the MCP-server side | subscriber | Falls back to polling the queue file every 2 s. Logged once; not repeated. |

#### (b) Pass-through

| Failure | Surface |
|---|---|
| OS service install fails (e.g., systemd not present) | `robot-md hotplug install-service` returns non-zero with the OS-specific error (e.g., "systemd not detected; run with `--launchd` on macOS"). |
| `pip install 'robot-md[hardware]'` not done at the time of hot-plug | LOW-tier event with `missing_backend_extra` hint; operator gets the install command. |

#### (c) Edge cases — defensive handling

| Edge case | Defense |
|---|---|
| Same device replugged within 1 s | Dedupe on `(vid, pid, serial, path)`; only emit once per unique key per hour. |
| Two arms plugged simultaneously | Each generates a separate event; matcher classifies each independently; both queue or both auto-bind. |
| HIGH-tier match but operator just rejected the same device an hour ago | Honor the recent rejection: emit pending with `tier=MEDIUM` + reason `"recently rejected; not auto-binding"`. Operator must confirm. |
| Manifest disappears mid-watch (operator deleted it) | inotify fires `delete`; MCP server clears `RobotSpec` from memory; daemon keeps queueing events until a manifest reappears. HIGH-tier needs a manifest target — emits `merge_failed: no_manifest_in_cwd` instead. |
| Audit log write fails (disk full) | Daemon logs the failure; continues operating but emits a `daemon_alert` queue record. Compliance gap acknowledged. Operator sees the alert via `hotplug_review`. |
| Operator runs `robot-md init` while the daemon has a HIGH-tier merge in flight | `init` and daemon both call `manifest.merge`; both take an `flock` on the manifest. First wins; second sees the new manifest and re-validates its own write against it. |

#### Explicit non-goals

- **Hot-unplug graceful unbinding.** v1: removed device → audit-log entry only. The manifest stays bound. Re-plug behaves like a new HIGH-tier event (already idempotent on dedupe).
- **Cross-host event sync.** Single-host only. Multi-host rigs need a different design.
- **Driver download.** Daemon never invokes `pip install` automatically.
- **VID:PID database curation.** Initial table ships with the SO-ARM and RealSense families; community contributions land via PR. No autoupdate.

### Testing

#### Daemon core

| Test | Verifies |
|---|---|
| `test_daemon_starts_and_stops_clean.py` (NEW) | Daemon process starts, binds socket, exits on SIGTERM with status 0. |
| `test_daemon_dedupes_replug_within_window.py` (NEW) | Same `(vid,pid,serial,path)` within 1 hour → single queue record. |
| `test_daemon_two_instances_second_exits_eaddrinuse.py` (NEW) | Second daemon exits status 2 with clear message; first keeps running. |
| `test_daemon_handles_pending_ttl_expiry.py` (NEW) | Pending event older than `pending_ttl_days` is rewritten to `resolution: expired` on next scan. |

#### Per-platform watchers

| Test | Verifies |
|---|---|
| `test_linux_watch_devices_emits_on_pyudev_event.py` (NEW, `@linux`) | Mock pyudev monitor; emit fake "add" → `DeviceEvent` produced with correct VID:PID. |
| `test_linux_watch_devices_filters_subsystems.py` (NEW, `@linux`) | Only `usb` + `tty` events make it through. |
| `test_macos_watch_devices_polling_diff.py` (NEW, `@darwin`) | Mock `ioreg` output; new device appears between polls → emitted; existing device → not re-emitted. |
| `test_windows_watch_devices_message_pump.py` (NEW, `@win32`) | Mock `WM_DEVICECHANGE` message; emitted as `DeviceEvent`. |
| `test_device_event_shape_consistent_across_platforms.py` (NEW) | Hand-crafted fixture per platform → all yield the same `DeviceEvent` schema. |

#### Matcher

| Test | Verifies |
|---|---|
| `test_matcher_high_tier_exact_preset_single_backend.py` (NEW) | SO-ARM101 VID:PID:serial + only `lerobot` installed → `tier=HIGH, unambiguous=True`. |
| `test_matcher_medium_tier_multi_preset.py` (NEW) | Generic feetech VID:PID → `tier=MEDIUM` with 3 alternatives ordered. |
| `test_matcher_medium_tier_multi_backend.py` (NEW) | SO-ARM101 VID:PID + both `lerobot` and `feetech_depthai` installed → `tier=MEDIUM` with 2 alternatives. |
| `test_matcher_low_tier_unknown_vid_pid.py` (NEW) | Unknown VID:PID → `tier=LOW` with `missing_preset_match` reason. |
| `test_matcher_low_tier_no_backend.py` (NEW) | Known VID:PID but no backend installed → `tier=LOW` with `missing_backend_extra` hint. |
| `test_matcher_recent_reject_demotes_high_to_medium.py` (NEW) | Same device rejected <1h ago → next plug demoted from HIGH to MEDIUM. |

#### Queue

| Test | Verifies |
|---|---|
| `test_queue_append_pending_is_atomic.py` (NEW) | Concurrent appenders → all records present; hash chain unbroken. |
| `test_queue_resolution_first_writer_wins.py` (NEW) | Two `hotplug_confirm` calls race → first writes resolved record; second gets back `already_resolved`. |
| `test_queue_truncation_recovery.py` (NEW) | Last record bytes truncated → `EventQueue.open()` drops invalid record, emits `daemon_alert`, continues. |
| `test_queue_hash_chain_validates_with_existing_audit_tooling.py` (NEW) | RRF's `verify_audit_chain` helper accepts queue file. |

#### Manifest merge

| Test | Verifies |
|---|---|
| `test_manifest_merge_appends_driver_preserves_others.py` (NEW) | Existing manifest → new `drivers[]` entry appended; other fields byte-identical. |
| `test_manifest_merge_validates_before_write.py` (NEW) | Bad proposal (e.g., backend name with spaces) → no write, `merge_failed` queue record. |
| `test_manifest_merge_locking.py` (NEW) | `init` and daemon both attempting merge → fcntl lock serializes; both succeed sequentially. |
| `test_manifest_merge_no_manifest_returns_clear_error.py` (NEW) | No `ROBOT.md` in cwd → `merge_failed: no_manifest_in_cwd`. |

#### MCP server integration

| Test | Verifies |
|---|---|
| `test_mcp_inotify_reload_on_manifest_change.py` (NEW) | Touch `ROBOT.md` → `RobotSpec` reloaded, registry refreshed, `notifications/tools/list_changed` emitted. |
| `test_mcp_socket_subscribe_drains_queue.py` (NEW, `@linux`) | Daemon nudges socket → MCP server drains queue, returns new pending events from `hotplug_review`. |
| `test_mcp_socket_fallback_to_polling.py` (NEW) | Socket missing → MCP polls queue every 2 s and still surfaces events. |
| `test_hotplug_review_returns_pending_only.py` (NEW) | Resolved events excluded from `hotplug_review` output. |
| `test_hotplug_confirm_bind_writes_manifest.py` (NEW) | `hotplug_confirm(id, "bind", 0)` triggers daemon merge → manifest gains driver. |
| `test_hotplug_confirm_reject_appends_resolution.py` (NEW) | `hotplug_confirm(id, "reject")` → resolution=reject queued; manifest unchanged. |

#### CLI

| Test | Verifies |
|---|---|
| `test_cli_hotplug_install_service_linux.py` (NEW, `@linux`) | Writes `~/.config/systemd/user/robot-md-hotplug.service` with the right ExecStart. |
| `test_cli_hotplug_install_service_macos.py` (NEW, `@darwin`) | Writes `~/Library/LaunchAgents/dev.robotmd.hotplug.plist` with the right `ProgramArguments`. |
| `test_cli_hotplug_status_reports_running.py` (NEW) | `robot-md hotplug-daemon status` returns running PID + queue depth + last event time. |
| `test_cli_hotplug_review_lists_pending.py` (NEW) | `robot-md hotplug review` prints pending events as a table. |

#### Hardware tests

| Test | Verifies |
|---|---|
| `test_sphp_replug_so_arm101_high_tier.py` (NEW, `@hardware`) | Real SO-ARM101 replug on bob → daemon emits HIGH-tier auto-bind; manifest updated; MCP server reloads. End-to-end <1 s wall clock from plug-click. |
| `test_sphp_unknown_device_low_tier.py` (NEW, `@hardware`) | Plug a CH340 dev board → LOW tier with `missing_preset_match` reason. |

#### Manual smoke checklist — `cli/tests/manual/sphp_smoke.md`

1. **Linux: HIGH-tier auto-bind.** Daemon running on bob; replug SO-ARM101; verify `ROBOT.md` gains `drivers[]` entry within 1 s; MCP server in Claude session emits tools/list_changed.
2. **Linux: MEDIUM-tier queue + confirm.** Plug a generic feetech bus chip; verify queue has pending event; in Claude, `hotplug_review` surfaces it; `hotplug_confirm` binds it.
3. **macOS: file-poll path.** Same as #1 on macOS; verify 1–2 s detection latency; manifest still updates.
4. **Windows: WM_DEVICECHANGE path.** Same as #1 on Windows; verify message pump triggers.
5. **Daemon survives Claude restart.** Kill Claude session mid-event; verify pending event persists; reopen Claude; `hotplug_review` still surfaces it.
6. **TTL expiry.** Set `pending_ttl_days = 0.001`; queue an event; wait; verify resolution=expired record appears.

#### Coverage gaps acknowledged

- Cross-platform CI: GitHub Actions covers Linux + macOS + Windows runners, but USB hot-plug isn't physically simulatable in CI. Watcher tests are mocked; hardware tests are bob-local.
- Long-haul daemon stability: 7-day TTL handling tested via clock skew, not real elapsed time.
- Multi-arm rigs: single-arm scenarios are the v1 baseline; multi-arm tested by hand only on bob.

## Decisions deferred / future work

1. **`pending_ttl_days` default.** Picked 7 days as a vacation-length window. Roll back to 3 days if event-queue accumulation becomes a UX problem after first hands-on use.
2. **macOS launchd permission prompt.** First daemon launch may trigger macOS's "allow background app" prompt. Action item (not a question): smoke-test on a fresh macOS account during plan execution and document the click-through in the operator install hint.
3. **Pendant + web UI surfaces (SP-AN v2).** Tracked in SP-AN. SP-HP's queue contract is shape-correct for any future subscriber; no SP-HP changes needed when those land.

## Success Criteria

SP-HP is done when:

- [ ] Six in-process components implemented + tested.
- [ ] OS service wrappers ship for Linux/macOS/Windows; `robot-md hotplug install-service` works on all three.
- [ ] All unit + integration tests pass on Linux, macOS, Windows runners.
- [ ] Hardware tests pass on bob (SO-ARM101 replug → HIGH-tier auto-bind end-to-end <1 s wall clock).
- [ ] Manual smoke checklist passes 6/6.
- [ ] Daemon survives a 24-hour idle soak with no socket leaks, queue corruption, or audit-log gaps.
- [ ] Demo dry-run: bob reboots, no display attached; SO-ARM101 powered up; daemon detects, binds, manifest updated; Claude (in another window) sees `tools/list_changed`. (SP-AN delivers the operator-facing announcement on top of this.)

## Sub-project Relationships

- **SP3 → SP-HP.** SP-HP consumes SP3's `enumerate_capabilities()` to preview a backend's tools at hot-plug time. Without the SP3 addendum, SP-HP would have to re-build the lookup.
- **SP-HP → SP-AN.** SP-AN v1's surfaces (audio + Claude chat) are subscribers of the queue SP-HP produces; SP-AN v2 adds the pendant surface. SP-AN doesn't write to the queue.
- **SP-HP ↔ SP1.** SP1's MCP server gains the inotify watch + socket subscriber + two new tools as part of SP-HP. No SP1 changes outside that delta.
- **SP-HP ↔ SP4.** When LOW-tier events surface "no backend can drive this hardware," SP4's `author-backend` flow is the operator's path forward. SP-HP doesn't trigger SP4 automatically; surfaces the option.
- **SP-HP unblocks the auto-onboard demo moment.** Combined with SP-AN, the headline beat is: *robot reboots, no display, audio onboarding, Claude takes over.* SP-HP is the eyes; SP-AN is the mouth.

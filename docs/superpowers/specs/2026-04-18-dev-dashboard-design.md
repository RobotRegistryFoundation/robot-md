# robot-md dev dashboard — design

**Date:** 2026-04-18
**Status:** Approved — ready for implementation plan
**Owner:** craigm26
**Ships as:** v0.4.1 (bundled with issue #1 + #2 fixes)

## Summary

A local dev-environment dashboard for robot-md. One command (`robot-md dashboard serve`) opens a glanceable live web UI on `http://127.0.0.1:8091` showing servo positions, the last OAK-D frame, tool-call log, estop state, validator warnings, and tunnel status for the current robot. Shipped with the `pip install robot-md` base package; no extra services, no build toolchain.

Bundled into the same PR as the two issues filed during the v0.4.0 E2E smoke (#1 read-only capabilities skip estop gate; #2 `estop_clear` tool), so the dashboard's safety buttons work end-to-end on first use.

## Decisions (brainstorming answers)

| # | Decision | Chosen |
|---|---|---|
| Q1 | Tech stack | **(b)** — Custom lightweight web UI. FastAPI + HTMX. No Grafana/Prometheus in v1. |
| Q2 | Data source | **(c)** — Hybrid: MCP publishes to `~/.robot-md/events.jsonl` (durable) AND broadcasts on local WebSocket `:8092` (live). Dashboard subscribes to both. |
| Q3 | Feature set | **(b)** — Read-only observability + safety controls (estop + estop_clear buttons). No dashboard-initiated capability invocation. |
| Q4 | Deployment shape | **(b)** — Sidecar. MCP always publishes; dashboard is a pure subscriber in its own process. Order-independent startup. |

## Architecture

```
robot-md/cli/src/robot_md/
  dashboard/
    __init__.py
    server.py              # FastAPI app; /, /ws, /api/* endpoints
    events.py              # EventLog (JSONL tail + WS subscriber)
    templates/
      index.html           # HTMX partials: servos, frame, log, estop
    static/
      style.css
  mcp/
    context.py             # MODIFY: McpContext grows a publisher + command watcher
    tools/
      estop.py             # MODIFY: publisher.publish("estop.set", ...)
      execute_capability.py  # MODIFY: publish "tool.call" + "tool.result"
  __main__.py              # MODIFY: add `robot-md dashboard serve` Typer subcommand
```

### Data flow

```
Claude (MCP client) → MCP stdio tool call
         │
         ▼
   McpContext.publisher
         │
         ├──▶ append to ~/.robot-md/events.jsonl       (durable record)
         └──▶ broadcast on ws://127.0.0.1:8092/events  (live pipe)
                  │
                  ▼
         Dashboard FastAPI (:8091)
                  │
                  ├──▶ GET /                (HTMX page; initial render from JSONL)
                  ├──▶ GET /ws              (pushes swap fragments on events)
                  ├──▶ GET /api/frame/latest.png
                  ├──▶ POST /api/estop      (writes commands.jsonl → MCP watcher)
                  ├──▶ POST /api/estop/clear
                  └──▶ GET /api/tunnel      (reads ~/.robot-md/tunnel.json)
```

### Key invariants

- **Sidecar contract.** Dashboard never mutates state directly. Estop-set, estop-clear, and snapshot actions all flow through `~/.robot-md/commands.jsonl` → MCP command watcher → state change → published event → dashboard update. MCP remains the sole owner of backend state.
- **Non-blocking publishing.** `EventPublisher.publish()` must not block the MCP hot path. Slow WS clients drop from the broadcast but events always land in JSONL.
- **Localhost-only.** All binds are `127.0.0.1`. No auth. Operators who want remote access tunnel it themselves (same cloudflared pattern as the v0.4.0 E2E test).
- **Opt-out via env var.** `ROBOT_MD_DASHBOARD_DISABLED=1` disables the publisher entirely. Default is on — the JSONL log is the truth-of-record for later features (sync-memories, replay).

## Event schema

### Published kinds

| kind | data | frequency |
|---|---|---|
| `heartbeat` | `{joints: {name: steps}, estop: bool}` | every 2s (skipped if exec_lock busy) |
| `tool.call` | `{tool: str, args: dict, request_id: str}` | per MCP tool call |
| `tool.result` | `{tool: str, status: str, request_id: str, events: list}` | per MCP tool response |
| `estop.set` | `{set: true}` | on flag transition 0→1 |
| `estop.cleared` | `{set: false}` | on flag transition 1→0 (after #2 ships) |
| `frame` | `{png_b64: str, width: int, height: int}` | on `vision.describe` OR on `snapshot` command; rate-limited 1/5s |

### `Event` type (both sides import)

```python
@dataclass(frozen=True)
class Event:
    kind: str
    ts: float                      # epoch seconds
    data: dict[str, Any]

    def to_jsonl(self) -> str: ...
    @classmethod
    def from_jsonl(cls, line: str) -> "Event": ...
```

### File layout

- `~/.robot-md/events.jsonl` — current event log, appended. Rotates at 10 MB to `events.1.jsonl.gz`; up to 3 rotations kept.
- `~/.robot-md/commands.jsonl` — dashboard → MCP command queue. Append-only. MCP watcher polls 200 ms.
- `~/.robot-md/tunnel.json` — optional, written by an external tunnel helper (e.g., the cloudflared wrapper from the v0.4.0 E2E test). Dashboard reads for header display.

## Module contracts

### `dashboard/events.py`

```python
class EventPublisher:
    """Lives in the MCP server. Writes JSONL + broadcasts WS. Never blocks."""
    def __init__(self, *, jsonl_path: Path, ws_port: int | None = 8092) -> None: ...
    def start(self) -> None: ...         # spawns WS server + heartbeat loop
    def stop(self) -> None: ...
    def publish(self, kind: str, data: dict) -> None: ...


class EventLog:
    """Lives in the dashboard. Tails JSONL + listens to WS for live events."""
    def __init__(self, *, jsonl_path: Path, ws_url: str = "ws://127.0.0.1:8092/events") -> None: ...
    async def snapshot(self, *, n: int = 200) -> list[Event]: ...   # last N events
    async def tail(self) -> AsyncIterator[Event]: ...               # live stream forever
```

### `dashboard/server.py`

FastAPI app. Routes:

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | HTMX page; initial render from `EventLog.snapshot()` |
| GET | `/ws` | WebSocket; server pushes HTMX swap fragments keyed by target id |
| GET | `/api/frame/latest.png` | Serves most-recent `frame` PNG; 404 if none |
| POST | `/api/estop` | Writes `{"cmd":"estop.set"}` to commands.jsonl |
| POST | `/api/estop/clear` | Writes `{"cmd":"estop.clear"}` |
| POST | `/api/snapshot` | Writes `{"cmd":"snapshot"}` — MCP triggers scene_describe, publishes `frame` |
| GET | `/api/tunnel` | Reads `~/.robot-md/tunnel.json` or returns `{}` |

CLI:

```
robot-md dashboard serve [--manifest ROBOT.md] [--port 8091] [--host 127.0.0.1]
```

`--manifest` is optional; when passed, dashboard runs `validate` once on startup and pipes warnings into the header banner.

### `mcp/context.py` additions

```python
@dataclass
class McpContext:
    # ...existing fields...
    publisher: EventPublisher | None = None
    _command_watcher: Any | None = None

def load_context(manifest_path: Path) -> McpContext:
    # ...existing logic...
    if os.environ.get("ROBOT_MD_DASHBOARD_DISABLED") != "1":
        events_path = Path.home() / ".robot-md" / "events.jsonl"
        events_path.parent.mkdir(exist_ok=True)
        ctx.publisher = EventPublisher(jsonl_path=events_path)
        ctx.publisher.start()
        ctx._command_watcher = _start_command_watcher(
            ctx, Path.home() / ".robot-md" / "commands.jsonl"
        )
    return ctx
```

### Command watcher

`_start_command_watcher` spawns a background thread that:
1. Opens `commands.jsonl` in read mode; seeks to end on first open.
2. Every 200 ms, checks `os.path.getsize()` vs current `tell()`; if larger, reads new lines.
3. Parses each line; dispatches by `cmd`:
   - `estop.set` → `ctx.estop.set()` + `publisher.publish("estop.set", {"set": True})`
   - `estop.clear` → `ctx.estop.clear()` + `publisher.publish("estop.cleared", {"set": False})`
   - `snapshot` → `ctx.backend.scene_describe()` + `publisher.publish("frame", {png_b64, width, height})`
4. Unknown `cmd` values log a warning and are skipped.
5. On file truncation/rotation, reopens and seeks to new EOF.

Crude but reliable inotify substitute. No extra deps.

## UI layout

Desktop (two rows × three columns); mobile collapses to stacked:

```
┌──────────────────────────────────────────────────────────────────┐
│ bob (robot-md v0.4.0)  🟢 connected  [🔴 E-STOP]  [↻ Clear]     │
│ ⚠ 2 validator warnings · tunnel: postage-mardi...trycloudflare   │
├──────────────────┬──────────────────┬───────────────────────────┤
│ Servo positions  │ Last OAK-D frame │ Estop state               │
│ (6 joints, live) │ (refresh 5s)     │ [red/green pill]          │
├──────────────────┴──────────────────┴───────────────────────────┤
│ Recent tool calls (last 50, streaming)                            │
│   14:02:03  arm.pick(object=lego) → blocked (estop_set)           │
│   14:01:58  estop.set → ok                                        │
│   14:01:42  status.report → ok                                    │
└──────────────────────────────────────────────────────────────────┘
```

HTMX partials, swap targets, and swap triggers:

- `#servos` — swaps on `heartbeat`. Shows joint table: name, current position (steps + degrees if DH params present), last delta.
- `#frame` — swaps on `frame`. `<img src="/api/frame/latest.png?ts={ts}">`. Throttled refresh.
- `#estop` — swaps on `estop.set` / `estop.cleared`. Pill color + "set at {ts}" / "clear".
- `#toolcall-log` — appends on any `tool.call` / `tool.result`. Bounded to last 50 rows.
- `#warnings-banner` — rendered once at page load from `validate` output.

## Edge cases

| Condition | Behavior |
|---|---|
| Dashboard starts before MCP server | `events.jsonl` doesn't exist yet; dashboard creates `~/.robot-md/` and renders "waiting for MCP server" state. |
| MCP server crashes mid-session | Dashboard WS drops; reconnect loop with exponential backoff. On reconnect, snapshot() replays last 200 events from JSONL to resync. |
| JSONL grows > 10 MB | Rotates to `events.1.jsonl.gz`; up to 3 rotations kept. Dashboard `snapshot()` reads across current + most recent rotated. |
| Two concurrent dashboards | Both subscribe to same WS; both write to same commands.jsonl (append-only, no conflict). Second dashboard gets the same view. |
| Port 8091 or 8092 in use | Dashboard: fail-fast with clear error + `--port` override suggestion. Publisher: logs warning, continues without WS; dashboard still works via JSONL polling. |
| No ROBOT.md / no MCP running | Dashboard still serves; shows "no manifest configured" banner; all other panels show "no events yet". |
| Heartbeat read collides with `execute_capability` | Heartbeat acquires `ctx.exec_lock` non-blocking; if busy, skips this tick. Dashboard shows stale-indicator when gap > 4s. |
| `frame` event bloats JSONL | Rate-limited to 1/5s in the publisher. Only emitted on explicit `vision.describe` tool call or `snapshot` command — not on heartbeat. |

## Testing

### Unit (mocked — CI)

- `test_event_jsonl_roundtrip` — `Event.to_jsonl()` / `from_jsonl()` lossless across all 6 kinds.
- `test_publisher_writes_jsonl` — `publish()` appends a line matching the Event.
- `test_publisher_broadcasts_ws` — `publish()` delivers to a connected WS client via `websockets` test harness.
- `test_publisher_no_ws_fallback` — publisher works when WS port is in use; JSONL still populated.
- `test_rotation_at_10mb` — publisher rotates; `snapshot()` reads across boundary.
- `test_command_watcher_dispatches_estop_set` — writing `{"cmd":"estop.set"}` flips `ctx.estop`.
- `test_command_watcher_dispatches_estop_clear` — `{"cmd":"estop.clear"}` clears the flag (requires issue #2 landed).
- `test_command_watcher_ignores_unknown_cmd` — logs warning, doesn't crash.
- `test_heartbeat_skips_when_exec_lock_busy` — no read_positions call when lock is held.
- `test_dashboard_snapshot_returns_last_200` — EventLog.snapshot() respects `n`.
- `test_dashboard_tail_yields_live` — EventLog.tail() yields events as publisher publishes.

### Integration (local FastAPI + subprocess — CI)

- `test_dashboard_renders_with_events` — launch publisher subprocess, publish N heartbeats, `GET /` returns HTML containing the latest joint values.
- `test_dashboard_estop_button_sets_flag` — `POST /api/estop` → command file grows → heartbeat shows `estop=true`.
- `test_dashboard_estop_clear_button` — (after #2) `POST /api/estop/clear` clears the flag.
- `test_dashboard_ws_pushes_swap_fragment` — connect WS test client, publish `tool.call`, client receives an HTMX swap for `#toolcall-log`.
- `test_dashboard_starts_without_mcp_running` — serves initial render with "waiting for MCP server" state.

### Hardware (`--run-hardware` gated)

- `test_dashboard_snapshot_button_publishes_frame` — requires OAK-D; POST `/api/snapshot`, verify a `frame` event with non-empty PNG lands in JSONL + streams to WS.

## Rollout

Single PR landing as **v0.4.1** bundled with:

1. Issue #1 fix — read-only capabilities skip estop gate.
2. Issue #2 fix — `estop_clear` tool.
3. `dashboard/events.py` — Publisher + EventLog.
4. `dashboard/server.py` — FastAPI app + routes.
5. `dashboard/templates/index.html` + static CSS — UI.
6. `dashboard` CLI subcommand in `__main__.py`.
7. `mcp/context.py` modifications — Publisher init, command watcher.
8. Event publishing hooks in `mcp/tools/{estop,execute_capability}.py`.
9. Dependency additions + CHANGELOG + README "Dev observability" section.

Each numbered item is a clean commit inside the PR.

### New dependencies

- `fastapi>=0.110` (base)
- `jinja2>=3.1` (base)
- `websockets>=12` (base — verify not transitive via `mcp`)
- `uvicorn[standard]>=0.27` (base — likely transitive)

No new optional-extras. Dashboard ships in the base `pip install robot-md`.

## Breaking-change surface

**None.** All additions. `McpContext` grows optional fields; existing code paths unchanged. Publisher can be disabled via `ROBOT_MD_DASHBOARD_DISABLED=1`; default is on but no-ops if `~/.robot-md/` can't be created.

## Out of scope

- **Authentication.** Localhost-only; operators who want remote dashboard tunnel it themselves.
- **Prometheus exporter.** Deferred. Could land as a thin adapter in v0.5+ reading the same JSONL feed.
- **Dashboard-initiated capability invocation.** Overlaps with Claude's role; creates a second authorization surface.
- **Skill browser / teach launcher.** Depends on P2 (skill store) — natural v0.5+ enhancement.
- **Multi-robot view.** v0.4 doesn't support multi-manifest MCP servers.
- **Log querying / search UI.** JSONL is greppable with `jq`; v1 dashboard just tails recent.
- **Time-series graphs.** Current values live; historical trends wait for Prometheus adapter or `robot-md replay`.
- **Frame video stream (MJPEG).** Latest frame only; video is v0.5+.

## What this unlocks

With the JSONL event log as truth-of-record for tool calls + state changes, several later features become natural:

- **`robot-md replay events.jsonl`** — re-run a skill trajectory or inspect a past session (v0.5+).
- **`robot-md sync-memories`** (v0.8) — DSL extractors can use JSONL as a second source: "scan events.jsonl since $last, count tool.result outcomes per skill, update skill counters."
- **Prometheus exporter** — reads JSONL, emits counters. Thin adapter.
- **Dashboard time-series charts** — same JSONL, plotted.

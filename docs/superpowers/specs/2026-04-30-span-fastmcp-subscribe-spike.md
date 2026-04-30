# SP-AN spike: FastMCP `notifications/resources/updated` plumbing

**Date:** 2026-04-30
**Status:** Spike findings — informs SP-AN Task 3 wiring.
**Predecessor:** `2026-04-27-sp-an-announce-confirm-design.md` (which assumed
`@server.on_connect` + `server.send_resource_updated(uri)` — neither exists
on FastMCP).

## What works on FastMCP today

- `@server.resource("uri://...")` — registers a resource handler. ✓
- `Context.session.send_resource_updated(uri)` — exists on the `ServerSession`
  class (in `mcp.server.session`). ✓ Reachable from any handler that takes
  `ctx: Context`, via `ctx.session`.
- `FastMCP(lifespan=...)` — per-server-process startup/teardown hook. ✓
- `server.list_resources()` — returns the registered resource list (for the
  Task 2 registration test). ✓

## What does NOT work

- `@server.on_connect` / `@server.on_disconnect` — **do not exist**. Plan
  draft was illustrative and never resolved.
- `server.send_resource_updated(uri)` — **does not exist** on FastMCP itself.
  The notification is on `ServerSession` (per-connection), not on the server.
- `server.state` — **does not exist**. No bag for session-shared state on
  the high-level FastMCP API.
- `subscribe_resource()` / `unsubscribe_resource()` — exist on the **lowlevel**
  `mcp.server.lowlevel.Server` but FastMCP doesn't expose them. To track
  per-client subscription state we'd need to drop down to lowlevel.
- Capability advertisement — FastMCP's default `NotificationOptions` sets
  `resources_changed.subscribe=False`. Clients per MCP spec MAY ignore
  `notifications/resources/updated` if `subscribe` capability isn't declared.

## Path forward for SP-AN v1

Pragmatic, single-session stdio-mode focused (the bob baseline):

1. **Capture the active session opportunistically.** Inside the
   `hotplug_pending_resource(ctx: Context)` handler, on every read, store
   `ctx.session` in a module-global `_active_session` variable. Each read
   refreshes it. (Most reads happen at session start — Claude reads the
   resource when subscribing, again when prompted.)

2. **Background socket subscriber.** Start a `HotplugResourceSubscriber`
   from the FastMCP `lifespan` async context manager. The subscriber
   connects to `/run/user/$UID/robot-md-hotplug.sock`, reads 1-byte nudges,
   and on each nudge calls `_active_session.send_resource_updated(URI)` if
   `_active_session` is set.

3. **File-poll fallback** (per the SP-AN plan Task 4) — same closure target,
   triggered by mtime change on `~/.robot-md/hotplug-events.jsonl`. macOS /
   Windows path.

4. **Document the v1 limitation:** "Single session per server process is
   reliably notified. Multi-session servers (HTTP-streamable mode) only
   notify the most-recent session that read the resource." Lands in
   `cli/docs/hotplug-roadmap.md` as a v2 follow-up: "drop to lowlevel
   `Server` with proper per-session subscribe/unsubscribe handlers."

## Test design implications

- The plan's Task 2 test (`test_resource_uri_appears_in_server_list_resources`)
  needs to import `build_server` and call it with a fake `McpContext`,
  not `from robot_md.mcp.server import server` (which is local to
  `build_server`). Adapt the test accordingly.
- The plan's Task 3 test verifies the *subscriber* receives a nudge byte
  from the daemon socket — that part is correct and now works given the
  SP-HP broadcast extension landed (commits 742cfd0 + 9ccb484). What
  remains is verifying that `on_change` triggers
  `session.send_resource_updated(URI)` — testable with a mock session.

## Out-of-scope notes

- Per-spec MCP `subscribe` capability — not advertising it in v1; clients
  may receive notifications anyway (Claude Code does). v2 work to do this
  properly with lowlevel handlers + a subscription registry.
- Cross-session fanout — solved by lifting the active-session tracker to
  a `set[ServerSession]` if/when v2 multi-session support lands.

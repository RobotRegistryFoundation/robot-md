# Hot-plug roadmap (v2 and beyond)

SP-AN v1 ships Claude chat + voice-mode audio. The following items are
explicitly deferred and tracked here so v2 work has a starting point.

## v1 single-session limitation

The v1 implementation captures the active `ServerSession` opportunistically
inside the `robot-md://hotplug/pending` resource handler. In stdio mode
this is reliable: a server process serves one Claude session, and Claude
reads the resource at session start. In HTTP-streamable / multi-session
modes, only the most-recent session that read the resource will receive
`notifications/resources/updated` for hot-plug events.

The v2 fix is to drop down to the lowlevel `mcp.server.lowlevel.Server`
API (which exposes `subscribe_resource` / `unsubscribe_resource` decorators
unavailable on FastMCP) and maintain a per-session subscription registry.

See `docs/superpowers/specs/2026-04-30-span-fastmcp-subscribe-spike.md`
for the spike that established this trade-off.

## v2 — pendant screen surface

- `pendant-mcp` gains `pendant_set_pending_panel(events)` tool. Skill
  text calls it whenever new pending events appear; pendantd's existing
  status renderer shows a "NEW HARDWARE" panel + Confirm/Reject/Skip
  button bindings.
- `pendant-mcp` depends on the separate
  `2026-04-25-voice-host-audio-design.md` spec landing first.
- Pendant hardware bring-up must unblock (BOOT button issue).

## v2 — pendant independent subscriber

- `pendantd` hosts its own Linux Unix-socket subscriber (mirroring the
  MCP server's path). Removes the v1 limitation that the pendant
  requires an active Claude session to see real-time events.

## v2 — manifest unbind tool (`hotplug_unbind`)

- Complement to `hotplug_confirm`. Takes an existing `driver_id`;
  removes it from `drivers[]` after safety checks (no kinematics
  referencing, no in-flight execution).
- Driver-dependency + safety semantics designed during the v2 plan.

## v2 — capability advertisement (`resources_subscribed=True`)

- FastMCP defaults `NotificationOptions.resources_changed.subscribe`
  to `False`; clients per the MCP spec MAY ignore
  `notifications/resources/updated` if the server doesn't declare the
  `subscribe` capability. v1 ships without this declaration; v2 wires
  it once we own the lowlevel `Server` and the per-session subscribe
  handlers.

## v3+ — web UI surface

- Out of scope for v2; tracked here so the queue contract design choices
  (pending → resolved single-writer, hash-chained) hold the line on what
  surfaces are addable without queue-shape changes.

## v3+ — operator preferences

- Per-RRN `~/.robot-md/hotplug-preferences.toml`: "always confirm even
  on HIGH" / "never bind backend X" / etc. v1 uses SP-HP's tier policy
  as-is.

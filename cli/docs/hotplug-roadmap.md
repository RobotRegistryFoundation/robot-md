# Hot-plug roadmap (v2 and beyond)

SP-AN v1 shipped Claude chat + voice-mode audio with a single-session
ServerSession capture. v2 (PR after v1.4.0) closed the multi-session
gap; the items below remain explicitly deferred and are tracked here.

## v2 done — multi-session subscribe (closed)

The v1 single-active-session limitation is gone. We attach lowlevel
`subscribe_resource` / `unsubscribe_resource` handlers to FastMCP's
underlying `_mcp_server` and route per-session subscriptions through a
`SessionRegistry`. Each daemon nudge fans out to every currently-
subscribed session on the URI. The server now also advertises
`resources.subscribe = True` in its capabilities so MCP-spec-strict
clients honor `notifications/resources/updated`.

See `docs/superpowers/specs/2026-04-30-span-fastmcp-subscribe-spike.md`
for the original FastMCP-vs-lowlevel trade-off; the spike's "v2 fix"
recommendation was implemented without the full lowlevel migration.

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

## v3+ — web UI surface

- Out of scope for v2; tracked here so the queue contract design choices
  (pending → resolved single-writer, hash-chained) hold the line on what
  surfaces are addable without queue-shape changes.

## v3+ — operator preferences

- Per-RRN `~/.robot-md/hotplug-preferences.toml`: "always confirm even
  on HIGH" / "never bind backend X" / etc. v1 uses SP-HP's tier policy
  as-is.

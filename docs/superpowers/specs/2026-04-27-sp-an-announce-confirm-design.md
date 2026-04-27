# SP-AN — Hot-Plug Announce + Confirm Surfaces

**Date:** 2026-04-27
**Status:** Design — pending implementation plan
**Sub-project:** Companion to SP3 (not numbered in the SP1-5 sequence)
**Depends on:** SP-HP (`2026-04-27-sp-hp-hotplug-daemon-design.md`) — provides the event queue, manifest merge API, and MCP-server tools.
**Companion to:** SP3 (`2026-04-26-sp3-sdk-adapter-pattern-design.md`).

## Problem

SP-HP produces a durable queue of hot-plug events. Without SP-AN, the operator has to *check* the queue manually (`robot-md hotplug review` from a terminal). That works, but it's the wrong shape for the headline demo: *the robot rebooted, you didn't open a terminal, you have no display, just audio in/out, and Claude says "Found a SO-ARM101 — should I bind it?"*

SP-AN is the operator-facing layer on top of SP-HP — the announce + confirm surfaces that turn a queued event into a moment the operator perceives and can act on, with their hands free.

## Scope

**In scope:**
- **Claude-chat surface.** Whenever a Claude session is active (MCP server connected), pending events surface in two ways:
  - Proactive: on session connect or on socket-nudge, Claude is informed via the existing `notifications/tools/list_changed` plus a new `notifications/resources/updated` for the queue resource. Claude's `using-robot-md` skill text instructs it to call `hotplug_review` and surface pending events to the operator inline.
  - Reactive: operator can ask "any new hardware?" → Claude calls `hotplug_review`.
- **Audio onboarding announcement** for HIGH-tier auto-binds. When the daemon writes a `bind` resolution, the MCP server (next session connect) reads the audit-log entry and surfaces the bind to Claude with a "tell the operator" hint. Audio is rendered by Claude's existing voice surface (when the operator is in voice mode); falls back to text otherwise. **No separate TTS engine is shipped by SP-AN** — we ride on Claude's voice mode.
- **Pendant screen surface** (when the operator's robot-md-pendant is attached AND a Claude session is active). The pendant subscribes via MCP notifications routed through Claude. Pending events appear on the pendant's status panel; the pendant's existing buttons drive `hotplug_confirm`.
- **State model: pending → resolved (`bind | reject | expired`).** Both surfaces (Claude + pendant) read the same queue and both can act on it. The daemon (SP-HP) is the **single writer**. First surface to call `hotplug_confirm` wins; the other shows "(resolved on pendant)" or "(resolved by Claude)" on next refresh.
- **One new MCP server-side resource:** `robot-md://hotplug/pending` (URI). Subscribers get `notifications/resources/updated` on socket nudge or queue change.
- **Skill-text additions** to `using-robot-md.SKILL.md`: instructions for Claude on how to surface pending events without being asked, including the "audio first, screen if available" hierarchy.

**Out of scope** (v1 limitations or follow-ups):
- **Pendant subscription without an active Claude session.** Pendant subscribes via MCP notifications routed through Claude's session. No Claude session = pendant doesn't see live events. Events still queue (SP-HP) and surface on next Claude connect. Future work: pendant hosts its own socket subscriber. **Called out as a known v1 limitation in this spec; not fixed.**
- **Standalone TTS / SP-AN-owned audio engine.** Audio rides on Claude's voice mode.
- **Multi-pendant rigs.** Single pendant assumed.
- **Cross-host event sync.** Inherited from SP-HP's out-of-scope list.
- **Persistent operator preferences for tier-based prompting.** v1 uses SP-HP's tier policy as-is. Future: per-RRN "always confirm even on HIGH" preference.

## Design

### Architecture

Three operator-facing surfaces, all subscribers of SP-HP's queue + manifest. SP-AN ships as additions to existing components — not a new long-running process.

1. **Claude chat surface** (lives in the MCP server + skill text). Claude is informed of pending events via two MCP primitives: `notifications/tools/list_changed` (already wired in SP-HP for newly bound capabilities) and a new `notifications/resources/updated` for the `robot-md://hotplug/pending` resource. Claude's skill text tells it what to do on each.
2. **Audio announcement surface** (skill text only, no new code). When the MCP server detects a recent `hotplug_bind` audit-log entry on session connect (or via the socket nudge), it informs Claude via the same resource update. Skill text instructs Claude to announce the bind to the operator using its current modality (voice if active, text otherwise).
3. **Pendant screen surface** (lives in the pendant's existing renderer). The pendant already polls the MCP session for status via the existing `pendant_status` tool. SP-AN extends `pendant_status` to include `pending_hotplug_events`. The pendant's display routine adds a "Pending hardware" panel + a "Confirm / Reject" button mapping.

Net new code is small (~200 LoC across server + pendant). Most SP-AN value is in the skill text + the resource subscription.

#### Channel-availability matrix

| Channel state | Claude session active | Pendant attached | Visible event surfaces |
|---|---|---|---|
| Both available | yes | yes | Claude chat (proactive announce) + pendant screen |
| Claude only | yes | no | Claude chat only |
| Pendant only | no | yes | **none in v1** (limitation) |
| Neither | no | no | Events queue durably (SP-HP); surface on next connect |

The "Pendant only, no Claude" cell is the v1 limitation. The pendant doesn't have an independent socket subscriber yet.

### Components

#### 1. MCP server: `robot-md://hotplug/pending` resource

```python
# cli/src/robot_md/mcp/resources/hotplug_pending.py (NEW)

URI = "robot-md://hotplug/pending"

@mcp_server.resource(URI)
def hotplug_pending_resource(ctx) -> Resource:
    """Read-only view over the pending hot-plug events.

    Subscribers receive notifications/resources/updated on socket nudge
    or file-poll detected change.
    """
    pending = read_pending_from_queue()  # uses SP-HP's queue.py
    return Resource(
        uri=URI,
        mimeType="application/json",
        text=json.dumps({"pending": [p.to_summary() for p in pending]}),
    )
```

Why a resource rather than a tool: resources support subscription and `notifications/resources/updated`, which is the right primitive for "Claude should know about new pending events without being asked."

#### 2. Skill-text additions to `using-robot-md.SKILL.md`

Three new sections (per the Revision 7 canonical-source rule, edited only in `~/robot-md-mcp/skills/using-robot-md/SKILL.md`):

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

If a pendant is attached (visible via `pendant_status`), the pendant will
ALSO show the pending event independently. Don't assume the operator
needs you to read aloud what they can already see; do mention "you can
also confirm on the pendant."

## Resolved-elsewhere handling

If you call `hotplug_confirm` and get back `already_resolved`, the
operator confirmed it on the pendant first. Tell them you saw it
("Got it — I see {decision} happened on the pendant.") and move on.
```

The skill text is a contract: it's how Claude turns the resource update into the announce-confirm flow.

#### 3. Pendant: `pending_hotplug_events` panel

```python
# pendant repo: pendant/src/views/status.py (extend existing)

def render_status(state: PendantState) -> Frame:
    panels = [...]
    if state.pending_hotplug_events:
        panels.append(_render_pending_panel(state.pending_hotplug_events))
    return Frame(panels=panels)

def _render_pending_panel(events: list[PendingEventSummary]) -> Panel:
    top = events[0]  # one-at-a-time UX; queue depth shown as "+N more"
    return Panel(
        title=f"NEW HARDWARE ({len(events)} pending)" if len(events) > 1
              else "NEW HARDWARE",
        body=[
            f"{top.preset_name or top.transport} on {top.port}",
            f"Tier: {top.tier}",
            f"Bind as {top.bind_proposal.backend_name}? (button A)",
            "Reject (button B)  •  Skip to next (button C)",
        ],
    )
```

Pendant's existing button-handler wires:
- A → `mcp_call("hotplug_confirm", {event_id, decision: "bind"})`
- B → `mcp_call("hotplug_confirm", {event_id, decision: "reject"})`
- C → cycle to next event in `pending_hotplug_events`

The pendant **does not** subscribe to the daemon's socket directly in v1 — it relies on the MCP session's `pending_hotplug_events` value being refreshed by the server (which is itself a subscriber of the socket nudge / file-poll). One transport hop adds ≤2 s of latency, acceptable for v1.

#### 4. Audio announce — no new code, just skill-text

Audio rides on Claude's voice mode entirely. SP-AN does NOT ship a TTS engine, an audio device manager, or a separate speech subsystem. The "audio onboarding moment" is the operator being in voice mode + Claude reading the announce text. If Claude is in text mode, the same announcement appears in chat.

This keeps SP-AN's surface area small and avoids parallel infrastructure.

### Data Flow

#### HIGH-tier auto-bind: voice-mode operator (the headline beat)

```
(Operator in voice mode with        →  SP-HP daemon classifies device:
 Claude. Robot reboots, USB plug        tier=HIGH, unambiguous.
 click on bob.)                         manifest.merge() succeeds.
                                        audit.append(hotplug_bind, ...)
                                        socket.nudge_subscribers()

(MCP server, socket subscriber)     →  Reads queue, sees new bind record.
                                        Emits notifications/resources/updated
                                        for robot-md://hotplug/pending AND
                                        notifications/tools/list_changed
                                        (because new tools exist via the
                                        new driver's capabilities).

(Claude, voice mode)                →  Skill text triggers: announce by
                                        voice — "Found an SO-ARM101 on
                                        /dev/ttyACM0. I bound it as
                                        arm_servos using lerobot. Say
                                        'undo' to reject."

Operator: "Looks good."             →  Claude continues normally.

(or)
Operator: "Undo."                    →  Claude calls
                                        hotplug_confirm(event_id, "reject").
                                        Daemon appends rejection record.
                                        Claude: "Rejected. The manifest
                                        stays bound for now — want me to
                                        help edit ROBOT.md to remove the
                                        driver?"
```

#### MEDIUM-tier event: text-mode operator with pendant

```
(Generic feetech bus chip plug.     →  Daemon classifies tier=MEDIUM.
 Operator in text mode. Pendant         queue.append_pending(...)
 attached.)                             socket nudge.

(MCP server)                        →  Resource update emitted.
                                        Pendant's next pendant_status call
                                        gets pending_hotplug_events
                                        populated.

(Claude, text mode)                 →  Skill text: surface the pending
                                        event in chat:
                                        "New hardware detected on
                                        /dev/ttyACM0 (generic feetech).
                                        Three preset matches:
                                          1. so_arm101 + lerobot (most
                                             likely)
                                          2. koch_arm + lerobot
                                          3. so_arm101 + feetech_depthai
                                        Or reject. The pendant is also
                                        showing this. Which?"

(Operator presses pendant button A) →  Pendant calls hotplug_confirm.
                                        Daemon merges manifest.
                                        Resolution=bind appended.
                                        socket nudge.

(MCP server next refresh)           →  Resource updated. Claude sees
                                        already_resolved on its next
                                        check.
                                        Claude (next message):
                                        "Got it — I see the pendant just
                                        bound it as so_arm101 + lerobot."
```

#### LOW-tier: voice-mode operator, no pendant, unknown hardware

```
(Unknown VID:PID, no preset match.) →  Daemon: tier=LOW, queue.append.
                                        socket nudge.

(Claude, voice mode)                →  Skill text: announce by voice —
                                        "I see new hardware on
                                        /dev/ttyACM0, but I don't
                                        recognize it. It looks like a
                                        feetech bus device. Want me to
                                        try to write a backend for it?
                                        (That'll start a guided setup.)
                                        Or skip for now."

Operator: "Try it."                 →  Claude triggers SP4's
                                        author-backend flow.
                                        SP-HP queue gets a resolution
                                        of "deferred_to_sp4" so the
                                        event doesn't keep nagging.
```

#### Resolved-elsewhere race

```
(Both Claude and pendant see the    →  Both call hotplug_confirm.
 same MEDIUM event.)                    Daemon serializes via socket
                                        listener fcntl lock.

(Pendant gets there first.)         →  Daemon writes resolution=bind,
                                        by="pendant".
                                        socket nudge.

(Claude's call arrives second.)     →  Daemon: already_resolved.
                                        Returns {ok: false,
                                                 reason: "already_resolved",
                                                 by: "pendant"}.

(Claude, text or voice)             →  Skill text: "Looks like the
                                        pendant just confirmed it as
                                        so_arm101 + lerobot. Done."
```

#### v1 limitation: no Claude session, pendant only

```
(No Claude session running.         →  SP-HP daemon queues events.
 Pendant attached, idle.)               No socket subscriber → MCP server
                                        is the only would-be subscriber,
                                        and it's not running.

                                        Pendant has no path to see the
                                        event in v1.
                                        Pendant's status panel shows
                                        normal status; pending events
                                        are invisible until a Claude
                                        session opens.

(Operator opens Claude later.)      →  MCP server connects, drains
                                        queue, gets all pending events,
                                        surfaces them. Pendant's next
                                        pendant_status call now shows
                                        them too.
```

This is the explicit v1 limitation. Future work: pendant gains an
independent socket subscriber.

### Error Handling

#### (a) Caught — structured handling

| Failure | Where caught | Operator sees |
|---|---|---|
| `notifications/resources/updated` not delivered (Claude session dropped mid-write) | MCP server next reconnect | On reconnect, MCP server emits a fresh resource update for any pending events; Claude surfaces them on next message. |
| Pendant's `pendant_status` call fails | Pendant existing handler | Pendant retries; existing pendant offline/online icon flips. SP-AN doesn't add new failure UI. |
| Operator's "undo" arrives after the 30 s window | Claude skill text | Claude still passes through `hotplug_confirm({decision:"reject"})`; daemon appends the rejection record (manifest stays bound; audit trail captures intent). Claude tells the operator "the manifest is already bound; want me to help unbind by hand?" |
| Audio announcement attempted but operator is muted | Claude voice mode | Falls through to text rendering (Claude's existing behavior). Skill text doesn't need special handling. |
| `hotplug_confirm` call from Claude/pendant returns `already_resolved` | Each surface | Both surfaces show "(resolved on \<other surface\>)" on next refresh — no error to operator. |

#### (b) Pass-through

| Failure | Surface |
|---|---|
| Claude voice mode failure (TTS audio device unavailable) | Existing Claude behavior — falls back to text. SP-AN does nothing extra. |
| Pendant disconnects mid-confirm | Pendant's existing reconnect logic handles. The daemon's resolution record is the source of truth. |
| Daemon down at the time of operator confirmation | `hotplug_confirm` call from MCP server fails with `daemon_unreachable`. Claude tells the operator to start the daemon (`robot-md hotplug-daemon start`). |

#### (c) Edge cases — defensive handling

| Edge case | Defense |
|---|---|
| Operator confirms via pendant, then says "undo" to Claude | Daemon already wrote `resolved: bind`. Claude responds "the pendant already bound it; the manifest now has the driver. Want me to help unbind by hand?" — no quiet retry. |
| Two pending events at once, voice mode | Skill text instructs Claude to handle them sequentially: announce the highest-tier first; queue the rest as "I have N more pending." |
| Operator dismisses an event by saying "later" | Claude takes no action (no `hotplug_confirm` called). The pending record stays in the queue until the TTL elapses (SP-HP's 7-day default). |
| Pendant shows stale events (subscription lag) | Pendant's `pendant_status` call returns the latest server-side snapshot on each tick; staleness window ≤2 s. Acceptable. |
| Skill text drift between robot-md-mcp and CLI copies | Revision 7 sync script + CI check (existing in SP1). SP-AN editor edits the canonical copy; sync handles propagation. |

#### Explicit non-goals

- **Background TTS engine.** Voice rides on Claude's existing voice mode.
- **Operator preferences UI** (e.g., "always confirm even on HIGH"). v1 uses SP-HP's tier policy. Custom preferences land as a follow-up.
- **Multi-channel arbitration beyond pendant + Claude.** Other surfaces (web UI, OS notifications) deferred.
- **Manifest unbind tool.** Reject after a HIGH-tier auto-bind logs intent only; manifest hand-edit remains the operator's path. Future work: `hotplug_unbind` tool that mirrors `hotplug_confirm` but for removal.

### Testing

#### Resource subscription

| Test | Verifies |
|---|---|
| `test_hotplug_pending_resource_lists_pending.py` (NEW) | Resource read returns all pending events; resolved events excluded. |
| `test_hotplug_pending_resource_emits_updated_on_nudge.py` (NEW) | Daemon socket nudge → MCP server emits `notifications/resources/updated` for the URI. |
| `test_hotplug_pending_resource_emits_updated_on_file_poll.py` (NEW) | File-poll path (no socket) → same notification within 2 s of queue change. |
| `test_hotplug_pending_resource_subscribers_only_get_changes.py` (NEW) | Two clients subscribed; one client gets `updated` for the change it caused (no infinite loops). |

#### Skill-text behavior (sandboxed Claude harness)

| Test | Verifies |
|---|---|
| `test_skill_announce_high_tier_in_voice_mode.py` (NEW) | Mock voice-mode session + HIGH bind audit entry → Claude's first response is the announce string. |
| `test_skill_undo_within_window_calls_reject.py` (NEW) | Same as above; operator says "undo" within 30 s → Claude calls `hotplug_confirm("reject")`. |
| `test_skill_undo_after_window_warns_manifest_bound.py` (NEW) | Operator says "undo" 60 s later → Claude still calls reject AND tells operator manifest stays bound. |
| `test_skill_medium_tier_surfaces_alternatives.py` (NEW) | MEDIUM event → Claude's response lists top-3 alternatives + asks operator. |
| `test_skill_resolved_elsewhere_acknowledges.py` (NEW) | `hotplug_confirm` returns `already_resolved` → Claude says "I see {decision} happened on {by}". |

#### Pendant integration

| Test | Verifies |
|---|---|
| `test_pendant_status_includes_pending_events.py` (NEW) | Mock daemon with 2 pending events → pendant's `pendant_status` payload includes them. |
| `test_pendant_button_a_calls_confirm_bind.py` (NEW) | Press A → mocked MCP call invokes `hotplug_confirm({decision:"bind"})`. |
| `test_pendant_button_b_calls_confirm_reject.py` (NEW) | Press B → invokes `hotplug_confirm({decision:"reject"})`. |
| `test_pendant_button_c_cycles_events.py` (NEW) | With 2 pending → C → display advances to event 2. |
| `test_pendant_panel_omitted_when_no_pending.py` (NEW) | Empty queue → panel not rendered. |

#### Manual smoke checklist — `cli/tests/manual/span_smoke.md`

1. **Voice-mode HIGH-tier auto-bind.** Replug SO-ARM101 on bob with operator in Claude voice mode; verify Claude's first audio response is the announce string within 5 s of the plug click.
2. **Voice-mode undo within window.** Same as #1; operator says "undo" within 30 s; verify rejection record appears in queue.
3. **Voice-mode undo after window.** Same as #1; operator says "undo" 60 s later; verify Claude warns manifest is bound.
4. **Text-mode MEDIUM with pendant.** Plug generic feetech bus; verify Claude chat surfaces alternatives + pendant shows the pending panel; press pendant button A; verify Claude acknowledges in next message ("the pendant just bound it...").
5. **No-Claude-session pendant invisibility.** With no Claude session running, plug a device. Verify pendant does NOT show the pending event (v1 limitation behaving as documented).
6. **Resolved-elsewhere race.** Two Claude sessions + pendant all see the same MEDIUM event; one acts; verify the others get `already_resolved` and acknowledge cleanly.

#### Coverage gaps acknowledged

- Voice-mode tests are the hardest to automate. Skill-text tests use a sandboxed harness; real voice-mode behavior tested by hand.
- Pendant tests assume the existing pendant codebase compiles and runs; SP-AN doesn't include pendant-runtime CI changes beyond the new panel test.
- `notifications/resources/updated` is a relatively new MCP feature; client-side rendering varies. Skill text targets the MCP-spec-compliant path; non-Claude clients may not surface resource updates.

## Open Questions

1. **Undo window length.** 30 s default. Long enough to react after a voice announce; short enough to not silently linger. Roll back to 15 s if operators report the manifest "feels editable for too long."
2. **Manifest unbind tool.** Should v1 include a `hotplug_unbind` complement to handle the reject-after-HIGH case cleanly? **Decision: defer to v2** — the v1 path (Claude offers to help hand-edit) is acceptable for the demo, and the unbind semantics deserve their own design pass (driver dependencies, safety).
3. **Pendant independent subscriber.** The v1 limitation (pendant requires Claude session) is the most-likely future complaint. Tracked as the SP-AN v2 headline item.

## Success Criteria

SP-AN is done when:

- [ ] `robot-md://hotplug/pending` resource implemented + tested; resource updates fire on nudge and on file-poll.
- [ ] Skill-text additions land in the canonical `using-robot-md.SKILL.md`; sync script propagates.
- [ ] Pendant gains the pending-events panel + button bindings; existing pendant tests still pass.
- [ ] All unit + integration tests pass (resource subscription + skill harness + pendant render).
- [ ] Manual smoke checklist passes 6/6 on bob with the SO-ARM101 + a generic feetech bus chip.
- [ ] Demo dry-run: operator in voice mode, no display attached; replug SO-ARM101; Claude announces the bind audibly within 5 s; operator says "looks good"; conversation continues. **This is the headline auto-onboard moment.**
- [ ] v1 limitation (pendant requires Claude session) documented in `using-robot-md.SKILL.md` and in `cli/docs/hotplug-limitations.md`.

## Sub-project Relationships

- **SP-HP → SP-AN.** SP-HP's queue + manifest merge + audit log are the foundation. SP-AN is read-only on SP-HP's writes (except via `hotplug_confirm`, which SP-HP defines).
- **SP3 → SP-AN.** SP-AN's "what tools just appeared" surfacing uses SP3's `enumerate_capabilities()` to enrich the announce with "you can now use {tool list}."
- **SP-AN ↔ SP1.** SP-AN's resource + skill-text additions land in the existing SP1 MCP server. No SP1 architecture changes.
- **SP-AN ↔ SP4.** SP-AN's LOW-tier path can offer to trigger SP4's `author-backend`. SP-AN itself does not own that flow.
- **SP-AN delivers the auto-onboard demo moment.** Combined with SP-HP, the headline pitch beat: *robot reboots, no display, audio onboarding, Claude announces "Found a SO-ARM101, binding it. Say 'undo' to reject" — operator nods, conversation continues.* SP-AN is the mouth of the system; SP-HP is the eyes.

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

**In scope (v1):**
- **Claude-chat surface.** Whenever a Claude session is active (MCP server connected), pending events surface in two ways:
  - Proactive: on session connect or on socket-nudge, Claude is informed via the existing `notifications/tools/list_changed` plus a new `notifications/resources/updated` for the queue resource. Claude's `using-robot-md` skill text instructs it to call `hotplug_review` and surface pending events to the operator inline.
  - Reactive: operator can ask "any new hardware?" → Claude calls `hotplug_review`.
- **Audio onboarding announcement** for HIGH-tier auto-binds. When the daemon writes a `bind` resolution, the MCP server (next session connect or socket-nudge) reads the audit-log entry and surfaces the bind to Claude with a "tell the operator" hint. Audio is rendered by Claude's existing voice surface (when the operator is in voice mode); falls back to text otherwise. **No separate TTS engine is shipped by SP-AN** — we ride on Claude's voice mode.
- **State model: `pending → resolved (bind | reject | expired)`.** v1 has a single operator-acting surface (Claude); the daemon (SP-HP) is the **single writer** of the queue; the resolution-race semantics are still implemented end-to-end so the queue contract is correct from day one. (Future surfaces — pendant, web UI — slot in without queue-shape changes.)
- **One new MCP server-side resource:** `robot-md://hotplug/pending` (URI). Subscribers get `notifications/resources/updated` on socket-nudge or queue change.
- **Skill-text additions** to `using-robot-md.SKILL.md`: instructions for Claude on how to surface pending events without being asked, including the audio-first / text-fallback hierarchy and the resolution flow.

**Out of scope (deferred to SP-AN v2):**
- **Pendant screen surface.** Originally co-scoped with v1, **deferred** because the pendant repo (`robot-md-pendant`) is in early bring-up — there's no MCP-client subscriber on `pendantd`, the `pendant-mcp` server itself is only introduced by the separate `2026-04-25-voice-host-audio-design.md` spec, and pendant hardware bring-up is blocked on the stuck BOOT button. v2 SP-AN will add a pendant-mcp tool (`pendant_set_pending_panel`) + a pending-events panel in pendantd's renderer + the explicit dependency on pendant-mcp landing.
- **Standalone TTS / SP-AN-owned audio engine.** Audio rides on Claude's voice mode.
- **Cross-host event sync.** Inherited from SP-HP's out-of-scope list.
- **Persistent operator preferences for tier-based prompting.** v1 uses SP-HP's tier policy as-is. Future: per-RRN "always confirm even on HIGH" preference.
- **Manifest unbind tool.** A reject-after-HIGH-tier-auto-bind logs intent only; manifest hand-edit remains the operator's path. v2 will add `hotplug_unbind` complementing `hotplug_confirm` once driver-dependency + safety semantics are designed.
- **Web UI surface.** Out of scope.

## Design

### Architecture

Two operator-facing surfaces in v1, both driven by the MCP server. SP-AN ships as additions to existing components — not a new long-running process.

1. **Claude chat surface** (lives in the MCP server + skill text). Claude is informed of pending events via two MCP primitives: `notifications/tools/list_changed` (already wired in SP-HP for newly bound capabilities) and a new `notifications/resources/updated` for the `robot-md://hotplug/pending` resource. Claude's skill text tells it what to do on each.
2. **Audio announcement surface** (skill text only, no new code). When the MCP server detects a recent `hotplug_bind` audit-log entry on session connect (or via the socket-nudge), it informs Claude via the same resource update. Skill text instructs Claude to announce the bind to the operator using its current modality (voice if active, text otherwise).

Net new code is small (~120 LoC in the MCP server, plus skill-text additions). Most SP-AN value is in the skill text + the resource subscription.

#### Channel-availability matrix

| Claude session active | Visible event surface |
|---|---|
| yes | Claude chat (proactive announce on tier=HIGH; reactive review on operator ask) |
| no | Events queue durably (SP-HP); surface on next Claude connect |

The "no Claude session" case is what makes SP-HP's durable queue load-bearing — events aren't lost; they wait.

### Components

#### 1. MCP server: `robot-md://hotplug/pending` resource

```python
# cli/src/robot_md/mcp/resources/hotplug_pending.py (NEW)

URI = "robot-md://hotplug/pending"

@mcp_server.resource(URI)
def hotplug_pending_resource(ctx) -> Resource:
    """Read-only view over the pending hot-plug events.

    Subscribers receive notifications/resources/updated on socket-nudge
    or file-poll-detected change.
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

Three new sections (per the SP1 simplification-revisions Revision 7 canonical-source rule, edited only in `~/robot-md-mcp/skills/using-robot-md/SKILL.md`):

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

The skill text is a contract: it's how Claude turns the resource update into the announce-confirm flow.

#### 3. Audio announce — no new code, just skill-text

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

#### MEDIUM-tier event: text-mode operator

```
(Generic feetech bus chip plug.     →  Daemon classifies tier=MEDIUM.
 Operator in text mode.)                queue.append_pending(...)
                                        socket nudge.

(MCP server)                        →  Resource update emitted.

(Claude, text mode)                 →  Skill text: surface the pending
                                        event in chat:
                                        "New hardware detected on
                                        /dev/ttyACM0 (generic feetech).
                                        Three preset matches:
                                          1. so_arm101 + lerobot (most
                                             likely)
                                          2. koch_arm + lerobot
                                          3. so_arm101 + feetech_depthai
                                        Or reject. Which?"

Operator: "Bind it as so_arm101."   →  Claude calls
                                        hotplug_confirm(event_id, "bind",
                                                        choice_index=0).
                                        Daemon merges manifest, appends
                                        resolution=bind to queue, appends
                                        hotplug_bind to audit.
                                        socket nudge → MCP reloads spec.

(Claude, next message)              →  "Done — bound. The manifest now
                                        has the new driver."
```

#### LOW-tier: voice-mode operator, unknown hardware

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

#### Resolved-elsewhere (terminal CLI)

```
(Operator runs `robot-md hotplug    →  CLI calls back to daemon over the
 confirm <event_id> --bind` from a      socket; daemon serializes via
 terminal while a Claude session        fcntl lock; writes resolution=bind,
 is also open.)                         by="cli".
                                        socket nudge.

(Claude session learns)             →  Resource update fires; Claude's
                                        next call to hotplug_review shows
                                        no pending (or fewer pending).
                                        On next operator interaction:
                                        "I see you confirmed the
                                        SO-ARM101 from the terminal.
                                        Done."
```

This race-handling exists in v1 even though the only other channel today is the CLI. The contract is correct from day one; pendant in v2 plugs into the same resolution path.

### Error Handling

#### (a) Caught — structured handling

| Failure | Where caught | Operator sees |
|---|---|---|
| `notifications/resources/updated` not delivered (Claude session dropped mid-write) | MCP server next reconnect | On reconnect, MCP server emits a fresh resource update for any pending events; Claude surfaces them on next message. |
| Operator's "undo" arrives after the 30 s window | Claude skill text | Claude still passes through `hotplug_confirm({decision:"reject"})`; daemon appends the rejection record (manifest stays bound; audit trail captures intent). Claude tells the operator "the manifest is already bound; want me to help unbind by hand?" |
| Audio announcement attempted but operator is muted | Claude voice mode | Falls through to text rendering (Claude's existing behavior). Skill text doesn't need special handling. |
| `hotplug_confirm` call from Claude returns `already_resolved` | Claude skill text | Claude says "(resolved on \<other surface\>)" on next message. No error to operator. |

#### (b) Pass-through

| Failure | Surface |
|---|---|
| Claude voice mode failure (TTS audio device unavailable) | Existing Claude behavior — falls back to text. SP-AN does nothing extra. |
| Daemon down at the time of operator confirmation | `hotplug_confirm` call from MCP server fails with `daemon_unreachable`. Claude tells the operator to start the daemon (`robot-md hotplug-daemon start`). |

#### (c) Edge cases — defensive handling

| Edge case | Defense |
|---|---|
| Two pending events at once, voice mode | Skill text instructs Claude to handle them sequentially: announce the highest-tier first; queue the rest as "I have N more pending." |
| Operator dismisses an event by saying "later" | Claude takes no action (no `hotplug_confirm` called). The pending record stays in the queue until the TTL elapses (SP-HP's 7-day default). |
| Operator confirms via terminal mid-session, then says "undo" to Claude | Daemon already wrote `resolved: bind`. Claude responds "the terminal already bound it; the manifest now has the driver. Want me to help unbind by hand?" — no quiet retry. |
| Skill text drift between robot-md-mcp and CLI copies | SP1 simplification-revisions Revision 7 sync script + CI check (existing). SP-AN editor edits the canonical copy; sync handles propagation. |

#### Explicit non-goals

- **Background TTS engine.** Voice rides on Claude's existing voice mode.
- **Operator preferences UI** (e.g., "always confirm even on HIGH"). v1 uses SP-HP's tier policy. Custom preferences land as a follow-up.
- **Multi-channel arbitration beyond Claude + CLI in v1.** Pendant + web UI deferred.
- **Manifest unbind tool.** Reject after a HIGH-tier auto-bind logs intent only; manifest hand-edit remains the operator's path. v2 work.

### Testing

#### Resource subscription

| Test | Verifies |
|---|---|
| `test_hotplug_pending_resource_lists_pending.py` (NEW) | Resource read returns all pending events; resolved events excluded. |
| `test_hotplug_pending_resource_emits_updated_on_nudge.py` (NEW) | Daemon socket-nudge → MCP server emits `notifications/resources/updated` for the URI. |
| `test_hotplug_pending_resource_emits_updated_on_file_poll.py` (NEW) | File-poll path (no socket) → same notification within 2 s of queue change. |
| `test_hotplug_pending_resource_subscribers_only_get_changes.py` (NEW) | Two clients subscribed; one client gets `updated` for the change it caused (no infinite loops). |

#### Skill-text behavior (sandboxed Claude harness)

| Test | Verifies |
|---|---|
| `test_skill_announce_high_tier_in_voice_mode.py` (NEW) | Mock voice-mode session + HIGH bind audit entry → Claude's first response is the announce string. |
| `test_skill_undo_within_window_calls_reject.py` (NEW) | Same as above; operator says "undo" within 30 s → Claude calls `hotplug_confirm("reject")`. |
| `test_skill_undo_after_window_warns_manifest_bound.py` (NEW) | Operator says "undo" 60 s later → Claude still calls reject AND tells operator manifest stays bound. |
| `test_skill_medium_tier_surfaces_alternatives.py` (NEW) | MEDIUM event → Claude's response lists top-3 alternatives + asks operator. |
| `test_skill_resolved_elsewhere_acknowledges.py` (NEW) | `hotplug_confirm` returns `already_resolved` → Claude says "I see {decision} happened from {by}". |

#### Manual smoke checklist — `cli/tests/manual/span_smoke.md`

1. **Voice-mode HIGH-tier auto-bind.** Replug SO-ARM101 on bob with operator in Claude voice mode; verify Claude's first audio response is the announce string within 5 s of the plug click.
2. **Voice-mode undo within window.** Same as #1; operator says "undo" within 30 s; verify rejection record appears in queue.
3. **Voice-mode undo after window.** Same as #1; operator says "undo" 60 s later; verify Claude warns manifest is bound.
4. **Text-mode MEDIUM event.** Plug generic feetech bus; verify Claude chat surfaces alternatives; operator picks one; verify manifest updates.
5. **No-Claude-session durability.** With no Claude session running, plug a device. Verify queue grows. Open Claude later; verify event surfaces on connect.
6. **Resolved-elsewhere via terminal CLI.** Have a Claude session open; in another shell run `robot-md hotplug confirm <id> --bind`; verify Claude's next interaction acknowledges cleanly.

#### Coverage gaps acknowledged

- Voice-mode tests are the hardest to automate. Skill-text tests use a sandboxed harness; real voice-mode behavior tested by hand.
- `notifications/resources/updated` is a relatively new MCP feature; client-side rendering varies. Skill text targets the MCP-spec-compliant path; non-Claude clients may not surface resource updates.

## Decisions deferred / future work

1. **Undo window length.** 30 s default. Long enough to react after a voice announce; short enough to not silently linger. Roll back to 15 s if operators report the manifest "feels editable for too long."
2. **Pendant screen surface (SP-AN v2).** Defer until pendant-mcp lands (per `2026-04-25-voice-host-audio-design.md`) AND pendant hardware bring-up unblocks. v2 will add a pendant-mcp tool (`pendant_set_pending_panel`) + a pending-events panel in pendantd's renderer; the queue's resolution-race contract is already implemented in v1, so pendant slots in without queue-shape changes.
3. **Manifest unbind tool (`hotplug_unbind`).** v2 work after driver-dependency + safety semantics are designed. v1 path: Claude offers to help hand-edit ROBOT.md.
4. **Independent pendant subscriber (no Claude session).** Future SP-AN v2+ work — pendantd hosts its own socket subscriber to the daemon. Removes the "no Claude session = pendant blind" limitation entirely.

## Success Criteria

SP-AN v1 is done when:

- [ ] `robot-md://hotplug/pending` resource implemented + tested; resource updates fire on socket-nudge and on file-poll.
- [ ] Skill-text additions land in the canonical `using-robot-md.SKILL.md`; sync script propagates.
- [ ] All unit + integration tests pass (resource subscription + skill harness).
- [ ] Manual smoke checklist passes 6/6 on bob with the SO-ARM101 + a generic feetech bus chip.
- [ ] Demo dry-run: operator in voice mode, no display attached; replug SO-ARM101; Claude announces the bind audibly within 5 s; operator says "looks good"; conversation continues. **This is the headline auto-onboard moment.**
- [ ] v2 pendant integration is documented as future work in `using-robot-md.SKILL.md` and in `cli/docs/hotplug-roadmap.md`.

## Sub-project Relationships

- **SP-HP → SP-AN.** SP-HP's queue + manifest merge + audit log are the foundation. SP-AN is read-only on SP-HP's writes (except via `hotplug_confirm`, which SP-HP defines).
- **SP3 → SP-AN.** SP-AN's "what tools just appeared" surfacing uses SP3's `enumerate_capabilities()` to enrich the announce with "you can now use {tool list}."
- **SP-AN ↔ SP1.** SP-AN's resource + skill-text additions land in the existing SP1 MCP server. No SP1 architecture changes.
- **SP-AN ↔ SP4.** SP-AN's LOW-tier path can offer to trigger SP4's `author-backend`. SP-AN itself does not own that flow.
- **SP-AN v1 delivers the auto-onboard demo moment via Claude.** Combined with SP-HP, the headline pitch beat: *robot reboots, no display, audio onboarding, Claude announces "Found a SO-ARM101, binding it. Say 'undo' to reject" — operator nods, conversation continues.* SP-AN is the mouth of the system; SP-HP is the eyes.
- **SP-AN v2 → robot-md-pendant.** When the pendant hardware ships and pendant-mcp lands, v2 SP-AN extends the same queue-contract to a third surface (pendant screen). No v1 queue-shape changes required.

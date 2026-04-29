# Spec: extreme ease-of-use UX for robot-md across Anthropic surfaces

**Status:** design proposal, not yet implemented.
**Target:** the user-facing UX layer for robot-md, spanning Claude Code, claude.ai (web/desktop), Claude mobile, and voice.
**Author:** drafted with Craig, 2026-04-27 (after a full-session attempt at picking a blue lego that exposed the friction points this spec aims to remove).
**Companion specs:** `perception-architecture-v2-spec.md`, `hand-eye-calibration-v2-spec.md`, `calibrate-zero-spec.md`.

## Thesis

LLMs + agent harnesses can solve robotics with **great UX from any Anthropic surface**. The same MCP server, the same conversation, the same continuity — driven from Claude Code, claude.ai web, Claude desktop, Claude mobile, or voice. Surfaces differ in what they show; the *robot* and the *conversation* are the same.

## Headline demo

**A complete novice plugs in bob, opens any Claude surface, and within ~2 minutes is making bob pick things up.**

This is the falsifiable proof point. Filmable. Repeatable. If we hit it for out-of-box robots and the same UX path applies to DIY robots (just with a one-time fiducial-on-gripper step), the thesis lands. Other proof points — surface portability, autonomous task completion, classroom demos — fall out of the same architecture.

## Design philosophy

Three principles that reinforce each other:

1. **Extreme ease of use for non-developers.** The default user has a robot and a goal — "pick the blue lego, put it in the bowl" — not a robotics engineer. Manifest edits, depth bounds, axis conventions, IK envelope reasoning all live *inside the agent's loop*, never on the operator's plate.

2. **Data-rich primitives so the agent can reason.** Every operation surfaces enough context for Claude to diagnose: raw frames, all detection candidates with metadata, kinematic envelope details with axis-decomposed reasons, FK + IK traces. The agent is the analyst; the CLI/MCP is the data plane.

3. **The agent is reactive, not driven.** Operator says one thing. Everything between that utterance and the result — choosing among candidates, tightening descriptors, panning the arm to clear an occlusion, switching IK branches, retrying a failed grasp — happens *autonomously* inside the agent's loop. The operator answers questions only when there is genuine ambiguity or a HiTL gate fires.

Together: rich data lets the agent be reactive, reactivity lets the operator stay at one utterance, and ease of use is the result.

## Audience

A **single UX baseline** simple enough for a complete beginner, with **depth available on demand** for tinkerers, researchers, and developers. There are not separate "consumer" and "developer" modes; there is one experience that lets the operator dig deeper when they want to. Depth surfaces as: status panels in the surface UI, slash-commands in Claude Code, MCP resources for direct programmatic access. Beginners never encounter these unless they go looking.

## First-time UX

### Out-of-box robot

The robot ships pre-calibrated: zero-pose values, camera extrinsic, workspace bounds, declared object descriptors all populated and validated. ROBOT.md travels with the device.

1. Operator powers on the robot. The MCP connector / plugin announces the robot to the operator's logged-in Claude account.
2. Operator opens any Claude surface and asks for something — "hi" or "what can bob do" or "pick something up."
3. Bob responds within seconds. First useful action (a wave, a pick, a scene description) within ~30 seconds.
4. **Time to first pick: ~2 minutes** including unboxing physical setup. The minimal-UX pattern (one utterance → action → "got it") applies from the first command.

No setup wizard, no calibration prompts, no manifest editing. The operator interacts as if Bob has always existed.

### DIY robot

The operator has assembled the robot themselves: chosen mount orientation, attached the camera at some position, set up the workspace. ROBOT.md exists but the per-instance values (zero, extrinsic, workspace) need to be discovered.

1. Operator powers on, connects via MCP plugin (same as out-of-box).
2. First time the operator says anything that needs the calibrated state, bob detects "uncalibrated" and offers a one-action setup: **"Tape this fiducial onto the gripper face and let me do the rest."** Bob displays/links the fiducial PDF (a small ChArUco board sized for the gripper). Operator prints, tapes, says "done."
3. Bob runs the full calibration autonomously: zero pose discovery, hand-eye extrinsic via the fiducial sweep, workspace bounds via reach probing. Operator watches; total ~5–10 minutes including print + tape time.
4. From that point on, the operator's experience is identical to the out-of-box flow.

The fiducial-on-gripper step is the *only* manual action a DIY operator does for setup. Mounting orientation, axis conventions, workspace shape — all auto-discovered. (Today, every one of these is a manifest edit; in the new architecture, none are.)

## Routine pick UX

Minimal. The operator says it; bob does it.

> **Operator:** "pick the red lego"
>
> *(arm motion)*
>
> **Bob:** "got it"

No mid-motion narration, no per-pick auth prompts, no descriptor tuning. If bob succeeds, the operator hears one word and sees the result on whatever surface they're on (text on Claude Code; live camera with a green target overlay on web/mobile; voice narration on voice).

## Safety architecture

Two layers, both encoded in the manifest's `safety.hitl_gates`:

1. **Workflow-level auth, prompted once per session.** When the operator first asks for arm motion in a session (the first "pick X" or "place Y" or "wave"), bob asks once: "okay to let me move?" After approval, all routine motions inherit that auth — silent for the rest of the session.

2. **Unusual-condition overrides, always fire per-action.** Even after workflow-level auth, certain conditions still prompt:
   - Payload near declared limit
   - Velocity near declared max
   - Trajectory passing close to workspace boundary or a singularity
   - Target outside any descriptor bob has high confidence in
   - Duty-cycle warnings (e.g., wrist_flex stall risk)

The manifest's existing `safety.hitl_gates` is reframed: *scope: arm, require_auth: true* becomes "auth-once-per-session for routine, auth-per-action for unusual." The unusual-condition list lives in `safety.hitl_overrides` (new manifest block) so each robot can declare its own envelope.

## Failure UX

Layered, in this order:

1. **Silent auto-retry.** Bob tries alternative IK branches, tightens descriptor depth bounds, pans the arm to clear occlusion, re-detects after small motions — all without saying anything. Most failures resolve here.

2. **Visual disambiguation.** When there is genuine ambiguity (two equally-good red legos), surfaces with screens highlight the candidates with bounding boxes; the operator taps/clicks the right one. Text on Claude Code: "two red legos — left or right?" Voice: same as text.

3. **Plain-English fallback.** When fundamentally blocked (out of reach, no detection at all, manifest contradiction), bob says one line in plain English with one suggested fix: *"Can't reach that — it's about 5 cm below my arm's range. Try moving it up a bit."*

The agent never returns an opaque error code or boolean to the operator. The structured failure data from the primitives is consumed by Claude and translated into one of the three layers above.

## Vocabulary and perception

**Claude's multimodal vision is the perception brain.** Bob exposes primitives — `grab_frame`, `depth_at_pixel`, `detect_candidates`, `back_project`, `plan_motion`, `execute_motion` — and Claude composes them. When the operator says "the red lego," Claude looks at the frame, identifies what's there, picks the right candidate, and proceeds. There is no on-device ML model trained on object classes.

**Show-and-tell for novel objects.** "Call this one 'sort target'" while bob's camera is on it; "watch where I drop this"; "the thing I'm holding." Bob captures the visual fingerprint (Claude-generated embedding) and stores it in the descriptor store. Next time the operator says "sort target," it just works.

**Descriptive language as fallback.** "The small red rectangle near the bowl." "The tall blue thing." Claude parses the description against the current frame.

**Descriptor store** lives in `<robot_root>/.bob/objects.db` (per the perception-architecture-v2 spec). Holds Claude-generated embeddings + per-object metadata (last_known_pose, registered/ephemeral class, lighting hints). The manifest's `vision.object_descriptors[]` becomes a thin migration target — registered descriptors only, not the catalog.

## Multi-step task composition

Hybrid:

- **Default: single utterance, silent execution.** "Pick the red lego and put it in the bowl" → bob plans pick + place, executes, says "done." One green checkmark.
- **Long sequences: narrate phase transitions only.** "Sort the legos by color" → bob says "sorting" at start, transitions ("picked the blue one, placing"), and "done" at end. Not chatty; just enough for the operator to know the phase.
- **Demonstration / imitation as a separate explicit feature.** "Watch me do this — I want you to call it 'sort'." Operator hand-guides bob through the task once (torque off; visual servoing); bob captures the trajectory and the perception conditions; afterwards, "do sort" replays it adapted to current scene.

## Visualization and surface adaptation

Same MCP backend, surface-tailored front-ends:

| Surface | Visual treatment |
|---|---|
| **Claude Code** | Text-mostly. Status lines like "moving... grasp complete." Image attachments (camera snapshot with overlays) included in replies when useful. |
| **claude.ai web / desktop** | Live camera feed panel alongside the chat. Overlays for current target, planned trajectory, completed grasp. Status panel showing arm pose. |
| **Claude mobile** | Full-screen video on capture/in-action; text-overlay status. Native to "operator standing near the robot." |
| **Voice** | Rich narration: "I see the red lego near the bowl. Picking it up now. Got it. Where would you like it?" |

The MCP server exposes resources surfaces can render: `current_frame_url`, `current_target_overlay`, `arm_pose_status`, `task_phase`. Surfaces consume what they can, ignore the rest.

**Multimodal data flow back to Claude.** Frames, depth maps, FK trace, motion overlays, candidate detection lists — all available as MCP resources Claude can read on demand. This makes Claude's reasoning richer: when something fails, Claude can pull the actual depth at the centroid, see the candidate alternatives, render the planned trajectory in 3D — without going outside the published API.

## Memory and continuity

> **Status: open. The shape below is a working draft, not a settled commitment.** Memory/continuity needs more brainstorming before this spec is finalized or used as marketing copy. Not yet on the site.

The aspirational target is **full continuity** — same bob across sessions and across surfaces. Working draft of what that might mean:

- **Persistent state:** descriptor store entries (objects bob knows), calibration values, operator preferences (default cautiousness, preferred narration verbosity), learned tasks (from demonstration), in-progress task state.
- **Conversation continuity:** the operator can start a "sort the legos" task on Claude Code at the desk, switch to Claude mobile to watch from across the room, ask a question on claude.ai web on a laptop — same task, same conversation thread.
- **Storage:** persistent state in `<robot_root>/.bob/` (descriptor store, preferences, task log). Conversation continuity via standard Claude session-handoff mechanisms (Claude memory, project state).

**Open questions before this section gets nailed down:**

- *Conversation continuity across surfaces:* what mechanism actually delivers this? Claude memory features differ between Claude Code, claude.ai, and Claude mobile. Is "the same conversation" carried by Claude's session/memory infrastructure, or do we need our own session ID we attach to messages? Likely depends on what Anthropic ships and exposes; needs research.
- *Auth carryover:* if the operator authorizes motion on Claude Code, does that auth carry to a Claude mobile conversation about the same task? (Same operator, same robot — but different Claude instance.)
- *Task state persistence:* is "in-progress task" something the agent reasons about (carried in conversation context) or something the robot side persists (carried in a server-side state machine)?
- *Privacy boundary:* what state lives on the robot vs. what crosses to Anthropic? Descriptor embeddings + frames the agent has analyzed are sensitive; the storage model needs to make this explicit.

Until these resolve, the spec asserts only the *minimum*: persistent objects + persistent calibration in `<robot_root>/.bob/`. Cross-surface conversation continuity is a stated *goal*, not a spec'd guarantee.

## Architecture notes (high level)

This spec describes the UX. The architecture that delivers it is composed from the three companion specs:

- **MCP server** ([perception-architecture-v2-spec.md](perception-architecture-v2-spec.md)) exposes the rich primitives + descriptor store + slash commands. Same server, every surface.
- **Hand-eye calibration v2** ([hand-eye-calibration-v2-spec.md](hand-eye-calibration-v2-spec.md)) provides the fiducial-on-gripper auto-calibration that makes DIY first-run viable.
- **Calibrate-zero v2** ([calibrate-zero-spec.md](calibrate-zero-spec.md)) handles zero-pose calibration via MCP tools, no shell.
- **This spec** ties them together into the operator-facing experience.

## Out of scope

- Specific ML model selection for the descriptor store (deferred to perception spec; depends on device benchmarking).
- Voice surface implementation details (the abstract "voice" target stands in for whatever Anthropic ships).
- Multi-robot fleets / shared vocabularies across robots.
- Cloud / remote operation (local-first design assumed).
- Bob's "personality" / tone — kept neutral and minimal by default; could be a future config knob.

## Open questions

- **Workflow-level auth lifetime.** A "session" — is that a Claude conversation? A time window? Until the operator closes the surface? Likely: per-conversation, with re-auth required on a fresh conversation.
- **Cross-surface auth handoff.** If the operator authorizes motion on Claude Code, then opens Claude mobile, does the auth carry? Probably yes if it's the same Claude conversation; ambiguous if it's a separate conversation referencing the same task. Implementer to decide.
- **Demonstration mode safety.** Hand-guided imitation requires torque-off; the captured trajectory then replays under torque. The replay's safety envelope must be derived from the demonstrated trajectory's bounds, not the manifest's full envelope, to prevent runaway motion. Spec needed.
- **What "done" means in a multi-step task.** When does bob declare a place "successful"? Visual confirmation that the object is in the target zone? Force-sensor confirmation of a release? Operator confirmation? Probably: visual + IK-position check by default, operator override available.
- **Failure modes for `current_frame_url`.** If the camera disconnects mid-task, what's the surface UX? Text fallback is obvious; the visual surfaces need a graceful "camera offline" state.

## Why this matters

The session this spec was drafted from spent hours on a single pick attempt. The blockers were not algorithmic novelty — every individual primitive worked — they were **UX**: opaque error codes, manual manifest edits, axis conventions the operator and the system disagreed on, calibration that needed a printer the operator didn't have. None of those should ever reach the operator's awareness.

If we hit the headline ("2 minutes from box to first pick, on any Anthropic surface"), the thesis is proven: agent harnesses + multimodal LLMs can run robotics with consumer-grade UX. The path from this spec to that demo runs through the three companion specs — perception primitives, fiducial calibration, agent-orchestrated zero — all of which are specced. The work remaining is implementation.

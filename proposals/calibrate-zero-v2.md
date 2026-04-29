# Spec: zero-calibration UX in `robot-md-mcp`

**Status:** design proposal, not yet implemented.
**Target repo:** `~/robot-md-mcp` (dev repo, out of scope for today).
**Audience:** complete beginners running Claude Code with the `robot-md` plugin.
**Author:** drafted with Craig, 2026-04-27.

## Problem

Today, zero-calibration of a Feetech-bus arm requires the operator to run shell commands:

```
! robot-md calibrate --zero --dry-run /path/to/ROBOT.md
```

The CLI prompts at stdin ("Pose the arm... press Enter"), then writes the manifest. This is fine for developers but wrong for first-time users: they don't know what `!` does, why the path is needed, or how to tell whether a dry-run "worked." Worse, when an agent (Claude) tries to drive it, `--yes` aborts the prompt — there is no agent-friendly path through the workflow at all.

Zero-calibration is one of the first things a new operator does after unboxing. The friction lands on the worst possible user.

## Design

Move orchestration into the agent. Expose three MCP tools and one slash-command prompt. The user only ever speaks natural language; Claude calls tools.

### MCP tools

| Tool | Purpose | Mutates manifest? | Hardware effect |
|---|---|---|---|
| `mcp__robot-md__torque_off` | Disable torque on all kinematic-bus servos | no | arm goes limp |
| `mcp__robot-md__torque_on` | Re-enable torque on all kinematic-bus servos | no | arm holds position |
| `mcp__robot-md__zero_capture_and_commit` | Read current encoders, write `zero_pose_steps` for every joint | yes | none (read-only on bus) |

**Signatures (input/output shape, not full JSONSchema):**

- `torque_off(robot_md_path: str) → { servos: [{id, ok, comm_err, status_err}], port: str }`
- `torque_on(robot_md_path: str) → { servos: [{id, ok, comm_err, status_err}], port: str }`
- `zero_capture_and_commit(robot_md_path: str, dry_run: bool) → { proposed: {joint_id: steps}, current_in_manifest: {joint_id: steps}, written: bool, manifest_path: str }`

### Slash command: `/calibrate-zero`

Prompt content (paraphrased — implementer writes the actual text):

> Walk the operator through zero-calibration. Steps:
> 1. Confirm the manifest path. Default to a `ROBOT.md` in cwd if exactly one exists; otherwise ask.
> 2. Run `validate` first. Bail if invalid.
> 3. Tell the operator what's about to happen in plain English ("the arm will go limp; support it if needed"). Wait for them to say ready.
> 4. Call `torque_off`.
> 5. Tell them how to pose the arm: "straight along the base +x axis, gripper forward" — but read the manifest's `solver.base_frame` to phrase it correctly for non-default conventions. Wait for them to say it's posed.
> 6. Call `zero_capture_and_commit(dry_run=true)`. Show a markdown table: joint | current | proposed | delta. Ask if they want to commit.
> 7. On confirmation, call `zero_capture_and_commit(dry_run=false)`. Show what was written.
> 8. Always finish with `torque_on`, including on cancel/abort paths.

## Closed design decisions

### 1. Cleanup on abort

`torque_on` is a standalone tool *and* the `/calibrate-zero` flow guarantees it runs on every exit path including user cancel, error, or "no don't commit." If the agent session dies between `torque_off` and `torque_on`, the next session's `/calibrate-zero` (or any tool that opens the bus) re-enables torque before doing anything else. Cleanup is belt + suspenders, not either/or.

### 2. HiTL gate granularity — workflow-level

Invoking `/calibrate-zero` is the authorization for the whole sequence on scope `arm`. Individual tools (`torque_off`, `zero_capture_and_commit`) **do not** re-prompt for HiTL within a single workflow. Outside the workflow (e.g. an agent calling `torque_off` directly during some other task), the `arm`-scope HiTL gate fires normally on the first call.

This matches the precedent set in interactive sessions: when an operator says "disable torque for me," that's workflow-level auth, not a per-tool ask.

### 3. Capture and commit are one tool

Two-step (`zero_capture` → `zero_commit`) was tempting for the "show diff, ask, then commit" UX. Rejected because: between capture and commit, the operator might bump the arm — commit would write the bumped pose instead of the captured one.

Instead: `zero_capture_and_commit(dry_run: bool)`. The slash command calls it twice — once with `dry_run=true` to show the diff, once with `dry_run=false` to commit. Each call re-reads encoders. If the operator bumps the arm between the two calls, the commit writes the *current* pose (which is what they actually want — they re-posed). The diff displayed in step 6 is then technically stale by step 7, but trivially so; if it's a meaningful drift, the implementer can compare proposed-now to proposed-then and re-show.

### 4. Scope: `--zero` only

This spec covers zero-calibration. `--sign` (per-joint encoder direction test) and `--extrinsic` (camera-to-arm via gripper silhouette) have the same shell-prompt UX problem and want the same agent-orchestrated treatment, but they're future work. Same pattern: torque-gated tools + a slash command per workflow.

## Pre-flight checks the tools must do

- **Port busy.** If `/dev/ttyACM0` (or whatever `drivers[].port` declares) is held by another process — typically `castor-gateway` — fail fast with a clear message naming the process and the systemctl command to stop it. Do not hang.
- **Servo enumeration.** Before any write, confirm all servos in `physics.kinematics[].servo_id` respond. Surface missing servos by id; do not silently skip and write a partial manifest.
- **Manifest validity.** Run schema validation first. A broken manifest doesn't get a calibration write.

## Out of scope

- Implementation. This is a spec.
- New protocol support beyond Feetech. The existing CLI only supports `protocol: feetech` for `--zero`; this spec inherits that.
- Touching the `robot-md` CLI. The CLI keeps its existing flags; the new MCP tools live in `robot-md-mcp` and may share helpers with `robot-md/calibrate.py`, but this spec doesn't dictate where the shared logic lives.
- Calibration of the camera extrinsic or per-joint sign — see "Scope" above.

## Open questions for implementer

- **Where does the slash command live?** Plugin's `commands/` dir vs. an MCP `prompts/` entry. Both work; Claude Code surfaces them differently. Probably MCP prompt for parity with `/brief-me` and `/check-safety`.
- **Audit trail.** Should `zero_capture_and_commit` write an entry to `~/.robot-md/audit/`? Probably yes, with the before/after `zero_pose_steps` table. Decide format.
- **Auto-`torque_on` on bus open.** The "session-died-mid-flow" recovery path: should *every* tool that opens the Feetech bus first ensure torque is enabled? Or only the calibration tools? The conservative answer is "every tool re-enables on entry, disables on intentional flow only" — but that has its own footguns (e.g. an inspect-only read tool re-enabling torque is surprising). Decide.

## Lesson from 2026-04-27 session: capture pose ≠ held pose

When `zero_capture_and_commit` was run with torque off and the operator hand-posing the arm, the captured `zero_pose_steps` reflected the **limp pose** (where gravity settled the arm) — not the **held pose** (where the operator intended). After torque was re-enabled with goal=present, the arm settled into the held pose, ~7° offset from the captured zero on `shoulder_lift`. Every subsequent FK calculation was off by that much.

This is a workflow bug, not a code bug. The fix is in the slash command's UX:

1. After torque-off and the operator's "ready" signal, the tool should briefly re-enable torque at *low* current (or with the operator supporting the arm) and read present positions while the arm is **actively held** in the zero configuration — not while it's drooping under gravity.
2. Alternatively: capture two readings — once limp, once with operator supporting the arm against gravity — and report the discrepancy. If >2° on any joint, prompt the operator to physically support the arm and recapture.
3. Or: provide a calibration jig (3D-printable) that physically locks the arm in zero pose, eliminating gravity-droop entirely.

The implementer's choice. The MCP tool spec needs a `/zero-cal-recapture` operation that handles "I noticed the captured pose was limp, let me redo it correctly" without having to walk the operator through the whole flow again.

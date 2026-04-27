# SP4 — Claude-Authored Driver Workflow

**Date:** 2026-04-26
**Status:** Design — pending implementation plan
**Sub-project:** 4 of 5 (see SP1-SP3 specs in this directory)

> **REVISION 2026-04-27:** Several sections superseded by `2026-04-27-sp1-5-simplification-revisions.md` — Revision 4 specifically applies to SP4. Notably: collapse 6 operator-facing phases into 3 (Setup / Motion testing / Finalize); internal AuthorGate state machine still tracks 6 sub-phases. `--strict-phases` flag preserves the original 6-phase model.

## Problem

SP3 ships a backend authoring template (`examples/backend-template/`) and a guide (`docs/authoring-a-backend.md`) — operators with hardware that no installed backend supports can copy the template and fill it in. But that's still an "expert author writes a Python package" workflow. For the demo's moat narrative ("any hardware, with Claude's help"), we need an *interactive* path: operator says *"Claude, write a backend for my arm"*, and Claude walks them through it phase by phase, gated for safety, ending with a working installed backend and an optional contribution PR.

Without SP4, novel hardware is either operator-blocked (they need to write the backend themselves) or stuck behind SP3 alone. The promise of *robot-md as a self-extending system* requires the interactive flow.

## Scope

**In scope:**
- A 6-phase workflow orchestrator (`robot-md author-backend`) that walks Claude through Discovery → Scaffold → Read-only → Motion (dry_run) → Live motion → Finalize.
- Strict per-phase HiTL gating; per-command authorization for the first 10 live commands of Phase 5 with optional "proceed unattended" toggle.
- A new skill (`authoring-a-backend`) that activates on operator intent or CLI handoff and follows the phased structure.
- Doc-source fall-through: `known_hardware.json` lookup → context7 → WebFetch → operator-paste.
- Failure handling after 3 attempts: escalate to SP5 OR drop to pair-programming mode.
- Workflow state persistence via `.author-state.json` so Ctrl-C / lost terminal allows `--resume`.
- Project-local default output (`<cwd>/backends/<name>/`) with optional Phase 6 graduation to PyPI publish prep OR upstream PR draft (artifacts only — operator runs the publish/push step).
- Minimal LOW-tier init mention pointing operators to `robot-md author-backend` when autodetect finds unrecognized devices.

**Out of scope** (SP5 or follow-up):
- Authoring backends for hardware where SP3's `lerobot`/`realsense` already covers (operator just `pip install`s).
- Auto-publishing to PyPI / auto-opening PRs (Phase 6 stops at preparing artifacts).
- Long-session "proceed unattended" walk-away with idle timeout (deferred to v2).
- Multi-hardware authoring in one workflow (one backend at a time).
- Real-time hardware-protocol fuzzing or auto-reverse-engineering.
- Co-authoring across multiple operators.
- Editing `known_hardware.json` (SP5's writer side).

## Design

### Architecture

Eight components, all in-tree to `robot-md/cli/`:

1. **`cli/src/robot_md/author_backend/`** (NEW package) — Phase orchestrator. One module per phase + `state.py` + `__init__.py`.
2. **`cli/src/robot_md/__main__.py`** — New CLI command `robot-md author-backend [--target-device] [--docs-url] [--workdir] [--resume]`.
3. **`integrations/claude-code-skill/AUTHORING-A-BACKEND.SKILL.md`** (NEW) — Skill guiding Claude through the 6 phases.
4. **`cli/src/robot_md/init_phases/install_mcp.py`** (UPDATED, additive on SP1) — LOW-tier init prints one-liner mentioning `author-backend` when autodetect finds unrecognized devices.
5. **`cli/src/robot_md/known_hardware.py`** (NEW, shared with SP5) — Read-side consumer for `known_hardware.json` lookup. SP5 owns the writer side.
6. **`cli/src/robot_md/safety/author_gate.py`** (NEW) — Per-phase HiTL enforcement; per-command auth for Phase 5 first 10 commands.
7. **`cli/src/robot_md/author_backend/contribution.py`** (NEW) — Phase 6 graduation: PyPI publish prep AND/OR upstream PR draft generation.
8. **`examples/backend-template/`** (UPDATED, from SP3) — SP4 reuses; adds `AUTHORING-LOG-TEMPLATE.md` for capturing phase decisions (used by SP5 escalation path).

**Out of scope for architecture:**
- New backends (SP3's pattern carries the work).
- Real-time fuzzing / protocol RE.
- Editing `known_hardware.json` (SP5).

**Design principles:**
- **Gate before write.** Every phase transition requires operator confirmation. Every motion command in Phase 5 (until "proceed unattended") requires per-command auth.
- **Read-only first.** Phases 1-3 cannot write to motion hardware. Implementation order is enforced by phase structure, not just convention.
- **Docs source fall-through.** lookup → context7 → WebFetch → operator-paste. First useful source wins. No source ever crashes the workflow if it's empty.
- **Fail productively.** After 3 phase failures, escalate offers SP5 (file issue) or pair-programming (operator-led, Claude-assisted) — never silent abandon.
- **Project-local default.** Output lands in `<cwd>/backends/<name>/`. Graduation to PyPI/upstream is opt-in.

**Backward compatibility:**
- Doesn't touch existing backends (`feetech_depthai`, `lerobot`, `realsense`).
- Doesn't change `BackendRegistry` API — new backends use the same entry-point group.
- Init's LOW-tier path was already minimal; adding a one-liner is additive.

### Components

#### 1. `author_backend/` package

```
cli/src/robot_md/author_backend/
├── __init__.py          # run_workflow(opts) — top-level entry
├── state.py             # WorkflowState dataclass — work area, decisions, artifacts
├── discovery.py         # Phase 1
├── scaffold.py          # Phase 2
├── read_only.py         # Phase 3
├── motion_dryrun.py     # Phase 4
├── motion_live.py       # Phase 5
├── finalize.py          # Phase 6
└── contribution.py      # PyPI/PR draft generation (used by finalize)
```

`WorkflowState`:

```python
@dataclass
class WorkflowState:
    workdir: Path                          # <cwd>/backends/<name>/
    target_device: Path | None             # /dev/ttyUSB0 etc.
    autodetect_fingerprint: dict           # USB vid:pid, label, etc.
    sdk_hint: str | None
    docs_url: str | None
    backend_name: str                      # e.g. "trossen_wx250"
    package_name: str                      # PyPI-style: robot-md-backend-trossen-wx250
    phase: Literal[1, 2, 3, 4, 5, 6]
    confirmations: dict[int, bool]
    failed_attempts: int
    authoring_log: list[dict]              # phase decisions, for SP5 escalation
```

State persists to `<workdir>/.author-state.json` after every meaningful step. `--resume` reads it and re-enters the saved phase.

Phase entry signature (every module):

```python
def run_phase(state: WorkflowState) -> PhaseResult:
    """Execute the phase. Returns result with status + next-phase guidance."""
```

#### 2. CLI command

```python
@app.command("author-backend")
def author_backend_cmd(
    target_device: Path | None = typer.Option(None, "--target-device"),
    docs_url: str | None = typer.Option(None, "--docs-url"),
    workdir: Path | None = typer.Option(None, "--workdir"),
    resume: bool = typer.Option(False, "--resume"),
) -> None:
    """Author a robot-md backend with Claude's help (6-phase workflow)."""
    from robot_md.author_backend import run_workflow
    raise typer.Exit(code=run_workflow(
        target_device=target_device, docs_url=docs_url,
        workdir=workdir, resume=resume,
    ))
```

Bootstraps Phase 1, prints structured handoff text the skill picks up via the `<<<robot-md-author-backend>>>` sentinel.

#### 3. `authoring-a-backend` skill

Activates on: (a) operator says "Claude, write a backend for X" / "implement a driver for Y", or (b) `robot-md author-backend` invocation prints the sentinel.

Skill content (sketch):

```
---
name: authoring-a-backend
description: Use when operator wants Claude to write a robot-md backend
  for hardware that no installed backend supports. Walks through 6 phased
  gates with safety enforcement.
---

# Authoring a robot-md backend

Six phases. NEVER skip ahead. Every phase transition requires operator
confirmation.

## Phase 1: Discovery
Read state.autodetect_fingerprint. Look up: known_hardware.json (call
lookup_hardware), context7 (query-docs), WebFetch (manufacturer site),
then ask operator. Propose: "Looks like vendor X using SDK Y. Docs at Z."
Stop. Wait.

## Phase 2: Scaffold
Copy examples/backend-template/ to state.workdir. Edit pyproject.toml.
Verify scaffold via pytest. Stop. Wait.

## Phase 3: Read-only
Implement open(), close(), scene_describe(), perceive.* handlers. Test
against real hardware. Confirm reads return sensible values. NO motion
code yet. Stop. Wait.

## Phase 4: Motion (dry_run only)
Implement arm.* / gripper.* handlers. Run execute(..., dry_run=True).
Inspect trajectories. Stop. Wait for "yes proceed to live."

## Phase 5: Live motion (per-command HiTL)
First 10 live commands: ask operator to authorize EACH command before
execute(..., dry_run=False). After 10, offer "proceed unattended" toggle.

## Phase 6: Finalize
Move workdir into project, pip install -e ., update ROBOT.md. Offer (don't
execute): publish to PyPI? PR upstream?

## Failure handling
After 3 phase failures, offer: (a) escalate to SP5 (file gap issue), or
(b) drop to pair-programming mode. NEVER silently abandon. NEVER skip phases.
```

#### 4. `init_phases/install_mcp.py` LOW-tier mention (additive)

```python
if tier == "LOW" and any_unrecognized_devices(scan):
    print(
        "No backend matches detected hardware. To author one with "
        "Claude's help: `robot-md author-backend`, or just ask Claude "
        "in the next session.",
        file=sys.stderr,
    )
```

Quiet for "no robot at all"; loud for "I see hardware I don't know."

#### 5. `known_hardware.py` (read side; SP5 owns writes)

```python
@dataclass(frozen=True)
class HardwareEntry:
    vid: str; pid: str
    vendor_name: str
    hardware_label: str
    suggested_sdk: str | None
    docs_url: str | None
    community_backend_hints: list[str]


def load_known_hardware() -> dict[tuple[str, str], HardwareEntry]: ...
def lookup(vid: str, pid: str) -> HardwareEntry | None: ...
```

Bundled `cli/src/robot_md/data/known_hardware.json` ships with the package. The MCP tool `lookup_hardware` (Python MCP server, SP1) wraps for skill access.

#### 6. `safety/author_gate.py`

```python
class AuthorGate:
    def __init__(self, state: WorkflowState):
        self.state = state
        self.live_commands_count = 0
        self.proceed_unattended = False

    def check(self, capability, args, *, dry_run) -> AuthorizationResult:
        if self.state.phase == 4:
            return AuthorizationResult.allow() if dry_run else \
                   AuthorizationResult.deny("Phase 4 is dry_run only")
        if self.state.phase == 5:
            if dry_run:
                return AuthorizationResult.allow()
            if self.live_commands_count < 10 or not self.proceed_unattended:
                return AuthorizationResult.require_per_command_auth(capability, args)
            return AuthorizationResult.allow()
        return AuthorizationResult.deny(f"Unexpected phase {self.state.phase}")
```

Integrates with `execute_capability` MCP tool: when workflow is active, runtime checks AuthorGate before manifest's normal `hitl_gates`. Auto-reverts `proceed_unattended` on failure (re-establishes per-command for next 5 commands).

#### 7. `contribution.py`

PyPI publish prep:
- Validates pyproject.toml has all required fields.
- Augments README with autodetect fingerprint, supported hardware, install instructions.
- Generates `python -m build && twine upload dist/*` command — does NOT execute.

Upstream PR draft:
- Suggested target path: `cli/src/robot_md/backends/<name>/`.
- Commit message draft from `state.authoring_log`.
- PR body referencing `known_hardware.json` entry SP5 should add.
- Outputs `gh pr create ...` command — does NOT execute.

Phase 6 prints a menu:

```
Backend authored successfully. Installed at ./backends/trossen_wx250/.
Manifest updated.

Optional next steps:
  [p] Generate PyPI publish files
  [u] Generate upstream PR draft
  [s] Skip — keep it project-local

Pick [s]:
```

#### 8. `examples/backend-template/AUTHORING-LOG-TEMPLATE.md`

Captures phase decisions in structured Markdown. Used by SP5 escalation flow when an operator can't complete authoring and files an issue.

### Data Flow

End-to-end walkthrough: Trossen WX250 arm (Dynamixel, no robot-md preset, no installed backend).

#### Trigger (LOW-tier init mention)

```
Operator                                State
─────────────────────────────────────────────────────────────────
$ robot-md init wx250 --yes        →    Autodetect: dynamixel bus on /dev/ttyUSB0
                                          (vid:0403 pid:6014 — FTDI U2D2)
                                        Score: all presets ≤ 3 → LOW tier.
                                        any_unrecognized_devices(scan) → True

                                        Output (stdout):
                                          ✓ Wrote ROBOT.md (minimal, LOW tier)
                                        Output (stderr):
                                          No backend matches detected hardware.
                                          To author one with Claude's help:
                                          `robot-md author-backend`, or just ask
                                          Claude in the next session.
```

#### Phase 1: Discovery

```
$ claude                            →   Session starts (SP1 servers connect).

> "Claude, write a backend for      →   authoring-a-backend skill activates.
   the WX250 attached to wx250"         Phase 1 begins.

                                        Step 1: lookup_hardware("0403", "6014")
                                          → vendor: "Trossen Robotics"
                                            suggested_sdk: "interbotix-ros-arms"
                                            docs_url: "https://docs.trossenrobotics.com/..."
                                            community_backend_hints: ["robot-md-backend-trossen-wx (PyPI, alpha)"]

                                        Step 2: context7 query-docs("interbotix-ros-arms")
                                          → ROS2-coupled, heavy.

                                        Step 3: Decide approach
                                          - Trossen SDK requires ROS2; heavy.
                                          - Direct dynamixel-sdk lighter; WX250 uses XM430.
                                          → Recommend dynamixel-sdk.

                                        Output:
                                          Phase 1: Discovery
                                          Hardware: Trossen WX250 (FTDI U2D2)
                                          Two SDK options:
                                            (a) interbotix-ros-arms — official, ROS2.
                                            (b) dynamixel-sdk — direct, lighter.
                                          Recommendation: (b). Confirm to proceed.

> "yes, b"                          →   State.sdk_hint = "dynamixel-sdk"
                                        State.confirmations[1] = True
                                        Phase 1 complete.
```

#### Phase 2: Scaffold

```
                                        Phase 2 begins.
Bash: cp -r examples/backend-template ./backends/trossen_wx250
Edit pyproject.toml: name, deps, entry-point.
Edit src/trossen_wx250/__init__.py: TrossenWX250Backend skeleton.
Bash: pytest ./backends/trossen_wx250/tests/ → 3 xfails. OK.

                                        Output:
                                          Phase 2: Scaffold
                                          Created ./backends/trossen_wx250/
                                          Entry-point: trossen_wx250
                                          Confirm to proceed to read-only impl.

> "yes"                             →   State.confirmations[2] = True
```

#### Phase 3: Read-only

```
                                        Phase 3 begins.
Edit src/trossen_wx250/__init__.py + servo.py + capabilities.py
  (Claude writes code from context7's dynamixel-sdk docs)
Bash: pip install -e ./backends/trossen_wx250/

                                        AuthorGate: phase=3, no motion allowed.

                                        Output:
                                          Need to reload MCP: /mcp → robot-md-motion
                                            → Reconnect, then I'll test reads.

> /mcp → Reconnect                  →   Server restarts. Loads trossen_wx250 entry-point.

Claude calls scene_describe via MCP
  → SceneSnapshot with joint_state populated.

                                        Output:
                                          Reads OK. Sample: shoulder=-1.45 rad.
                                          Confirm to proceed to motion impl (still
                                            dry_run only).

> "yes"                             →   Phase 3 complete.
```

#### Phase 4: Motion impl, dry_run only

```
                                        Phase 4 begins. AuthorGate enforces dry_run.
Edit src/trossen_wx250/motion.py
  (Claude writes IK + dispatch to GroupSyncWrite)

Claude calls execute_capability("arm.home", {}, dry_run=True)
  AuthorGate.check(phase=4, dry_run=True) → allow
  Backend returns trajectory, no motor writes.

                                        Output:
                                          arm.home dry_run: 8-point trajectory.
                                          arm.pick dry_run for "test_target":
                                            12-point trajectory, max vel 0.8 rad/s.
                                          Confirm to proceed to LIVE motion.

> "yes"                             →   Phase 4 complete. Phase 5 begins.
```

#### Phase 5: Live motion, per-command HiTL

```
                                        AuthorGate: live_commands_count=0.

Claude calls execute_capability("arm.home", {}, dry_run=False)
  AuthorGate.check(phase=5, count=0) → require_per_command_auth
  Returns: {status: "blocked", reason: "author_gate", count_so_far: 0}

                                        Output:
                                          [Live command 1/10] arm.home requested.
                                          Trajectory preview: 8 points, max vel 0.5 rad/s.
                                          Authorize? [y/n]

> "y"                               →   Backend executes for real.
                                        live_commands_count = 1.

(Operator authorizes 9 more commands one by one.)

                                        Output:
                                          10 live commands successful.
                                          Continue per-command, or toggle "unattended"?
                                          [auth | unattended]

> "unattended"                      →   AuthorGate.proceed_unattended = True

(Commands 11-15 succeed in unattended mode.)

> "yes"                             →   Phase 5 complete.
```

#### Phase 6: Finalize

```
                                        contribution.run_phase(state):
                                          - Workdir already at ./backends/trossen_wx250/
                                          - pip install -e already done in Phase 3
                                          - Edit ROBOT.md: drivers[0].backend = "trossen_wx250"
                                          - Append authoring summary to body section

                                        Output:
                                          ✓ Backend trossen_wx250 installed and active.
                                          ✓ ROBOT.md updated.
                                          Optional next steps:
                                            [p] PyPI publish files
                                            [u] Upstream PR draft
                                            [s] Skip

> "u"                               →   contribution.generate_upstream_pr():
                                          - Suggested target path
                                          - Commit message draft from authoring_log
                                          - PR body cross-references SP5 known_hardware entry
                                          - Output: gh pr create --title "..." --body-file ...

                                        Output:
                                          ✓ PR draft prepared at ./pr-draft.md
                                          Run when ready:
                                            cp -r ./backends/trossen_wx250 ~/robot-md/cli/src/robot_md/backends/
                                            cd ~/robot-md && gh pr create --title ... --body-file ./pr-draft.md
                                          Workflow complete.
```

#### Failure escalation

```
(In Phase 3, after 3 failed attempts:)

                                        State.failed_attempts = 3.

                                        Output:
                                          Phase 3 failed 3 times. Two options:
                                            (a) Escalate to SP5 — file gap issue.
                                            (b) Pair-program — you drive, I assist.
                                          Pick [a/b]:

> "a"                               →   contribution.escalate_to_sp5(state):
                                          Builds issue body via SP5's structured template.
                                          Outputs gh issue create command.
                                        Workflow exits with status=5 (escalated).
```

#### State summary

| Phase | Operator action | Hardware writes? | Gate |
|---|---|---|---|
| 1 Discovery | Confirm SDK | None | Phase confirmation |
| 2 Scaffold | Confirm structure | None | Phase confirmation |
| 3 Read-only | Reconnect MCP, confirm reads | None (reads only) | Phase + AuthorGate enforces no motion |
| 4 Motion (dry) | Confirm trajectories | None (dry_run) | Phase + AuthorGate forces dry_run |
| 5 Live motion | Per-command auth ×10, then optional unattended | Yes (gated) | Per-command HiTL |
| 6 Finalize | Pick contribution path | None | None |

### Error Handling

#### (a) Caught — structured handling per phase

| Phase | Failure | Operator sees |
|---|---|---|
| 1 Discovery | All four doc sources empty | Workflow prompts: "Tell me the SDK name or paste docs. Or escalate to SP5 / pair-program." |
| 1 Discovery | `lookup_hardware` MCP call fails (malformed JSON) | Logged; treated as empty result. Doesn't block. |
| 1 Discovery | WebFetch 403 / login wall | Logged; falls through to operator-paste. |
| 2 Scaffold | `cp -r` fails (disk/permission) | Phase fails with OS error. Workflow exits — fix and `--resume`. |
| 2 Scaffold | pyproject.toml malformed after edit | Validates with `tomllib`; restores backup; exits with debug capture. |
| 2 Scaffold | Entry-point name collision | Operator prompted to rename; default suggestion appends vid:pid. |
| 3 Read-only | SDK ImportError after `pip install -e .` | Logged in failed_attempts. Skill prompts retry or revisit Phase 1. |
| 3 Read-only | Port permission denied | Phase failure with `dialout` group hint. |
| 3 Read-only | Servo doesn't respond to ping | Phase failure; suggests baud sweep + wiring check. |
| 3 Read-only | Reads return implausible values | Skill emits warning; operator decides. |
| 4 Motion dry_run | IK fails (target unreachable) | `execute()` returns `ik_unreachable`; operator picks new target. Doesn't fail phase. |
| 4 Motion dry_run | Trajectory empty | Phase failure; logs IK + planner inputs. |
| 5 Live motion | Hardware timeout | Returns `hardware_timeout`. AuthorGate auto-reverts unattended → per-command for next 5 commands. |
| 5 Live motion | Hardware error response (overload) | Returns `hardware_error` with error byte. AuthorGate reverts. |
| 5 Live motion | Operator denies (`n`) | Skill asks: skip / modify args / abort phase. |
| 6 Finalize | `pip install -e .` fails | Phase failure; full pip output captured; resume after env fix. |
| 6 Finalize | ROBOT.md edit conflict | Show diff; operator picks apply/skip/merge-by-hand. |
| 6 Finalize | PyPI metadata missing fields | Lists missing; operator fills in; phase retries. |
| 6 Finalize | `gh` CLI missing | Falls back to writing `pr-draft.md` + manual instructions. |
| Escalation | `gh` missing or auth absent | Writes `gap-issue-draft.md`; prints manual `gh issue create`. |

#### (b) Pass-through

| Failure | Surface |
|---|---|
| Hardware physically damaged mid-Phase 5 | Operator's responsibility. Phase 5 per-command gates are the prevention story. |
| `author-backend` with no ROBOT.md in cwd | CLI fails fast at startup. |
| Network outage during context7/WebFetch | Caught; treats source as empty; falls through. No retry. |
| pip pulls newer SDK with breaking API | Out of SP4 scope; pin in pyproject; document in Phase 2. |

#### (c) Edge cases — defensive handling

| Edge case | Defense |
|---|---|
| Workflow interrupted mid-phase | State saved after every meaningful step. `--resume` re-enters saved phase; completed phases not re-prompted. |
| Two operators run `author-backend` against same project | File lock on `.author-state.json` via `fcntl.flock`. Second fails with lock error. |
| Operator picks "proceed unattended" then immediately fails | Auto-revert to per-command + 5-command re-prompt cycle. |
| Backend works in dry_run but fails live | Phase 5 first failure surfaces "this didn't fail in dry_run; difference is X." |
| Phase 6 PyPI step but no `python -m build` | Checks before generating; prints `pip install build twine` if missing. Doesn't auto-install. |
| Suggested entry-point name is invalid Python identifier | Validator transforms (`wx-250` → `wx_250`); shows transformation, asks confirmation. |
| Stale community hint in known_hardware.json | Reports the hint but flags: "package unreachable; treat as suggestion only." |
| Malicious docs URL from lookup | Out of scope; `known_hardware.json` is RRF-curated; SP5 PR review. |
| Operator escalates to SP5, later wants to resume | State marks `escalated=True`. `--resume` prompts: resume anyway / wipe state. |
| Phase 5 unattended walk-away | No timeout in v1 (documented). v2 may add. |
| Template modified locally and no longer scaffolds | Skill checks integrity via known fixture before Phase 2; prompts to use as-is or restore from git. |

#### Workflow integrity gates

1. **No phase skipping.** State machine rejects out-of-phase ops with `WrongPhaseError`. Belt-and-suspenders with AuthorGate.
2. **`failed_attempts` resets on phase advance.** Failures don't accumulate across phases.
3. **AuthorGate active even if skill misbehaves.** Runtime check; even if Claude hallucinates an authorization, Python-side `AuthorGate.check()` enforces. Defense in depth.

#### Explicit non-goals

- Auto-recovering hardware damage.
- Predicting which SDK Claude *should* pick — operator confirms.
- Long-running unattended exploration beyond current session.
- Multi-hardware authoring in one workflow.
- Full conformance testing of authored backend.

### Testing

#### Phase orchestrator state machine

| Test | Verifies |
|---|---|
| `test_workflow_state_persistence.py` (NEW) | `WorkflowState` round-trips through `.author-state.json`. |
| `test_workflow_advance_phase.py` (NEW) | Advancing requires confirmation; rejects skip-ahead. `failed_attempts` resets. |
| `test_workflow_resume_mid_phase.py` (NEW) | `--resume` reads state, picks up at saved phase. |
| `test_workflow_resume_after_escalation.py` (NEW) | Escalated state prompts wipe-or-resume. |
| `test_workflow_concurrent_lock.py` (NEW) | Two workflows: second fails with lock. Lock released on exit. |

#### Each phase module (mocked dependencies)

| Test | Verifies |
|---|---|
| `test_phase1_discovery_lookup_only.py` (NEW) | `lookup_hardware` returns known entry; subsequent sources skipped. |
| `test_phase1_discovery_falls_through.py` (NEW) | Sources called in order until one returns content. |
| `test_phase1_discovery_all_empty.py` (NEW) | All empty → prompts escalate-or-pair. Returns `awaiting_operator`. |
| `test_phase2_scaffold_template_copy.py` (NEW) | Mock template; copy + edit pyproject + pytest smoke. |
| `test_phase2_scaffold_entry_point_collision.py` (NEW) | Mocked existing entry-point; phase prompts new name. |
| `test_phase2_scaffold_invalid_toml_after_edit.py` (NEW) | Malformed TOML → restore backup, fail cleanly. |
| `test_phase3_readonly_open_close.py` (NEW) | Mocked open + scene_describe pass; phase passes confirmation. |
| `test_phase3_readonly_port_permission_error.py` (NEW) | Mocked `OSError` → fails with dialout hint. |
| `test_phase3_readonly_implausible_values.py` (NEW) | Implausible joint state → warning emitted. |
| `test_phase4_motion_dryrun_only.py` (NEW) | AuthorGate denies `dry_run=False` in phase 4. |
| `test_phase4_motion_ik_unreachable.py` (NEW) | IKError → `execute` returns `ik_unreachable`; phase doesn't fail. |
| `test_phase5_motion_first_10_per_command.py` (NEW) | First 10 live require per-command auth. |
| `test_phase5_motion_unattended_toggle.py` (NEW) | After 10 + toggle: subsequent skip per-command. |
| `test_phase5_motion_failure_reverts_unattended.py` (NEW) | Hardware timeout → revert to per-command for 5. |
| `test_phase6_finalize_install_and_manifest_update.py` (NEW) | `pip install -e .` + ROBOT.md update; backup retained. |
| `test_phase6_finalize_pyproject_metadata_missing.py` (NEW) | Missing fields → list returned; phase awaits operator. |
| `test_phase6_finalize_gh_missing.py` (NEW) | No `gh` → falls back to `pr-draft.md`. |

#### AuthorGate

| Test | Verifies |
|---|---|
| `test_author_gate_phase4_blocks_live.py` (NEW) | Phase 4 dry_run=False denied. |
| `test_author_gate_phase5_per_command_first_10.py` (NEW) | First 10 live require auth. |
| `test_author_gate_phase5_unattended.py` (NEW) | After toggle: allow live. |
| `test_author_gate_unexpected_phase.py` (NEW) | Phase 3 dry_run=False denied. |
| `test_author_gate_revert_on_failure.py` (NEW) | Hardware failure auto-reverts proceed_unattended. |

#### `known_hardware.py`

| Test | Verifies |
|---|---|
| `test_known_hardware_lookup_hit.py` (NEW) | Known vid:pid returns full HardwareEntry. |
| `test_known_hardware_lookup_miss.py` (NEW) | Unknown returns None. |
| `test_known_hardware_malformed_json.py` (NEW) | Corrupt JSON logged + empty dict. No raise. |
| `test_known_hardware_schema_validation.py` (NEW) | Bundled file validates against schema. |

#### `contribution.py`

| Test | Verifies |
|---|---|
| `test_contribution_pypi_metadata_complete.py` (NEW) | Valid pyproject → publish command + README augment. |
| `test_contribution_pypi_metadata_missing_fields.py` (NEW) | Missing fields → list returned, no artifacts. |
| `test_contribution_pr_draft_message.py` (NEW) | Commit msg + PR body from authoring_log. Snapshot test. |
| `test_contribution_escalate_to_sp5.py` (NEW) | Generates issue body via SP5 template; writes `gap-issue-draft.md`. |

#### Integration tests

| Test | Verifies |
|---|---|
| `test_author_backend_full_flow_mocked.py` (NEW) | All 6 phases with mocked hardware. State updates each phase, ROBOT.md updated, contribution menu shown. |
| `test_author_backend_resume.py` (NEW) | Kill mid-Phase 3; `--resume` picks up Phase 4. Earlier phases not re-prompted. |
| `test_author_backend_escalate_to_sp5.py` (NEW) | Force 3 failures, pick `a`. Issue draft written; state escalated; exit. |
| `test_author_backend_pair_programming.py` (NEW) | Force 3 failures, pick `b`. Workflow continues; failed_attempts resets; mode change verified. |
| `test_author_backend_low_tier_init_mention.py` (NEW) | Init with mocked unrecognized device → LOW-tier output includes one-liner. |

#### CLI tests

| Test | Verifies |
|---|---|
| `test_cli_author_backend_no_robot_md.py` (NEW) | Without ROBOT.md → fail fast, exit 1. |
| `test_cli_author_backend_target_device_arg.py` (NEW) | `--target-device` populates state. |
| `test_cli_author_backend_resume_arg.py` (NEW) | `--resume` requires state file. |

#### Skill text — manual smoke checklist (`cli/tests/manual/sp4_skill_smoke.md`)

1. Trigger detection: "write a backend for my arm" with ROBOT.md → skill activates.
2. CLI sentinel trigger: `robot-md author-backend` printout → skill activates.
3. No-trigger guard: "what backends exist?" → using-robot-md handles; SP4 skill silent.
4. Phase boundary: "skip to motion" in Phase 3 → skill refuses, explains.
5. Failure escalation: 3 forced failures → `[a/b]` choice presented.
6. AuthorGate respected: Phase 4 + nudging "just try it" → skill refuses.

#### Hardware tests

| Test | Verifies |
|---|---|
| `test_sp4_full_flow_dynamixel_arm.py` (NEW, `@hardware`) | Real Dynamixel rig (single XM430 servo). Walks all 6 phases against real hardware. Phase 5 limited to safe single-servo motion. |
| `test_sp4_authorgate_runtime_integration.py` (NEW, `@hardware`) | Real bob's RPi5. Workflow active in Phase 5; verifies per-command authorization end-to-end. |

#### Documentation tests

| Test | Verifies |
|---|---|
| `test_known_hardware_json_schema_valid.py` (NEW) | Bundled JSON validates against schema; runs on every PR. |
| `test_skill_phase_descriptions_match_orchestrator.py` (NEW) | Skill phase names match `WorkflowState.phase` literal + module names. Catches drift. |

#### Coverage gaps acknowledged

- Real hardware diversity — limited to Dynamixel + bob.
- Skill prose vs Claude actual behavior — manual smoke only.
- Concurrent operator scenarios across machines — untested.
- Long-session unattended walk-away — no idle timeout in v1.
- Pair-programming mode UX — only smoke-tested manually.

## Open Questions

1. **MCP reload between Phase 2 and Phase 3.** The newly installed backend's entry-point isn't visible to the running MCP server until reload. Phase 3 instructs operator to run `/mcp` → Reconnect (per SP1's lazy path). **Action:** during implementation, verify the reconnect picks up the new entry-point reliably; if not, document `claude mcp add robot-md-motion-restart -- robot-md mcp` workaround.
2. **AuthorGate integration with the runtime's existing safety stack.** Manifest's `hitl_gates[]` already enforces per-scope auth at runtime. AuthorGate adds a second layer. Need to confirm the two gates compose (AuthorGate first, then manifest gate) without confusing the operator. **Action:** during implementation, prototype both active and validate UX with one operator.
3. **`known_hardware.json` schema versioning.** SP5 will add entries; SP4 reads. If the schema changes between releases, SP4 needs to handle both versions or RRF needs to keep backward-compat indefinitely. **Action:** stamp `schema_version: 1` at file root; SP4's loader handles version 1 only; bump triggers explicit migration.

## Success Criteria

SP4 is done when:

- [ ] Eight components built and merged.
- [ ] All unit + integration tests pass.
- [ ] Manual skill smoke checklist passes 6/6.
- [ ] Hardware test passes on real Dynamixel rig (single-servo motion through all 6 phases).
- [ ] Authoring guide reviewed by an external robotics engineer; feedback incorporated.
- [ ] Demo dry-run: operator with novel hardware (e.g., a Trossen WX250 borrowed for the demo) completes Phases 1-6 in <30 minutes, ending with a working backend installed and a PR draft ready.
- [ ] Failure escalation tested: 3-failure path correctly surfaces SP5 + pair-program options.

## Sub-project Relationships

- **SP3 → SP4.** SP4 reuses SP3's `examples/backend-template/` and `docs/authoring-a-backend.md`. Without SP3, SP4 has no shape to fill in.
- **SP4 ↔ SP5.** SP5 owns `known_hardware.json`'s writer side (filing PRs from gap signals); SP4 owns the reader side. SP4's escalation path produces SP5-shaped issues. They're two halves of the same feedback loop.
- **SP4 unblocks the moat narrative.** "Watch Claude write a driver for hardware no one's wired up before, in 30 minutes, with safety gates the whole way." Strongest SP4 reveal — distinguishes robot-md from any "just install and run" tooling.

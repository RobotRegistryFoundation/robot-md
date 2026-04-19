---
date: 2026-04-19
title: One-command actuatable init
status: design
---

# One-command actuatable init — design

## Problem

`robot-md init` writes a validated manifest but leaves the robot **uncalibrated** and **unregistered** with the operator's agent harness. A fresh `robot-md init bob --preset so-arm101` produces a ROBOT.md whose `zero_pose_steps` defaults to encoder 2048 for every joint — a nominal value that does not correspond to any physical pose. Attempting to actuate against it drives the arm to a geometrically arbitrary position. The operator must separately:

1. Run `robot-md calibrate --zero` (pose arm, press Enter).
2. Run `claude mcp add robot-md -- robot-md-mcp <path>`.
3. Run `robot-md install-skill` (opt-in).
4. (Optional) Run encoder-sign verification — not yet implemented.

These four follow-ups are currently printed as a "Next:" hint. Operators miss them; marketing copy that promises "one command → Claude knows your robot *and* can move it" is not delivered by the default path.

This spec closes that gap by folding registration, MCP install, skill install, and calibration into `init` as best-effort phases.

## Goals

- Bare `robot-md init bob --preset so-arm101` on a TTY with hardware detected produces an **actuatable** robot: manifest written, MCP server registered with Claude Code, skill installed, zero and (optionally) sign calibration completed.
- Marketing one-liner stays short: `robot-md init bob --preset so-arm101 --register --contact-email me@acme.com` delivers the full D-tier setup from the brainstorming dialogue.
- Each phase is independently callable as a library function, so Claude Code can orchestrate them piecemeal when it prefers finer control.
- Non-interactive / scripted callers keep a clean escape hatch (`--non-interactive`) that preserves today's `quick()` behavior.
- Per-phase failures and operator declines do not abort the rest of the flow; manifest-write failure is the only fatal error.

## Non-goals

- Hand-eye calibration (`robot-md calibrate --hand-eye`) — remains a separate verb.
- Camera intrinsic calibration — remains `robot-md calibrate-intrinsic`, not folded into init.
- Claude Desktop / Cursor / Zed MCP install — Claude Code only in this cut. Desktop has its own `install-desktop` verb today; future work can fold that in behind a `--host` flag.
- Non-feetech calibration drivers — sign/zero calibration in this cut supports feetech only, same as today's `calibrate` verb.
- Reactive or vision-based actuation — out of scope; this change wires the *setup* flow only.

## CLI surface

```
robot-md init [NAME] [OPTIONS]
```

### Default behavior (new)

Bare `robot-md init bob --preset so-arm101` under TTY + hardware runs all six phases:

1. Write manifest (required; abort on failure).
2. Register RRN — only if `--register` was passed (preserves current gating).
3. Install MCP server with Claude Code.
4. Install `using-robot-md` skill.
5. Prompt Y/n, run encoder-sign calibration.
6. Prompt Y/n, run zero-pose calibration.

Headless (no TTY) callers auto-skip phases 5 and 6.

### Options

Existing, unchanged: `--preset/-p`, `--out/-o`, `--register`, `--contact-email`, `--manufacturer`, `--model`, `--version-`, `--device-id`, `--force`, `--wizard`.

New:

- `--no-install-mcp` — skip phase 3.
- `--no-install-skill` — skip phase 4.
- `--no-sign` — skip phase 5 only.
- `--no-calibrate` — skip phases 5 and 6.
- `--non-interactive` — manifest only. Preserves today's `quick()` behavior for scripted callers; implies `--no-install-mcp --no-install-skill --no-calibrate`.

`--wizard` becomes an alias for the new default flow; emits a one-time deprecation warning. Kept for compatibility with any docs or scripts that pass it.

### Marketing one-liner

Unchanged text, richer behavior:

```
robot-md init bob --preset so-arm101 --register --contact-email me@acme.com
```

## Architecture

`init.py` becomes a thin orchestrator over a new `init_phases/` package. Each phase is an independently-callable function returning a uniform `PhaseResult`.

```
cli/src/robot_md/
├── init.py                          # orchestrator, phase dispatch
├── init_phases/                     # NEW package
│   ├── __init__.py                  # exports PhaseResult + all phase functions
│   ├── write_manifest.py            # phase_write_manifest(...)
│   ├── register.py                  # phase_register(manifest_path, ...)
│   ├── install_mcp.py               # phase_install_mcp(manifest_path, scope="local")
│   ├── install_skill.py             # phase_install_skill()
│   ├── calibrate_sign.py            # phase_calibrate_sign(manifest_path, prompt=True)
│   └── calibrate_zero.py            # phase_calibrate_zero(manifest_path, prompt=True)
├── install_mcp_claude_code.py       # NEW: shells out to `claude mcp add`
├── calibrate.py                     # existing cli_calibrate_{zero,sign} — reused by phases
├── register.py                      # existing mint logic — wrapped by phase
├── skill.py                         # existing install() — wrapped by phase
└── claude_md.py                     # MODIFIED: refresh template to advertise
                                     #          execute_capability, estop, execute_task
```

### PhaseResult

```python
@dataclass(frozen=True)
class PhaseResult:
    phase: str                   # "write_manifest" | "register" | "install_mcp"
                                 # | "install_skill" | "sign_cal" | "zero_cal"
    status: Literal["ok", "skipped", "failed"]
    message: str                 # one-line human summary
    detail: dict | None          # phase-specific payload (rrn, skill_path, ...)
```

Each phase function catches its own exceptions and returns a `PhaseResult`. Phases never raise, with one exception: `phase_write_manifest` may raise `OSError` / `FileExistsError` on truly fatal conditions (disk full, output path refuses overwrite without `--force`). The orchestrator catches those at the top level and exits nonzero.

### install_mcp_claude_code.py

New module, minimal surface:

```python
def add(
    server_name: str,
    manifest_path: Path,
    *,
    command: str = "robot-md-mcp",
    scope: Literal["local", "user", "project"] = "local",
) -> PhaseResult:
    """Register a stdio MCP server with Claude Code via `claude mcp add`.

    Idempotent: if server_name already exists at this scope, returns
    status="ok" with a detail note. Returns status="failed" with a
    clear message if the `claude` CLI is not in PATH.
    """
```

Uses `shutil.which("claude")` first to detect presence cleanly. Shells out via `subprocess.run([...], check=False, capture_output=True, text=True)`; never raises.

Default server name is `robot-md-<robot_name>` (e.g. `robot-md-bob`), so multiple robots can coexist in one `~/.claude.json`. Operators with a single robot workspace can still type the shorter intuitive command by hand later; the init default chooses the disambiguated form to avoid collisions.

## Data flow

```
init(name, preset, --register, --no-install-mcp, ...)
  │
  ├─ phase_write_manifest(name, preset, scan, out_path, force)
  │     → ROBOT.md on disk
  │     → status=ok | raises if fatal
  │
  ├─ (if --register) phase_register(manifest_path, contact_email, ...)
  │     → ROBOT.md.metadata.rrn patched
  │     → status=ok | failed (network, 4xx)
  │
  ├─ (unless --no-install-mcp) phase_install_mcp(manifest_path)
  │     → ~/.claude.json updated
  │     → status=ok | failed (claude not in PATH) | ok ("already registered")
  │
  ├─ (unless --no-install-skill) phase_install_skill()
  │     → ~/.claude/skills/using-robot-md/
  │     → status=ok | failed (perms)
  │
  ├─ (unless --no-calibrate or --no-sign) phase_calibrate_sign(manifest_path)
  │     → ROBOT.md.physics.kinematics[].encoder_sign patched
  │     → status=ok | skipped (no TTY, no hw, operator declined)
  │             | failed (bus error, ctrl-c during motion)
  │
  └─ (unless --no-calibrate) phase_calibrate_zero(manifest_path)
        → ROBOT.md.physics.kinematics[].zero_pose_steps patched
        → status=ok | skipped (no TTY, no hw, operator declined)
                | failed (bus error)
```

Phase 1 rewrites the whole manifest from the preset. Subsequent phases patch individual frontmatter fields in place, preserving YAML comments (the existing `calibrate.py` already does this — reuse that path).

Order rationale:

- **MCP + skill before calibration**: MCP and skill install are fast, safe, and don't need hardware. If the operator decides to ctrl-c somewhere in calibration, the agent environment is still wired up.
- **Sign before zero**: sign calibration wiggles each joint from the current pose; zero calibration reads a single pose. Running sign first means zero is read from a known-direction state. (If `--no-sign` is passed, zero proceeds alone — no dependency.)
- **Register before MCP**: optional, and mints the RRN referenced in the manifest that the MCP server reads.

## Error handling

### Pre-flight for calibration phases

Before prompting Y/n for sign or zero calibration, each phase:

1. Checks `sys.stdin.isatty()`. If False, return `status="skipped"`, `message="no TTY; re-run with --wizard or run 'robot-md calibrate' separately"`.
2. Probes the feetech port declared in `drivers[]`. If the port does not exist or the first servo does not respond, return `status="skipped"`, `message="no hardware detected on <port>; plug the arm in and run 'robot-md calibrate' separately"`.

This keeps CI / headless / hardware-absent runs clean — they see `skipped` lines rather than errors.

### Fatal vs. non-fatal

- **Fatal (exit nonzero)**: `phase_write_manifest` raises. Nothing else can proceed if the manifest isn't on disk.
- **Non-fatal**: every other phase returning `failed` or `skipped` is tallied and the flow continues.

Exit code is 0 if phase 1 succeeded, regardless of the status of phases 2–6. This matches the brainstorming decision (option C, mixed).

### Operator ctrl-c

- During a Y/n prompt: treat as a `no` answer; return `skipped` with `message="operator aborted"`.
- During a motion phase (mid-sign-cal): return `failed` with a clear message. Torque-off is the responsibility of `cli_calibrate_sign`'s existing `finally` block. Flow continues to the next phase.

### Final tally

At the end of `default_flow`, print one line per phase:

```
✓ manifest          wrote ROBOT.md (preset so-arm101)
✓ register          minted RRN-ABC123456789 at rcan.dev
✓ install-mcp       registered 'robot-md-bob' in local config
✓ install-skill     installed at ~/.claude/skills/using-robot-md/
- sign-cal          skipped (operator declined)
✓ zero-cal          patched 6 joints' zero_pose_steps

bob is actuatable. Open Claude Code in this dir:
  cd /home/craigm26/rm-test-bob && claude
```

Legend: `✓` ok, `-` skipped, `✗` failed.

If any phase was `failed` or `skipped`, the tally footer includes a hint for how to run that individual verb later (`robot-md calibrate --zero`, `robot-md install-skill`, `claude mcp add ...`).

## Testing

### Unit tests — phases in isolation

One test file per phase under `cli/tests/unit/test_init_phase_<name>.py`. Mocks:

- `input()` for Y/n prompts
- `subprocess.run()` for `install_mcp`
- The existing `autodetect.scan_system()` fake used by `test_init.py`
- Feetech servo bus via the existing fixture pattern in `test_calibrate.py`

Each phase test asserts the `PhaseResult` shape for the three statuses: `ok`, `skipped`, `failed`.

### Integration tests — orchestrator

`cli/tests/integration/test_init_default_flow.py`:

- All phases mocked. Drive `init.default_flow(...)` with various flag combinations.
- Assertions: phases called in documented order; `--no-install-mcp` skips phase 3; `--non-interactive` skips phases 3–6; phase-1 failure raises and orchestrator exits nonzero; phase-2-to-6 failures do not abort.
- Tally output is regression-tested against a golden string per scenario.

### Escape-hatch compat test

`cli/tests/unit/test_init_non_interactive.py`:

Verifies `robot-md init bob --preset so-arm101 --non-interactive` produces exactly what today's `quick()` produces (manifest only, no prompts). Guards against breaking scripted callers.

### Hardware smoke test (opt-in)

`cli/tests/hardware/test_init_e2e_feetech.py`:

- Gated by env var `ROBOT_MD_HARDWARE=1`. Not run in default CI.
- Runs `init.default_flow()` against a real plugged-in arm in a tmp dir.
- Verifies: ROBOT.md written; `zero_pose_steps` patched to the reading from the connected arm; at least one joint's `encoder_sign` field is non-default.
- Cleans up: removes tmp dir, does not mint a real RRN (uses a dry-run register flag if the register path is exercised at all — spec says leave `--register` off for this test).

### Existing tests carried forward

- `test_init.py` gets renamed methods: `test_quick_*` → `test_non_interactive_*`. Same inputs, same outputs.
- `test_calibrate.py` unchanged; the phase wrappers call the same `cli_calibrate_*` functions.
- `test_claude_md.py` updated to verify the refreshed template lists `execute_capability`, `estop`, `execute_task`.

## Documentation changes

1. README hero section: the "Install" / "Adopt it for your robot (60 seconds)" block gets a second paragraph describing the new default behavior. The shell example stays the same.
2. `docs/getting-started-claude-code.md`: walk-through updated — after `init`, the operator can type a motion sentence in a fresh session. Describe the Y/n prompts. Document `--no-calibrate`, `--non-interactive` for CI.
3. `CHANGELOG.md`: new minor version entry (target v0.5.0) — "feat(init): one-command actuatable setup. Default flow now installs MCP, skill, and prompts for zero/sign calibration. `--non-interactive` preserves old behavior."
4. `claude_md.py` template: motion-action row gets the MCP tool name: `| "Pick up the X" / motion | Call mcp__robot-md-<name>__execute_capability. Dry-run first; check hitl_gates for the cap's scope. |`. Also list all six MCP tools instead of only `validate` + `render`.

## Migration and compatibility

- Scripted callers relying on `robot-md init` being non-interactive must add `--non-interactive` (or pass `--no-calibrate --no-install-mcp --no-install-skill`). Document this prominently in the changelog.
- `--wizard` still works; warns once that it's now an alias.
- Today's `robot-md init --preset so-arm101 my-bob` on a headless CI runner: with no TTY, calibration phases auto-skip. MCP install skips if `claude` is not in PATH. Skill install runs (no hardware needed). Net change: `~/.claude.json` may be modified on CI — this is the main compat risk. The spec's escape-hatch pattern (`--non-interactive` flag) is the recommended CI invocation.

## Out of scope

- Hand-eye / intrinsic calibration inside init.
- Claude Desktop / Cursor / Zed MCP registration (future `--host` flag).
- Non-feetech calibration drivers.
- Auto-starting the dashboard (`robot-md dashboard serve`) — remains a separate verb.
- Changing the `ROBOT_MD_DASHBOARD_DISABLED` env var semantics.
- Refactoring `autodetect.py` or the preset-matching heuristic.

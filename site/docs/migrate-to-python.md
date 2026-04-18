# Migrating from `robot-md-mcp@0.1.x` (Node) to `robot-md` (Python)

As of v0.3.0, the MCP server ships as part of the Python `robot-md` package. The npm `robot-md-mcp@0.2.0` is a migration stub that prints this message and exits non-zero.

## Why

- Python backends can drive `/dev/ttyACM*` servos and `depthai` cameras in-process instead of shelling out.
- One installation surface — the same `robot-md` that validates your manifest now serves it.
- New tools (`estop`, `execute_capability`, `execute_task`) require the in-process backend.

## Migration in three steps

**1. Install `robot-md` via pipx or uv:**

```
pipx install robot-md
# or
uv tool install robot-md
```

For the reference `feetech + depthai` backend:

```
pipx install "robot-md[feetech-depthai]"
```

**2. Update the Claude Code MCP registration:**

```
claude mcp remove robot-md
claude mcp add robot-md -- robot-md-mcp /path/to/ROBOT.md
```

**3. Verify:**

```
robot-md validate /path/to/ROBOT.md
```

If that passes, the MCP will come up cleanly the next time Claude Code starts.

## What changes

| Area | Before (v0.1.x npm) | After (v0.3.0 Python) |
|---|---|---|
| `render` tool | same | same |
| `validate` tool | errors only | errors + warnings (null intrinsic, deprecations) |
| `estop` tool | — | new, sets process-wide software E-stop |
| `execute_capability` tool | — | new, deterministic primitive with HITL gates |
| `execute_task` tool | — | new, NL prompt → planner → capability sequence |
| Schema | v1 (singular `physics.solver.camera`) | v1 (cameras[] + per-stream intrinsics; singular auto-upgraded) |

## What if I need the old behaviour?

Pin `robot-md-mcp@0.1.3` in your `claude mcp add` command — it's still on npm and won't be removed. It will not get new features or bug fixes.

## Troubleshooting

**"command not found: robot-md-mcp"** — the Python install didn't add `~/.local/bin` (pipx) or `~/.cargo/bin` (uv tool) to PATH. Either prepend the right dir to PATH or use the absolute path in `claude mcp add`.

**Validation errors after install** — compare the new validator's `warnings` list. Many previously-silent issues (null camera intrinsics on the primary stream, legacy singular `camera` block) now surface as warnings. Fix or run `robot-md calibrate-intrinsic` as applicable.

**`execute_task` returns `no_planner_declared`** — your ROBOT.md needs a `brain.planning` block naming a provider + model. Example:

```yaml
brain:
  planning:
    provider: anthropic
    model: claude-opus-4-7
    confidence_gate: 0.6
```

Set `ANTHROPIC_API_KEY` in the environment where the MCP server runs.

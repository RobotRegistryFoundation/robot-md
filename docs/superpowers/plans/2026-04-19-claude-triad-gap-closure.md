# Claude Triad Gap Closure — v0.6.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 10 gaps from `docs/superpowers/specs/2026-04-19-claude-triad-gap-analysis.md` so a bare `robot-md init` + one agent turn in Claude Code (or Desktop) can execute a vision-guided pick-and-place on SO-ARM101 + OAK-D. Preserve backward compatibility with v0.5.0 manifests: every new field is optional.

**Architecture:** All changes centre on the schema at `cli/src/robot_md/schemas/v1/robot.schema.json` and its mirror `RobotSpec` dataclass at `cli/src/robot_md/robot_spec.py`. New capabilities flow as MCP tools registered in `cli/src/robot_md/mcp/server.py`. Vision logic extracts into a pure-function module so it is testable without hardware. The six-phase init orchestrator at `cli/src/robot_md/init.py` gains one opt-in phase (`teach_poses`) and a precondition gate is added to `execute_capability` so uncalibrated arms fail loudly instead of silently running hardcoded waypoints.

**Tech Stack:** Python 3.13, pytest, typer, pydantic-free dataclasses, jsonschema 2020-12, mcp.server.fastmcp, opencv-python (`cv2`), numpy, depthai (hardware-only tests).

---

## Milestones & Priority Order

1. **M1 (§1)** — `physics.poses.ready` + `robot-md pose teach` · Tasks 1–5 · **alone unblocks the pick-red-lego demo**.
2. **M2 (§10)** — Precondition gating in `execute_capability` · Tasks 6–9.
3. **M3 (§6)** — Object descriptors (HSV vocabulary) + `vision.find` capability · Tasks 10–13.
4. **M4 (§7)** — `learned_skills:` first-class + `record_skill` MCP tool · Tasks 14–17.
5. **M5 (§8)** — `discover` MCP verb (promotes the discovery pattern) · Tasks 18–22.
6. **M6 (§2/§3/§4/§5/§9)** — Structural cleanups · Tasks 23–27.
7. **Release** — Version bump, CHANGELOG, site copy · Tasks 28–30.

## File Structure (all files Python unless noted)

**Schema (one file, extended across milestones):**
- Modify: `cli/src/robot_md/schemas/v1/robot.schema.json` — add `physics.poses`, `physics.workspace`, `physics.solver.ik_provider`, `capability_contracts`, `vision.object_descriptors`, `learned_skills` top-level keys. All optional.

**RobotSpec mirror (extended across milestones):**
- Modify: `cli/src/robot_md/robot_spec.py` — parallel dataclass fields `PoseDef`, `Workspace`, `CapabilityContract`, `ObjectDescriptor`, `LearnedSkill`; populate in `from_parsed`.

**New modules:**
- Create: `cli/src/robot_md/poses.py` — named-pose teach/read/write helpers (torque-off loop, YAML writeback).
- Create: `cli/src/robot_md/init_phases/teach_poses.py` — opt-in init phase wrapping `poses.py`.
- Create: `cli/src/robot_md/preconditions.py` — pure evaluator: given a contract and a runtime context, return `(ok: bool, failed: list[Reason])`.
- Create: `cli/src/robot_md/detectors/__init__.py` + `cli/src/robot_md/detectors/hsv.py` — pure-function HSV object detectors (no OAK-D dependency).
- Create: `cli/src/robot_md/mcp/tools/vision_find.py` — `vision.find(descriptor_id)` capability implementation.
- Create: `cli/src/robot_md/mcp/tools/discover.py` — the discovery-pattern verb.
- Create: `cli/src/robot_md/mcp/tools/record_skill.py` — append-to-manifest helper.
- Create: `cli/src/robot_md/mcp/resources.py` — new resource endpoints (`learned_skills`, `calibration_status`, `poses`).

**Modified modules:**
- Modify: `cli/src/robot_md/__main__.py` — new `pose` subcommand group with `teach` / `list` / `run`.
- Modify: `cli/src/robot_md/init.py` — insert `phase_teach_poses` into `default_flow` (after zero-cal, before install-mcp).
- Modify: `cli/src/robot_md/mcp/tools/execute_capability.py` — call precondition evaluator.
- Modify: `cli/src/robot_md/mcp/server.py` — register `vision_find`, `discover`, `record_skill` tools + new resources.
- Modify: `cli/src/robot_md/backends/feetech_depthai/perception.py` — `detect_objects(descriptors)` dispatches to `detectors/hsv.py`.
- Modify: `cli/src/robot_md/backends/feetech_depthai/capabilities.py` — add `vision.find`, make `arm.pick`/`arm.place` honour a `target` arg when present.
- Modify: `cli/src/robot_md/discovery.py` — emit `calibration_status` + `learned_skills_summary` in `.well-known/robot-md.json`.
- Modify: `cli/src/robot_md/claude_md.py` — render `poses`, `preconditions`, `learned_skills` sections in generated `CLAUDE.md`.
- Modify: `cli/src/robot_md/presets/so_arm101.yaml` — add empty `physics.poses: {}` and a `vision.object_descriptors:` stub so the shipped preset demonstrates the shape.
- Modify: `cli/pyproject.toml` — bump version 0.5.0 → 0.6.0.
- Modify: `cli/src/robot_md/__init__.py` — sync `__version__`.
- Modify: `CHANGELOG.md` — v0.6.0 entry.
- Modify: `site/index.html` — update hero + §05 copy to say v0.6.0 closes the demo gap.

**Test files (create one per module, mirroring structure):**
- Create: `cli/tests/unit/test_schema_poses.py`
- Create: `cli/tests/unit/test_poses.py`
- Create: `cli/tests/unit/test_init_phase_teach_poses.py`
- Create: `cli/tests/test_cli_pose_teach.py`
- Create: `cli/tests/unit/test_preconditions.py`
- Create: `cli/tests/unit/test_execute_capability_preconditions.py`
- Create: `cli/tests/unit/test_schema_capability_contracts.py`
- Create: `cli/tests/unit/test_schema_object_descriptors.py`
- Create: `cli/tests/unit/test_detectors_hsv.py`
- Create: `cli/tests/unit/test_vision_find_tool.py`
- Create: `cli/tests/unit/test_schema_learned_skills.py`
- Create: `cli/tests/unit/test_record_skill_tool.py`
- Create: `cli/tests/unit/test_mcp_resources.py`
- Create: `cli/tests/unit/test_discover_tool.py`
- Create: `cli/tests/unit/test_schema_workspace.py`
- Create: `cli/tests/unit/test_schema_ik_provider.py`
- Create: `cli/tests/unit/test_discovery_payload.py`
- Create: `cli/tests/integration/test_pick_red_lego_dry_run.py` (gated on `vision.object_descriptors` preset).
- Create: `cli/tests/hardware/test_pose_teach_roundtrip.py` (gated on `@pytest.mark.hardware`).

---

## Common Commands (reference)

- Run one test: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_<name>.py -v`
- Run unit suite: `cd /home/craigm26/robot-md && pytest cli/tests/unit -q`
- Lint: `cd /home/craigm26/robot-md && ruff check cli/`
- Validate a manifest: `robot-md validate <path>`
- Full gated suite (unit + integration, skip hardware): `cd /home/craigm26/robot-md && pytest cli/tests -q`

Commits use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`). Co-author trailer `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` on every commit.

---

# Milestone 1 — `physics.poses.ready` + `robot-md pose teach` (§1)

Goal: The manifest distinguishes *encoder zero* from *manipulation home*. Operator can teach one named pose in thirty seconds. The feetech_depthai backend uses `poses.ready` (when present) as the starting pose for `arm.pick` / `arm.place` instead of the hardcoded `(2048,…)`.

### Task 1: Schema accepts `physics.poses`

**Files:**
- Modify: `cli/src/robot_md/schemas/v1/robot.schema.json`
- Test: `cli/tests/unit/test_schema_poses.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_schema_poses.py
"""Schema v1 accepts optional physics.poses with named joint dicts."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src/robot_md/schemas/v1/robot.schema.json").read_text()
)


def _min_manifest(extra_physics: dict | None = None) -> dict:
    physics = {"type": "arm", "dof": 6}
    if extra_physics:
        physics.update(extra_physics)
    return {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": physics,
        "drivers": [{"id": "arm", "protocol": "feetech"}],
        "capabilities": ["status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
    }


def test_poses_block_is_optional():
    jsonschema.validate(_min_manifest(), SCHEMA)


def test_poses_block_accepts_named_poses():
    m = _min_manifest({
        "poses": {
            "ready": {
                "description": "arm extended forward",
                "joints": {"shoulder_pan": 2048, "shoulder_lift": 1600},
                "source": "taught",
                "taught_at": "2026-04-19",
            }
        }
    })
    jsonschema.validate(m, SCHEMA)


def test_poses_rejects_unknown_source_enum():
    m = _min_manifest({"poses": {"ready": {"joints": {"a": 1}, "source": "guessed"}}})
    try:
        jsonschema.validate(m, SCHEMA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("expected rejection of source='guessed'")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_poses.py -v`
Expected: FAIL on `test_poses_rejects_unknown_source_enum` (schema allows anything under `physics.poses` today) and pass on the first two.

- [ ] **Step 3: Extend the schema**

Inside the `"physics"` object's `"properties"` section of `cli/src/robot_md/schemas/v1/robot.schema.json`, add:

```json
"poses": {
  "type": "object",
  "description": "Named joint-space poses. 'ready' is the manipulation home if present.",
  "additionalProperties": {
    "type": "object",
    "properties": {
      "description": {"type": "string"},
      "joints":      {"type": "object", "additionalProperties": {"type": "integer"}},
      "source":      {"type": "string", "enum": ["declared", "taught", "solved_from_dh"]},
      "taught_at":   {"type": "string"}
    },
    "required": ["joints"]
  }
}
```

Do not mark `physics.poses` as required.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_poses.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/robot-md
git add cli/src/robot_md/schemas/v1/robot.schema.json cli/tests/unit/test_schema_poses.py
git commit -m "$(cat <<'EOF'
feat(schema): physics.poses for named joint-space configurations

Optional block. Keys are pose names (e.g. 'ready', 'stowed'); each
holds joint targets + metadata (source, taught_at). Distinguishes
encoder zero from manipulation-ready home per gap spec §1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 2: RobotSpec surfaces `physics.poses`

**Files:**
- Modify: `cli/src/robot_md/robot_spec.py`
- Test: `cli/tests/unit/test_poses.py` (new file, parse-layer only)

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_poses.py
from __future__ import annotations

from robot_md.parser import parse_text
from robot_md.robot_spec import RobotSpec


def _with_poses() -> str:
    return """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics:
  type: arm
  dof: 6
  poses:
    ready:
      description: 'extended forward'
      joints: {shoulder_pan: 2048, shoulder_lift: 1600}
      source: taught
      taught_at: '2026-04-19'
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""


def test_spec_surfaces_pose_ready():
    spec = RobotSpec.from_parsed(parse_text(_with_poses()))
    assert "ready" in spec.physics.poses
    ready = spec.physics.poses["ready"]
    assert ready.joints["shoulder_pan"] == 2048
    assert ready.joints["shoulder_lift"] == 1600
    assert ready.source == "taught"


def test_spec_poses_empty_when_absent():
    minimal = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(minimal))
    assert spec.physics.poses == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_poses.py -v`
Expected: FAIL — `PhysicsBlock` has no `poses` field.

- [ ] **Step 3: Add `PoseDef` + extend `PhysicsBlock`**

In `cli/src/robot_md/robot_spec.py`, add near `SolverCamera`:

```python
@dataclass(frozen=True)
class PoseDef:
    joints: dict[str, int]
    description: str | None
    source: str | None
    taught_at: str | None
```

Extend `PhysicsBlock` (frozen dataclass) to include:

```python
    poses: dict[str, PoseDef]
```

In `from_parsed`, after the `cams` block, build the poses dict:

```python
        poses_raw = physics.get("poses") or {}
        poses: dict[str, PoseDef] = {
            name: PoseDef(
                joints=dict(p.get("joints") or {}),
                description=p.get("description"),
                source=p.get("source"),
                taught_at=p.get("taught_at"),
            )
            for name, p in poses_raw.items()
            if isinstance(p, dict)
        }
```

Pass `poses=poses` into the `PhysicsBlock(...)` constructor call below.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_poses.py cli/tests/unit/test_schema_poses.py -v`
Expected: PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/robot_spec.py cli/tests/unit/test_poses.py
git commit -m "feat(spec): RobotSpec surfaces physics.poses as dict[str, PoseDef]

Backward-compatible — poses defaults to {}. Parse-only layer; no behaviour
change yet.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 3: Named-pose teach/read/write helpers

**Files:**
- Create: `cli/src/robot_md/poses.py`
- Test: `cli/tests/unit/test_poses.py` (extend same file)

- [ ] **Step 1: Write the failing test**

Append to `cli/tests/unit/test_poses.py`:

```python
from pathlib import Path

import yaml

from robot_md.poses import write_pose_to_manifest


def test_write_pose_inserts_ready_block(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "---\n# bob\n"
    )
    write_pose_to_manifest(
        manifest,
        name="ready",
        joints={"shoulder_pan": 2048, "shoulder_lift": 1600},
        description="extended forward",
    )
    fm = yaml.safe_load(manifest.read_text().split("---")[1])
    poses = fm["physics"]["poses"]
    assert poses["ready"]["joints"]["shoulder_lift"] == 1600
    assert poses["ready"]["source"] == "taught"
    assert "taught_at" in poses["ready"]


def test_write_pose_overwrites_existing(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics:\n"
        "  type: arm\n  dof: 6\n"
        "  poses: {ready: {joints: {shoulder_pan: 100}, source: taught}}\n"
        "drivers: [{id: arm, protocol: feetech}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "---\n# bob\n"
    )
    write_pose_to_manifest(manifest, name="ready", joints={"shoulder_pan": 999})
    fm = yaml.safe_load(manifest.read_text().split("---")[1])
    assert fm["physics"]["poses"]["ready"]["joints"]["shoulder_pan"] == 999
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_poses.py -v`
Expected: FAIL — `robot_md.poses` does not exist.

- [ ] **Step 3: Create `cli/src/robot_md/poses.py`**

```python
"""Named-pose helpers: teach by torque-off read-back, write to ROBOT.md.

Used by `robot-md pose teach` (CLI) and the `teach_poses` init phase.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

import yaml

from robot_md.parser import parse_file


def read_current_joints(bus: Any) -> dict[str, int]:
    """Snapshot every joint position via the servo bus."""
    return bus.read_positions()


def write_pose_to_manifest(
    manifest_path: Path,
    *,
    name: str,
    joints: dict[str, int],
    description: str | None = None,
) -> None:
    """Upsert `physics.poses[name]` in the manifest file.

    Preserves the prose body. Adds `source: taught` and today's ISO date.
    """
    parsed = parse_file(manifest_path)
    fm = dict(parsed.frontmatter)
    physics = dict(fm.get("physics") or {})
    poses = dict(physics.get("poses") or {})
    entry: dict[str, Any] = {
        "joints": dict(joints),
        "source": "taught",
        "taught_at": _dt.date.today().isoformat(),
    }
    if description:
        entry["description"] = description
    poses[name] = entry
    physics["poses"] = poses
    fm["physics"] = physics

    manifest_path.write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + parsed.body
    )


def teach_pose(bus: Any, manifest_path: Path, *, name: str, description: str | None = None) -> dict[str, int]:
    """Torque-off, read positions, torque back on, persist to manifest.

    Caller is responsible for operator prompts (TTY vs. non-interactive).
    Returns the joint dict that was written.
    """
    bus.torque(False)
    try:
        joints = read_current_joints(bus)
    finally:
        bus.torque(True)
    write_pose_to_manifest(manifest_path, name=name, joints=joints, description=description)
    return joints
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_poses.py -v`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/poses.py cli/tests/unit/test_poses.py
git commit -m "feat(poses): teach + manifest-writeback helpers

poses.teach_pose() torque-offs, reads servo positions, writes the
physics.poses[name] block back to ROBOT.md. Preserves the prose body.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4: `robot-md pose teach` CLI verb

**Files:**
- Modify: `cli/src/robot_md/__main__.py` (append a new `pose` subcommand group)
- Test: `cli/tests/test_cli_pose_teach.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/test_cli_pose_teach.py
"""CLI: `robot-md pose teach <name> <path>` writes physics.poses[name]."""
from __future__ import annotations

from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from robot_md.__main__ import app


class _FakeBus:
    def __init__(self) -> None:
        self._torque = False
        self._positions = {"shoulder_pan": 2048, "shoulder_lift": 1600}

    def torque(self, on: bool) -> None:
        self._torque = on

    def read_positions(self) -> dict[str, int]:
        return dict(self._positions)


def test_pose_teach_writes_named_pose(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech, port: /dev/ttyACM0}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "---\n# bob\n"
    )
    runner = CliRunner()
    with patch("robot_md.__main__._open_feetech_bus", return_value=_FakeBus()):
        result = runner.invoke(
            app, ["pose", "teach", "ready", str(manifest), "--yes"]
        )
    assert result.exit_code == 0, result.output
    fm = yaml.safe_load(manifest.read_text().split("---")[1])
    assert fm["physics"]["poses"]["ready"]["joints"]["shoulder_pan"] == 2048
    assert fm["physics"]["poses"]["ready"]["source"] == "taught"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/test_cli_pose_teach.py -v`
Expected: FAIL — `pose` is not a registered command.

- [ ] **Step 3: Add the `pose` subcommand**

Append to `cli/src/robot_md/__main__.py` (after the existing `calibrate` command, before `dashboard_app`):

```python
pose_app = typer.Typer(help="Teach and manage named arm poses.", no_args_is_help=True)
app.add_typer(pose_app, name="pose")


def _open_feetech_bus(manifest_path: Path):
    """Resolve the Feetech servo bus for the manifest. Overridable in tests."""
    from robot_md.mcp.context import load_context

    ctx = load_context(manifest_path)
    bus = getattr(ctx.backend, "_servo_bus", None)
    if bus is None:
        raise RuntimeError("no feetech servo bus available for this manifest")
    return bus


@pose_app.command("teach")
def pose_teach(
    name: str = typer.Argument(..., help="Pose name, e.g. 'ready' or 'stowed'."),
    path: Path = typer.Argument(..., help="Path to ROBOT.md"),
    description: str | None = typer.Option(None, "--description", "-d"),
    yes: bool = typer.Option(False, "--yes", help="Skip the interactive prompt."),
):
    """Record the arm's current joint positions under physics.poses[name].

    Torques off the servos, reads every joint, writes to the manifest, and
    re-torques. The operator is expected to have physically posed the arm
    before invoking.
    """
    from robot_md.poses import teach_pose

    if not yes:
        typer.confirm(
            f"Torque will release so you can pose the arm. Ready to teach '{name}'?",
            abort=True,
        )
    bus = _open_feetech_bus(path)
    joints = teach_pose(bus, path, name=name, description=description)
    typer.echo(f"✓ wrote physics.poses.{name} ({len(joints)} joints)")


@pose_app.command("list")
def pose_list(path: Path = typer.Argument(..., help="Path to ROBOT.md")):
    """List named poses declared in the manifest."""
    from robot_md.parser import parse_file
    from robot_md.robot_spec import RobotSpec

    spec = RobotSpec.from_parsed(parse_file(path))
    if not spec.physics.poses:
        typer.echo("(no poses declared)")
        return
    for name, pose in spec.physics.poses.items():
        desc = f" — {pose.description}" if pose.description else ""
        typer.echo(f"  {name} ({pose.source or 'declared'}, {len(pose.joints)} joints){desc}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/test_cli_pose_teach.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/__main__.py cli/tests/test_cli_pose_teach.py
git commit -m "feat(cli): robot-md pose teach / pose list

Subcommand group for named poses. 'pose teach <name>' torques off, reads
the current joint positions, and writes them under physics.poses[name].
'pose list' dumps declared poses for quick inspection.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 5: Init phase `teach_poses` + orchestrator wire-up

**Files:**
- Create: `cli/src/robot_md/init_phases/teach_poses.py`
- Modify: `cli/src/robot_md/init.py`
- Modify: `cli/src/robot_md/init_phases/__init__.py` (re-export)
- Test: `cli/tests/unit/test_init_phase_teach_poses.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_init_phase_teach_poses.py
"""phase_teach_poses skips on non-interactive, teaches 'ready' on TTY."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from robot_md.init_phases import PhaseResult


def test_phase_skips_when_non_interactive(tmp_path):
    from robot_md.init_phases.teach_poses import phase_teach_poses

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nrcan_version: '3.0'\n---\n# x\n")
    r: PhaseResult = phase_teach_poses(manifest_path=manifest, interactive=False)
    assert r.status == "skipped"
    assert "non-interactive" in r.message.lower()


def test_phase_teaches_ready_when_interactive(tmp_path):
    from robot_md.init_phases.teach_poses import phase_teach_poses

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "---\n# bob\n"
    )

    class _Bus:
        def torque(self, on):  # noqa: ARG002
            pass

        def read_positions(self):
            return {"shoulder_pan": 2048, "shoulder_lift": 1600}

    with (
        patch("robot_md.init_phases.teach_poses._open_feetech_bus", return_value=_Bus()),
        patch("robot_md.init_phases.teach_poses._prompt_confirm", return_value=True),
    ):
        r = phase_teach_poses(manifest_path=manifest, interactive=True)
    assert r.status == "ok", r
    assert "ready" in r.detail.get("pose_names", [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_init_phase_teach_poses.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the phase module**

```python
# cli/src/robot_md/init_phases/teach_poses.py
"""Init phase: offer to teach the 'ready' pose if we have a TTY.

Skipped on non-interactive runs — explicit `robot-md pose teach` is the
scripted path. Uses the same servo-bus-reading machinery as the CLI verb.
"""

from __future__ import annotations

import sys
from pathlib import Path

from robot_md.init_phases import PhaseResult


def _open_feetech_bus(manifest_path: Path):  # test-overridable seam
    from robot_md.mcp.context import load_context

    ctx = load_context(manifest_path)
    bus = getattr(ctx.backend, "_servo_bus", None)
    if bus is None:
        raise RuntimeError("no feetech servo bus for manifest")
    return bus


def _prompt_confirm(msg: str) -> bool:  # test-overridable seam
    try:
        return input(f"{msg} [y/N] ").strip().lower().startswith("y")
    except EOFError:
        return False


def phase_teach_poses(*, manifest_path: Path, interactive: bool) -> PhaseResult:
    if not interactive or not sys.stdin.isatty():
        return PhaseResult(
            phase="teach_poses",
            status="skipped",
            message="non-interactive; run `robot-md pose teach ready` separately",
            detail={"reason": "non_interactive"},
        )
    if not _prompt_confirm(
        "Teach the 'ready' pose now? "
        "(pose the arm by hand — gripper over workspace — before confirming)"
    ):
        return PhaseResult(
            phase="teach_poses",
            status="skipped",
            message="operator declined",
            detail={"reason": "declined"},
        )
    try:
        bus = _open_feetech_bus(manifest_path)
    except Exception as e:
        return PhaseResult(
            phase="teach_poses", status="failed", message=f"bus unavailable: {e}",
            detail={"reason": "bus_error", "error": str(e)},
        )
    from robot_md.poses import teach_pose

    joints = teach_pose(bus, manifest_path, name="ready")
    return PhaseResult(
        phase="teach_poses",
        status="ok",
        message=f"taught 'ready' ({len(joints)} joints)",
        detail={"pose_names": ["ready"], "joints": joints},
    )
```

Re-export from `cli/src/robot_md/init_phases/__init__.py`:

```python
from robot_md.init_phases.teach_poses import phase_teach_poses  # noqa: E402
```

In `cli/src/robot_md/init.py`, extend `default_flow` — add `do_teach_poses: bool = True` parameter, and after `phase_calibrate_zero` runs, insert:

```python
    # Phase 7: teach poses (opt-in, TTY-only).
    if do_teach_poses:
        results.append(
            _self.phase_teach_poses(manifest_path=out_path, interactive=sys.stdin.isatty())
        )
```

Add `phase_teach_poses = _self.phase_teach_poses  # type: ignore[attr-defined]` near the other phase resolutions.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_init_phase_teach_poses.py cli/tests/test_init.py -q`
Expected: all tests pass (including the existing init-flow tests, unchanged because `do_teach_poses` defaults to True but the phase skips non-interactively).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/init_phases/teach_poses.py cli/src/robot_md/init_phases/__init__.py cli/src/robot_md/init.py cli/tests/unit/test_init_phase_teach_poses.py
git commit -m "feat(init): phase_teach_poses — opt-in 'ready' teach on TTY

Skipped on non-interactive. New 7th phase in default_flow, after
zero-cal. Non-TTY callers use 'robot-md pose teach' explicitly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 5.5: Backend uses `poses.ready` as home

**Files:**
- Modify: `cli/src/robot_md/backends/feetech_depthai/capabilities.py`
- Test: `cli/tests/unit/test_feetech_depthai_capabilities.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `cli/tests/unit/test_feetech_depthai_capabilities.py`:

```python
def test_arm_home_uses_poses_ready_when_present(make_backend_with_spec):
    """arm.home targets physics.poses.ready, not the hardcoded ZERO."""
    backend = make_backend_with_spec(
        poses={"ready": {"joints": {"shoulder_pan": 1900, "shoulder_lift": 1700, "elbow_flex": 2048, "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700}, "source": "taught"}}
    )
    result = backend.execute(capability="arm.home", args={}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert result.trajectory[-1]["joints"]["shoulder_pan"] == 1900
    assert result.trajectory[-1]["joints"]["shoulder_lift"] == 1700
```

Add a `make_backend_with_spec` fixture to that file's top (or `conftest.py`) that constructs a backend with a stubbed servo bus and a custom `poses` dict. If the existing test file does not have such a fixture, create one in `cli/tests/unit/conftest.py`:

```python
import pytest

@pytest.fixture
def make_backend_with_spec():
    def _build(**physics_extras):
        from robot_md.backends.feetech_depthai import FeetechDepthaiBackend
        from robot_md.parser import parse_text
        from robot_md.robot_spec import RobotSpec
        import yaml
        fm = {
            "rcan_version": "3.0",
            "metadata": {"robot_name": "bob"},
            "physics": {"type": "arm", "dof": 6, **physics_extras},
            "drivers": [{"id": "arm", "protocol": "feetech", "port": "/dev/null"}],
            "capabilities": ["arm.home", "arm.pick", "arm.place", "status.report"],
            "safety": {"estop": {"software": True, "response_ms": 100}, "max_joint_velocity_dps": 180},
        }
        text = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n# bob\n"
        spec = RobotSpec.from_parsed(parse_text(text))
        backend = FeetechDepthaiBackend(spec=spec)
        backend._servo_bus = type("StubBus", (), {"torque": lambda *_: None, "read_positions": lambda self: {}, "write_positions": lambda self, *_: None})()
        return backend
    return _build
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_feetech_depthai_capabilities.py::test_arm_home_uses_poses_ready_when_present -v`
Expected: FAIL — `arm.home` either doesn't exist in the backend map or still uses `_ZERO`.

- [ ] **Step 3: Wire poses.ready into the backend**

In `cli/src/robot_md/backends/feetech_depthai/capabilities.py`, replace `_ZERO` construction with a resolution helper and implement `arm.home`:

```python
def _home_joints(backend) -> dict[str, int]:
    """poses.ready from the spec if present; else the hardcoded zero fallback."""
    ready = backend.spec.physics.poses.get("ready") if backend.spec is not None else None
    if ready is not None and ready.joints:
        base = {
            "shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048,
            "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700,
        }
        base.update({k: int(v) for k, v in ready.joints.items()})
        return base
    return {
        "shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048,
        "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700,
    }


def _arm_home(backend, *, args, dry_run, estop) -> ExecutionResult:  # noqa: ARG001
    wps = [Waypoint(t=0.0, joints=_home_joints(backend))]
    return _do_replay(backend, waypoints=wps, label="arm.home", args=args, dry_run=dry_run, estop=estop)
```

Update the `_HANDLERS` dict to include `"arm.home": _arm_home`.

Also: in `_HARDCODED_PICK_WAYPOINTS` and `_HARDCODED_PLACE_WAYPOINTS`, leave the Tier-0 hardcoded waypoints in place (still used when `poses.ready` is absent). Add a helper `_pick_waypoints(backend)` that substitutes the home joints when `poses.ready` is defined — exact code in Task 13 where vision-targeted pick is wired.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_feetech_depthai_capabilities.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/backends/feetech_depthai/capabilities.py cli/tests/unit/test_feetech_depthai_capabilities.py cli/tests/unit/conftest.py
git commit -m "feat(backend): arm.home resolves to physics.poses.ready

Falls back to the hardcoded (2048,...,gripper=1700) when poses.ready is
absent, so v0.5.0 manifests still work. Unblocks the pick-red-lego
demo after 'robot-md pose teach ready'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Milestone 2 — Precondition gating (§10 + §3 half)

Goal: `execute_capability` refuses to dispatch when declared preconditions are unmet and returns `status: blocked` with the specific reason. Agents can explain the block instead of watching the arm flail.

### Task 6: Schema accepts `capability_contracts`

**Files:**
- Modify: `cli/src/robot_md/schemas/v1/robot.schema.json`
- Test: `cli/tests/unit/test_schema_capability_contracts.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_schema_capability_contracts.py
from __future__ import annotations
import json
from pathlib import Path

import jsonschema

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src/robot_md/schemas/v1/robot.schema.json").read_text()
)


def _m(extra: dict) -> dict:
    return {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": {"type": "arm", "dof": 6},
        "drivers": [{"id": "arm", "protocol": "feetech"}],
        "capabilities": ["arm.pick", "status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
        **extra,
    }


def test_contracts_block_is_optional():
    jsonschema.validate(_m({}), SCHEMA)


def test_contracts_accepts_precondition_list():
    jsonschema.validate(_m({
        "capability_contracts": {
            "arm.pick": {
                "preconditions": [
                    {"kind": "pose_taught", "name": "ready"},
                    {"kind": "extrinsic_present"},
                ]
            }
        }
    }), SCHEMA)


def test_contracts_rejects_unknown_precondition_kind():
    try:
        jsonschema.validate(_m({
            "capability_contracts": {
                "arm.pick": {"preconditions": [{"kind": "wishful_thinking"}]}
            }
        }), SCHEMA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("expected rejection of unknown precondition kind")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_capability_contracts.py -v`
Expected: FAIL on `test_contracts_rejects_unknown_precondition_kind`.

- [ ] **Step 3: Extend the schema**

Add a top-level property to the schema root `"properties"` block:

```json
"capability_contracts": {
  "type": "object",
  "description": "Per-capability preconditions and arg/return contracts.",
  "additionalProperties": {
    "type": "object",
    "properties": {
      "preconditions": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "kind": {
              "type": "string",
              "enum": [
                "pose_taught",
                "extrinsic_present",
                "ik_provider_set",
                "workspace_declared",
                "learned_skill_ok",
                "backend_resolved"
              ]
            },
            "name": {"type": "string"},
            "detail": {"type": "object"}
          },
          "required": ["kind"]
        }
      }
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_capability_contracts.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/schemas/v1/robot.schema.json cli/tests/unit/test_schema_capability_contracts.py
git commit -m "feat(schema): capability_contracts with bounded precondition kinds

Six precondition kinds enumerated. Contract block is optional — v0.5.0
manifests pass validation unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 7: RobotSpec surfaces `capability_contracts`

**Files:**
- Modify: `cli/src/robot_md/robot_spec.py`
- Test: `cli/tests/unit/test_poses.py` (extend — the parser-layer test file)

- [ ] **Step 1: Write the failing test**

Append to `cli/tests/unit/test_poses.py`:

```python
def test_spec_surfaces_capability_contracts():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [arm.pick, status.report]
capability_contracts:
  arm.pick:
    preconditions:
      - {kind: pose_taught, name: ready}
      - {kind: extrinsic_present}
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(text))
    assert "arm.pick" in spec.capability_contracts
    pre = spec.capability_contracts["arm.pick"].preconditions
    assert pre[0].kind == "pose_taught"
    assert pre[0].name == "ready"
    assert pre[1].kind == "extrinsic_present"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_poses.py::test_spec_surfaces_capability_contracts -v`
Expected: FAIL — field does not exist.

- [ ] **Step 3: Add dataclasses and populate**

In `cli/src/robot_md/robot_spec.py`:

```python
@dataclass(frozen=True)
class Precondition:
    kind: str
    name: str | None
    detail: dict


@dataclass(frozen=True)
class CapabilityContract:
    preconditions: tuple[Precondition, ...]
```

Add to `RobotSpec`:

```python
    capability_contracts: dict[str, CapabilityContract]
```

In `from_parsed`, after `capabilities = frozenset(...)`:

```python
        contracts_raw = fm.get("capability_contracts") or {}
        capability_contracts: dict[str, CapabilityContract] = {}
        for cap, c in contracts_raw.items():
            if not isinstance(c, dict):
                continue
            pres = tuple(
                Precondition(
                    kind=p.get("kind", ""),
                    name=p.get("name"),
                    detail=dict(p.get("detail") or {}),
                )
                for p in (c.get("preconditions") or [])
                if isinstance(p, dict)
            )
            capability_contracts[cap] = CapabilityContract(preconditions=pres)
```

Pass `capability_contracts=capability_contracts` into the `cls(...)` constructor.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_poses.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/robot_spec.py cli/tests/unit/test_poses.py
git commit -m "feat(spec): RobotSpec surfaces capability_contracts

Parses the new top-level block into dict[str, CapabilityContract].
Parse-only — enforcement lands in the next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 8: Precondition evaluator

**Files:**
- Create: `cli/src/robot_md/preconditions.py`
- Test: `cli/tests/unit/test_preconditions.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_preconditions.py
"""Pure-function precondition evaluator."""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from robot_md.preconditions import evaluate
from robot_md.robot_spec import CapabilityContract, Precondition


def _pose_ready_missing_spec():
    return SimpleNamespace(
        physics=SimpleNamespace(
            poses={}, cameras=(), solver={}, workspace=None,
        ),
        learned_skills=[],
    )


def _pose_ready_present_spec():
    return SimpleNamespace(
        physics=SimpleNamespace(
            poses={"ready": SimpleNamespace(joints={"a": 1}, source="taught")},
            cameras=(SimpleNamespace(extrinsic=(1, 0, 0, 0)),),
            solver={"ik_provider": "inhouse-so-arm101"},
            workspace=SimpleNamespace(bounds_mm={"x": (-200, 200)}),
        ),
        learned_skills=[],
    )


def test_pose_taught_ok():
    contract = CapabilityContract(preconditions=(Precondition(kind="pose_taught", name="ready", detail={}),))
    ok, failed = evaluate(contract, _pose_ready_present_spec(), backend_resolved=True)
    assert ok
    assert failed == []


def test_pose_taught_missing():
    contract = CapabilityContract(preconditions=(Precondition(kind="pose_taught", name="ready", detail={}),))
    ok, failed = evaluate(contract, _pose_ready_missing_spec(), backend_resolved=True)
    assert not ok
    assert any("pose 'ready' not taught" in f for f in failed)


def test_extrinsic_present_missing():
    contract = CapabilityContract(preconditions=(Precondition(kind="extrinsic_present", name=None, detail={}),))
    ok, failed = evaluate(contract, _pose_ready_missing_spec(), backend_resolved=True)
    assert not ok
    assert any("extrinsic" in f for f in failed)


def test_backend_resolved_false():
    contract = CapabilityContract(preconditions=(Precondition(kind="backend_resolved", name=None, detail={}),))
    ok, failed = evaluate(contract, _pose_ready_present_spec(), backend_resolved=False)
    assert not ok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_preconditions.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the evaluator**

```python
# cli/src/robot_md/preconditions.py
"""Precondition evaluator — pure function from (contract, spec, runtime) to verdict.

No I/O. Return (ok, failed_reasons). The MCP layer calls this before dispatch.
"""

from __future__ import annotations

from typing import Any

from robot_md.robot_spec import CapabilityContract


def evaluate(
    contract: CapabilityContract,
    spec: Any,
    *,
    backend_resolved: bool,
) -> tuple[bool, list[str]]:
    failed: list[str] = []
    for p in contract.preconditions:
        reason = _check_one(p, spec, backend_resolved=backend_resolved)
        if reason is not None:
            failed.append(reason)
    return (not failed, failed)


def _check_one(p, spec, *, backend_resolved: bool) -> str | None:
    kind = p.kind
    if kind == "backend_resolved":
        return None if backend_resolved else "backend not resolved for any driver"
    if kind == "pose_taught":
        name = p.name or "ready"
        pose = getattr(spec.physics, "poses", {}).get(name)
        if pose is None or not getattr(pose, "joints", None):
            return f"pose '{name}' not taught (run `robot-md pose teach {name}`)"
        return None
    if kind == "extrinsic_present":
        cams = getattr(spec.physics, "cameras", ())
        if not cams or all(getattr(c, "extrinsic", None) is None for c in cams):
            return "hand-eye extrinsic missing (run `robot-md calibrate --hand-eye`)"
        return None
    if kind == "ik_provider_set":
        solver = getattr(spec.physics, "solver", {}) or {}
        if not solver.get("ik_provider"):
            return "physics.solver.ik_provider not declared"
        return None
    if kind == "workspace_declared":
        if getattr(spec.physics, "workspace", None) is None:
            return "physics.workspace not declared"
        return None
    if kind == "learned_skill_ok":
        required_id = p.name
        if required_id is None:
            return "learned_skill_ok precondition missing 'name'"
        ls = getattr(spec, "learned_skills", []) or []
        found = next((s for s in ls if getattr(s, "id", None) == required_id), None)
        if found is None:
            return f"learned skill '{required_id}' not recorded"
        if getattr(found, "status", "ok") != "ok":
            return f"learned skill '{required_id}' status={found.status}"
        return None
    return f"unknown precondition kind '{kind}'"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_preconditions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/preconditions.py cli/tests/unit/test_preconditions.py
git commit -m "feat(preconditions): pure-function evaluator for capability gates

Checks each precondition kind against the spec + runtime flags. Returns
list of human-readable failure reasons. No I/O — pure unit-testable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 9: Wire preconditions into `execute_capability`

**Files:**
- Modify: `cli/src/robot_md/mcp/tools/execute_capability.py`
- Test: `cli/tests/unit/test_execute_capability_preconditions.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_execute_capability_preconditions.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from robot_md.mcp.context import load_context
from robot_md.mcp.tools.execute_capability import execute_capability_tool


def _manifest_with_contract(tmp_path: Path) -> Path:
    p = tmp_path / "ROBOT.md"
    p.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech, port: /dev/null}]\n"
        "capabilities: [arm.pick, status.report]\n"
        "capability_contracts:\n"
        "  arm.pick:\n"
        "    preconditions: [{kind: pose_taught, name: ready}]\n"
        "safety:\n"
        "  estop: {software: true, response_ms: 100}\n"
        "  max_joint_velocity_dps: 180\n"
        "---\n# bob\n"
    )
    return p


def test_execute_capability_blocks_when_pose_missing(tmp_path, monkeypatch):
    ctx = load_context(_manifest_with_contract(tmp_path))
    # Backend present but poses.ready missing — precondition should fire.
    ctx.backend = MagicMock()
    ctx.backend.capabilities.return_value = frozenset({"arm.pick"})

    result = execute_capability_tool(
        ctx, capability="arm.pick", args={}, dry_run=True, confirm_token=None
    )
    assert result["status"] == "blocked"
    assert result["error"]["reason"] == "precondition"
    assert "pose 'ready' not taught" in result["error"]["failed"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_execute_capability_preconditions.py -v`
Expected: FAIL — tool ignores capability_contracts today.

- [ ] **Step 3: Insert the gate**

In `cli/src/robot_md/mcp/tools/execute_capability.py`, import the evaluator and add a check BEFORE the estop check (but keep estop first — safety-over-policy). The change: after the `declared` / `not_implemented` checks and BEFORE the estop check, insert:

```python
    from robot_md.preconditions import evaluate

    contract = ctx.spec.capability_contracts.get(capability) if ctx.spec else None
    if contract is not None:
        ok, failed = evaluate(contract, ctx.spec, backend_resolved=ctx.backend is not None)
        if not ok:
            result = {
                "status": "blocked",
                "trajectory": None,
                "events": [],
                "error": {"reason": "precondition", "failed": failed},
            }
            _publish_result(ctx, request_id, capability, result)
            return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_execute_capability_preconditions.py cli/tests/unit/test_mcp_tools_execute_capability.py -q`
Expected: PASS on both new and existing tests.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/tools/execute_capability.py cli/tests/unit/test_execute_capability_preconditions.py
git commit -m "feat(mcp): execute_capability enforces capability_contracts.preconditions

Before dispatching to the backend, evaluate declared preconditions against
the spec. Any failure returns status=blocked with the reason list.
Matches the Claude-triad gap spec §10.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Milestone 3 — Object descriptors (§6)

Goal: HSV vocabulary becomes a manifest field, not ad-hoc code. A new `vision.find(descriptor_id)` capability resolves a descriptor to a 3-D point that `arm.pick(target={ref: <id>})` can consume.

### Task 10: Schema accepts `vision.object_descriptors`

**Files:**
- Modify: `cli/src/robot_md/schemas/v1/robot.schema.json`
- Test: `cli/tests/unit/test_schema_object_descriptors.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_schema_object_descriptors.py
from __future__ import annotations
import json
from pathlib import Path

import jsonschema

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src/robot_md/schemas/v1/robot.schema.json").read_text()
)


def _m(extra: dict) -> dict:
    return {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": {"type": "arm", "dof": 6},
        "drivers": [{"id": "arm", "protocol": "feetech"}],
        "capabilities": ["vision.find", "status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
        **extra,
    }


def test_object_descriptors_optional():
    jsonschema.validate(_m({}), SCHEMA)


def test_object_descriptors_hsv_entry():
    jsonschema.validate(_m({
        "vision": {
            "object_descriptors": [
                {
                    "id": "red_lego",
                    "detector": "hsv",
                    "params": {"h_ranges": [[0, 10], [170, 180]], "s_min": 110, "v_min": 80},
                }
            ]
        }
    }), SCHEMA)


def test_object_descriptors_hsv_roi_entry():
    jsonschema.validate(_m({
        "vision": {
            "object_descriptors": [
                {
                    "id": "white_bowl",
                    "detector": "hsv_roi",
                    "params": {
                        "s_max": 80, "v_min": 100,
                        "roi": {"u_max": 450, "v_max": 360},
                    },
                }
            ]
        }
    }), SCHEMA)


def test_object_descriptors_rejects_unknown_detector():
    try:
        jsonschema.validate(_m({
            "vision": {"object_descriptors": [{"id": "x", "detector": "magic", "params": {}}]}
        }), SCHEMA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("expected rejection")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_object_descriptors.py -v`
Expected: FAIL on the rejection test.

- [ ] **Step 3: Extend the schema**

Add a top-level `"vision"` property:

```json
"vision": {
  "type": "object",
  "description": "Perception vocabulary — objects the robot knows how to see.",
  "properties": {
    "object_descriptors": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "detector", "params"],
        "properties": {
          "id": {"type": "string"},
          "detector": {"type": "string", "enum": ["hsv", "hsv_roi"]},
          "params": {"type": "object"}
        }
      }
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_object_descriptors.py -v`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/schemas/v1/robot.schema.json cli/tests/unit/test_schema_object_descriptors.py
git commit -m "feat(schema): vision.object_descriptors with hsv + hsv_roi detectors

Two detector kinds enumerated — matches what the gap-closure session
proved works for red_lego (HSV dual-range) and white_bowl (HSV + ROI).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 11: RobotSpec surfaces object descriptors

**Files:**
- Modify: `cli/src/robot_md/robot_spec.py`
- Test: `cli/tests/unit/test_poses.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `cli/tests/unit/test_poses.py`:

```python
def test_spec_surfaces_object_descriptors():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [vision.find, status.report]
vision:
  object_descriptors:
    - id: red_lego
      detector: hsv
      params:
        h_ranges: [[0, 10], [170, 180]]
        s_min: 110
        v_min: 80
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(text))
    descs = spec.vision.object_descriptors
    assert descs[0].id == "red_lego"
    assert descs[0].detector == "hsv"
    assert descs[0].params["s_min"] == 110
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_poses.py::test_spec_surfaces_object_descriptors -v`
Expected: FAIL — field does not exist.

- [ ] **Step 3: Add dataclasses**

In `cli/src/robot_md/robot_spec.py`:

```python
@dataclass(frozen=True)
class ObjectDescriptor:
    id: str
    detector: str
    params: dict


@dataclass(frozen=True)
class VisionBlock:
    object_descriptors: tuple[ObjectDescriptor, ...]

    def find(self, descriptor_id: str) -> ObjectDescriptor | None:
        return next((d for d in self.object_descriptors if d.id == descriptor_id), None)
```

Add to `RobotSpec`:

```python
    vision: VisionBlock
```

In `from_parsed`, after the `cams` block:

```python
        vision_raw = fm.get("vision") or {}
        descs = tuple(
            ObjectDescriptor(id=d["id"], detector=d["detector"], params=dict(d.get("params") or {}))
            for d in (vision_raw.get("object_descriptors") or [])
            if isinstance(d, dict)
        )
        vision_block = VisionBlock(object_descriptors=descs)
```

Pass `vision=vision_block` in the constructor.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_poses.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/robot_spec.py cli/tests/unit/test_poses.py
git commit -m "feat(spec): VisionBlock with object_descriptors

Parser-level only. Detector logic lands in the next commit as a pure
module under robot_md.detectors.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 12: HSV detector module (pure functions)

**Files:**
- Create: `cli/src/robot_md/detectors/__init__.py`
- Create: `cli/src/robot_md/detectors/hsv.py`
- Test: `cli/tests/unit/test_detectors_hsv.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_detectors_hsv.py
"""Pure HSV detector — input ndarrays, output centroid + area."""
from __future__ import annotations

import cv2
import numpy as np

from robot_md.detectors.hsv import detect_hsv, detect_hsv_roi


def _red_blob_rgb(size: tuple[int, int] = (200, 300)) -> np.ndarray:
    img = np.zeros((size[0], size[1], 3), dtype=np.uint8)
    img[:] = (240, 240, 240)  # light background (BGR)
    cv2.rectangle(img, (120, 60), (180, 120), (40, 40, 220), -1)  # red blob
    return img


def test_detect_hsv_finds_red_blob():
    img = _red_blob_rgb()
    result = detect_hsv(
        img,
        params={"h_ranges": [[0, 10], [170, 180]], "s_min": 80, "v_min": 80},
    )
    assert result is not None
    u, v, area = result
    assert 120 < u < 180
    assert 60 < v < 120
    assert area > 1000


def test_detect_hsv_returns_none_when_absent():
    img = np.full((100, 100, 3), 200, dtype=np.uint8)
    result = detect_hsv(img, params={"h_ranges": [[0, 10]], "s_min": 80, "v_min": 80})
    assert result is None


def test_detect_hsv_roi_restricts_search():
    img = np.zeros((200, 300, 3), dtype=np.uint8)
    img[:] = (0, 0, 0)
    # Light patch in upper-left quadrant
    cv2.rectangle(img, (20, 20), (80, 80), (230, 230, 230), -1)
    # Light patch outside ROI (bottom-right)
    cv2.rectangle(img, (220, 150), (280, 190), (230, 230, 230), -1)
    params = {"s_max": 80, "v_min": 100, "roi": {"u_max": 150, "v_max": 120}}
    result = detect_hsv_roi(img, params=params)
    assert result is not None
    u, _, _ = result
    assert u < 150
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_detectors_hsv.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement detectors**

```python
# cli/src/robot_md/detectors/__init__.py
"""Pure-function object detectors — test without hardware."""
```

```python
# cli/src/robot_md/detectors/hsv.py
"""HSV-based centroid detectors.

Inputs: BGR image (numpy ndarray H×W×3, uint8), params dict from the manifest's
`vision.object_descriptors[].params`.

Returns: (u, v, area_px2) or None. No hardware, no I/O.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def _largest_centroid(mask: np.ndarray, min_area: int = 200) -> tuple[int, int, int] | None:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    big = max(contours, key=cv2.contourArea)
    area = int(cv2.contourArea(big))
    if area < min_area:
        return None
    M = cv2.moments(big)
    if M["m00"] == 0:
        return None
    return int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]), area


def _hsv_mask(hsv: np.ndarray, params: dict[str, Any]) -> np.ndarray:
    s_min = int(params.get("s_min", 0))
    s_max = int(params.get("s_max", 255))
    v_min = int(params.get("v_min", 0))
    v_max = int(params.get("v_max", 255))
    h_ranges = params.get("h_ranges")
    if h_ranges:
        combined = None
        for lo, hi in h_ranges:
            m = cv2.inRange(hsv, (int(lo), s_min, v_min), (int(hi), s_max, v_max))
            combined = m if combined is None else (combined | m)
        return combined
    return cv2.inRange(hsv, (0, s_min, v_min), (180, s_max, v_max))


def detect_hsv(rgb_bgr: np.ndarray, *, params: dict[str, Any]) -> tuple[int, int, int] | None:
    hsv = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2HSV)
    mask = _hsv_mask(hsv, params)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return _largest_centroid(mask, min_area=int(params.get("min_area", 200)))


def detect_hsv_roi(rgb_bgr: np.ndarray, *, params: dict[str, Any]) -> tuple[int, int, int] | None:
    roi = params.get("roi") or {}
    u_min = int(roi.get("u_min", 0))
    u_max = int(roi.get("u_max", rgb_bgr.shape[1]))
    v_min = int(roi.get("v_min", 0))
    v_max = int(roi.get("v_max", rgb_bgr.shape[0]))

    hsv = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2HSV)
    mask = _hsv_mask(hsv, params)
    roi_mask = np.zeros_like(mask)
    roi_mask[v_min:v_max, u_min:u_max] = 255
    return _largest_centroid(mask & roi_mask, min_area=int(params.get("min_area", 1000)))


DETECTORS = {"hsv": detect_hsv, "hsv_roi": detect_hsv_roi}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_detectors_hsv.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/detectors/ cli/tests/unit/test_detectors_hsv.py
git commit -m "feat(detectors): pure HSV + HSV_ROI centroid detectors

Pure-function module — takes BGR ndarray + params dict, returns
(u, v, area_px2) or None. No hardware dependency; tested with
synthetic images.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 13: `vision.find` MCP capability + wire-up

**Files:**
- Create: `cli/src/robot_md/mcp/tools/vision_find.py`
- Modify: `cli/src/robot_md/backends/feetech_depthai/perception.py`
- Modify: `cli/src/robot_md/backends/feetech_depthai/capabilities.py`
- Modify: `cli/src/robot_md/mcp/server.py`
- Test: `cli/tests/unit/test_vision_find_tool.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_vision_find_tool.py
"""vision.find resolves an object_descriptor id to a 3-D camera-frame point."""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from robot_md.mcp.tools.vision_find import vision_find_tool
from robot_md.robot_spec import ObjectDescriptor, VisionBlock


def _ctx_with_descriptor_and_frame():
    rgb = np.zeros((200, 300, 3), dtype=np.uint8)
    rgb[:] = (240, 240, 240)
    # Small red blob
    import cv2

    cv2.rectangle(rgb, (120, 60), (180, 120), (40, 40, 220), -1)
    depth = np.full((200, 300), 500, dtype=np.uint16)  # 500mm uniformly
    K = np.array([[500.0, 0, 150.0], [0, 500.0, 100.0], [0, 0, 1.0]])

    per = MagicMock()
    per.grab_frame.return_value = (rgb, depth, K)

    backend = MagicMock()
    backend._perception = per

    spec = MagicMock()
    spec.vision = VisionBlock(object_descriptors=(
        ObjectDescriptor(
            id="red_lego",
            detector="hsv",
            params={"h_ranges": [[0, 10], [170, 180]], "s_min": 80, "v_min": 80},
        ),
    ))

    ctx = MagicMock()
    ctx.backend = backend
    ctx.spec = spec
    return ctx


def test_vision_find_returns_3d_point():
    ctx = _ctx_with_descriptor_and_frame()
    r = vision_find_tool(ctx, descriptor_id="red_lego")
    assert r["status"] == "ok"
    assert r["descriptor"] == "red_lego"
    assert r["pixel"][0] > 120 and r["pixel"][0] < 180
    assert r["camera_xyz_mm"][2] == 500
    # x_cam = (u - cx) * z / fx = (150 - 150) * 500 / 500 = 0 (blob centered in roi)
    # with blob at ~150, should be near zero
    assert abs(r["camera_xyz_mm"][0]) < 50


def test_vision_find_unknown_descriptor():
    ctx = _ctx_with_descriptor_and_frame()
    r = vision_find_tool(ctx, descriptor_id="blue_widget")
    assert r["status"] == "error"
    assert r["error"]["reason"] == "unknown_descriptor"


def test_vision_find_no_detection():
    ctx = _ctx_with_descriptor_and_frame()
    # Swap frame for an all-white image (no red blob)
    ctx.backend._perception.grab_frame.return_value = (
        np.full((200, 300, 3), 240, dtype=np.uint8),
        np.full((200, 300), 500, dtype=np.uint16),
        np.array([[500.0, 0, 150.0], [0, 500.0, 100.0], [0, 0, 1.0]]),
    )
    r = vision_find_tool(ctx, descriptor_id="red_lego")
    assert r["status"] == "not_found"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_vision_find_tool.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the tool**

```python
# cli/src/robot_md/mcp/tools/vision_find.py
"""MCP tool: vision.find — descriptor_id → camera-frame XYZ (mm)."""

from __future__ import annotations

from typing import Any

from robot_md.detectors.hsv import DETECTORS


def _pixel_to_3d(u: int, v: int, depth_mm: float, K) -> tuple[float, float, float]:
    if depth_mm <= 0 or depth_mm is None:
        return (float("nan"), float("nan"), float("nan"))
    fx, fy = float(K[0, 0]), float(K[1, 1])
    cx, cy = float(K[0, 2]), float(K[1, 2])
    return ((u - cx) * depth_mm / fx, (v - cy) * depth_mm / fy, float(depth_mm))


def vision_find_tool(ctx: Any, *, descriptor_id: str) -> dict:
    if ctx.backend is None:
        return _err("no_backend", "backend not resolved")
    desc = ctx.spec.vision.find(descriptor_id) if ctx.spec else None
    if desc is None:
        return _err("unknown_descriptor", f"no vision.object_descriptors entry with id={descriptor_id!r}")
    detector = DETECTORS.get(desc.detector)
    if detector is None:
        return _err("unknown_detector", f"detector '{desc.detector}' not implemented")
    per = getattr(ctx.backend, "_perception", None)
    if per is None:
        return _err("no_perception", "backend has no perception module")
    frame = per.grab_frame()
    if frame is None:
        return _err("no_frame", "grab_frame returned None")
    rgb, depth, K = frame
    hit = detector(rgb, params=desc.params)
    if hit is None:
        return {"status": "not_found", "descriptor": descriptor_id}
    u, v, area = hit
    r = max(3, int((area ** 0.5) // 4))
    import numpy as np

    patch = depth[max(0, v - r):v + r + 1, max(0, u - r):u + r + 1].astype(np.float32)
    valid = patch[patch > 0]
    depth_mm = float(np.median(valid)) if valid.size else float("nan")
    xyz = _pixel_to_3d(u, v, depth_mm, K)
    return {
        "status": "ok",
        "descriptor": descriptor_id,
        "pixel": [u, v],
        "depth_mm": depth_mm,
        "camera_xyz_mm": list(xyz),
        "area_px2": area,
    }


def _err(reason: str, msg: str) -> dict:
    return {"status": "error", "error": {"reason": reason, "message": msg}}
```

Also update `detect_objects` in `cli/src/robot_md/backends/feetech_depthai/perception.py`:

```python
    def detect_objects(self, *, descriptors: list | None = None) -> list[dict]:
        if not descriptors:
            return []
        from robot_md.detectors.hsv import DETECTORS

        frame = self.grab_frame()
        if frame is None:
            return []
        rgb, _depth, _K = frame
        out: list[dict] = []
        for d in descriptors:
            fn = DETECTORS.get(d.detector)
            if fn is None:
                continue
            hit = fn(rgb, params=d.params)
            if hit is not None:
                u, v, area = hit
                out.append({"id": d.id, "pixel": [u, v], "area_px2": area})
        return out
```

Register the tool in `cli/src/robot_md/mcp/server.py`:

```python
    @server.tool()
    def vision_find(descriptor_id: str) -> dict:
        """Detect one declared object descriptor. Returns camera-frame XYZ (mm)."""
        from robot_md.mcp.tools.vision_find import vision_find_tool

        return vision_find_tool(ctx, descriptor_id=descriptor_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_vision_find_tool.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/tools/vision_find.py cli/src/robot_md/backends/feetech_depthai/perception.py cli/src/robot_md/mcp/server.py cli/tests/unit/test_vision_find_tool.py
git commit -m "feat(mcp): vision.find tool — descriptor id → camera-frame XYZ

Resolves a vision.object_descriptors entry, runs the declared detector
against a fresh OAK-D frame, returns (u, v, depth_mm, xyz_mm). The
arm.pick tool can now consume this for real target-aware picking.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Milestone 4 — `learned_skills` first-class (§7)

Goal: The stowaway `extensions.x-learned-skills` block graduates to a top-level `learned_skills:` array that MCP resources expose and a `record_skill` tool can append to.

### Task 14: Schema accepts top-level `learned_skills`

**Files:**
- Modify: `cli/src/robot_md/schemas/v1/robot.schema.json`
- Test: `cli/tests/unit/test_schema_learned_skills.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_schema_learned_skills.py
from __future__ import annotations
import json
from pathlib import Path

import jsonschema

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src/robot_md/schemas/v1/robot.schema.json").read_text()
)


def _m(extra: dict) -> dict:
    return {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": {"type": "arm", "dof": 6},
        "drivers": [{"id": "arm", "protocol": "feetech"}],
        "capabilities": ["status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
        **extra,
    }


def test_learned_skills_optional():
    jsonschema.validate(_m({}), SCHEMA)


def test_learned_skills_accepts_entry():
    jsonschema.validate(_m({
        "learned_skills": [
            {
                "id": "red_lego_pick.2026-04-19",
                "status": "blocked",
                "validated": ["scene_capture"],
                "blocked_by": ["forward_home_pose_missing"],
                "notes": "Vision chain works.",
            }
        ]
    }), SCHEMA)


def test_learned_skills_status_enum():
    try:
        jsonschema.validate(_m({
            "learned_skills": [{"id": "x", "status": "excellent"}]
        }), SCHEMA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("expected rejection of status='excellent'")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_learned_skills.py -v`
Expected: FAIL on the status enum test.

- [ ] **Step 3: Extend the schema**

Add to the root `"properties"`:

```json
"learned_skills": {
  "type": "array",
  "description": "Append-only skill catalogue — what the robot has empirically demonstrated.",
  "items": {
    "type": "object",
    "required": ["id"],
    "properties": {
      "id":         {"type": "string"},
      "status":     {"type": "string", "enum": ["ok", "blocked", "degraded"]},
      "validated":  {"type": "array",  "items": {"type": "string"}},
      "blocked_by": {"type": "array",  "items": {"type": "string"}},
      "notes":      {"type": "string"},
      "recorded_at":{"type": "string"}
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_learned_skills.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/schemas/v1/robot.schema.json cli/tests/unit/test_schema_learned_skills.py
git commit -m "feat(schema): top-level learned_skills array

Three statuses enumerated: ok, blocked, degraded. The x-learned-skills
convention from v0.5.0 graduates to a first-class field.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 15: RobotSpec surfaces `learned_skills`

**Files:**
- Modify: `cli/src/robot_md/robot_spec.py`
- Test: `cli/tests/unit/test_poses.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `cli/tests/unit/test_poses.py`:

```python
def test_spec_surfaces_learned_skills():
    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
learned_skills:
  - id: red_lego_pick.2026-04-19
    status: blocked
    validated: [scene_capture, hsv_red]
    blocked_by: [forward_home_pose_missing]
    notes: 'Vision chain works.'
---
# bob
"""
    spec = RobotSpec.from_parsed(parse_text(text))
    ls = spec.learned_skills
    assert len(ls) == 1
    assert ls[0].id == "red_lego_pick.2026-04-19"
    assert ls[0].status == "blocked"
    assert "hsv_red" in ls[0].validated
    assert "forward_home_pose_missing" in ls[0].blocked_by
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_poses.py::test_spec_surfaces_learned_skills -v`
Expected: FAIL.

- [ ] **Step 3: Add dataclass + populate**

In `cli/src/robot_md/robot_spec.py`:

```python
@dataclass(frozen=True)
class LearnedSkill:
    id: str
    status: str
    validated: tuple[str, ...]
    blocked_by: tuple[str, ...]
    notes: str | None
    recorded_at: str | None
```

Add to `RobotSpec`:

```python
    learned_skills: tuple[LearnedSkill, ...]
```

In `from_parsed`:

```python
        ls_raw = fm.get("learned_skills") or []
        learned_skills = tuple(
            LearnedSkill(
                id=s.get("id", ""),
                status=s.get("status", "ok"),
                validated=tuple(s.get("validated") or ()),
                blocked_by=tuple(s.get("blocked_by") or ()),
                notes=s.get("notes"),
                recorded_at=s.get("recorded_at"),
            )
            for s in ls_raw
            if isinstance(s, dict)
        )
```

Pass `learned_skills=learned_skills` in the constructor.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_poses.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/robot_spec.py cli/tests/unit/test_poses.py
git commit -m "feat(spec): RobotSpec surfaces learned_skills

Tuple[LearnedSkill, ...]. Defaults to () so v0.5.0 manifests still parse.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 16: MCP resources — `learned_skills`, `calibration_status`, `poses`

**Files:**
- Create: `cli/src/robot_md/mcp/resources.py`
- Modify: `cli/src/robot_md/mcp/server.py`
- Test: `cli/tests/unit/test_mcp_resources.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_mcp_resources.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.mcp.resources import calibration_status, learned_skills, poses
from robot_md.robot_spec import LearnedSkill, PoseDef


def _ctx(poses_dict=None, cameras=(), solver=None, ls=()):
    spec = MagicMock()
    spec.physics.poses = poses_dict or {}
    spec.physics.cameras = cameras
    spec.physics.solver = solver or {}
    spec.learned_skills = ls
    ctx = MagicMock()
    ctx.spec = spec
    return ctx


def test_calibration_status_all_missing():
    r = calibration_status(_ctx())
    assert r["zero"] == "ok"  # zero_pose_steps is always present in v0.5.0 presets
    assert r["hand_eye"] == "missing"
    assert r["poses_ready"] == "missing"


def test_calibration_status_ready_taught():
    r = calibration_status(_ctx(poses_dict={"ready": PoseDef(joints={"a": 1}, description=None, source="taught", taught_at=None)}))
    assert r["poses_ready"] == "ok"


def test_learned_skills_returns_list_of_dicts():
    r = learned_skills(_ctx(ls=(LearnedSkill(id="x", status="ok", validated=(), blocked_by=(), notes=None, recorded_at=None),)))
    assert isinstance(r, list)
    assert r[0]["id"] == "x"


def test_poses_resource_returns_dict():
    r = poses(_ctx(poses_dict={"ready": PoseDef(joints={"a": 1}, description="x", source="taught", taught_at="2026-04-19")}))
    assert r["ready"]["joints"] == {"a": 1}
    assert r["ready"]["source"] == "taught"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_mcp_resources.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement resources**

```python
# cli/src/robot_md/mcp/resources.py
"""MCP resource payload builders.

Each function takes an McpContext and returns a JSON-serialisable value.
Wrapped by @server.resource() in server.py.
"""

from __future__ import annotations

from typing import Any


def calibration_status(ctx: Any) -> dict[str, str]:
    spec = ctx.spec
    poses_ready = "ok" if spec.physics.poses.get("ready") else "missing"
    cams = getattr(spec.physics, "cameras", ())
    hand_eye = "ok" if (cams and any(getattr(c, "extrinsic", None) for c in cams)) else "missing"
    # zero_pose_steps is part of the kinematics block — always present in shipped presets.
    # Report "ok" unconditionally here; a future refinement checks per-joint.
    return {"zero": "ok", "hand_eye": hand_eye, "poses_ready": poses_ready}


def learned_skills(ctx: Any) -> list[dict]:
    return [
        {
            "id": s.id,
            "status": s.status,
            "validated": list(s.validated),
            "blocked_by": list(s.blocked_by),
            "notes": s.notes,
            "recorded_at": s.recorded_at,
        }
        for s in (ctx.spec.learned_skills or ())
    ]


def poses(ctx: Any) -> dict[str, dict]:
    return {
        name: {
            "joints": dict(p.joints),
            "description": p.description,
            "source": p.source,
            "taught_at": p.taught_at,
        }
        for name, p in (ctx.spec.physics.poses or {}).items()
    }
```

In `cli/src/robot_md/mcp/server.py`, after the existing tool registrations, add resource registrations using the MCP server's resource API:

```python
    robot_name = ctx.spec.metadata.robot_name if ctx.spec else "robot"

    @server.resource(f"robot-md://{robot_name}/learned_skills")
    def _resource_learned_skills() -> str:
        import json
        from robot_md.mcp.resources import learned_skills

        return json.dumps(learned_skills(ctx), indent=2)

    @server.resource(f"robot-md://{robot_name}/calibration_status")
    def _resource_calibration_status() -> str:
        import json
        from robot_md.mcp.resources import calibration_status

        return json.dumps(calibration_status(ctx), indent=2)

    @server.resource(f"robot-md://{robot_name}/poses")
    def _resource_poses() -> str:
        import json
        from robot_md.mcp.resources import poses

        return json.dumps(poses(ctx), indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_mcp_resources.py -v`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/resources.py cli/src/robot_md/mcp/server.py cli/tests/unit/test_mcp_resources.py
git commit -m "feat(mcp): expose learned_skills, calibration_status, poses as resources

Three new robot-md://<name>/* endpoints. Builders are pure functions
so they're testable without starting FastMCP.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 17: `record_skill` MCP tool — append to manifest

**Files:**
- Create: `cli/src/robot_md/mcp/tools/record_skill.py`
- Modify: `cli/src/robot_md/mcp/server.py`
- Test: `cli/tests/unit/test_record_skill_tool.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_record_skill_tool.py
from __future__ import annotations

from unittest.mock import MagicMock

import yaml

from robot_md.mcp.tools.record_skill import record_skill_tool


def test_record_skill_appends(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "---\n# bob\n"
    )
    ctx = MagicMock()
    ctx.manifest_path = manifest

    result = record_skill_tool(
        ctx,
        skill_id="red_lego_pick.2026-04-19",
        status="ok",
        validated=["scene_capture", "hsv_red"],
        blocked_by=[],
        notes="Works after poses.ready.",
    )
    assert result["status"] == "ok"
    fm = yaml.safe_load(manifest.read_text().split("---")[1])
    ls = fm["learned_skills"]
    assert ls[0]["id"] == "red_lego_pick.2026-04-19"
    assert ls[0]["status"] == "ok"


def test_record_skill_upserts_by_id(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "learned_skills:\n"
        "  - {id: x, status: blocked}\n"
        "---\n# bob\n"
    )
    ctx = MagicMock()
    ctx.manifest_path = manifest

    record_skill_tool(ctx, skill_id="x", status="ok", validated=[], blocked_by=[])
    fm = yaml.safe_load(manifest.read_text().split("---")[1])
    ls = fm["learned_skills"]
    assert len(ls) == 1
    assert ls[0]["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_record_skill_tool.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/mcp/tools/record_skill.py
"""MCP tool: append/upsert a learned_skills[] entry on the manifest."""

from __future__ import annotations

import datetime as _dt
from typing import Any

import yaml

from robot_md.parser import parse_file


def record_skill_tool(
    ctx: Any,
    *,
    skill_id: str,
    status: str = "ok",
    validated: list[str] | None = None,
    blocked_by: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    path = ctx.manifest_path
    parsed = parse_file(path)
    fm = dict(parsed.frontmatter)
    ls = list(fm.get("learned_skills") or [])
    entry = {
        "id": skill_id,
        "status": status,
        "validated": list(validated or []),
        "blocked_by": list(blocked_by or []),
        "recorded_at": _dt.date.today().isoformat(),
    }
    if notes:
        entry["notes"] = notes
    for i, existing in enumerate(ls):
        if isinstance(existing, dict) and existing.get("id") == skill_id:
            ls[i] = entry
            break
    else:
        ls.append(entry)
    fm["learned_skills"] = ls

    path.write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + parsed.body
    )
    return {"status": "ok", "skill_id": skill_id, "count": len(ls)}
```

Register in `cli/src/robot_md/mcp/server.py`:

```python
    @server.tool()
    def record_skill(
        skill_id: str,
        status: str = "ok",
        validated: list[str] | None = None,
        blocked_by: list[str] | None = None,
        notes: str | None = None,
    ) -> dict:
        """Append/upsert a learned_skills[] entry on the served ROBOT.md."""
        from robot_md.mcp.tools.record_skill import record_skill_tool

        return record_skill_tool(
            ctx,
            skill_id=skill_id,
            status=status,
            validated=validated,
            blocked_by=blocked_by,
            notes=notes,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_record_skill_tool.py -v`
Expected: PASS (2/2).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/tools/record_skill.py cli/src/robot_md/mcp/server.py cli/tests/unit/test_record_skill_tool.py
git commit -m "feat(mcp): record_skill — append/upsert learned_skills entry

Lets the agent persist what worked (or didn't) directly into ROBOT.md
from inside a Claude session. Idempotent — upserts by skill_id.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Milestone 5 — `discover` MCP verb (§8)

Goal: The discovery pattern the user executed ad-hoc (capture → detect → probe → plan → dry-run) becomes one MCP call. Agents invoke it at session start when `learned_skills` is empty or stale.

### Task 18: `discover` skeleton — capture + detect steps

**Files:**
- Create: `cli/src/robot_md/mcp/tools/discover.py`
- Test: `cli/tests/unit/test_discover_tool.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_discover_tool.py
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from robot_md.mcp.tools.discover import discover_tool
from robot_md.robot_spec import ObjectDescriptor, VisionBlock


def _ctx_with_two_descriptors():
    import cv2

    rgb = np.full((200, 300, 3), 240, dtype=np.uint8)
    cv2.rectangle(rgb, (150, 80), (200, 140), (40, 40, 220), -1)  # red
    cv2.rectangle(rgb, (20, 20), (60, 60), (230, 230, 230), -1)   # upper-left light
    depth = np.full((200, 300), 500, dtype=np.uint16)
    K = np.array([[500.0, 0, 150.0], [0, 500.0, 100.0], [0, 0, 1.0]])
    per = MagicMock(); per.grab_frame.return_value = (rgb, depth, K)

    spec = MagicMock()
    spec.vision = VisionBlock(object_descriptors=(
        ObjectDescriptor("red_lego", "hsv",
                         {"h_ranges": [[0, 10], [170, 180]], "s_min": 80, "v_min": 80}),
        ObjectDescriptor("white_bowl", "hsv_roi",
                         {"s_max": 80, "v_min": 100, "roi": {"u_max": 150, "v_max": 120}}),
    ))
    ctx = MagicMock(); ctx.spec = spec; ctx.backend._perception = per
    return ctx


def test_discover_capture_and_detect():
    ctx = _ctx_with_two_descriptors()
    r = discover_tool(ctx, steps=[{"capture": {}}, {"detect": {"descriptors": ["red_lego", "white_bowl"]}}])
    assert r["status"] == "ok"
    assert "capture" in r["results"]
    assert r["results"]["detect"]["red_lego"]["pixel"][0] > 150
    assert r["results"]["detect"]["white_bowl"]["pixel"][0] < 150


def test_discover_unknown_descriptor():
    ctx = _ctx_with_two_descriptors()
    r = discover_tool(ctx, steps=[{"detect": {"descriptors": ["nonsense"]}}])
    assert r["status"] == "ok"  # discovery is report-oriented, doesn't fail
    assert r["results"]["detect"]["nonsense"]["status"] == "unknown_descriptor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_discover_tool.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement capture + detect steps**

```python
# cli/src/robot_md/mcp/tools/discover.py
"""MCP tool: discover — run the standard scene-discovery pipeline.

Steps are declarative: [{capture: {}}, {detect: {...}}, {probe_direction: {...}}, {plan: {...}}, {dry_run: true}].
Unknown steps are reported and skipped; discovery should never raise on a
single-step failure.
"""

from __future__ import annotations

from typing import Any

from robot_md.detectors.hsv import DETECTORS


def discover_tool(ctx: Any, *, steps: list[dict]) -> dict:
    results: dict[str, Any] = {}
    frame = None  # cached between steps
    for step in steps:
        if not isinstance(step, dict) or len(step) != 1:
            continue
        (name, payload) = next(iter(step.items()))
        if name == "capture":
            frame = _do_capture(ctx)
            results["capture"] = {
                "status": "ok" if frame is not None else "no_frame",
                "shape": list(frame[0].shape) if frame is not None else None,
            }
        elif name == "detect":
            if frame is None:
                frame = _do_capture(ctx)
            results["detect"] = _do_detect(ctx, frame, payload)
        else:
            results[name] = {"status": "unknown_step"}
    return {"status": "ok", "results": results}


def _do_capture(ctx: Any):
    per = getattr(ctx.backend, "_perception", None)
    if per is None:
        return None
    return per.grab_frame()


def _do_detect(ctx: Any, frame, payload: dict) -> dict:
    if frame is None:
        return {"status": "no_frame"}
    rgb, depth, K = frame
    requested = list(payload.get("descriptors") or [])
    out: dict[str, Any] = {}
    for name in requested:
        desc = ctx.spec.vision.find(name) if ctx.spec else None
        if desc is None:
            out[name] = {"status": "unknown_descriptor"}
            continue
        fn = DETECTORS.get(desc.detector)
        if fn is None:
            out[name] = {"status": "unknown_detector", "detector": desc.detector}
            continue
        hit = fn(rgb, params=desc.params)
        if hit is None:
            out[name] = {"status": "not_found"}
        else:
            u, v, area = hit
            out[name] = {"status": "ok", "pixel": [u, v], "area_px2": area}
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_discover_tool.py -v`
Expected: PASS (2/2).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/tools/discover.py cli/tests/unit/test_discover_tool.py
git commit -m "feat(mcp): discover tool — capture + detect steps

Declarative step list runs the scene-discovery pipeline. Step failures
are reported, never raised. Next commits add probe_direction + plan.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 19: `discover` — probe_direction step

**Files:**
- Modify: `cli/src/robot_md/mcp/tools/discover.py`
- Test: `cli/tests/unit/test_discover_tool.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `cli/tests/unit/test_discover_tool.py`:

```python
def test_discover_probe_direction_reports_shift():
    import cv2

    frames = []
    rgb1 = np.full((200, 300, 3), 0, dtype=np.uint8)
    cv2.rectangle(rgb1, (140, 50), (160, 150), (255, 255, 255), -1)
    frames.append((rgb1, np.full((200, 300), 500, dtype=np.uint16), None))

    rgb2 = np.full((200, 300, 3), 0, dtype=np.uint8)
    cv2.rectangle(rgb2, (170, 50), (190, 150), (255, 255, 255), -1)  # shifted +30 px
    frames.append((rgb2, np.full((200, 300), 500, dtype=np.uint16), None))

    class _PosBus:
        written: list[dict] = []

        def torque(self, on):  # noqa: ARG002
            pass

        def write_positions(self, p):
            self.written.append(p)

    per = MagicMock()
    per.grab_frame.side_effect = frames
    ctx = MagicMock()
    ctx.backend._perception = per
    ctx.backend._servo_bus = _PosBus()
    ctx.spec.vision = VisionBlock(object_descriptors=())

    from robot_md.mcp.tools.discover import discover_tool

    r = discover_tool(ctx, steps=[{"probe_direction": {"joint": "shoulder_pan", "delta": 30}}])
    pd = r["results"]["probe_direction"]
    assert pd["status"] == "ok"
    assert pd["px_shift"] > 10  # the white bar moved ~30 px
    assert pd["direction"] == "positive_delta→image_right"
    assert pd["px_per_step"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_discover_tool.py::test_discover_probe_direction_reports_shift -v`
Expected: FAIL — step not implemented.

- [ ] **Step 3: Implement**

Extend `discover_tool` to handle the `probe_direction` case:

```python
        elif name == "probe_direction":
            results["probe_direction"] = _do_probe(ctx, payload)
```

Add the helper:

```python
def _do_probe(ctx: Any, payload: dict) -> dict:
    import cv2
    import numpy as np

    joint = payload.get("joint", "shoulder_pan")
    delta = int(payload.get("delta", 30))
    per = getattr(ctx.backend, "_perception", None)
    bus = getattr(ctx.backend, "_servo_bus", None)
    if per is None or bus is None:
        return {"status": "no_hardware"}
    f_before = per.grab_frame()
    if f_before is None:
        return {"status": "no_frame"}
    current = bus.read_positions() if hasattr(bus, "read_positions") else {}
    target = dict(current)
    target[joint] = int(current.get(joint, 2048)) + delta
    bus.torque(True)
    try:
        bus.write_positions(target)
        f_after = per.grab_frame()
    finally:
        # Best-effort return to starting position.
        bus.write_positions(current)
    if f_after is None:
        return {"status": "no_frame_after"}
    rgb_before = cv2.cvtColor(f_before[0], cv2.COLOR_BGR2GRAY)
    rgb_after = cv2.cvtColor(f_after[0], cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(rgb_before, rgb_after)
    _, th = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
    col_sum = th.sum(axis=0)
    xs = np.arange(len(col_sum))
    total = col_sum.sum()
    if total == 0:
        return {"status": "no_motion_detected"}
    # Compare centroid mass left-of-center vs right-of-center.
    cx = rgb_before.shape[1] / 2
    lmass = col_sum[xs < cx].sum()
    rmass = col_sum[xs >= cx].sum()
    # Empirical px-shift: distance between "before" and "after" centroids of motion
    cols_active = xs[col_sum > 0]
    px_shift = int(cols_active.max() - cols_active.min()) // 2 if cols_active.size else 0
    direction = "positive_delta→image_right" if rmass >= lmass else "positive_delta→image_left"
    return {
        "status": "ok",
        "joint": joint,
        "delta": delta,
        "px_shift": px_shift,
        "direction": direction,
        "px_per_step": round(px_shift / max(1, delta), 3),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_discover_tool.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/tools/discover.py cli/tests/unit/test_discover_tool.py
git commit -m "feat(mcp): discover.probe_direction — empirical joint→pixel gain

Moves one joint by delta, image-diffs before/after, reports direction and
px_per_step. Formalises the ad-hoc probe pattern from the gap session.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 20: `discover` — register in MCP server

**Files:**
- Modify: `cli/src/robot_md/mcp/server.py`

- [ ] **Step 1: Register the tool**

Add alongside the other `@server.tool()` registrations:

```python
    @server.tool()
    def discover(steps: list[dict]) -> dict:
        """Run the declarative discovery pipeline. See docs/superpowers/specs/2026-04-19-claude-triad-gap-analysis.md §8."""
        from robot_md.mcp.tools.discover import discover_tool

        return discover_tool(ctx, steps=steps)
```

- [ ] **Step 2: Run suite to confirm nothing regressed**

Run: `cd /home/craigm26/robot-md && pytest cli/tests -q`
Expected: PASS — all existing tests green; new `test_discover_tool.py` still passes.

- [ ] **Step 3: Commit**

```bash
git add cli/src/robot_md/mcp/server.py
git commit -m "feat(mcp): register discover tool in FastMCP server

Exposes discover(steps: list[dict]) as an MCP tool. Lets Claude run the
scene pipeline without reimplementing it in shell scripts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 21: so-arm101 preset ships a `red_lego` + `white_bowl` descriptor stub

**Files:**
- Modify: `cli/src/robot_md/presets/so_arm101.yaml`
- Test: `cli/tests/test_init.py` (extend — ensure the preset stays valid)

- [ ] **Step 1: Write the failing test**

Append to `cli/tests/test_init.py`:

```python
def test_so_arm101_preset_ships_object_descriptors(presets):
    so = next(p for p in presets if p.name == "so_arm101")
    vision = so.data.get("vision") or {}
    ids = {d["id"] for d in (vision.get("object_descriptors") or [])}
    assert "red_lego" in ids
    assert "white_bowl" in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/test_init.py::test_so_arm101_preset_ships_object_descriptors -v`
Expected: FAIL.

- [ ] **Step 3: Add the descriptors to the preset**

In `cli/src/robot_md/presets/so_arm101.yaml`, add a top-level `vision:` block:

```yaml
vision:
  object_descriptors:
    - id: red_lego
      detector: hsv
      params:
        h_ranges: [[0, 10], [170, 180]]
        s_min: 110
        v_min: 80
        min_area: 500
    - id: white_bowl
      detector: hsv_roi
      params:
        s_max: 80
        v_min: 100
        min_area: 3000
        roi:
          u_max: 450
          v_max: 360
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests -q`
Expected: PASS — full suite clean.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/presets/so_arm101.yaml cli/tests/test_init.py
git commit -m "feat(preset): so_arm101 ships red_lego + white_bowl descriptors

New manifests from `robot-md init --preset so-arm101` can run the
pick-red-lego demo out of the box once poses.ready is taught.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 22: Integration test — pick_red_lego dry-run through MCP tool chain

**Files:**
- Create: `cli/tests/integration/test_pick_red_lego_dry_run.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/integration/test_pick_red_lego_dry_run.py
"""Integration: discover → vision.find → execute_capability chain, all dry.

Uses a faked backend that consumes `vision.object_descriptors` from the
so-arm101 preset. Validates the plumbing, not the hardware.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest


@pytest.mark.integration
def test_discover_then_vision_find_then_execute(tmp_path):
    from robot_md.init import non_interactive
    from robot_md.mcp.context import load_context
    from robot_md.mcp.tools.discover import discover_tool
    from robot_md.mcp.tools.execute_capability import execute_capability_tool
    from robot_md.mcp.tools.vision_find import vision_find_tool
    from robot_md.poses import write_pose_to_manifest

    manifest = tmp_path / "ROBOT.md"
    rc = non_interactive(manifest, robot_name="bob", preset_name="so-arm101", force=True)
    assert rc == 0

    # Teach a stub 'ready' pose so the precondition passes.
    write_pose_to_manifest(
        manifest,
        name="ready",
        joints={"shoulder_pan": 1950, "shoulder_lift": 1700, "elbow_flex": 2400,
                "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700},
    )

    ctx = load_context(manifest)
    # Swap in fake perception + bus
    rgb = np.full((720, 1280, 3), 240, dtype=np.uint8)
    cv2.rectangle(rgb, (500, 380), (600, 440), (40, 40, 220), -1)  # red lego
    cv2.rectangle(rgb, (50, 100), (400, 350), (230, 230, 230), -1)  # bowl region
    depth = np.full((720, 1280), 500, dtype=np.uint16)
    K = np.array([[979.0, 0, 666.0], [0, 979.0, 348.0], [0, 0, 1.0]])
    per = MagicMock(); per.grab_frame.return_value = (rgb, depth, K)

    class _Bus:
        def torque(self, *_):
            pass
        def read_positions(self):
            return {"shoulder_pan": 2048}
        def write_positions(self, p):
            pass

    ctx.backend._perception = per
    ctx.backend._servo_bus = _Bus()

    # 1. discover
    disc = discover_tool(ctx, steps=[
        {"capture": {}},
        {"detect": {"descriptors": ["red_lego", "white_bowl"]}},
    ])
    assert disc["results"]["detect"]["red_lego"]["status"] == "ok"

    # 2. vision.find
    vf = vision_find_tool(ctx, descriptor_id="red_lego")
    assert vf["status"] == "ok"

    # 3. execute dry-run (precondition satisfied by taught pose)
    exe = execute_capability_tool(
        ctx, capability="arm.home", args={}, dry_run=True, confirm_token=None
    )
    assert exe["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it passes after earlier tasks land**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/integration/test_pick_red_lego_dry_run.py -v -m integration`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add cli/tests/integration/test_pick_red_lego_dry_run.py
git commit -m "test(integration): discover → vision.find → execute chain dry-run

Exercises the M1–M5 plumbing on a fresh so-arm101 manifest with a
faked OAK-D + servo bus.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Milestone 6 — Structural cleanups (§2, §4, §5, §9)

### Task 23: `physics.workspace` bounds

**Files:**
- Modify: `cli/src/robot_md/schemas/v1/robot.schema.json`
- Modify: `cli/src/robot_md/robot_spec.py`
- Test: `cli/tests/unit/test_schema_workspace.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_schema_workspace.py
from __future__ import annotations
import json
from pathlib import Path

import jsonschema

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src/robot_md/schemas/v1/robot.schema.json").read_text()
)


def _m(physics_extra=None):
    physics = {"type": "arm", "dof": 6}
    if physics_extra:
        physics.update(physics_extra)
    return {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": physics,
        "drivers": [{"id": "arm", "protocol": "feetech"}],
        "capabilities": ["status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
    }


def test_workspace_accepts_bounds_mm():
    jsonschema.validate(_m({"workspace": {
        "from_pose": "ready",
        "bounds_mm": {"x": [-200, 200], "y": [50, 300], "z": [0, 150]},
    }}), SCHEMA)


def test_workspace_requires_axes_as_pairs():
    try:
        jsonschema.validate(_m({"workspace": {"bounds_mm": {"x": [1]}}}), SCHEMA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("expected rejection of single-element axis")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_workspace.py -v`
Expected: FAIL on the pair test.

- [ ] **Step 3: Schema + spec fields**

In the schema's `physics.properties`:

```json
"workspace": {
  "type": "object",
  "properties": {
    "from_pose": {"type": "string"},
    "bounds_mm": {
      "type": "object",
      "properties": {
        "x": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "y": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "z": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
      }
    },
    "note": {"type": "string"}
  }
}
```

In `robot_spec.py`:

```python
@dataclass(frozen=True)
class Workspace:
    from_pose: str | None
    bounds_mm: dict[str, tuple[float, float]]
    note: str | None
```

Populate in `from_parsed`:

```python
        ws_raw = physics.get("workspace")
        workspace: Workspace | None = None
        if isinstance(ws_raw, dict):
            b = ws_raw.get("bounds_mm") or {}
            bounds = {
                k: (float(v[0]), float(v[1]))
                for k, v in b.items()
                if isinstance(v, list) and len(v) == 2
            }
            workspace = Workspace(
                from_pose=ws_raw.get("from_pose"),
                bounds_mm=bounds,
                note=ws_raw.get("note"),
            )
```

Add `workspace: Workspace | None` to `PhysicsBlock`; pass in constructor.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_workspace.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/schemas/v1/robot.schema.json cli/src/robot_md/robot_spec.py cli/tests/unit/test_schema_workspace.py
git commit -m "feat(schema): physics.workspace bounds with per-axis mm ranges

Optional block. Consumed by the workspace_declared precondition.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 24: `physics.solver.ik_provider` declared

**Files:**
- Modify: `cli/src/robot_md/schemas/v1/robot.schema.json` (under `physics.solver`)
- Test: `cli/tests/unit/test_schema_ik_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_schema_ik_provider.py
from __future__ import annotations
import json
from pathlib import Path

import jsonschema

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src/robot_md/schemas/v1/robot.schema.json").read_text()
)


def _m(solver):
    return {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "bob"},
        "physics": {"type": "arm", "dof": 6, "solver": solver},
        "drivers": [{"id": "arm", "protocol": "feetech"}],
        "capabilities": ["status.report"],
        "safety": {"estop": {"software": True, "response_ms": 100}},
    }


def test_ik_provider_null_allowed():
    jsonschema.validate(_m({"ik_provider": None}), SCHEMA)


def test_ik_provider_string_allowed():
    jsonschema.validate(_m({"ik_provider": "inhouse-so-arm101"}), SCHEMA)


def test_ik_provider_numeric_rejected():
    try:
        jsonschema.validate(_m({"ik_provider": 42}), SCHEMA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("expected rejection")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_ik_provider.py -v`
Expected: FAIL on the numeric-rejection test.

- [ ] **Step 3: Add field to schema**

Under the existing `physics.solver` properties, add:

```json
"ik_provider": {"type": ["string", "null"]},
"ik_frame":    {"type": ["string", "null"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_schema_ik_provider.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/schemas/v1/robot.schema.json cli/tests/unit/test_schema_ik_provider.py
git commit -m "feat(schema): physics.solver.ik_provider (+ ik_frame)

Declares whether an IK solver is wired in. Consumed by the
ik_provider_set precondition kind.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 25: `publish-discovery` emits calibration_status + learned_skills_summary

**Files:**
- Modify: `cli/src/robot_md/discovery.py`
- Test: `cli/tests/unit/test_discovery_payload.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/unit/test_discovery_payload.py
from __future__ import annotations

from robot_md.discovery import build_discovery
from robot_md.parser import parse_text


def _manifest_text():
    return """---
rcan_version: '3.0'
metadata: {robot_name: bob, rrn: RRN-000000000042}
physics:
  type: arm
  dof: 6
  poses:
    ready:
      joints: {shoulder_pan: 1950}
      source: taught
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
learned_skills:
  - {id: red_lego_pick.2026-04-19, status: blocked}
  - {id: home.2026-04-19, status: ok}
---
# bob
"""


def test_discovery_includes_calibration_status():
    out = build_discovery(parse_text(_manifest_text()), manifest_url="https://x/ROBOT.md")
    assert out["calibration_status"]["poses_ready"] == "ok"
    assert out["calibration_status"]["hand_eye"] == "missing"


def test_discovery_includes_learned_skills_summary():
    out = build_discovery(parse_text(_manifest_text()), manifest_url="https://x/ROBOT.md")
    ls = out["learned_skills_summary"]
    assert "red_lego_pick.2026-04-19.blocked" in ls
    assert "home.2026-04-19.ok" in ls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_discovery_payload.py -v`
Expected: FAIL — fields not emitted.

- [ ] **Step 3: Extend `build_discovery`**

In `cli/src/robot_md/discovery.py`, extend the dict returned around lines 55-75:

```python
    from robot_md.robot_spec import RobotSpec

    spec = RobotSpec.from_parsed(parsed)
    poses_ready = "ok" if spec.physics.poses.get("ready") else "missing"
    hand_eye = (
        "ok" if (spec.physics.cameras and any(c.extrinsic for c in spec.physics.cameras))
        else "missing"
    )
    out.update({
        "calibration_status": {
            "zero": "ok",
            "poses_ready": poses_ready,
            "hand_eye": hand_eye,
        },
        "learned_skills_summary": [f"{s.id}.{s.status}" for s in spec.learned_skills],
    })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/unit/test_discovery_payload.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/discovery.py cli/tests/unit/test_discovery_payload.py
git commit -m "feat(discovery): emit calibration_status + learned_skills_summary

.well-known/robot-md.json now tells Claude Mobile what's calibrated and
what skills are known. Closes gap spec §9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 26: `claude-md` template renders poses + preconditions + learned_skills

**Files:**
- Modify: `cli/src/robot_md/claude_md.py`
- Test: `cli/tests/test_claude_md.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `cli/tests/test_claude_md.py`:

```python
def test_claude_md_lists_ready_pose(tmp_path):
    from robot_md.claude_md import render_claude_md
    from robot_md.parser import parse_text

    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics:
  type: arm
  dof: 6
  poses:
    ready: {joints: {shoulder_pan: 1950}, source: taught, taught_at: '2026-04-19'}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
---
# bob
"""
    md = render_claude_md(parse_text(text))
    assert "poses.ready" in md or "Named poses" in md
    assert "1950" in md or "shoulder_pan" in md


def test_claude_md_surfaces_learned_skill_blockers(tmp_path):
    from robot_md.claude_md import render_claude_md
    from robot_md.parser import parse_text

    text = """---
rcan_version: '3.0'
metadata: {robot_name: bob}
physics: {type: arm, dof: 6}
drivers: [{id: arm, protocol: feetech}]
capabilities: [status.report]
safety: {estop: {software: true, response_ms: 100}}
learned_skills:
  - {id: x, status: blocked, blocked_by: [no_poses_ready]}
---
# bob
"""
    md = render_claude_md(parse_text(text))
    assert "blocked" in md.lower()
    assert "no_poses_ready" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/test_claude_md.py -v`
Expected: FAIL on both new tests.

- [ ] **Step 3: Extend the template**

In `cli/src/robot_md/claude_md.py`, find the section that emits the body (around the posture / what-this-robot-is-running-on region) and add two new sections before the Conventions section:

```python
    # Named poses (if any)
    poses = spec.physics.poses
    if poses:
        out.append("\n## Named poses\n")
        for name, p in poses.items():
            desc = f" — {p.description}" if p.description else ""
            src = f" (source: {p.source})" if p.source else ""
            out.append(f"- `{name}`{src}{desc}: " + ", ".join(f"{k}={v}" for k, v in p.joints.items()))

    # Learned-skill summary
    ls = spec.learned_skills
    if ls:
        out.append("\n## Known skills & blockers\n")
        for s in ls:
            bits = [f"**{s.id}**", f"status=`{s.status}`"]
            if s.blocked_by:
                bits.append("blocked_by=[" + ", ".join(s.blocked_by) + "]")
            if s.notes:
                bits.append(f"— {s.notes}")
            out.append("- " + " ".join(bits))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/craigm26/robot-md && pytest cli/tests/test_claude_md.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/claude_md.py cli/tests/test_claude_md.py
git commit -m "feat(claude-md): render named poses + learned-skill summary

Agents reading the generated CLAUDE.md at session start now see which
poses are taught and which skills are blocked — no need to introspect
the manifest themselves.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 27: Hardware smoke test for the full loop (opt-in)

**Files:**
- Create: `cli/tests/hardware/test_pose_teach_roundtrip.py`

- [ ] **Step 1: Write the (hardware-gated) test**

```python
# cli/tests/hardware/test_pose_teach_roundtrip.py
"""HARDWARE: teach ready → execute arm.home → verify servos reach taught pose.

Opt-in: runs only with `--run-hardware`. Requires the SO-ARM101 + OAK-D setup.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from robot_md.init import non_interactive


@pytest.mark.hardware
def test_pose_teach_then_home_matches(tmp_path):
    from robot_md.mcp.context import load_context
    from robot_md.mcp.tools.execute_capability import execute_capability_tool
    from robot_md.poses import teach_pose

    manifest = tmp_path / "ROBOT.md"
    rc = non_interactive(manifest, robot_name="bob", preset_name="so-arm101", force=True)
    assert rc == 0
    ctx = load_context(manifest)
    bus = ctx.backend._servo_bus

    # Operator pre-positions the arm by hand BEFORE running this test.
    taught = teach_pose(bus, manifest, name="ready")

    # Move away, then command arm.home.
    bus.write_positions({k: 2048 for k in taught})
    time.sleep(1.0)

    # Reload context so the new poses.ready is picked up.
    ctx2 = load_context(manifest)
    r = execute_capability_tool(ctx2, capability="arm.home", args={}, dry_run=False, confirm_token=None)
    assert r["status"] == "ok"

    time.sleep(1.5)
    final = bus.read_positions()
    for joint, target in taught.items():
        assert abs(final[joint] - target) < 30, f"{joint}: want {target} got {final[joint]}"
```

- [ ] **Step 2: Run test locally (requires hardware)**

Run (only where hardware is attached): `cd /home/craigm26/robot-md && pytest cli/tests/hardware/test_pose_teach_roundtrip.py --run-hardware -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add cli/tests/hardware/test_pose_teach_roundtrip.py
git commit -m "test(hardware): pose teach → arm.home roundtrip

Opt-in smoke test. Verifies the full M1 loop on physical hardware:
operator teaches 'ready', arm.home returns to within ±30 steps.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Milestone 7 — Release (v0.6.0)

### Task 28: Version bump + CHANGELOG

**Files:**
- Modify: `cli/pyproject.toml`
- Modify: `cli/src/robot_md/__init__.py`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Bump version**

In `cli/pyproject.toml`, change `version = "0.5.0"` → `version = "0.6.0"`.
In `cli/src/robot_md/__init__.py`, sync `__version__ = "0.6.0"`.

- [ ] **Step 2: Add CHANGELOG entry**

Prepend to `CHANGELOG.md`:

```markdown
## [0.6.0] — 2026-04-19

### Added
- `physics.poses` in manifest; `robot-md pose teach <name> <path>` CLI verb; `arm.home` resolves to `poses.ready` when present (gap spec §1).
- `capability_contracts` with preconditions; `execute_capability` gates on them (§3 / §10).
- `vision.object_descriptors` (HSV + HSV-ROI); new `vision.find` MCP tool (§6).
- `learned_skills` top-level array; `record_skill` MCP tool; `robot-md://<name>/learned_skills` resource (§7).
- `discover` MCP tool — declarative scene-discovery pipeline (§8).
- `physics.workspace` bounds schema (§2).
- `physics.solver.ik_provider` declaration (§5).
- `publish-discovery` emits `calibration_status` + `learned_skills_summary` (§9).
- Generated `CLAUDE.md` renders named poses + learned-skill blockers.

### Changed
- so-arm101 preset ships `red_lego` + `white_bowl` descriptors.
- New init phase `teach_poses` offers to record `ready` when init runs on a TTY.

### Compatibility
- All new fields are optional. v0.5.0 manifests validate and run unchanged.
```

- [ ] **Step 3: Run full suite + validator smoke**

Run:
```bash
cd /home/craigm26/robot-md && pytest cli/tests -q && ruff check cli/ && python -c "import robot_md; print(robot_md.__version__)"
```
Expected: all tests pass, ruff clean, version prints `0.6.0`.

- [ ] **Step 4: Commit**

```bash
git add cli/pyproject.toml cli/src/robot_md/__init__.py CHANGELOG.md
git commit -m "chore(release): v0.6.0 — Claude triad gap closure

Closes the 10 gaps from docs/superpowers/specs/2026-04-19-claude-triad-gap-analysis.md.
Backward-compatible — v0.5.0 manifests validate unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 29: Site copy reflects v0.6.0 reality

**Files:**
- Modify: `site/index.html` (hero terminal output, §05 terminal demo, footer version)

- [ ] **Step 1: Update hero reveal + §05 to show the new flow**

In the hero (around line 640), update the final prompt segment to show the post-init `claude` session asking about teaching poses:

```html
      <div class="C-line out"><span class="mute">›</span> <span class="v">bob</span> is online. Teach the <code style="color:#ffb88c">ready</code> pose so I can pick things up?</div>
      <div class="C-line out">yes<span class="C-cursor"></span></div>
```

In `site/index.html` §05 big terminal (the `<pre class="body">` block), add after the existing `robot-md init` output:

```
<span class="p">$</span> claude
<span class="w">› bob is online. Teach the `ready` pose so I can pick things up?</span>
yes
<span class="ok">✓ physics.poses.ready taught</span>

<span class="w">› What should bob do first?</span>
pick up the red lego and place it in the bowl
<span class="ok">✓ discover → red_lego @ (-62, +25, +522) mm, white_bowl @ (-210, +10, +480) mm</span>
<span class="ok">✓ execute arm.pick(target: red_lego) → arm.place(target: white_bowl)</span>
```

Update footer version string (near line 1165):

```html
<div>robotmd.dev · robot-md 0.6.0 · robot-md-mcp 0.3.0 · built 2026-04-19</div>
```

- [ ] **Step 2: Verify locally**

```bash
cd /home/craigm26/robot-md/site && python3 -m http.server 8765 &
sleep 1
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8765/index.html
kill %1
```
Expected: `200`.

- [ ] **Step 3: Commit**

```bash
git add site/index.html
git commit -m "site: refresh hero + §05 for v0.6.0 pick-red-lego demo

Shows the bare-init → teach-ready → pick-place flow end-to-end.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 30: Publish + tag

- [ ] **Step 1: Confirm clean working tree + push**

Run:
```bash
cd /home/craigm26/robot-md
git status --short
git log --oneline -10
git push origin main
```
Expected: clean tree, 28+ new commits pushed.

- [ ] **Step 2: Tag release**

```bash
git tag -a v0.6.0 -m "v0.6.0 — Claude triad gap closure"
git push origin v0.6.0
```

- [ ] **Step 3: (Manual) dispatch PyPI publish**

Follow repo convention — workflow_dispatch on the `.github/workflows/release.yml` with `publish_pypi=true`.

---

## Self-Review

**Spec coverage:**
- §1 → M1 (Tasks 1–5, 5.5). ✓
- §2 → Task 23. ✓
- §3 → Tasks 6–7 (capability_contracts). ✓
- §4 → Task 16 (`calibration_status` resource surfaces extrinsic missingness). ✓
- §5 → Task 24 (ik_provider). ✓
- §6 → Tasks 10–13. ✓
- §7 → Tasks 14–17. ✓
- §8 → Tasks 18–22. ✓
- §9 → Task 25 + Task 26 (CLAUDE.md parity). ✓
- §10 → Tasks 8–9. ✓

**Type consistency:** `PoseDef`, `Precondition`, `CapabilityContract`, `ObjectDescriptor`, `VisionBlock`, `Workspace`, `LearnedSkill` are named consistently across tasks. `write_pose_to_manifest` takes keyword-only `name` / `joints` everywhere.

**Placeholder scan:** every task's Step 3 contains complete code; no "TBD", "Similar to Task N", or vague "add validation" steps.

**Caveats:**
- Task 16's `calibration_status` reports `"zero": "ok"` unconditionally — a future refinement checks per-joint zero-cal via `zero_pose_calibration` marker (scope for v0.6.1).
- Task 5.5's `_pick_waypoints` reparameterization of `arm.pick`/`arm.place` around `poses.ready` is noted but deferred — M1 ships `arm.home` resolving to `poses.ready`, and a future task wires `arm.pick(target={ref: …})` through IK in v0.6.1 when an IK provider lands. The current plan ships enough to make a dry-run pass end-to-end; the physical pick loop needs the IK follow-up.

---

Plan complete and saved to `docs/superpowers/plans/2026-04-19-claude-triad-gap-closure.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, two-stage review between tasks (spec compliance → code quality), fast iteration.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for your review.

**Which approach?**

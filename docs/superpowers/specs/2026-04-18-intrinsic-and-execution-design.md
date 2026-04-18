# robot-md: camera intrinsics + execution MCP — design

**Date:** 2026-04-18
**Status:** Approved — ready for implementation plan
**Owner:** craigm26

## Summary

Three coordinated feature additions to robot-md so the framework can stand up a pick-and-place demo (and any other capability-driven workflow) without an external runtime like OpenCastor:

1. **Camera intrinsics in the schema** — per-stream intrinsic blocks on `drivers[]`, referenced from `physics.solver.cameras[]`, autodetected from factory calibration at `robot-md init`.
2. **Execution MCP tools** — a Python MCP server exposing `execute_capability` (deterministic primitive) and `execute_task` (natural-language planner) alongside ported `render` + `validate` + new `estop`.
3. **Pluggable `CapabilityBackend` interface** — one reference backend (`feetech_depthai`) shipping in-repo; third parties register via Python entry points.

Supporting changes: npm `robot-md-mcp@0.1.3` is hard-cut to a migration stub at v0.2.0; a claude-code skill guides operator checkerboard calibration for cameras without factory intrinsics.

## Decisions (brainstorming answers)

| # | Decision | Chosen |
|---|---|---|
| Q1 | Execution tool scope | **b** — Pluggable `CapabilityBackend` + one reference implementation. |
| Q2 | Intrinsic block shape | **c** — Multi-stream intrinsics (rgb/left/right/depth/mono/…). |
| Q3 | Init behavior | **b** — Factory-calibration autodetect at `init`; wizard-skill ships alongside (not later). |
| Q4 | MCP server location | **c** — One Python MCP in this repo; TS npm package sunset. |
| S  | Sunset strategy | **S1** — Hard cut: publish `robot-md-mcp@0.2.0` as a migration stub that exits non-zero with an actionable message. |
| NL | Natural-language scope | NL in scope this session via a separate `execute_task` tool; `execute_capability` stays deterministic. |

Everything below follows from these decisions.

## Architecture

```
robot-md (pip install robot-md)
 ├── cli/                        # existing: autodetect, init, validate, render, calibrate
 │   └── calibrate/              # + new: --intrinsic verb (session-file driven)
 ├── mcp/                        # NEW: Python MCP server replacing robot-md-mcp@0.1.3
 │   └── tools/
 │       ├── render              # ported from TS
 │       ├── validate            # ported from TS (+ new warnings)
 │       ├── estop               # NEW
 │       ├── execute_capability  # NEW: deterministic primitive
 │       └── execute_task        # NEW: NL planner
 ├── backends/                   # NEW: pluggable CapabilityBackend
 │   ├── base.py                 #   abstract interface + RobotSpec types
 │   └── feetech_depthai/        #   reference backend (default)
 ├── planning/                   # NEW: NL → capability decomposition
 ├── schema/v1/robot.schema.json # + drivers[].streams[].intrinsic, physics.solver.cameras[]
 └── presets/                    # migrated to cameras[] shape
```

Runtime flow for pick-and-place:

```
Claude (MCP client)
  ──> execute_task(prompt="pick the lego and place it left")
     ──> planning: brain.planning.provider/model decomposes
          → [arm.pick{object:lego}, arm.place{pose:…}]
     ──> for each step:
          execute_capability → backend resolved by drivers[].protocol
             ──> FeetechDepthaiBackend
                  ──> depthai stream (intrinsic from ROBOT.md) → detect
                  ──> DH + zero_pose_steps → IK → joint targets
                  ──> feetech serial → servos
```

Key invariant: **backends only consume `RobotSpec`** (a typed view of ROBOT.md). They never read their own config files. Everything needed — intrinsics, extrinsic, gripper steps, joint limits, HITL gates, planner provider — lives in the manifest.

## Schema changes

All additive to v1. No breaking changes.

### Intrinsic lives on the device

Intrinsic is factory calibration — a property of the camera, travels with the hardware:

```yaml
drivers:
  - id: oak-d-1
    protocol: depthai
    model: OAK-D
    streams:
      rgb:
        intrinsic:
          fx: 860.2
          fy: 860.2
          cx: 640.0
          cy: 360.0
          width: 1280
          height: 720
          distortion_model: plumb_bob      # plumb_bob | equidistant | rational | none
          distortion_coeffs: [k1, k2, p1, p2, k3]
      left:
        intrinsic: { ... }
        baseline_m: 0.0375                 # offset from device frame
      right:
        intrinsic: { ... }
        baseline_m: -0.0375
      depth:
        derived_from: [left, right]        # no own intrinsic
```

### Mount/extrinsic live on the robot

`physics.solver.camera` (singular) is deprecated and auto-upgraded at read time to `physics.solver.cameras[]` (plural):

```yaml
physics:
  solver:
    cameras:
      - driver_id: oak-d-1                 # → drivers[].id
        primary_stream: rgb                # which stream the planner uses
        mount: world                       # world | tool0 | link_<id>
        extrinsic: null                    # [tx,ty,tz,rx,ry,rz] — deployment-specific
```

### JSON-Schema rules

- `intrinsic` required keys: `fx, fy, cx, cy, width, height`. Optional: `distortion_model`, `distortion_coeffs`.
- `distortion_model`: enum `plumb_bob | equidistant | rational | none`.
- `distortion_coeffs`: array of numbers, length tied to model (plumb_bob=5, equidistant=4, rational=8).
- `streams` keys: canonical set `rgb | left | right | depth | mono | ir | thermal` enforced by pattern; additional keys allowed via schema extension.
- Cross-reference: every `physics.solver.cameras[].driver_id` must resolve to a `drivers[].id` whose entry has ≥1 `streams.*.intrinsic` OR null intrinsics with an operator TODO. Validator warns (not errors) on null intrinsic for a camera's declared `primary_stream`.
- Legacy `physics.solver.camera` (singular) read-time auto-upgraded; validator emits a deprecation warning.

### Preset migration

All 10 presets in `cli/src/robot_md/presets/*.yaml` move to the `cameras[]` shape. Arm-focused presets (so_arm101, etc.) keep the camera block optional.

## Init behavior

Pure Tier A — deterministic host-side read, zero new prompts. Slots into the existing `init.py` flow.

### Camera probe in `autodetect.scan_system()`

New `Scan.cameras` field alongside `Scan.devices`. Three probes tried in order, all lazy-imported:

1. **depthai** — `dai.Device().readCalibration().getCameraIntrinsics(socket, w, h)` per `getConnectedCameraFeatures()` socket. Factory cal on OAK-D is authoritative.
2. **pyrealsense2** — `profile.get_stream(...).as_video_stream_profile().get_intrinsics()`.
3. **v4l2** — enumerate `/dev/video*`. No intrinsic available (webcams don't publish one); emit `intrinsic: null` + provenance `v4l2 enum / no cal`.

If neither `depthai` nor `pyrealsense2` is installed, probes return zero cameras; `autodetect` still succeeds.

### Preset merge

For each detected camera, `merge_preset_into_draft` emits a `drivers[]` entry with `streams[].intrinsic` populated (or null) and a matching `physics.solver.cameras[]` entry with `mount: world, extrinsic: null, primary_stream: rgb` defaults. Provenance lands in YAML comments:

```yaml
drivers:
  - id: oak-d-1
    protocol: depthai
    model: OAK-D
    streams:
      rgb:
        # autodetected from depthai factory cal (2026-04-18T14:22:01Z)
        intrinsic: { fx: 860.2, fy: 860.2, cx: 640.0, cy: 360.0, ... }
```

### Operator calibration for non-factory-cal cameras

New CLI verb `robot-md calibrate --intrinsic --driver <id> --stream <name> --session-file <path>`:

- On first invocation: emits a printable 9×6 checkerboard PNG to the session directory.
- Accepts captured frames via `--frame <path>` (repeatable).
- Writes progress to a JSON session file: `{coverage, rms_error, frames_captured, next_hint, complete: false}`. A skill can poll this to drive guided UX.
- On `--finalize`: solves (`cv2.calibrateCamera`) and writes the intrinsic block back into ROBOT.md with provenance `operator checkerboard N=<frames> rms=<err>`.

### Wizard-skill

`integrations/claude-code-skill/intrinsic-calibration.md` ships in this spec. Describes the guided flow (show checkerboard, prompt N poses across coverage zones, poll session file, narrate progress). Drives the CLI through the stable `--session-file` contract; no CLI change required to evolve the skill.

## Python MCP server

### Layout

```
cli/src/robot_md/mcp/
  __init__.py
  server.py           # stdio MCP server, registers tools
  context.py          # loaded RobotSpec + resolved backend, lifecycle
  tools/
    __init__.py
    render.py
    validate.py
    estop.py
    execute_capability.py
    execute_task.py
```

### Entry points (pyproject.toml)

```toml
[project.scripts]
robot-md = "robot_md.__main__:main"
robot-md-mcp = "robot_md.mcp.server:main"
```

Fresh-install MCP registration:
```
claude mcp add robot-md -- uv tool run robot-md-mcp "$(pwd)/ROBOT.md"
```

### Tool contracts

| Tool | Params | Returns |
|---|---|---|
| `render` | none | canonical YAML frontmatter string |
| `validate` | none | `{ok: bool, summary: str, errors: [...], warnings: [...]}` |
| `estop` | none | `{ok: bool, set_at: ts}` — sets process-wide flag backends honor at joint-command boundaries |
| `execute_capability` | `{capability: str, args: dict, dry_run: bool, confirm_token?: str}` | `{status, trajectory?, events, error?}` where `status ∈ {ok, blocked, error}` |
| `execute_task` | `{prompt: str, context?: dict, dry_run: bool, confirm_token?: str}` | `{status, plan: [...], executions: [...], events}` |

Blocked responses carry a `gate` or `challenge` object and are resolved by re-invocation with a `confirm_token` (single-use, opaque).

### Lifecycle

- Loads ROBOT.md at startup → validates → resolves backend via `drivers[].protocol` registry → holds backend open for server lifetime.
- Validation failure on startup is fatal: non-zero exit + structured error on stderr. No silently degraded server.
- File-watch on ROBOT.md: drops and reopens backend on change.
- One `execute_*` at a time per server (backend-serialized mutex). Parallel calls return `{status: "blocked", reason: "busy"}` with no side effects.
- Velocity clamp enforcement: server refuses to dispatch if `safety.max_joint_velocity_dps` is missing.

### Sunset of npm `robot-md-mcp` (S1)

Published simultaneously with Python v0.2:
- `robot-md-mcp@0.2.0` (npm): 40-line Node stub printing migration instructions, exits non-zero.
- `site/docs/migrate-to-python.md`: migration guide (one-time `pipx install robot-md` + updated `claude mcp add` line).

## CapabilityBackend + reference backend

### Abstract interface

```python
# cli/src/robot_md/backends/base.py

@dataclass(frozen=True)
class ExecutionEvent:
    kind: str                   # "plan" | "joint_cmd" | "frame" | "gate" | "done" | "error"
    data: dict[str, Any]

@dataclass(frozen=True)
class ExecutionResult:
    status: str                 # "ok" | "blocked" | "error"
    trajectory: list[dict] | None
    events: list[ExecutionEvent]
    error: dict | None

@dataclass(frozen=True)
class SceneSnapshot:
    frame: bytes | None         # latest camera frame (PNG)
    detections: list[dict]      # [{class, bbox_xyxy, conf}, …]
    joint_state: dict[str, float]
    ts: float

    @classmethod
    def empty(cls) -> "SceneSnapshot": ...

class CapabilityBackend(ABC):
    name: str                   # e.g. "feetech-depthai"
    protocols: frozenset[str]   # drivers[].protocol values this backend claims

    @abstractmethod
    def open(self, spec: RobotSpec) -> None: ...
    @abstractmethod
    def close(self) -> None: ...
    @abstractmethod
    def capabilities(self) -> frozenset[str]: ...
    @abstractmethod
    def execute(
        self, capability: str, args: dict, *, dry_run: bool, estop: EstopFlag
    ) -> ExecutionResult: ...
    def scene_describe(self) -> SceneSnapshot:
        return SceneSnapshot.empty()    # default: empty snapshot
```

### RobotSpec — the typed view

Built once at server startup from validated YAML. Backends never re-parse YAML.

```python
@dataclass(frozen=True)
class Intrinsic:
    fx: float; fy: float; cx: float; cy: float
    width: int; height: int
    distortion_model: str | None
    distortion_coeffs: tuple[float, ...] | None

@dataclass(frozen=True)
class CameraStream:
    name: str
    intrinsic: Intrinsic | None
    baseline_m: float | None
    derived_from: tuple[str, ...] | None

@dataclass(frozen=True)
class DriverEntry:
    id: str; protocol: str
    port: str | None; baud_rate: int | None
    model: str | None; count: int | None
    streams: dict[str, CameraStream]

@dataclass(frozen=True)
class SolverCamera:
    driver_id: str; primary_stream: str
    mount: str; extrinsic: tuple[float, ...] | None

@dataclass(frozen=True)
class RobotSpec:
    rcan_version: str
    metadata: MetadataBlock
    physics: PhysicsBlock
    drivers: tuple[DriverEntry, ...]
    safety: SafetyBlock
    capabilities: frozenset[str]
    brain: BrainBlock | None
    raw_yaml: str
```

### Registry via entry points

```toml
[project.entry-points."robot_md.backends"]
feetech_depthai = "robot_md.backends.feetech_depthai:FeetechDepthaiBackend"
```

Resolution at startup: collect all registered backends → for each `drivers[].protocol`, pick the first backend whose `protocols` set includes it. Unresolved protocols still pass `validate`; `execute_capability` returns `{status: "error", error: {reason: "no_backend", protocol: …}}`.

### Reference backend: `feetech_depthai`

```
cli/src/robot_md/backends/feetech_depthai/
  __init__.py           # FeetechDepthaiBackend
  servo.py              # feetech serial I/O (STS3215)
  perception.py         # depthai pipeline + object detection
  motion.py             # DH fwd/inv kinematics, trajectory gen
  capabilities.py       # arm.pick / arm.place / arm.reach / vision.describe / status.report
```

- `protocols = frozenset({"feetech", "depthai"})` — one backend claims both so it can cross-refer servos ↔ camera.
- Hardware deps are **extras**: `pip install robot-md[feetech-depthai]`. Plain `pip install robot-md` gives CLI + MCP + `render`/`validate`/`estop` with no hardware libs.
- Object detection: depthai's MobileNet-SSD blob. Classes not in MobileNet-SSD (e.g. "lego") fall back to "largest contiguous blob near workspace center" with a warning event. Sufficient for Tier 0 demo; swap-in reactive models (OpenVLA) is a follow-up.

### Safety + HITL integration

- Before any `joint_cmd`, backend checks `estop.is_set()` and aborts with `{status: "blocked"}`.
- `safety.hitl_gates[]` evaluation lives in the **MCP server**, not the backend. Matching scope → server returns `{status: "blocked", gate: {…}}` before calling backend. Caller re-invokes with `confirm_token`.
- Trajectory generator enforces `safety.max_joint_velocity_dps`; backend refuses `open()` if the field is missing.

## Natural-language planning

### Pipeline (cli/src/robot_md/planning/)

1. Build planner prompt from: `spec.capabilities` (verbs), `spec.safety.workspace_bounds_m`, `backend.scene_describe()` (camera frame + detections + joint state).
2. Call `brain.planning.provider` / `brain.planning.model` via a tiny shim:
   - `anthropic` → `anthropic.Anthropic().messages.create(...)`. API key from `ANTHROPIC_API_KEY`. Prompt caching enabled for the capability-schema block.
   - `openai` / `google` → same contract, different client. Anthropic-only in this spec; others are follow-ups.
   - `local` → returns capability directly (single-step; no decomposition).
3. Receive `[{capability, args, confidence}]`. Every `capability` must be in `spec.capabilities`; reject the plan otherwise ("hallucinated capability `arm.throw`").
4. Enforce `brain.planning.confidence_gate`: any step below threshold → `{status: "blocked", reason: "low_confidence", challenge: {...}}`.
5. Execute steps sequentially via `execute_capability`. Abort on first non-`ok`. Full execution log returned.

### Design rationale

- **Planner declared in ROBOT.md, not server flag**: manifest is the single source of truth; changing models is a reviewable diff. Matches existing `brain.planning` schema — no new fields.
- **Two tools, not one auto-detect**: deterministic callers shouldn't pay a planner roundtrip; the error surfaces differ (capability-unknown vs. prompt-ambiguous).

### Failure modes

| Condition | Response |
|---|---|
| No `brain.planning` block | `{status: "error", error: {reason: "no_planner_declared"}}` |
| Planner returns unknown capability | Rejected before any motion |
| Planner timeout (`brain.planning.timeout_ms`, default 30000) | `{status: "blocked", reason: "timeout"}` — retryable |
| Confidence below gate | `{status: "blocked", reason: "low_confidence", challenge}` |

## Testing

```
cli/tests/
  unit/
    test_schema_intrinsic.py
    test_schema_cameras_xref.py
    test_init_autodetect_cameras.py
    test_render.py
    test_validate.py
    test_backend_registry.py
    test_planning_prompt.py
    test_planning_validation.py
    test_hitl_gate_blocking.py
    test_estop_propagation.py
  integration/
    test_mcp_server_lifecycle.py
    test_execute_capability_dry.py
    test_execute_task_dry.py         # recorded anthropic cassettes
  hardware/                          # gated by --run-hardware
    test_feetech_smoke.py
    test_depthai_intrinsic_read.py
```

- Unit tests mock serial, depthai, anthropic SDK.
- Integration tests: MCP stdio lifecycle + dry-run execution.
- Hardware tests opt-in via pytest marker; CI runs unit + integration only.
- Anthropic calls in `test_execute_task_dry.py` use recorded cassettes (no network in CI).
- Schema fixtures under `schema/v1/fixtures/` — schema file independently testable.
- Coverage target: 85% on `mcp/`, `backends/base.py`, `planning/`.

## Rollout plan (single PR, this session)

Ordered for incremental-merge-safety:

1. Schema additions + fixtures + validator warnings (additive; no code paths use new fields yet).
2. Autodetect camera probes + preset migration (populates new fields; existing robots unaffected).
3. Python MCP server with `render` / `validate` / `estop` only (feature-parity with TS MCP minus `execute_*`).
4. `CapabilityBackend` base + registry + `execute_capability`.
5. `feetech_depthai` reference backend.
6. `planning/` module + `execute_task`.
7. `integrations/claude-code-skill/intrinsic-calibration.md`.
8. npm `robot-md-mcp@0.2.0` migration stub + `site/docs/migrate-to-python.md`.
9. CHANGELOG + README updates.

Each numbered item is a clean commit in the PR. Reviewers can walk commit-by-commit.

## Breaking-change surface

- **ROBOT.md**: `physics.solver.camera` (singular) deprecated, read-time auto-upgraded. No operator action.
- **MCP registration**: `npx -y robot-md-mcp …` → `robot-md-mcp …`. Documented in migrate doc; npm stub prints the new command.
- **New env var**: `ANTHROPIC_API_KEY` needed for `execute_task` with `provider: anthropic`. `execute_capability` has no new env deps.
- **No breaking change** to `render` / `validate` tool contracts.

## Out of scope

- URDF importer, MoveIt, ROS2 bridge.
- Backends beyond `feetech_depthai` (community PRs via entry-point registration).
- Intrinsic-calibration wizard UX polish (skill ships rough; iteration is follow-up).
- Signed `confirm_token` minting (stub uses opaque nonces; real tokens = v0.3).
- Multi-robot orchestration in one MCP server (federation schema present; server stays single-robot).

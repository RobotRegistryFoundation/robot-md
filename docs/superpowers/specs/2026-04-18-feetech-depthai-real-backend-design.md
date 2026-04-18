# feetech_depthai real backend + adaptive skill store — design

**Date:** 2026-04-18
**Status:** Approved — ready for implementation plan
**Owner:** craigm26
**Target:** Bob (SO-ARM101 + OAK-D + Raspberry Pi 5 + Hailo-8, Feetech STS3215 ×6)

## Summary

Fill in the `feetech_depthai` backend stubs shipped in robot-md v0.3.0/0.3.1 with real implementations, AND build the adaptive loop the user envisions: ROBOT.md accumulates taught "skills" over time, perception gates + adjusts replay, and Claude Code memories propose manifest refinements via a dedicated sync verb.

The design ships in five independently-deliverable phases (v0.4 → v0.8). Each phase has a working demo; you can stop at any phase if priorities shift.

## Decisions (brainstorming answers)

| # | Decision | Chosen |
|---|---|---|
| Q1 | Backend scope | **C** — Hybrid: teach-and-replay default with opt-in perception-reactive path. |
| Q2 | Spec scope | **C** — Full adaptive loop (backend + skill store + memory sync). Staged into 5 phases. |
| Q3 | Skill storage | **B** — Sidecar files in `skills/`, referenced from ROBOT.md via glob. |
| Q4 | Perception role | **C** — Gate + pose-adjust; degrades gracefully to gate-only when extrinsic is null. |
| Arch | Backend architecture | **Approach 1** — Skill-first, four loosely-coupled modules (servo, perception, motion, handeye) + skill_store + capabilities glue. |

All remaining decisions (Jacobian vs IK pose-adjust, forward-kinematics-only for hand-eye, etc.) follow from these and are locked in-design.

## Architecture

```
cli/src/robot_md/backends/feetech_depthai/
  __init__.py           # FeetechDepthaiBackend (existing; grows scene_describe, execute dispatch)
  servo.py              # real STS3215 wire protocol (ports examples/tier0/*)
  perception.py         # OAK-D pipeline + pluggable detectors (VLM, color-blob)
  motion.py             # trajectory interpolator + pose-adjust (Jacobian-bounded) + fwd kin
  handeye.py            # NEW — ArUco-free extrinsic calibration
  skill_store.py        # NEW — reads skills/*.yaml, resolves by capability + target
  capabilities.py       # glue — arm.pick = skill_store.find + perception.gate + motion.replay

cli/src/robot_md/
  teach.py              # NEW — `robot-md teach` CLI verb
  memory_sync.py        # NEW — `robot-md sync-memories` CLI verb (P5)

skills/                 # NEW — alongside ROBOT.md
  pick-red-lego.yaml
  drop-bowl-left.yaml
  ...
```

The backend already registers at `robot_md.backends` entry point; no new registration needed.

## Skill schema + ROBOT.md integration

### Sidecar skill file — `skills/<name>.yaml`

```yaml
name: pick-red-lego
capability: arm.pick
target: "red lego"                              # NL string the planner matches against
description: "Pick a red Lego brick from the workspace."

provenance:
  taught_by: craigm26
  taught_at: 2026-04-18T18:32:11Z
  taught_from_session: cf67b51c-...             # Claude session id (env var) or empty
  teach_method: operator-demonstration
  success_count: 0                              # incremented on successful replay
  failure_count: 0

preconditions:
  primary_camera: oak-d-1                       # must match a drivers[].id
  required_streams: [rgb, depth]
  detector: vlm                                 # vlm | color_blob | custom:<mod.attr>

# Taught reference — where the object was during capture. Used by
# pose_adjust to compute replay-time delta. Omitted if no camera.
reference:
  object_pose_camera_mm: [42.1, -18.3, 320.5]
  gripper_start_joints:
    shoulder_pan: 2048
    shoulder_lift: 2048
    elbow_flex: 2048
    wrist_flex: 2048
    wrist_roll: 2048
    gripper: 1700

trajectory:
  hz: 30
  waypoints:
    - t: 0.0
      joints: { shoulder_pan: 2048, shoulder_lift: 2048, elbow_flex: 2048,
                wrist_flex: 2048, wrist_roll: 2048, gripper: 1700 }
    - t: 0.4
      joints: { shoulder_pan: 2072, shoulder_lift: 2012, elbow_flex: 2110,
                wrist_flex: 2035, wrist_roll: 2048, gripper: 1700 }
    # ...50–200 waypoints
  post_actions:
    - { action: close_gripper, wait_ms: 400 }
    - { action: lift_shoulder, steps: 120 }
```

### ROBOT.md frontmatter addition

```yaml
skills:
  source: "skills/*.yaml"           # glob — auto-discover
  # OR:
  # files: [skills/pick-red-lego.yaml, ...]
```

### Validator rules

- Schema: `skills` is an object with either `source: <glob-string>` or `files: <array>`; not both; not neither.
- Cross-ref: each skill's `capability` must appear in ROBOT.md `capabilities[]` — warning (not error) if missing; the skill is latent until declared.
- Cross-ref: `preconditions.primary_camera` must resolve to `drivers[].id`.
- Cross-ref: `trajectory.waypoints[].joints` keys must match `physics.kinematics[].id` names.
- Size: skill files over 1 MB emit a warning (suggests splitting or decimating waypoints).

### `SkillStore` runtime

```python
class SkillStore:
    @classmethod
    def from_spec(cls, spec: RobotSpec, manifest_dir: Path) -> "SkillStore": ...
    def find(self, *, capability: str, target: str) -> Skill | None: ...   # fuzzy NL match
    def all_for(self, capability: str) -> list[Skill]: ...
    def increment_success(self, skill_name: str) -> None: ...               # ruamel round-trip
    def increment_failure(self, skill_name: str, reason: str) -> None: ...
```

Fuzzy matching: `difflib.get_close_matches(target, all_skill_targets, n=1, cutoff=0.6)`. If zero candidates, `find` returns `None` and the caller (planner/executor) is expected to surface the full skill list so the planner can disambiguate.

Success/failure counters write back to the sidecar file in place (mutate). `ruamel.yaml` preserves all other fields + comments on round-trip. No separate counter log — single grep-able truth.

## Backend module contracts

### `servo.py`

Wraps `feetech_servo_sdk`. The existing `examples/tier0/*.py` code moves in wholesale and becomes instance methods.

```python
class ServoBus:
    @classmethod
    def from_spec(cls, spec: RobotSpec) -> "ServoBus": ...
    def open(self) -> None: ...                                   # opens /dev/ttyACM0
    def close(self) -> None: ...
    def read_positions(self) -> dict[str, int]: ...               # {joint_name: steps}
    def write_positions(self, targets: dict[str, int]) -> None: ...
    def torque(self, on: bool) -> None: ...
    def interpolate(
        self, start: dict[str, int], target: dict[str, int],
        *, hz: int = 30, max_steps_per_tick: int = 12, estop,
    ) -> None: ...                                                 # port of tier0/_interpolate
```

Register addresses (constants from tier0): `ADDR_TORQUE_ENABLE=40`, `ADDR_GOAL_POSITION=42`, `ADDR_PRESENT_POSITION=56`.

Safety:

- Velocity clamp via `max_steps_per_tick`. If `safety.max_joint_velocity_dps` implies a higher steps/tick, the bus clamps down (never up). Clamping up is spec violation.
- Partial reads: a non-responder is logged but not fatal. Interpolator uses last known `present_position`.
- `estop` flag checked every tick in `interpolate`. On set: stop immediately, hold current position, return.

### `perception.py`

```python
@dataclass(frozen=True)
class Detection:
    target: str
    bbox_xyxy: tuple[int, int, int, int]
    pose_3d_camera_mm: tuple[float, float, float]
    confidence: float

class Detector(Protocol):
    def detect(self, rgb: bytes, depth: bytes, K: np.ndarray,
               target: str) -> list[Detection]: ...

class Perception:
    @classmethod
    def from_spec(cls, spec: RobotSpec) -> "Perception": ...
    def open(self) -> None: ...                                   # starts depthai pipeline
    def close(self) -> None: ...
    def grab_frame(self) -> tuple[bytes, bytes, np.ndarray]: ...  # rgb, depth, K
    def detect(self, target: str | None) -> list[Detection]: ...
    def set_detector(self, detector: Detector) -> None: ...
```

Detectors:

- **`VLMDetector`** (default) — sends RGB frame + `"identify <target>. Return bbox_xyxy as JSON {bbox: [x1,y1,x2,y2], conf: 0..1}"` to the provider declared in `brain.reactive` (default `anthropic` with `claude-opus-4-7`). Back-projects bbox center through depth + intrinsics to 3D camera frame (reuses the math from `examples/tier0/05_scene_snapshot.py`). ~1–2 s per call. Zero setup.
- **`ColorBlobDetector`** — HSV thresholding + contour detection (opencv). <50 ms. Requires `preconditions.color: "red"` (or similar) in the skill file. Good for primary-color objects.
- **Custom** — skills can reference any Python callable via `preconditions.detector: custom:<module>.<attr>`. Imported lazily at replay time.

### `motion.py`

```python
class Motion:
    @classmethod
    def from_spec(cls, spec: RobotSpec) -> "Motion": ...

    def replay(
        self, skill: Skill, servo_bus: ServoBus, estop,
    ) -> ExecutionResult: ...                    # drives servo_bus.interpolate per waypoint

    def pose_adjust(
        self, skill: Skill, observed: Detection,
        extrinsic: tuple[float, ...] | None,
    ) -> Skill | ExecutionResult: ...            # adjusted Skill, or blocked-result on too-large-delta

    def forward_kinematics(
        self, joints: dict[str, int],
    ) -> tuple[float, float, float]: ...          # DH fwd kin in arm base frame, mm
```

**Pose-adjust algorithm**:

1. `extrinsic is None` → return skill unchanged + surface `pose_adjust_skipped: no_extrinsic` warning event. Gate-only behavior.
2. Compute `delta_camera_mm = observed.pose_3d_camera_mm - skill.reference.object_pose_camera_mm`.
3. Transform to base frame: `delta_base_mm = apply_extrinsic(extrinsic, delta_camera_mm)`.
4. If `‖delta_base_mm‖ > MAX_SAFE_SHIFT_MM` (default 50 mm) → return `ExecutionResult(status="blocked", reason="object_moved_too_far", …)`. Operator re-teaches.
5. Else: nudge every waypoint by a Jacobian-linearized joint-delta around the reference pose. Bounded, cheap, accurate for small shifts. Full IK-based adjustment is explicitly out-of-scope for this spec.

Forward kinematics: DH params from `physics.kinematics[]` (already populated by presets). Standard 6-row Denavit-Hartenberg multiply chain. Shared with `handeye.py`.

### `handeye.py` — ArUco-free extrinsic calibration

Approach: **gripper-tip-as-fiducial**. Operator commands the arm to N (default 12) known joint poses that place the gripper across the camera field of view. Camera detects the gripper in each RGB frame (distinctive tip geometry; optionally with a colored sticker). Solve extrinsic from N pairs of (arm-frame XYZ via forward kinematics, camera-frame XYZ via back-projected depth).

```python
def calibrate_extrinsic(
    arm_poses: list[dict[str, int]],
    tip_detections: list[tuple[float, float, float]],     # camera-frame mm per observation
    fk: Callable[[dict[str, int]], tuple[float, float, float]],
) -> tuple[float, ...]:                                    # [tx, ty, tz, rx, ry, rz]
    """Solve camera→arm_base extrinsic via Kabsch/Umeyama alignment."""
```

CLI: `robot-md calibrate --hand-eye ROBOT.md` — interactive; guides the operator through N poses (commanded via `ServoBus.interpolate` to each target), auto-captures + detects gripper tip, solves, writes extrinsic into `physics.solver.cameras[].extrinsic`. Reprojection error RMS reported; > 10 mm prompts re-run.

Degenerate cases (collinear observations, detector failures > N/2) raise explicit errors; never write a silently-bad extrinsic.

## Teach CLI + memory-sync

### `robot-md teach`

```
robot-md teach --name <skill-name> --capability arm.pick --target "red lego" [--update]
```

Flow (ported from `examples/tier0/04_pick_place.py` + extended with perception):

1. Open `ROBOT.md`; verify the capability is declared. Abort with a diff showing the operator how to add it otherwise.
2. Open `ServoBus` + `Perception` (if any camera in spec).
3. **Observation phase** — grab one OAK-D frame; run active detector against `--target`. If found, record `reference.object_pose_camera_mm`. If not found and a camera exists, prompt operator to reposition, retry. If no camera, `reference` block is omitted; perception-gate skipped at replay.
4. **Demonstration phase** — torque off, operator poses arm, Enter captures, repeat for each phase (start → pick → lift → place → home, mirroring tier0/04).
5. **Trajectory capture** — interpolate recorded waypoints at 30 Hz, store as `waypoints[]`.
6. **Write sidecar** — `skills/<name>.yaml` with schema from §Skill schema. `taught_at` = ISO-8601 now; `taught_from_session` = `os.environ["CLAUDE_SESSION_ID"]` if set, else `""`.
7. **Update ROBOT.md** — if `skills:` block absent, inject `skills: { source: "skills/*.yaml" }`. If glob already matches the new sidecar, no edit. Preserve YAML comments via `ruamel.yaml`.
8. **Validate** — run `robot-md validate` post-write; surface any warnings; don't auto-fix.

Safety:

- Torque OFF before operator repositions; Enter re-enables at `present_position` (never snap).
- An abort in the middle persists nothing (all writes happen at steps 6–7).
- The tier0 session-state invariant holds: "any subsequent script must NOT snap-to a home pose before the operator removes the held object." Teach respects this by never commanding a move during the demonstration phase.

### Success / failure counters

`execute_task` chains through `execute_capability`. On successful `replay` → `skill_store.increment_success(skill_name)`. On `status != "ok"` → `increment_failure(skill_name, reason)`. Counters mutate the sidecar YAML in place via ruamel round-trip; only the two counter fields are touched.

### `robot-md sync-memories`

```
robot-md sync-memories <ROBOT.md> [--dry-run] [--apply]
```

Scans `~/.claude/projects/<slug>/memory/` for robot-relevant entries and proposes ROBOT.md diffs. Defaults to `--dry-run`.

**Memory discovery**:

- Reads `~/.claude/projects/-home-craigm26/memory/MEMORY.md` index.
- Follows pointers to individual `.md` memory files.
- Filters to memories where `type: project` AND the body mentions the robot's `metadata.robot_name`, `metadata.rrn`, or any `drivers[].id`.

**Extractor patterns** (structured templates — no NLP-heavy inference):

| Pattern in memory | Suggests |
|---|---|
| `skill \`<name>\` succeeded N times today` | Increment `provenance.success_count` |
| `skill \`<name>\` failed: <reason>` | Increment `provenance.failure_count`; append reason to history |
| `gripper slips on <surface>` | Add note to `safety.notes[]` (new optional field) |
| `servo <N> drifts under <voltage>` | Add an `hitl_gates[]` entry scoped to that joint |

Unmatched memories are skipped silently — the DSL is intentionally narrow. Extend the pattern table in follow-up specs as usage matures.

**Output**:

- `--dry-run` (default): colored diff of proposed ROBOT.md and skill-file changes.
- `--apply`: writes + `git commit -m "memory-sync: <summary>"`.

**Not in scope for v1**:

- No auto-execution. Every diff is operator-reviewed.
- No NLP inference. Templates only.
- No bidirectional write. We read `~/.claude/.../memory/`; Claude Code's auto-memory system still owns writes.

### MCP server integration

At server startup, `McpContext` loads the `SkillStore` alongside the backend. Available to `execute_task` as `ctx.skills`. The planner prompt grows a `## Taught skills` block:

```
## Taught skills (with taught targets)
- arm.pick "red lego" (taught 2026-04-18, 3 successes)
- arm.place "bowl-left" (taught 2026-04-18, 5 successes, 1 failure)
- ...
```

The planner is told to prefer a taught skill whose `target` matches the user's prompt. Planner returns `capability + args` as before; `skill_store.find` at execute time looks up the right sidecar.

## Rollout phases

| Phase | Content | Version |
|---|---|---|
| **P1 — Real backend wiring** | Port tier0 examples into `servo.py`, `perception.py`, `motion.py`. Capability handlers call real code. Skill embedded in capability handler (one hardcoded trajectory) for first demo. | v0.4.0 |
| **P2 — Skill store + teach CLI** | Sidecar schema, `skill_store.py`, `robot-md teach`. Capabilities resolve through `skill_store.find`. ROBOT.md gains `skills:` block. | v0.5.0 |
| **P3 — Perception gate + VLM detector** | `perception.py` goes from stub to real OAK-D pipeline. Detector strategies. Gate blocks on object-not-found. Pose-adjust still no-op (no extrinsic yet). | v0.6.0 |
| **P4 — Hand-eye + pose-adjust** | `robot-md calibrate --hand-eye`, `handeye.py`, Jacobian-bounded pose-adjust. | v0.7.0 |
| **P5 — Memory-sync** | `robot-md sync-memories`, memory-parsing DSL, diff proposer. | v0.8.0 |

Each phase has a shippable demo. Operators can stop at any phase if priorities shift. Each phase is its own implementation plan produced by `writing-plans` at the time we build it — this spec captures the full vision; plans stage it.

## Testing

### Unit (CI — fast)

- `servo.py` — mock `feetech_servo_sdk`; test torque, read_positions, interpolate bounds, estop propagation.
- `perception.py` — mock depthai pipeline with fixed frame bytes; test VLM detector with a monkeypatched fake client (no network); test color-blob detector on a synthetic HSV image.
- `motion.py` — test replay drives servo_bus.interpolate in order; test pose_adjust unchanged when extrinsic=None; test Jacobian correction keeps joints within limits; test block-when-delta-too-large.
- `handeye.py` — test Kabsch/Umeyama with synthetic (fk, camera) pairs and a known-good extrinsic; test degenerate case (collinear observations) raises explicit error.
- `skill_store.py` — fixture with sample skills; test find() fuzzy match, test counter writes preserve comments.
- `teach.py` — monkeypatch ServoBus + Perception; simulate Enter-presses via stdin; verify sidecar schema + ROBOT.md update.
- `memory_sync.py` — fixture memory dir; test each extractor template; test dry-run vs apply.

### Integration (CI)

- `execute_task` end-to-end — mocked planner returns `[arm.pick red lego]`; fake backend + seeded skill store; verify `increment_success` called after ok replay.
- `teach` CLI end-to-end — fake servos + camera; operator inputs piped via stdin; verify skill file + ROBOT.md on disk.
- `sync-memories` — fixture memory with each extractor pattern; verify proposed diff matches golden file.

### Hardware (`--run-hardware` gated)

- **Teach + replay roundtrip** on Bob — teach a trivial "wiggle" skill, replay it, verify servo positions match within tolerance.
- **`calibrate --hand-eye` on Bob** with OAK-D — capture 12 poses, solve extrinsic, verify reprojection error < 10 mm RMS.
- **`arm.pick red lego` on Bob** — requires pre-taught skill, hand-eye-calibrated manifest. Pass criterion: gripper ends up holding the Lego.

## Breaking-change surface

- **None in P1.** Pure additions under existing stubs.
- **P2 adds optional `skills:` to schema.** Legacy manifests validate unchanged.
- **P3 adds optional `preconditions.detector:` to skill files.** Skills captured in P2 without it default to `vlm`.
- **P4 writes `physics.solver.cameras[].extrinsic`.** Field already exists in v0.3 schema; `calibrate --hand-eye` populates it.
- **P5 adds `robot-md sync-memories`.** Pure CLI addition.

## Out of scope

- Full analytical/numeric 6-DoF IK. Pose-adjust uses local Jacobian only; operator re-teaches above 50 mm.
- Online learning mid-session. Skills captured by `teach`, mutated only by counters.
- Multi-arm coordination. Single-backend, single-arm.
- Non-OAK-D camera pose-adjust. RealSense/ZED paths land when a user needs them.
- Automatic skill curation (detecting redundant skills). v0.9+ story.
- Bidirectional memory-sync (writing to Claude's memory dir). Read-only.
- Non-anthropic VLM providers for the default detector. Follow-up.

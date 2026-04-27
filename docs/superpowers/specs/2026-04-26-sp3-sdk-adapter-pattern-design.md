# SP3 — SDK Adapter Pattern (Manufacturer SDKs as Backends)

**Date:** 2026-04-26
**Status:** Design — pending implementation plan
**Sub-project:** 3 of 5 (see SP1 + SP2 specs in this directory)

> **REVISION 2026-04-27:** Several sections superseded by `2026-04-27-sp1-5-simplification-revisions.md` — Revision 3 specifically applies to SP3. Notably: add a `[hardware]` meta-extra that pulls all common backends in one install; granular `[lerobot]`/`[realsense]`/`[feetech-depthai]` extras stay for advanced/minimal installs.

## Problem

`robot-md` has the `CapabilityBackend` ABC, the `robot_md.backends` entry-point group, and one reference implementation (`feetech_depthai`, ~1150 LoC). The runtime architecture is sound. What's missing is a *story* for how vendors (HuggingFace, Intel, Trossen, Pollen, etc.) ship their SDKs as `robot-md`-compatible backends — and how operators discover and install them. Today, owning a SO-100 with stock LeRobot tooling means there's no way to point Claude at it through `robot-md`. The runtime works, but the ecosystem doesn't yet.

For the Anthropic acquisition demo, the story is "watch Claude drive different vendors' hardware through the same flow — same `robot-md init`, same `execute_task`, different SDK underneath." That story breaks today because there's only one backend.

## Scope

**In scope:**
- Two reference adapters: `lerobot` (covers SO-100, SO-101, Koch, Aloha2 — multiple presets) and `realsense` (camera-only, covers Stretch3 / Reachy2 / generic depth rigs).
- Capability namespacing convention: core (`arm.*`, `nav.*`, `perceive.*`, `gripper.*`, `safety.*`) RRF-schemaed; vendor (`<vendor>.<name>`) free-form.
- Tier validator at backend registration: rejects malformed capability names with clear errors.
- Authoring docs (`docs/authoring-a-backend.md`) and a copy-paste skeleton (`examples/backend-template/`).
- Preset updates: SO-ARM presets gain `preferred_backend: lerobot` as alternative hint (SP2's hybrid resolver picks installed one).

**Out of scope** (handled by other sub-projects or follow-ups):
- Dynamixel, ROS2, Franka, UR adapters — deferred to SP3.x follow-up PRs using the same pattern.
- Backend registry UI / discovery service — docs page lists known adapters manually.
- Cross-adapter benchmarking tooling.
- Vendor adapter security audit / supply-chain validation.
- Migration of existing `feetech_depthai` (already core-prefixed; no changes needed).

## Design

### Architecture

Eight components, all in-tree to `robot-md/cli/`:

1. **`cli/src/robot_md/backends/lerobot/`** — New backend wrapping HuggingFace LeRobot. Implements `CapabilityBackend`. Targets SO-100, SO-101, Koch, Aloha2.
2. **`cli/src/robot_md/backends/realsense/`** — New backend wrapping `pyrealsense2`. Camera-only.
3. **`cli/src/robot_md/backends/registry.py`** — Add capability-tier validator: rejects backends with malformed capability names. Backends remain unchanged in shape — namespacing enforced at registration only.
4. **`cli/src/robot_md/schemas/capabilities.json`** — NEW. JSON-Schema for core capability arg shapes. Used by adapter tests and `execute_capability` arg validation.
5. **`cli/pyproject.toml`** — New extras `[lerobot]` and `[realsense]`. New entry-point declarations.
6. **`cli/src/robot_md/presets/*.yaml`** — Update SO-ARM presets to declare `preferred_backend: lerobot`.
7. **`docs/authoring-a-backend.md`** — NEW. Adapter authoring guide.
8. **`examples/backend-template/`** — NEW. Copy-paste skeleton package.

**Out of scope for architecture:**
- Dynamixel/ROS2/Franka/UR adapters (follow-ups).
- Backend discovery service.
- Capability-tier migration for `feetech_depthai` (already compliant).

**Design principles preserved:**
- Entry-point discovery is the only registration mechanism.
- Backends are independent — adding one doesn't require changes to others.
- Init-time and runtime resolution stay separate (`try_resolve` from SP2 vs `BackendRegistry.resolve` at call time).

**Backward compatibility:** Existing `feetech_depthai` continues to work. New tier validator allows all current capability names. New entry-point group entries don't conflict with existing one.

### Components

#### 1. `backends/lerobot/` — LeRobot adapter

```
backends/lerobot/
├── __init__.py        # LerobotBackend class
├── motion.py          # arm.pick / arm.place / arm.home → LeRobot policy invocations
├── perception.py      # perceive.rgb / perceive.depth via LeRobot's camera pipeline
├── servo.py           # Direct joint reads/writes (LeRobot's MotorBus)
├── doctor.py          # Health probe (port reachable, motors enumerable)
└── capabilities.py    # Dispatch table: capability_name → handler
```

```python
from lerobot.common.robot_devices.robots.factory import make_robot

class LerobotBackend(CapabilityBackend):
    name = "lerobot"
    protocols = frozenset({"feetech", "dynamixel"})
    read_only_capabilities = frozenset({"perceive.rgb", "perceive.depth"})

    def open(self, spec: RobotSpec) -> None:
        self._robot = make_robot(self._build_lerobot_config(spec))
        self._robot.connect()

    def capabilities(self) -> frozenset[str]:
        return frozenset({
            "arm.pick", "arm.place", "arm.home",
            "perceive.rgb", "perceive.depth",
            "gripper.open", "gripper.close",
            "lerobot.teleop",         # vendor-namespaced — leader-arm teleop
        })

    def execute(self, capability, args, *, dry_run, estop) -> ExecutionResult:
        return CAPABILITY_HANDLERS[capability](self, args, dry_run=dry_run, estop=estop)
```

**Mapping notes:**
- LeRobot's `make_robot()` factory accepts a config dict; `_build_lerobot_config()` translates manifest `drivers[]` + `kinematics[]`.
- `lerobot.teleop` vendor capability lets the operator drive the follower from the leader (matches `so_arm101_leader.yaml` use case).
- LeRobot's policy infrastructure (ACT, Diffusion Policy, etc.) is OUT of scope for SP3 — adapter exposes raw motion + camera primitives only. Could be a vendor capability `lerobot.run_policy` in a follow-up.

**Heavy install:** `[lerobot]` extra pulls PyTorch and LeRobot's deps. Documented as opt-in.

#### 2. `backends/realsense/` — RealSense adapter

```
backends/realsense/
├── __init__.py        # RealsenseBackend class
├── perception.py      # perceive.rgb / perceive.depth via pyrealsense2 pipeline
├── doctor.py          # Device enumeration check
└── capabilities.py    # Dispatch table
```

```python
import pyrealsense2 as rs

class RealsenseBackend(CapabilityBackend):
    name = "realsense"
    protocols = frozenset({"realsense"})
    read_only_capabilities = frozenset({"perceive.rgb", "perceive.depth"})

    def open(self, spec: RobotSpec) -> None:
        self._pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
        config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        self._pipeline.start(config)

    def capabilities(self) -> frozenset[str]:
        return frozenset({
            "perceive.rgb",
            "perceive.depth",
            "realsense.aligned_depth",  # vendor — depth aligned to RGB frame
        })

    def execute(self, capability, args, *, dry_run, estop) -> ExecutionResult:
        return CAPABILITY_HANDLERS[capability](self, args, dry_run=dry_run, estop=estop)

    def scene_describe(self) -> SceneSnapshot:
        frames = self._pipeline.wait_for_frames(timeout_ms=1000)
        # ... return SceneSnapshot with frame bytes
```

No motion methods. If a manifest declares `realsense` for an arm driver, runtime returns clean error.

#### 3. `backends/registry.py` — tier validator

```python
import re

CORE_CAPABILITY_PREFIXES = frozenset({"arm.", "nav.", "perceive.", "gripper.", "safety."})
_VENDOR_CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*$")


class BackendRegistrationError(Exception):
    pass


def _validate_capability_namespace(backend_name: str, caps: frozenset[str]) -> None:
    """Reject backend registration if any capability is malformed.

    Allowed:
      - Core: starts with one of CORE_CAPABILITY_PREFIXES
      - Vendor: matches r"^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_.]*$"

    Raises BackendRegistrationError on first violation.
    """
    for cap in caps:
        is_core = any(cap.startswith(p) for p in CORE_CAPABILITY_PREFIXES)
        is_vendor_shaped = bool(_VENDOR_CAPABILITY_PATTERN.match(cap))
        if not (is_core or is_vendor_shaped):
            raise BackendRegistrationError(
                f"Backend '{backend_name}' declared capability '{cap}': "
                f"not a core prefix and not in <vendor>.<name> form."
            )
```

Called from `discover_backends()` after `cls()` instantiation, before adding to the registry. Backend with malformed capabilities is logged and skipped (doesn't break the rest of the registry).

#### 4. `schemas/capabilities.json` — core capability schema

```json
{
  "$id": "https://robotmd.dev/schemas/capabilities.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "robot-md core capability arg shapes",
  "definitions": {
    "arm.pick": {
      "type": "object",
      "required": ["target"],
      "properties": {
        "target": {"type": "string", "description": "Object descriptor id from manifest.vision.object_descriptors"},
        "approach_height_mm": {"type": "number", "minimum": 0, "default": 50}
      }
    },
    "arm.place": {
      "type": "object",
      "required": ["destination"],
      "properties": {
        "destination": {"type": "string"},
        "release_height_mm": {"type": "number", "minimum": 0, "default": 30}
      }
    },
    "arm.home": {"type": "object", "additionalProperties": false},
    "perceive.rgb": {"type": "object", "additionalProperties": false},
    "perceive.depth": {"type": "object", "additionalProperties": false},
    "gripper.open": {"type": "object", "additionalProperties": false},
    "gripper.close": {"type": "object", "additionalProperties": false},
    "nav.go_to": {
      "type": "object",
      "required": ["pose"],
      "properties": {"pose": {"type": "object"}}
    },
    "safety.estop": {"type": "object", "additionalProperties": false}
  }
}
```

**Used at:**
- Adapter test time: `assert_capability_args(name, args)` validates adapter-emitted args against the schema.
- `execute_capability` MCP tool: validates incoming args before dispatch.

Vendor capabilities are NOT schemaed in this file — adapter authors define their own arg shapes in their adapter docstrings.

#### 5. `pyproject.toml` — new extras + entry-points

```toml
[project.optional-dependencies]
lerobot   = ["lerobot>=0.5,<0.8", "pyserial>=3.5"]
realsense = ["pyrealsense2>=2.55"]

[project.entry-points."robot_md.backends"]
feetech_depthai = "robot_md.backends.feetech_depthai:FeetechDepthaiBackend"  # existing
lerobot         = "robot_md.backends.lerobot:LerobotBackend"                  # NEW
realsense       = "robot_md.backends.realsense:RealsenseBackend"              # NEW
```

#### 6. Preset updates

Update SO-ARM presets to declare `preferred_backend: lerobot` as primary hint. SP2's `try_resolve` picks `lerobot` if installed, else falls back via the registry's protocol-match path.

```yaml
# so_arm101.yaml — diff
drivers:
  - id: arm_servos
    protocol: feetech
    preferred_backend: lerobot      # CHANGED from feetech_depthai
    # ...
```

`koch_arm.yaml`, `aloha2.yaml`, `so_arm101_leader.yaml`: same change.

Other presets (Stretch3, Reachy2, generic) remain at `feetech_depthai` or get `realsense` for camera drivers.

#### 7. `docs/authoring-a-backend.md` — authoring guide

Sections (target ~2000 words):

1. **What is a backend?** (relationship to ABC, to entry-points, to manifests)
2. **The 30-minute path: copy the template.**
3. **Implementing `CapabilityBackend`:** open/close/execute/capabilities/scene_describe — example-driven.
4. **Capability namespacing:** when to use `arm.*` vs `<vendor>.<name>`. Examples for both.
5. **Testing without hardware:** the mock pattern from `feetech_depthai`'s tests; how to fixture serial/USB.
6. **Packaging + entry-point declaration:** the one pyproject.toml block that makes `robot-md` discover your backend.
7. **Contributing first-party** (in-tree PR) **vs publishing third-party** (PyPI). Trade-offs.
8. **Versioning + ABC stability:** RRF's commitment — additive ABC changes have default impls; breaking changes get a major version bump + 6-month deprecation.

Linked from main README.

#### 8. `examples/backend-template/` — copy-paste template

```
examples/backend-template/
├── README.md                   # 5-step bring-up: copy, rename, edit, install, test
├── pyproject.toml              # Skeleton with [project.entry-points."robot_md.backends"] section
├── src/
│   └── my_backend/
│       ├── __init__.py        # MyBackend(CapabilityBackend) skeleton with TODOs
│       ├── capabilities.py    # Dispatch table skeleton
│       └── motion.py          # arm.* skeleton handlers (raise NotImplementedError)
└── tests/
    └── test_my_backend.py     # Mock-hardware test fixture + 3 example tests
```

Skeleton's `__init__.py` has explicit TODO comments at each abstract method.

### Data Flow

#### Operator: SO-100 owner using LeRobot adapter

```
Operator                                State
─────────────────────────────────────────────────────────────────
$ claude plugin install robot-md   →    Plugin installed (manifest-only by default
                                          per SP1).

$ pip install \                    →    LeRobot, PyTorch, etc. installed.
    'robot-md[lerobot]'                 Entry-point `lerobot` registered.

$ robot-md init so100              →    Autodetect runs; SO-ARM-shaped scan.
                                        Score: MEDIUM tier (per SP2).
                                        Operator picks so_arm101 from prompt.

                                        Backend resolution (SP2's try_resolve):
                                          drivers[0].preferred_backend = "lerobot"
                                          Entry-points scan:
                                            • lerobot          ✓ registered
                                            • feetech_depthai  ✗ not installed
                                          → resolves to "lerobot"

                                        write_manifest:
                                          drivers:
                                            - id: arm_servos
                                              protocol: feetech
                                              backend: lerobot
                                              preferred_backend: lerobot

                                        Output:
                                          ✓ Wrote ROBOT.md
                                          Resolved backend: lerobot (from entry-points).

$ claude                           →    Plugin spawns both MCP servers (per SP1).

> "Find a red lego..."              →   Skill activates → safety check → motion intent.
                                        Claude calls execute_task.

                                        Runtime resolves: BackendRegistry.resolve(spec)
                                          → spec.drivers[0].backend = "lerobot"
                                          → returns LerobotBackend instance.

                                        backend.open(spec) → LeRobot's make_robot(...).
                                        execute("arm.pick", {"target": "red_lego"})
                                          → motion.py handler →
                                          LeRobot policy/IK invocation →
                                          servo writes via MotorBus.

                                        Claude reports outcome to operator.
```

**What's new in SP3:** `lerobot` entry-point gets selected because (a) preset hints upgraded to point at it for SO-ARM kits, (b) it's the only backend installed for `feetech` on this operator's machine. SP1 wiring + SP2 resolver carry the work; SP3 just adds another option in the registry.

#### Operator: both `lerobot` and `feetech_depthai` installed

```
Resolution order (SP2's try_resolve, unchanged):
  1. drivers[].backend explicit → wins
  2. drivers[].preferred_backend hint → registry tries that name first
  3. Protocol fallback (alphabetical by entry-point name)

Preset hint disambiguates → "lerobot" wins.
Operator override: edit ROBOT.md to backend: feetech_depthai.
```

#### Operator: RealSense camera-only

```
$ pip install 'robot-md[realsense]' →    pyrealsense2 installed.
                                         Entry-point `realsense` registered.

$ robot-md init scanrig             →    Autodetect: no arm bus, RealSense D435.
                                         LOW tier (no arm preset matches).
                                         BUT camera autodetect found D435.
                                         write_manifest LOW path:
                                           - minimal manifest skeleton with TODOs for
                                             metadata.manufacturer + physics.dof
                                           - drivers[] DOES include the camera driver
                                             from autodetect:
                                               - id: vision
                                                 protocol: realsense
                                                 backend: realsense   ← try_resolve
                                           - physics.cameras[0] pre-filled with
                                             driver_id: vision + autodetect_default
                                             extrinsic placeholder

                                         Output:
                                           ✓ Wrote ROBOT.md (minimal, LOW tier)
                                           Pre-filled drivers[0]: vision (realsense backend).
                                           Pre-filled physics.cameras[0]: realsense_d435.
                                           No arm preset matched — TODO markers on
                                             metadata.manufacturer and physics.dof.
```

LOW tier still pre-fills both the camera *driver* and its perception entry — autodetect-derived hardware survives even when no arm preset matches. The only TODO markers are for fields autodetect can't probe (manufacturer, intended use). Camera-only rigs become valid manifests once those are filled in.

#### Adapter author: writing a Dynamixel adapter

```
Author                                  State
─────────────────────────────────────────────────────────────────
$ cp -r robot-md/examples/         →    ~/robot-md-backend-dynamixel/
    backend-template \                    ├── README.md
    ~/robot-md-backend-dynamixel          ├── pyproject.toml
                                          ├── src/my_backend/...
                                          └── tests/test_my_backend.py

$ cd ~/robot-md-backend-dynamixel
(Edit pyproject.toml, package name, entry-point name)
(Edit src/my_backend/__init__.py)  →    Implement protocols, capabilities,
                                          open/close/execute.
                                        Tier validator at registration:
                                          - arm.pick           ✓ core
                                          - dynamixel.indirect_address ✓ vendor
                                          → all valid

(Edit tests/ — wire mock SDK fixtures)

$ pip install -e .                 →    Editable install. Entry-point registered.
$ pytest                           →    Unit tests pass.

$ robot-md init reachy2            →    Autodetect, MEDIUM-tier prompt.
                                        try_resolve picks `dynamixel` for the protocol.
                                        Manifest written with backend: dynamixel.

$ claude                           →    Runtime imports new backend, drives Reachy2.
```

**Total time from `cp -r` to working entry-point:** target under 30 minutes for an experienced Python author.

**Two contribution paths:**
- **Standalone PyPI publish:** `python -m build && twine upload dist/*`. Operators run `pip install robot-md-backend-dynamixel`.
- **First-party PR:** move source into `cli/src/robot_md/backends/dynamixel/`, add `[dynamixel]` extra. Reviewed against template invariants.

#### State summary

| Scenario | Resolution path | Result |
|---|---|---|
| One backend installed for protocol | `try_resolve("feetech", None)` → that backend | Works automatically |
| Multiple backends installed, preset has hint | `try_resolve("feetech", "lerobot")` → "lerobot" | Hint wins |
| Multiple installed, no hint | First alphabetical | Deterministic, document order |
| Operator override | Manifest's `drivers[].backend` explicit | Wins over everything |
| No backend installed | `try_resolve` returns None; manifest has hint name only | Runtime fails with clean "no_backend" error |

### Error Handling

#### (a) Caught — structured handling

| Failure | Where caught | Operator/author sees |
|---|---|---|
| Adapter declares malformed capability | `_validate_capability_namespace` in `registry.py` | `BackendRegistrationError` raised at `discover_backends`. Logged. Adapter skipped — registry continues. |
| Adapter raises during `cls()` instantiation | Existing try/except in `discover_backends` | Adapter skipped silently. Surfaces in `robot-md doctor` as `backend 'X' failed to load`. |
| Adapter's `open(spec)` raises | Runtime — `execute_capability` wraps `backend.open()` | Returns `{status: "error", reason: "backend_open_failed", detail: "<exception>"}`. |
| Hardware SDK import fails (e.g., librealsense.so missing) | Adapter's `__init__.py` lazy-imports the SDK | Adapter raises `ImportError` at registration; caught + logged + adapter skipped. Doctor surfaces missing .so file. |
| Backend declared protocol it can't actually drive | Runtime — `execute_capability` returns no_backend | Authoring doc emphasizes: declare only what `execute()` actually handles. |
| Two backends installed for same protocol, no preset hint | `try_resolve` (SP2) returns alphabetical first | Init's closing line surfaces the choice and how to override. |
| Adapter's `execute()` returns malformed `ExecutionResult` | Runtime in `execute_capability` validates dataclass shape | Returns `{status: "error", reason: "adapter_protocol_violation"}`. Bug in adapter, not operator. |

#### (b) Pass-through

| Failure | Surface |
|---|---|
| `pip install 'robot-md[lerobot]'` fails | pip's own error. Init hints document the lerobot extra is heavy. |
| LeRobot's runtime errors during motion | Propagate up as ExecutionResult with `status="error"`, `reason="backend_runtime_error"`. |
| Adapter test fails because hardware SDK has new release with breaking API | Author's responsibility. SP3 ships pinned ranges in extras; author updates pin. |

#### (c) Edge cases — defensive handling

| Edge case | Defense |
|---|---|
| Vendor capability shadows core (`arm.pick_v2` to compete with `arm.pick`) | Tier validator allows `arm.*` (core prefix). Lints as confusing in adapter docs. Not blocked. |
| Vendor capability name has uppercase or hyphens | Regex rejects. Author sees registration error with the regex. |
| Adapter declares core capability it doesn't implement | `execute("arm.pick", ...)` raises `KeyError` from dispatch table. Caught; returns `not_implemented`. Tests catch this. |
| LeRobot adapter's `_build_lerobot_config()` fails (manifest fields missing) | Raises `ConfigError` with missing field name. `execute_capability` wraps and returns `{status: "error", reason: "config_invalid"}`. |
| Operator has fork of LeRobot at different version than pinned range | pip resolution fails (good — clean error) or fork wins (operator's choice). Document pinned range in extra. |
| Capability schema references unimplemented capability | Schema is forward-looking. Not an error. |
| Schema arg shape drifts from handler signature | Adapter test suite asserts handler accepts schema-valid args. Drift caught at `pytest`. |
| Operator pip-installs malicious third-party adapter | Out of SP3 scope. Document trust model: third-party unaudited; first-party reviewed. |
| Two adapters claim same name | Python entry-points dedupe by name; later-installed wins. Vendor coordination through naming convention (`robot-md-backend-<vendor>-<hardware>`). |
| Existing `feetech_depthai` regressed by tier validator | Verified: all capabilities are core-prefixed. Ships green. No grandfathering needed. |

#### Explicit non-goals

- **ABC versioning enforcement.** Documented, not mechanically enforced.
- **Vendor adapter audit.** Third-party PyPI adapters are not vetted by RRF.
- **Capability collision arbitration.** Manifest's `drivers[].backend` decides. No "merge" semantics.
- **Hardware SDK version coordination.** Each adapter pins its own SDK range.
- **Mock hardware fidelity.** Tests cover adapter plumbing, not LeRobot's correctness.

### Testing

#### Tier validator

| Test | Verifies |
|---|---|
| `test_capability_namespace_core_accepted.py` (NEW) | Validator passes for `arm.pick`, `nav.go_to`, `perceive.rgb`, `gripper.open`, `safety.estop`. |
| `test_capability_namespace_vendor_accepted.py` (NEW) | Validator passes for `lerobot.teleop`, `realsense.aligned_depth`, `franka.cartesian_impedance`, `my_corp.skill_x`. |
| `test_capability_namespace_malformed_rejected.py` (NEW) | Validator raises for `pick`, `Arm.pick`, `arm-pick`, `.arm.pick`, `arm.`. |
| `test_capability_namespace_skips_in_discovery.py` (NEW) | Backend with one bad capability skipped during `discover_backends()`; others still register. |

#### LeRobot adapter unit tests

| Test | Verifies |
|---|---|
| `test_lerobot_backend_protocols.py` (NEW) | `protocols == frozenset({"feetech", "dynamixel"})`. |
| `test_lerobot_backend_capabilities_valid.py` (NEW) | All declared capabilities pass tier validator. |
| `test_lerobot_backend_open_mocked.py` (NEW) | Mock `make_robot`. Pass minimal RobotSpec. Assert `_robot.connect()` called. |
| `test_lerobot_build_config_so_arm101.py` (NEW) | `_build_lerobot_config(spec)` for SO-ARM101 produces config dict with 6 motors, correct port, baud. |
| `test_lerobot_execute_arm_pick_mocked.py` (NEW) | Call `execute("arm.pick", {"target": "red_lego"}, dry_run=True)`. Assert dispatch table invoked correct handler. |
| `test_lerobot_execute_unknown_capability.py` (NEW) | `execute("arm.dance", ...)` returns `not_implemented` ExecutionResult. |
| `test_lerobot_dry_run.py` (NEW) | `dry_run=True` produces ExecutionResult with `trajectory` populated, no actual writes. |
| `test_lerobot_capabilities_schema_compliance.py` (NEW) | For each core capability declared, `capabilities.json` schema validates a minimal valid args dict. |

#### RealSense adapter unit tests

| Test | Verifies |
|---|---|
| `test_realsense_backend_protocols.py` (NEW) | `protocols == frozenset({"realsense"})`. |
| `test_realsense_capabilities_camera_only.py` (NEW) | Capabilities are `{"perceive.rgb", "perceive.depth", "realsense.aligned_depth"}`. No `arm.*`. |
| `test_realsense_open_mocked.py` (NEW) | Mock pyrealsense2 pipeline. Assert `start()` called with color + depth streams enabled. |
| `test_realsense_scene_describe_mocked.py` (NEW) | Mock pipeline returns frames; `scene_describe()` returns SceneSnapshot with non-empty frame bytes. |
| `test_realsense_no_arm_capability.py` (NEW) | `execute("arm.pick", ...)` returns `not_implemented`. |

#### Integration tests

| Test | Verifies |
|---|---|
| `test_init_sp3_lerobot_resolves.py` (NEW) | Mock entry-points: register both `lerobot` and `feetech_depthai`. SO-ARM101 scan + preset hint → manifest gets `backend: lerobot`. |
| `test_init_sp3_realsense_camera_only.py` (NEW) | Only `realsense` registered. RealSense-only scan → LOW tier, but cameras pre-filled with `realsense` backend. |
| `test_init_sp3_no_lerobot_falls_back.py` (NEW) | Only `feetech_depthai` registered. SO-ARM101 scan + preset hints `lerobot`. `try_resolve` returns `"lerobot"` (hint passes through). Manifest pre-filled. Closing output mentions install command. |
| `test_runtime_dispatches_to_correct_backend.py` (NEW) | Manifest has `backend: lerobot`; both backends installed. Runtime dispatches to `LerobotBackend`. |
| `test_runtime_two_backends_same_protocol_explicit_wins.py` (NEW) | Both installed; manifest explicit `backend: feetech_depthai`. Runtime dispatches to feetech_depthai. |

#### Schema tests

| Test | Verifies |
|---|---|
| `test_capabilities_schema_loads.py` (NEW) | `schemas/capabilities.json` parses as valid JSON-Schema (draft 2020-12). |
| `test_capabilities_schema_arg_validation.py` (NEW) | For `arm.pick`, valid `{target: "red_lego"}` passes; `{}` fails with clear error; `{target: 42}` fails. |
| `test_capabilities_schema_all_core_caps_present.py` (NEW) | Every prefix in `CORE_CAPABILITY_PREFIXES` has at least one defined capability. Catches drift. |
| `test_capabilities_schema_sync_ts.py` (NEW) | After `scripts/sync-schema.mjs`, TS schema bundle contains same definitions. |

#### Backend template tests

| Test | Verifies |
|---|---|
| `test_backend_template_scaffolds.py` (NEW) | Copy template to tmp dir. `pip install -e .`. Assert entry-point appears in `entry_points(group="robot_md.backends")`. |
| `test_backend_template_tests_pass.py` (NEW) | Template's `tests/` passes when run as-is (TODO handlers `xfail`). Smoke test of plumbing. |
| `test_backend_template_validates_namespace.py` (NEW) | Template's example capabilities pass tier validator. |

#### Documentation tests

| Test | Verifies |
|---|---|
| `test_docs_authoring_examples_executable.py` (NEW) | Extract Python code blocks from `docs/authoring-a-backend.md`. Run each through `compile()`. No syntax errors. |

#### Hardware tests

| Test | Verifies |
|---|---|
| `test_sp3_lerobot_so_arm101_pick.py` (NEW, `@hardware`) | Real SO-ARM101 + LeRobot installed. Run `arm.pick` for red lego on bob via LeRobot adapter. Compare trajectory roughly matches feetech_depthai. Skipped in CI. |
| `test_sp3_realsense_d435_perceive.py` (NEW, `@hardware`) | Real RealSense D435. `perceive.rgb` and `perceive.depth` produce non-empty frames. Skipped in CI. |

#### Manual smoke checklist — `cli/tests/manual/sp3_adapter_smoke.md`

1. **LeRobot adapter on bob:** `pip uninstall robot-md[feetech-depthai]; pip install robot-md[lerobot]; robot-md init bob --yes` → manifest `backend: lerobot`. `claude` → motion via LeRobot.
2. **Two adapters installed, preset hint:** `pip install robot-md[feetech-depthai,lerobot]; robot-md init bob` → init explanation surfaces both, picks `lerobot` per hint.
3. **RealSense camera-only:** rig with D435, no arm. `robot-md init scanrig --yes` → LOW tier with camera pre-filled.
4. **Template author flow:** `cp -r examples/backend-template ~/foo; cd ~/foo; pip install -e .; pytest` → entry-point registered, template tests pass.

#### Coverage gaps acknowledged

- Live LeRobot SDK behavior changes — mocked tests don't catch upstream drift. Pinned ranges + manual smoke at SDK release.
- Cross-platform RealSense — tests run on Linux only.
- Concurrent backend stress — two adapters opening same `/dev/ttyACM0` not tested. Documented as anti-pattern.
- Vendor adapter security audit — third-party PyPI adapters have no validation chain.

## Open Questions

1. **LeRobot version pinning.** LeRobot's API is pre-1.0 and changes between minor versions. **Action:** lock initial pin at `>=0.5,<0.8` based on current release; update before SP3 ships if newer compatible version exists.
2. **`make_robot()` config translation completeness.** LeRobot's RobotConfig dataclass has fields that don't map cleanly from `ROBOT.md` (e.g., calibration files). **Action:** during implementation, map what we can and document gaps; defer rich calibration to SP4 territory.
3. **Capability schema as Python validator vs JSON-Schema.** Python validation is more flexible but harder to share with rcan-ts. JSON-Schema is portable. **Action:** start with JSON-Schema (this design); consider Python wrapper if validation needs grow beyond what JSON-Schema expresses.

## Success Criteria

SP3 is done when:

- [ ] Eight components updated/created and merged.
- [ ] `[lerobot]` and `[realsense]` extras install cleanly on Linux + macOS (Linux primary; macOS best-effort).
- [ ] All unit + integration tests pass.
- [ ] Manual smoke checklist passes 4/4.
- [ ] Hardware tests pass on bob's RPi5 (LeRobot path) and a RealSense-equipped rig.
- [ ] Authoring guide reviewed by one external robotics engineer; feedback incorporated.
- [ ] Backend template scaffolds in <60 seconds end-to-end (`cp` + `pip install -e .` + `pytest`).
- [ ] Demo dry-run: `pip install robot-md[lerobot]; robot-md init so100; claude; "find a red lego"` end-to-end on a stock SO-100 (no RRF-specific config).

## Sub-project Relationships

- **SP2 → SP3.** SP2's `try_resolve` and preset `preferred_backend` field are the foundation SP3 plugs into. SP3 adds entries to the registry; resolution logic doesn't change.
- **SP3 → SP4.** SP4's "claude-authored driver" workflow scaffolds new backends using SP3's template. Without the template, SP4 has no shape to fill in.
- **SP3 → SP5.** SP5's gap-feedback loop sends "no backend matches this hardware" issues to RRF. The contributor response is "use SP3's template to write one." Closes the loop.
- **SP3 unblocks the multi-vendor demo.** "Watch Claude drive a SO-100 via LeRobot, then a RealSense-only rig via realsense, then back to bob's feetech_depthai — all the same flow." Strongest SP3 reveal.

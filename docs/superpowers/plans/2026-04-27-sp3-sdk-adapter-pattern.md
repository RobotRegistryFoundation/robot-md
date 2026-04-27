# SP3 — SDK Adapter Pattern Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the SP3 SDK adapter pattern — two new in-tree backends (`lerobot`, `realsense`), the capability-metadata addendum (`Capability` dataclass + optional `describe_capabilities()` ABC method + `enumerate_capabilities(registry)` walker), the capability-tier validator at backend registration, the core `capabilities.json` JSON-Schema, an authoring guide + copy-paste backend template, and updated SO-ARM presets that hint at `lerobot`. Existing `feetech_depthai` continues to work unchanged.

**Architecture:** Add `cli/src/robot_md/backends/{lerobot,realsense}/` adapter packages implementing the existing `CapabilityBackend` ABC. Extend `CapabilityBackend` with a concrete-default `describe_capabilities()` returning rich `Capability` metadata; preserve the `capabilities() -> frozenset[str]` method for backward compatibility. Add a tier validator in `backends/registry.py` (core prefix or `<vendor>.<name>` regex; malformed names cause the backend to be skipped during discovery). Add `enumerate_capabilities(registry)` as the public walker downstream consumers (SP-HP daemon, future robot-md-http bridge, the new `robot-md describe-capabilities` CLI) plug into. Per the SP1-5 simplification-revisions Revision 3, add a `[hardware]` meta-extra in `cli/pyproject.toml` that pulls all common backends; granular `[lerobot]` / `[realsense]` extras stay for advanced installs.

**Tech Stack:** Python 3.10+, pytest, FastMCP (`mcp.server.fastmcp`), HuggingFace LeRobot (`lerobot>=0.5,<0.8`), `pyrealsense2>=2.55`, existing `jsonschema` Draft 2020-12 validation, `importlib.metadata.entry_points` for backend discovery.

**Spec:** `docs/superpowers/specs/2026-04-26-sp3-sdk-adapter-pattern-design.md` (with the 2026-04-27 capability-metadata addendum).

---

## File Structure

**Capability metadata foundation (the addendum):**
- `cli/src/robot_md/backends/capability.py` — NEW. `Capability` dataclass + namespace-derivation helper.
- `cli/src/robot_md/backends/_capability_default.py` — NEW. `describe_default(backend_name, caps)` builds `Capability` objects from `capabilities.json` lookup.
- `cli/src/robot_md/backends/base.py` — MODIFY. Add concrete `describe_capabilities()` default method on `CapabilityBackend`.
- `cli/src/robot_md/backends/registry.py` — MODIFY. Add `CORE_CAPABILITY_PREFIXES`, `_VENDOR_CAPABILITY_PATTERN`, `BackendRegistrationError`, `_validate_capability_namespace`; wire validator into `discover_backends()`; add `iter_classes()` method on `BackendRegistry`.
- `cli/src/robot_md/backends/__init__.py` — MODIFY. Re-export `Capability`; add `enumerate_capabilities(registry)` module function.
- `cli/src/robot_md/schemas/capabilities.json` — NEW. JSON-Schema (Draft 2020-12) for core capability arg shapes.

**RealSense backend (camera-only):**
- `cli/src/robot_md/backends/realsense/__init__.py` — NEW. `RealsenseBackend` class.
- `cli/src/robot_md/backends/realsense/perception.py` — NEW. `perceive.rgb` / `perceive.depth` handlers.
- `cli/src/robot_md/backends/realsense/doctor.py` — NEW. Device enumeration health probe.
- `cli/src/robot_md/backends/realsense/capabilities.py` — NEW. Capability dispatch table.

**LeRobot backend (motion + camera):**
- `cli/src/robot_md/backends/lerobot/__init__.py` — NEW. `LerobotBackend` class.
- `cli/src/robot_md/backends/lerobot/motion.py` — NEW. `arm.pick` / `arm.place` / `arm.home` / `gripper.*` handlers.
- `cli/src/robot_md/backends/lerobot/perception.py` — NEW. `perceive.rgb` / `perceive.depth` via LeRobot's camera pipeline.
- `cli/src/robot_md/backends/lerobot/servo.py` — NEW. Direct joint reads/writes via LeRobot's `MotorBus`.
- `cli/src/robot_md/backends/lerobot/doctor.py` — NEW. Port-reachability + motor-enumeration probe.
- `cli/src/robot_md/backends/lerobot/capabilities.py` — NEW. Capability dispatch table.

**pyproject + entry-points:**
- `cli/pyproject.toml` — MODIFY. Add `[hardware]` (meta), `[lerobot]`, `[realsense]` optional-dependency groups; add `lerobot` and `realsense` entry-point declarations under `[project.entry-points."robot_md.backends"]`.

**Presets:**
- `cli/src/robot_md/presets/so_arm101.yaml` — MODIFY. Add `preferred_backend: lerobot` to the arm-servos driver entry.
- `cli/src/robot_md/presets/so_arm101_leader.yaml` — MODIFY. Same.
- `cli/src/robot_md/presets/koch_arm.yaml` — MODIFY. Same.
- `cli/src/robot_md/presets/aloha2.yaml` — MODIFY. Same.

**CLI consumer of `enumerate_capabilities()` (proves the API end-to-end):**
- `cli/src/robot_md/__main__.py` — MODIFY. Add `describe-capabilities` Typer subcommand.

**Authoring guide + backend template:**
- `docs/authoring-a-backend.md` — NEW. ~2000-word adapter authoring guide (8 sections per spec § 7).
- `examples/backend-template/README.md` — NEW. 5-step bring-up.
- `examples/backend-template/pyproject.toml` — NEW. Skeleton with entry-point block.
- `examples/backend-template/src/my_backend/__init__.py` — NEW. `MyBackend(CapabilityBackend)` skeleton with TODO comments.
- `examples/backend-template/src/my_backend/capabilities.py` — NEW. Dispatch-table skeleton.
- `examples/backend-template/src/my_backend/motion.py` — NEW. `arm.*` skeleton handlers (raise `NotImplementedError`).
- `examples/backend-template/tests/test_my_backend.py` — NEW. Mock-hardware test fixture + 3 example tests.

**Tests (under `cli/tests/`):**
- `cli/tests/backends/test_capability_dataclass.py` — NEW.
- `cli/tests/backends/test_capability_metadata_default.py` — NEW.
- `cli/tests/backends/test_enumerate_capabilities.py` — NEW.
- `cli/tests/backends/test_capability_namespace_core_accepted.py` — NEW.
- `cli/tests/backends/test_capability_namespace_vendor_accepted.py` — NEW.
- `cli/tests/backends/test_capability_namespace_malformed_rejected.py` — NEW.
- `cli/tests/backends/test_capability_namespace_skips_in_discovery.py` — NEW.
- `cli/tests/backends/test_capabilities_schema_loads.py` — NEW.
- `cli/tests/backends/test_capabilities_schema_arg_validation.py` — NEW.
- `cli/tests/backends/test_capabilities_schema_all_core_caps_present.py` — NEW.
- `cli/tests/backends/test_existing_capabilities_method_unchanged.py` — NEW.
- `cli/tests/backends/test_lerobot_backend_protocols.py` — NEW.
- `cli/tests/backends/test_lerobot_backend_capabilities_valid.py` — NEW.
- `cli/tests/backends/test_lerobot_backend_open_mocked.py` — NEW.
- `cli/tests/backends/test_lerobot_build_config_so_arm101.py` — NEW.
- `cli/tests/backends/test_lerobot_execute_arm_pick_mocked.py` — NEW.
- `cli/tests/backends/test_lerobot_execute_unknown_capability.py` — NEW.
- `cli/tests/backends/test_lerobot_dry_run.py` — NEW.
- `cli/tests/backends/test_lerobot_capabilities_schema_compliance.py` — NEW.
- `cli/tests/backends/test_realsense_backend_protocols.py` — NEW.
- `cli/tests/backends/test_realsense_capabilities_camera_only.py` — NEW.
- `cli/tests/backends/test_realsense_open_mocked.py` — NEW.
- `cli/tests/backends/test_realsense_scene_describe_mocked.py` — NEW.
- `cli/tests/backends/test_realsense_no_arm_capability.py` — NEW.
- `cli/tests/backends/test_describe_capabilities_cli.py` — NEW. End-to-end CLI smoke for the new subcommand.
- `cli/tests/integration/test_init_sp3_lerobot_resolves.py` — NEW.
- `cli/tests/integration/test_init_sp3_realsense_camera_only.py` — NEW.
- `cli/tests/integration/test_init_sp3_no_lerobot_falls_back.py` — NEW.
- `cli/tests/integration/test_runtime_dispatches_to_correct_backend.py` — NEW.
- `cli/tests/integration/test_runtime_two_backends_same_protocol_explicit_wins.py` — NEW.
- `cli/tests/backends/test_backend_template_scaffolds.py` — NEW.
- `cli/tests/backends/test_backend_template_tests_pass.py` — NEW.
- `cli/tests/backends/test_backend_template_validates_namespace.py` — NEW.
- `cli/tests/docs/test_docs_authoring_examples_executable.py` — NEW.
- `cli/tests/hardware/test_sp3_lerobot_so_arm101_pick.py` — NEW (`@pytest.mark.hardware`).
- `cli/tests/hardware/test_sp3_realsense_d435_perceive.py` — NEW (`@pytest.mark.hardware`).

**Manual smoke checklist:**
- `cli/tests/manual/sp3_adapter_smoke.md` — NEW.

---

## Phase A — Capability metadata foundation

These tasks deliver the spec's "Capability Metadata Addendum (2026-04-27)" plus the tier validator. Nothing else binds without them.

### Task 1: Add `capabilities.json` core schema

**Files:**
- Create: `cli/src/robot_md/schemas/capabilities.json`
- Test: `cli/tests/backends/test_capabilities_schema_loads.py`, `cli/tests/backends/test_capabilities_schema_arg_validation.py`, `cli/tests/backends/test_capabilities_schema_all_core_caps_present.py`

- [ ] **Step 1: Write the loads-and-parses test**

```python
# cli/tests/backends/test_capabilities_schema_loads.py
from __future__ import annotations

import json
from pathlib import Path


def test_capabilities_schema_parses_as_json() -> None:
    path = Path(__file__).parents[2] / "src" / "robot_md" / "schemas" / "capabilities.json"
    data = json.loads(path.read_text())
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "definitions" in data
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capabilities_schema_loads.py -v
```

Expected: FAIL with `FileNotFoundError` because `cli/src/robot_md/schemas/capabilities.json` does not exist yet.

- [ ] **Step 3: Create the schema file**

```json
// cli/src/robot_md/schemas/capabilities.json
{
  "$id": "https://robotmd.dev/schemas/capabilities.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "robot-md core capability arg shapes",
  "definitions": {
    "arm.pick": {
      "type": "object",
      "required": ["target"],
      "properties": {
        "target": {
          "type": "string",
          "description": "Object descriptor id from manifest.vision.object_descriptors"
        },
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

(Note: drop the `//` comment line when actually saving — JSON-Schema doesn't permit comments. The leading `//` is a marker for the engineer.)

- [ ] **Step 4: Run test to verify it passes**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capabilities_schema_loads.py -v
```

Expected: PASS.

- [ ] **Step 5: Add the arg-validation test**

```python
# cli/tests/backends/test_capabilities_schema_arg_validation.py
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


_SCHEMA_PATH = Path(__file__).parents[2] / "src" / "robot_md" / "schemas" / "capabilities.json"


def _load_def(name: str) -> dict:
    schema = json.loads(_SCHEMA_PATH.read_text())
    return schema["definitions"][name]


def test_arm_pick_accepts_minimal_valid_args() -> None:
    jsonschema.validate({"target": "red_lego"}, _load_def("arm.pick"))


def test_arm_pick_rejects_missing_target() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({}, _load_def("arm.pick"))


def test_arm_pick_rejects_wrong_target_type() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"target": 42}, _load_def("arm.pick"))


def test_arm_home_rejects_extra_properties() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"surprise": True}, _load_def("arm.home"))
```

- [ ] **Step 6: Run validation tests**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capabilities_schema_arg_validation.py -v
```

Expected: PASS (4/4).

- [ ] **Step 7: Add the all-core-prefixes-present drift test**

```python
# cli/tests/backends/test_capabilities_schema_all_core_caps_present.py
from __future__ import annotations

import json
from pathlib import Path


_SCHEMA_PATH = Path(__file__).parents[2] / "src" / "robot_md" / "schemas" / "capabilities.json"

# Mirrors backends/registry.py CORE_CAPABILITY_PREFIXES (introduced in Task 2).
_CORE_PREFIXES = ("arm.", "nav.", "perceive.", "gripper.", "safety.")


def test_every_core_prefix_has_at_least_one_capability_defined() -> None:
    schema = json.loads(_SCHEMA_PATH.read_text())
    defined = set(schema["definitions"].keys())
    for prefix in _CORE_PREFIXES:
        assert any(name.startswith(prefix) for name in defined), (
            f"capabilities.json has no capability for core prefix {prefix!r}"
        )
```

- [ ] **Step 8: Run drift test**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capabilities_schema_all_core_caps_present.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/schemas/capabilities.json cli/tests/backends/test_capabilities_schema_loads.py cli/tests/backends/test_capabilities_schema_arg_validation.py cli/tests/backends/test_capabilities_schema_all_core_caps_present.py
git commit -m "$(cat <<'EOF'
feat(sp3): add core capabilities.json JSON-Schema

JSON-Schema (Draft 2020-12) for the nine core capability arg shapes
(arm.pick / arm.place / arm.home / perceive.rgb / perceive.depth /
gripper.open / gripper.close / nav.go_to / safety.estop). Used at adapter
test time and at execute_capability dispatch time to validate operator-
or skill-supplied args before the backend ever sees them.

Tests: parses-as-JSON-Schema, valid/invalid arg validation per shape,
drift guard that every core prefix has at least one defined capability.

Vendor capabilities are NOT schemaed in this file — adapter authors
define their own arg shapes (see Task 5's describe_capabilities() default).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add capability tier validator (core / vendor namespaces)

**Files:**
- Modify: `cli/src/robot_md/backends/registry.py` (add `CORE_CAPABILITY_PREFIXES`, `_VENDOR_CAPABILITY_PATTERN`, `BackendRegistrationError`, `_validate_capability_namespace`)
- Test: `cli/tests/backends/test_capability_namespace_core_accepted.py`, `cli/tests/backends/test_capability_namespace_vendor_accepted.py`, `cli/tests/backends/test_capability_namespace_malformed_rejected.py`

- [ ] **Step 1: Write the core-accepted test**

```python
# cli/tests/backends/test_capability_namespace_core_accepted.py
from __future__ import annotations

from robot_md.backends.registry import _validate_capability_namespace


def test_core_prefixes_accepted() -> None:
    # Should not raise — these are all core-prefixed.
    _validate_capability_namespace(
        "test_backend",
        frozenset({"arm.pick", "nav.go_to", "perceive.rgb", "gripper.open", "safety.estop"}),
    )
```

- [ ] **Step 2: Write the vendor-accepted test**

```python
# cli/tests/backends/test_capability_namespace_vendor_accepted.py
from __future__ import annotations

from robot_md.backends.registry import _validate_capability_namespace


def test_vendor_namespaced_accepted() -> None:
    _validate_capability_namespace(
        "test_backend",
        frozenset({
            "lerobot.teleop",
            "realsense.aligned_depth",
            "franka.cartesian_impedance",
            "my_corp.skill_x",
        }),
    )
```

- [ ] **Step 3: Write the malformed-rejected test**

```python
# cli/tests/backends/test_capability_namespace_malformed_rejected.py
from __future__ import annotations

import pytest

from robot_md.backends.registry import (
    BackendRegistrationError,
    _validate_capability_namespace,
)


@pytest.mark.parametrize(
    "bad_capability",
    [
        "pick",        # no namespace
        "Arm.pick",    # uppercase
        "arm-pick",    # hyphen
        ".arm.pick",   # leading dot
        "arm.",        # trailing dot
        "1arm.pick",   # leading digit
        "arm. pick",   # whitespace
    ],
)
def test_malformed_capability_rejected(bad_capability: str) -> None:
    with pytest.raises(BackendRegistrationError) as excinfo:
        _validate_capability_namespace("bad_backend", frozenset({bad_capability}))
    assert "bad_backend" in str(excinfo.value)
    assert bad_capability in str(excinfo.value)
```

- [ ] **Step 4: Run all three tests to verify they fail**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capability_namespace_core_accepted.py tests/backends/test_capability_namespace_vendor_accepted.py tests/backends/test_capability_namespace_malformed_rejected.py -v
```

Expected: FAIL — `ImportError: cannot import name 'BackendRegistrationError' / '_validate_capability_namespace' from 'robot_md.backends.registry'`.

- [ ] **Step 5: Add validator to `registry.py`**

Edit `cli/src/robot_md/backends/registry.py`. After the existing imports (line 1-8), insert:

```python
import re

CORE_CAPABILITY_PREFIXES = frozenset({"arm.", "nav.", "perceive.", "gripper.", "safety."})
_VENDOR_CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*$")


class BackendRegistrationError(Exception):
    """Raised when a backend declares a malformed capability name."""


def _validate_capability_namespace(backend_name: str, caps: frozenset[str]) -> None:
    """Reject backend registration if any capability is malformed.

    Allowed:
      - Core: starts with one of CORE_CAPABILITY_PREFIXES.
      - Vendor: matches r"^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_.]*$".

    Raises BackendRegistrationError on first violation.

    Note: the existing feetech_depthai backend declares `vision.describe`
    and `status.report`. Both pass the vendor regex (they look like
    <vendor>.<name>) so the registry accepts them as vendor-shaped, even
    though they're shipped in a first-party backend. Do NOT expand
    CORE_CAPABILITY_PREFIXES here without coordinating with the SP3 spec
    section on namespacing (the prefix list is RRF-canonical for core
    capabilities only).
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

- [ ] **Step 6: Run all three validator tests to verify they pass**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capability_namespace_core_accepted.py tests/backends/test_capability_namespace_vendor_accepted.py tests/backends/test_capability_namespace_malformed_rejected.py -v
```

Expected: PASS (1 + 1 + 7 parametrized = 9 tests).

- [ ] **Step 7: Commit**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/backends/registry.py cli/tests/backends/test_capability_namespace_core_accepted.py cli/tests/backends/test_capability_namespace_vendor_accepted.py cli/tests/backends/test_capability_namespace_malformed_rejected.py
git commit -m "$(cat <<'EOF'
feat(sp3): capability tier validator at backend registration

CORE_CAPABILITY_PREFIXES = {arm., nav., perceive., gripper., safety.};
vendor regex ^[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*$. Backends that declare a
capability matching neither raise BackendRegistrationError at registration
time.

The existing feetech_depthai backend declares vision.describe and
status.report — these pass the vendor regex (look like <vendor>.<name>),
so feetech_depthai ships green. Do NOT add vision./status. to
CORE_CAPABILITY_PREFIXES — that list is RRF-canonical core only.

Wired into discover_backends() in the next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Wire validator into `discover_backends()`

**Files:**
- Modify: `cli/src/robot_md/backends/registry.py` (extend `discover_backends()` to call the validator and skip on failure)
- Test: `cli/tests/backends/test_capability_namespace_skips_in_discovery.py`

- [ ] **Step 1: Write the discovery-skip test**

```python
# cli/tests/backends/test_capability_namespace_skips_in_discovery.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

from robot_md.backends.base import CapabilityBackend
from robot_md.backends.registry import discover_backends


class _GoodBackend(CapabilityBackend):
    name = "good"
    protocols = frozenset({"feetech"})

    def open(self, spec):
        pass

    def close(self):
        pass

    def capabilities(self) -> frozenset[str]:
        return frozenset({"arm.pick"})

    def execute(self, capability, args, *, dry_run, estop):
        raise NotImplementedError


class _BadBackend(CapabilityBackend):
    name = "bad"
    protocols = frozenset({"feetech"})

    def open(self, spec):
        pass

    def close(self):
        pass

    def capabilities(self) -> frozenset[str]:
        return frozenset({"NOT-VALID"})

    def execute(self, capability, args, *, dry_run, estop):
        raise NotImplementedError


def _fake_entry_points(group: str):
    assert group == "robot_md.backends"
    good_ep = MagicMock()
    good_ep.name = "good"
    good_ep.load.return_value = _GoodBackend
    bad_ep = MagicMock()
    bad_ep.name = "bad"
    bad_ep.load.return_value = _BadBackend
    return [good_ep, bad_ep]


def test_malformed_backend_skipped_others_keep_loading() -> None:
    with patch("robot_md.backends.registry.entry_points", _fake_entry_points):
        out = discover_backends()
    names = sorted(b.name for b in out)
    assert names == ["good"], f"expected only 'good' to load, got {names}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capability_namespace_skips_in_discovery.py -v
```

Expected: FAIL — either `ImportError` on the `entry_points` patch target (current code imports inside the function), or both backends load (since the validator isn't wired yet).

- [ ] **Step 3: Refactor `discover_backends()` to import `entry_points` at module level + call the validator**

Edit `cli/src/robot_md/backends/registry.py`. Replace the entire `discover_backends()` function plus restructure the imports:

```python
"""Backend discovery + deterministic resolution."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from importlib.metadata import entry_points

from robot_md.backends.base import CapabilityBackend
from robot_md.robot_spec import RobotSpec

_log = logging.getLogger(__name__)

CORE_CAPABILITY_PREFIXES = frozenset({"arm.", "nav.", "perceive.", "gripper.", "safety."})
_VENDOR_CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*$")


class BackendRegistrationError(Exception):
    """Raised when a backend declares a malformed capability name."""


def _validate_capability_namespace(backend_name: str, caps: frozenset[str]) -> None:
    """(See Task 2 docstring — body unchanged.)"""
    for cap in caps:
        is_core = any(cap.startswith(p) for p in CORE_CAPABILITY_PREFIXES)
        is_vendor_shaped = bool(_VENDOR_CAPABILITY_PATTERN.match(cap))
        if not (is_core or is_vendor_shaped):
            raise BackendRegistrationError(
                f"Backend '{backend_name}' declared capability '{cap}': "
                f"not a core prefix and not in <vendor>.<name> form."
            )


def discover_backends() -> list[CapabilityBackend]:
    """Load backends registered under the `robot_md.backends` entry-point group.

    Backends with malformed capability names are logged and skipped — the rest
    of the registry continues to load.
    """
    try:
        eps = entry_points(group="robot_md.backends")
    except TypeError:
        # Python 3.9 compatibility fallback — not expected here, but harmless.
        all_eps = entry_points()
        eps = all_eps.get("robot_md.backends", []) if hasattr(all_eps, "get") else []
    out: list[CapabilityBackend] = []
    for ep in sorted(eps, key=lambda e: e.name):
        try:
            cls = ep.load()
            instance = cls()
        except Exception as e:  # noqa: BLE001 — adapter import failures are non-fatal
            _log.warning("backend %r failed to load: %s", ep.name, e)
            continue
        try:
            _validate_capability_namespace(ep.name, instance.capabilities())
        except BackendRegistrationError as e:
            _log.warning("%s — skipping backend.", e)
            continue
        out.append(instance)
    return out
```

(Note: the validator and `BackendRegistrationError` introduced in Task 2 are now at module top level — the same definitions, just relocated above `discover_backends()`. Delete the duplicate definitions you added in Task 2 if they ended up below the function during that edit.)

- [ ] **Step 4: Run discovery-skip test**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capability_namespace_skips_in_discovery.py -v
```

Expected: PASS.

- [ ] **Step 5: Run all backends tests to confirm no regression**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/ -v
```

Expected: all PASS (Task 1 + Task 2 + Task 3 tests).

- [ ] **Step 6: Run full test suite to confirm `feetech_depthai` still loads green**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/spatial_eval -x
```

Expected: all PASS. The feetech_depthai backend declares `vision.describe` and `status.report` — both vendor-shaped, both pass the validator.

- [ ] **Step 7: Commit**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/backends/registry.py cli/tests/backends/test_capability_namespace_skips_in_discovery.py
git commit -m "$(cat <<'EOF'
feat(sp3): wire capability tier validator into backend discovery

discover_backends() now calls _validate_capability_namespace on each
backend's capabilities() set after instantiation. On BackendRegistrationError
the offending backend is logged and skipped; the remaining registry
continues to load.

Hoists the entry_points import to module scope so tests can patch it
deterministically. Existing alphabetical sort + Python 3.9 fallback
preserved.

The existing feetech_depthai backend (vision.describe + status.report)
ships green — both pass the vendor regex.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Add `Capability` dataclass + namespace-derivation helper

**Files:**
- Create: `cli/src/robot_md/backends/capability.py`
- Test: `cli/tests/backends/test_capability_dataclass.py`

- [ ] **Step 1: Write the dataclass shape + namespace-derivation test**

```python
# cli/tests/backends/test_capability_dataclass.py
from __future__ import annotations

import pytest

from robot_md.backends.capability import Capability, derive_namespace


def test_capability_is_frozen_dataclass() -> None:
    cap = Capability(name="arm.pick", namespace="core", arg_schema=None, description="")
    with pytest.raises(Exception):
        cap.name = "arm.place"  # frozen — must raise


def test_derive_namespace_core_prefixes() -> None:
    for name in ("arm.pick", "nav.go_to", "perceive.rgb", "gripper.open", "safety.estop"):
        assert derive_namespace(name) == "core"


def test_derive_namespace_vendor() -> None:
    for name in ("lerobot.teleop", "realsense.aligned_depth", "my_corp.skill_x"):
        assert derive_namespace(name) == "vendor"


def test_derive_namespace_vendor_for_existing_feetech_capabilities() -> None:
    # vision.describe and status.report are NOT in CORE_CAPABILITY_PREFIXES;
    # they are vendor-shaped and should be classified as vendor.
    assert derive_namespace("vision.describe") == "vendor"
    assert derive_namespace("status.report") == "vendor"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capability_dataclass.py -v
```

Expected: FAIL — `ImportError: cannot import name 'Capability' from 'robot_md.backends.capability'`.

- [ ] **Step 3: Create `capability.py`**

```python
# cli/src/robot_md/backends/capability.py
"""Public Capability metadata API.

See SP3 spec § Capability Metadata Addendum (2026-04-27).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from robot_md.backends.registry import CORE_CAPABILITY_PREFIXES


@dataclass(frozen=True)
class Capability:
    """Rich metadata for a capability declared by a backend.

    name        — e.g. "arm.pick", "lerobot.teleop"
    namespace   — "core" if name starts with a CORE_CAPABILITY_PREFIXES entry,
                  otherwise "vendor"
    arg_schema  — JSON-Schema fragment from capabilities.json, or None for
                  vendor capabilities not in the schema
    description — short human-readable; "" if none available
    """

    name: str
    namespace: Literal["core", "vendor"]
    arg_schema: dict | None
    description: str


def derive_namespace(capability_name: str) -> Literal["core", "vendor"]:
    """Return 'core' if the name starts with a core prefix, else 'vendor'."""
    if any(capability_name.startswith(p) for p in CORE_CAPABILITY_PREFIXES):
        return "core"
    return "vendor"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capability_dataclass.py -v
```

Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/backends/capability.py cli/tests/backends/test_capability_dataclass.py
git commit -m "$(cat <<'EOF'
feat(sp3): Capability dataclass + namespace-derivation helper

frozen=True dataclass with name/namespace/arg_schema/description fields.
derive_namespace() classifies a capability name as 'core' (starts with
arm./nav./perceive./gripper./safety.) or 'vendor' (anything else that
passes the registration regex).

vision.describe and status.report (declared by feetech_depthai) are
classified as 'vendor' — documented behavior.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Add `describe_capabilities()` default impl on `CapabilityBackend`

**Files:**
- Create: `cli/src/robot_md/backends/_capability_default.py`
- Modify: `cli/src/robot_md/backends/base.py` (add the concrete default `describe_capabilities()` method)
- Test: `cli/tests/backends/test_capability_metadata_default.py`, `cli/tests/backends/test_existing_capabilities_method_unchanged.py`

- [ ] **Step 1: Write the default-impl test**

```python
# cli/tests/backends/test_capability_metadata_default.py
from __future__ import annotations

from robot_md.backends._capability_default import describe_default


def test_default_returns_capability_objects() -> None:
    out = describe_default("test_backend", frozenset({"arm.pick"}))
    assert len(out) == 1
    cap = out[0]
    assert cap.name == "arm.pick"
    assert cap.namespace == "core"
    assert cap.arg_schema is not None
    assert cap.arg_schema.get("required") == ["target"]


def test_default_for_core_capability_with_no_schema_entry() -> None:
    # No core capability is currently absent from capabilities.json,
    # but the default must handle the drift case gracefully.
    out = describe_default("test_backend", frozenset({"arm.future_capability"}))
    assert len(out) == 1
    cap = out[0]
    assert cap.name == "arm.future_capability"
    assert cap.namespace == "core"
    assert cap.arg_schema is None
    assert cap.description == ""


def test_default_for_vendor_capability() -> None:
    out = describe_default("lerobot", frozenset({"lerobot.teleop"}))
    assert len(out) == 1
    cap = out[0]
    assert cap.name == "lerobot.teleop"
    assert cap.namespace == "vendor"
    assert cap.arg_schema is None
    assert cap.description == ""


def test_default_for_existing_feetech_capabilities() -> None:
    # vision.describe and status.report from feetech_depthai → vendor with None schema.
    out = describe_default(
        "feetech_depthai",
        frozenset({"vision.describe", "status.report"}),
    )
    by_name = {c.name: c for c in out}
    assert by_name["vision.describe"].namespace == "vendor"
    assert by_name["vision.describe"].arg_schema is None
    assert by_name["status.report"].namespace == "vendor"
    assert by_name["status.report"].arg_schema is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capability_metadata_default.py -v
```

Expected: FAIL — `ImportError: cannot import name 'describe_default'`.

- [ ] **Step 3: Create `_capability_default.py`**

```python
# cli/src/robot_md/backends/_capability_default.py
"""Default impl of describe_capabilities() — looks up arg_schema in capabilities.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from robot_md.backends.capability import Capability, derive_namespace

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "capabilities.json"


@lru_cache(maxsize=1)
def _load_capabilities_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


def describe_default(backend_name: str, caps: frozenset[str]) -> list[Capability]:
    """Build Capability objects for each capability the backend declared.

    For each capability:
      - Look up arg_schema in capabilities.json under definitions[name]; None if absent.
      - description: schema's "description" field if present, else "".
      - namespace: derive_namespace(name) — "core" or "vendor".

    Vendor capabilities NOT in capabilities.json get arg_schema=None;
    adapter authors who want richer metadata override describe_capabilities()
    on their CapabilityBackend subclass.
    """
    schema = _load_capabilities_schema()
    defs = schema.get("definitions", {})
    out: list[Capability] = []
    for cap in sorted(caps):
        entry = defs.get(cap)
        out.append(
            Capability(
                name=cap,
                namespace=derive_namespace(cap),
                arg_schema=entry,
                description=(entry or {}).get("description", "") if entry else "",
            )
        )
    return out
```

- [ ] **Step 4: Run default-impl test**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capability_metadata_default.py -v
```

Expected: PASS (4/4).

- [ ] **Step 5: Add `describe_capabilities()` method to `CapabilityBackend`**

Edit `cli/src/robot_md/backends/base.py`. After the existing abstract `execute(...)` method (line 54-61), and before `scene_describe()` (line 63), insert:

```python
    def describe_capabilities(self) -> "list[Capability]":
        """Return rich metadata for each capability this backend declares.

        Default: walk self.capabilities(), look each up in
        cli/src/robot_md/schemas/capabilities.json for arg_schema +
        description; vendor capabilities not in the schema get
        arg_schema=None, description="".

        Adapters MAY override to provide richer vendor metadata
        (e.g., lerobot.teleop description, dynamixel.indirect_address
        arg shapes).
        """
        from robot_md.backends._capability_default import describe_default
        return describe_default(self.name, self.capabilities())
```

The `from robot_md.backends.capability import Capability` is referenced via string annotation to avoid an import cycle.

- [ ] **Step 6: Add the backward-compatibility test**

```python
# cli/tests/backends/test_existing_capabilities_method_unchanged.py
from __future__ import annotations

from robot_md.backends.feetech_depthai import FeetechDepthaiBackend


def test_capabilities_method_returns_frozenset() -> None:
    b = FeetechDepthaiBackend()
    caps = b.capabilities()
    assert isinstance(caps, frozenset)
    expected = frozenset({
        "arm.pick", "arm.place", "arm.reach", "arm.home",
        "vision.describe", "status.report",
    })
    assert caps == expected


def test_describe_capabilities_default_works_for_feetech() -> None:
    b = FeetechDepthaiBackend()
    out = b.describe_capabilities()
    by_name = {c.name: c for c in out}
    # Core capabilities have arg_schema; vendor (vision., status.) do not.
    assert by_name["arm.pick"].arg_schema is not None
    assert by_name["arm.pick"].namespace == "core"
    assert by_name["vision.describe"].arg_schema is None
    assert by_name["vision.describe"].namespace == "vendor"
```

- [ ] **Step 7: Run backward-compat test**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_existing_capabilities_method_unchanged.py -v
```

Expected: PASS (2/2).

- [ ] **Step 8: Commit**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/backends/_capability_default.py cli/src/robot_md/backends/base.py cli/tests/backends/test_capability_metadata_default.py cli/tests/backends/test_existing_capabilities_method_unchanged.py
git commit -m "$(cat <<'EOF'
feat(sp3): describe_capabilities() default impl on CapabilityBackend

Adds a concrete (non-abstract) describe_capabilities() method to the
CapabilityBackend ABC. Default implementation walks self.capabilities()
and looks each name up in capabilities.json — core capabilities get the
schema fragment; vendor capabilities not in the schema get arg_schema=None
and description="". Adapter authors MAY override.

Existing capabilities() -> frozenset[str] is preserved unchanged.
feetech_depthai ships green: arm.pick / arm.place / arm.reach / arm.home
get core arg_schemas; vision.describe + status.report are correctly
classified as vendor with None schema.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Add `iter_classes()` to `BackendRegistry`

**Files:**
- Modify: `cli/src/robot_md/backends/registry.py` (add `iter_classes()` method on `BackendRegistry`)
- Test: `cli/tests/backends/test_enumerate_capabilities.py` (just the iter_classes test for now; full enumerate test in Task 7)

- [ ] **Step 1: Write the iter_classes test**

```python
# cli/tests/backends/test_enumerate_capabilities.py
from __future__ import annotations

from robot_md.backends.base import CapabilityBackend
from robot_md.backends.registry import BackendRegistry


class _StubBackend(CapabilityBackend):
    name = "stub"
    protocols = frozenset({"feetech"})

    def open(self, spec):
        pass

    def close(self):
        pass

    def capabilities(self) -> frozenset[str]:
        return frozenset({"arm.pick"})

    def execute(self, capability, args, *, dry_run, estop):
        raise NotImplementedError


def test_iter_classes_yields_name_class_pairs() -> None:
    reg = BackendRegistry(backends=[_StubBackend()])
    pairs = list(reg.iter_classes())
    assert len(pairs) == 1
    name, cls = pairs[0]
    assert name == "stub"
    assert cls is _StubBackend
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_enumerate_capabilities.py::test_iter_classes_yields_name_class_pairs -v
```

Expected: FAIL — `AttributeError: 'BackendRegistry' object has no attribute 'iter_classes'`.

- [ ] **Step 3: Add `iter_classes()` to `BackendRegistry`**

Edit `cli/src/robot_md/backends/registry.py`. After the `resolve()` method on `BackendRegistry`, add:

```python
    def iter_classes(self) -> "list[tuple[str, type[CapabilityBackend]]]":
        """Return [(backend.name, type(backend)), ...] for every loaded backend.

        Used by enumerate_capabilities() in backends/__init__.py to walk the
        catalog without re-instantiating. The registry already holds live
        instances; iter_classes() exposes (name, class) for callers that
        specifically need the class object.
        """
        return [(b.name, type(b)) for b in self.backends]
```

- [ ] **Step 4: Run iter_classes test**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_enumerate_capabilities.py::test_iter_classes_yields_name_class_pairs -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/backends/registry.py cli/tests/backends/test_enumerate_capabilities.py
git commit -m "$(cat <<'EOF'
feat(sp3): BackendRegistry.iter_classes()

Returns [(backend.name, type(backend)), ...] over loaded backends so
callers that need the class object (rather than the instance) — primarily
the upcoming enumerate_capabilities() module function — can walk the
catalog without re-instantiating.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Add `enumerate_capabilities(registry)` module function

**Files:**
- Modify: `cli/src/robot_md/backends/__init__.py` (re-export `Capability`; add `enumerate_capabilities`)
- Test: `cli/tests/backends/test_enumerate_capabilities.py` (extend with the walker test)

- [ ] **Step 1: Inspect current `backends/__init__.py`**

```bash
cat cli/src/robot_md/backends/__init__.py
```

If it does not yet re-export `BackendRegistry`, prepare to add re-exports for `BackendRegistry`, `Capability`, and `enumerate_capabilities`.

- [ ] **Step 2: Add the enumerate-walker test**

Append to `cli/tests/backends/test_enumerate_capabilities.py`:

```python
from robot_md.backends import enumerate_capabilities, Capability


class _SecondStubBackend(CapabilityBackend):
    name = "stub2"
    protocols = frozenset({"realsense"})

    def open(self, spec):
        pass

    def close(self):
        pass

    def capabilities(self) -> frozenset[str]:
        return frozenset({"perceive.rgb", "stub2.vendor_thing"})

    def execute(self, capability, args, *, dry_run, estop):
        raise NotImplementedError


def test_enumerate_capabilities_walks_registry() -> None:
    reg = BackendRegistry(backends=[_StubBackend(), _SecondStubBackend()])
    pairs = enumerate_capabilities(reg)
    # 1 cap from stub + 2 caps from stub2 = 3 pairs.
    assert len(pairs) == 3
    by_backend = {}
    for backend_name, cap in pairs:
        assert isinstance(cap, Capability)
        by_backend.setdefault(backend_name, []).append(cap.name)
    assert sorted(by_backend["stub"]) == ["arm.pick"]
    assert sorted(by_backend["stub2"]) == ["perceive.rgb", "stub2.vendor_thing"]


def test_enumerate_capabilities_uses_describe_capabilities_override() -> None:
    """If a backend overrides describe_capabilities(), that wins over the default."""
    custom_cap = Capability(
        name="lerobot.teleop",
        namespace="vendor",
        arg_schema={"type": "object", "properties": {"leader_port": {"type": "string"}}},
        description="Drive follower from leader.",
    )

    class _OverrideBackend(_StubBackend):
        name = "override"

        def capabilities(self) -> frozenset[str]:
            return frozenset({"lerobot.teleop"})

        def describe_capabilities(self) -> list[Capability]:
            return [custom_cap]

    reg = BackendRegistry(backends=[_OverrideBackend()])
    pairs = enumerate_capabilities(reg)
    assert len(pairs) == 1
    backend_name, cap = pairs[0]
    assert backend_name == "override"
    assert cap is custom_cap  # exact object — override wins
```

- [ ] **Step 3: Run new tests to verify they fail**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_enumerate_capabilities.py -v
```

Expected: FAIL — `ImportError: cannot import name 'enumerate_capabilities' from 'robot_md.backends'`.

- [ ] **Step 4: Implement `enumerate_capabilities` in `backends/__init__.py`**

Replace `cli/src/robot_md/backends/__init__.py` with:

```python
"""Public backend API.

Re-exports CapabilityBackend, BackendRegistry, Capability, and the
enumerate_capabilities walker.
"""

from __future__ import annotations

from robot_md.backends.base import CapabilityBackend, ExecutionEvent, ExecutionResult, SceneSnapshot
from robot_md.backends.capability import Capability, derive_namespace
from robot_md.backends.registry import (
    BackendRegistrationError,
    BackendRegistry,
    CORE_CAPABILITY_PREFIXES,
    discover_backends,
)


def enumerate_capabilities(registry: BackendRegistry) -> list[tuple[str, Capability]]:
    """Walk all registered backends, return (backend_name, Capability) pairs.

    Used by:
      - The `robot-md describe-capabilities` CLI subcommand (Task 8).
      - Future SP-HP daemon — preview a backend's capabilities at hot-plug time.
      - Future robot-md-http OpenAPI generator.

    Backends MAY override describe_capabilities() to provide richer metadata;
    the override is preserved here.
    """
    out: list[tuple[str, Capability]] = []
    for backend in registry.backends:
        for cap in backend.describe_capabilities():
            out.append((backend.name, cap))
    return out


__all__ = [
    "BackendRegistrationError",
    "BackendRegistry",
    "CORE_CAPABILITY_PREFIXES",
    "Capability",
    "CapabilityBackend",
    "ExecutionEvent",
    "ExecutionResult",
    "SceneSnapshot",
    "derive_namespace",
    "discover_backends",
    "enumerate_capabilities",
]
```

- [ ] **Step 5: Run enumerate tests**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_enumerate_capabilities.py -v
```

Expected: PASS (3/3 — iter_classes + walker + override).

- [ ] **Step 6: Run full backends test suite to confirm no regression**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/ -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/backends/__init__.py cli/tests/backends/test_enumerate_capabilities.py
git commit -m "$(cat <<'EOF'
feat(sp3): enumerate_capabilities(registry) public walker

Module-level function that walks all backends in a BackendRegistry and
returns [(backend_name, Capability), ...] using each backend's
describe_capabilities() — overrides honored.

Public API surface for SP-HP (hot-plug capability preview), the eventual
robot-md-http OpenAPI generator, and the robot-md describe-capabilities
CLI subcommand (Task 8).

Re-exports Capability, BackendRegistry, BackendRegistrationError,
CORE_CAPABILITY_PREFIXES, and the existing CapabilityBackend ABC + result
dataclasses for one stable import path.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Add `robot-md describe-capabilities` CLI subcommand (proves the API end-to-end)

**Files:**
- Modify: `cli/src/robot_md/__main__.py` (add the Typer subcommand)
- Test: `cli/tests/backends/test_describe_capabilities_cli.py`

- [ ] **Step 1: Inspect the existing Typer app structure**

```bash
grep -n "app = typer.Typer\|@app.command\|^def \(init\|doctor\|mcp\)" cli/src/robot_md/__main__.py | head -30
```

Note where commands are registered. The new `describe-capabilities` subcommand follows the same pattern as `init`, `doctor`, etc. — `@app.command("describe-capabilities")` decorating a `def describe_capabilities(...)` function.

- [ ] **Step 2: Write the CLI smoke test**

```python
# cli/tests/backends/test_describe_capabilities_cli.py
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_describe_capabilities_json_output_lists_feetech_caps() -> None:
    cmd = [
        sys.executable,
        "-m",
        "robot_md",
        "describe-capabilities",
        "--json",
    ]
    env = {"PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**env}, check=False)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    # feetech_depthai is the in-tree default; should appear with its caps.
    by_backend = {entry["backend"]: entry for entry in payload}
    assert "feetech_depthai" in by_backend
    cap_names = {c["name"] for c in by_backend["feetech_depthai"]["capabilities"]}
    assert "arm.pick" in cap_names
    assert "vision.describe" in cap_names


def test_describe_capabilities_text_output_groups_by_namespace() -> None:
    cmd = [sys.executable, "-m", "robot_md", "describe-capabilities"]
    env = {"PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**env}, check=False)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "feetech_depthai" in out
    assert "core" in out  # section header for core capabilities
    assert "vendor" in out
    assert "arm.pick" in out
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_describe_capabilities_cli.py -v
```

Expected: FAIL — Typer reports unknown command `describe-capabilities`.

- [ ] **Step 4: Add the subcommand to `__main__.py`**

In `cli/src/robot_md/__main__.py`, find the section near other `@app.command(...)` registrations and add:

```python
@app.command("describe-capabilities")
def describe_capabilities(
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON instead of human-readable text."
    ),
) -> None:
    """List capabilities exposed by every installed backend.

    Walks the entry-point group `robot_md.backends`, builds a BackendRegistry,
    and dumps Capability metadata grouped by backend + namespace.
    """
    import json as _json

    from robot_md.backends import BackendRegistry, enumerate_capabilities

    reg = BackendRegistry.from_entry_points()
    pairs = enumerate_capabilities(reg)

    by_backend: dict[str, list] = {}
    for backend_name, cap in pairs:
        by_backend.setdefault(backend_name, []).append(cap)

    if json_output:
        payload = [
            {
                "backend": backend_name,
                "capabilities": [
                    {
                        "name": c.name,
                        "namespace": c.namespace,
                        "arg_schema": c.arg_schema,
                        "description": c.description,
                    }
                    for c in caps
                ],
            }
            for backend_name, caps in sorted(by_backend.items())
        ]
        typer.echo(_json.dumps(payload, indent=2, sort_keys=True))
        return

    for backend_name in sorted(by_backend):
        typer.echo(f"\n{backend_name}")
        typer.echo("=" * len(backend_name))
        caps = by_backend[backend_name]
        core = [c for c in caps if c.namespace == "core"]
        vendor = [c for c in caps if c.namespace == "vendor"]
        if core:
            typer.echo("  core:")
            for c in sorted(core, key=lambda x: x.name):
                desc = f" — {c.description}" if c.description else ""
                typer.echo(f"    {c.name}{desc}")
        if vendor:
            typer.echo("  vendor:")
            for c in sorted(vendor, key=lambda x: x.name):
                desc = f" — {c.description}" if c.description else ""
                typer.echo(f"    {c.name}{desc}")
```

(If the file uses `import typer` already, reuse it. If `app` is named differently, follow the existing convention.)

- [ ] **Step 5: Run CLI test**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_describe_capabilities_cli.py -v
```

Expected: PASS (2/2).

- [ ] **Step 6: Run a manual smoke against the live registry**

```bash
cd cli && PYTHONPATH=src python -m robot_md describe-capabilities
```

Expected output: a section for `feetech_depthai` listing its core capabilities (arm.pick / arm.place / arm.reach / arm.home) and vendor capabilities (vision.describe / status.report). Other backends only appear once their entry-points are added in Phase D.

- [ ] **Step 7: Commit**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/__main__.py cli/tests/backends/test_describe_capabilities_cli.py
git commit -m "$(cat <<'EOF'
feat(sp3): robot-md describe-capabilities CLI subcommand

Concrete first consumer of enumerate_capabilities(). Lists every
backend's capability metadata (core vs vendor namespaces, arg_schema if
present from capabilities.json, description) in human-readable text or
JSON via --json.

Today: shows feetech_depthai. After Phase D's entry-point declarations,
also shows lerobot + realsense. Future: SP-HP and robot-md-http use the
same enumerate_capabilities() path.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase B — RealSense backend (camera-only)

Simpler than LeRobot (no motion). Builds confidence in the adapter pattern + tier validator + describe_capabilities() integration before tackling the heavier LeRobot adapter.

### Task 9: Stub `RealsenseBackend` class + class-attr tests

**Files:**
- Create: `cli/src/robot_md/backends/realsense/__init__.py`
- Test: `cli/tests/backends/test_realsense_backend_protocols.py`, `cli/tests/backends/test_realsense_capabilities_camera_only.py`

- [ ] **Step 1: Write the protocols + class-attr test**

```python
# cli/tests/backends/test_realsense_backend_protocols.py
from __future__ import annotations

from robot_md.backends.realsense import RealsenseBackend


def test_name_and_protocols() -> None:
    b = RealsenseBackend()
    assert b.name == "realsense"
    assert b.protocols == frozenset({"realsense"})


def test_read_only_capabilities_marks_perception() -> None:
    b = RealsenseBackend()
    assert b.read_only_capabilities == frozenset({"perceive.rgb", "perceive.depth"})
```

- [ ] **Step 2: Write the camera-only-capabilities test**

```python
# cli/tests/backends/test_realsense_capabilities_camera_only.py
from __future__ import annotations

from robot_md.backends.realsense import RealsenseBackend


def test_capabilities_are_perception_plus_aligned_depth() -> None:
    b = RealsenseBackend()
    caps = b.capabilities()
    assert caps == frozenset({
        "perceive.rgb",
        "perceive.depth",
        "realsense.aligned_depth",
    })


def test_no_arm_or_gripper_capabilities() -> None:
    b = RealsenseBackend()
    caps = b.capabilities()
    for cap in caps:
        assert not cap.startswith("arm."), f"unexpected arm capability {cap}"
        assert not cap.startswith("gripper."), f"unexpected gripper capability {cap}"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_realsense_backend_protocols.py tests/backends/test_realsense_capabilities_camera_only.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'robot_md.backends.realsense'`.

- [ ] **Step 4: Create the package skeleton**

Create `cli/src/robot_md/backends/realsense/__init__.py`:

```python
"""RealSense camera adapter — perception only, no motion."""

from __future__ import annotations

from robot_md.backends.base import (
    CapabilityBackend,
    ExecutionEvent,
    ExecutionResult,
    SceneSnapshot,
)
from robot_md.robot_spec import RobotSpec


class RealsenseBackend(CapabilityBackend):
    name = "realsense"
    protocols = frozenset({"realsense"})
    read_only_capabilities = frozenset({"perceive.rgb", "perceive.depth"})

    def __init__(self) -> None:
        self._pipeline = None

    def open(self, spec: RobotSpec) -> None:
        # Implemented in Task 10.
        raise NotImplementedError

    def close(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None

    def capabilities(self) -> frozenset[str]:
        return frozenset({
            "perceive.rgb",
            "perceive.depth",
            "realsense.aligned_depth",
        })

    def execute(
        self,
        capability: str,
        args: dict,
        *,
        dry_run: bool,
        estop,
    ) -> ExecutionResult:
        from robot_md.backends.realsense.capabilities import dispatch
        return dispatch(self, capability=capability, args=dict(args), dry_run=dry_run, estop=estop)

    def scene_describe(self) -> SceneSnapshot:
        # Implemented in Task 13.
        return SceneSnapshot.empty()
```

Create `cli/src/robot_md/backends/realsense/capabilities.py`:

```python
"""RealSense capability dispatch — populated incrementally."""

from __future__ import annotations

from robot_md.backends.base import ExecutionResult


def dispatch(backend, *, capability: str, args: dict, dry_run: bool, estop) -> ExecutionResult:
    return ExecutionResult(
        status="error",
        trajectory=None,
        events=[],
        error={"reason": "not_implemented", "detail": f"capability {capability!r}"},
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_realsense_backend_protocols.py tests/backends/test_realsense_capabilities_camera_only.py -v
```

Expected: PASS (4/4).

- [ ] **Step 6: Commit (Task 9)**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/backends/realsense/__init__.py cli/src/robot_md/backends/realsense/capabilities.py cli/tests/backends/test_realsense_backend_protocols.py cli/tests/backends/test_realsense_capabilities_camera_only.py
git commit -m "feat(sp3): RealsenseBackend skeleton + capability set"
```

---

### Task 10: Implement `RealsenseBackend.open()` with mocked pipeline

**Files:**
- Modify: `cli/src/robot_md/backends/realsense/__init__.py` (real `open()` body)
- Test: `cli/tests/backends/test_realsense_open_mocked.py`

- [ ] **Step 1: Write the open-with-mocked-pyrealsense test**

```python
# cli/tests/backends/test_realsense_open_mocked.py
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

from robot_md.robot_spec import RobotSpec


def _install_fake_pyrealsense2(monkeypatch) -> tuple[MagicMock, MagicMock]:
    fake = types.ModuleType("pyrealsense2")
    pipeline = MagicMock(name="rs.pipeline_instance")
    pipeline_factory = MagicMock(name="rs.pipeline_factory", return_value=pipeline)
    config = MagicMock(name="rs.config_instance")
    config_factory = MagicMock(name="rs.config_factory", return_value=config)
    fake.pipeline = pipeline_factory
    fake.config = config_factory

    class _Stream:
        color = "color"
        depth = "depth"

    class _Format:
        bgr8 = "bgr8"
        z16 = "z16"

    fake.stream = _Stream()
    fake.format = _Format()
    monkeypatch.setitem(sys.modules, "pyrealsense2", fake)
    return pipeline, config


def test_open_starts_pipeline_with_color_and_depth_streams(monkeypatch) -> None:
    pipeline, config = _install_fake_pyrealsense2(monkeypatch)
    from robot_md.backends.realsense import RealsenseBackend

    spec = RobotSpec.empty(rrn="RRN-test")
    b = RealsenseBackend()
    b.open(spec)

    pipeline.start.assert_called_once()
    args, _ = pipeline.start.call_args
    assert args[0] is config

    enable_calls = config.enable_stream.call_args_list
    enabled = {call.args[0] for call in enable_calls}
    assert enabled == {"color", "depth"}


def test_close_stops_pipeline(monkeypatch) -> None:
    pipeline, _ = _install_fake_pyrealsense2(monkeypatch)
    from robot_md.backends.realsense import RealsenseBackend

    b = RealsenseBackend()
    b.open(RobotSpec.empty(rrn="RRN-test"))
    b.close()
    pipeline.stop.assert_called_once()
```

- [ ] **Step 2: Run test (expect FAIL with NotImplementedError)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_realsense_open_mocked.py -v
```

- [ ] **Step 3: Implement `open()`**

Replace the stub `open()` in `cli/src/robot_md/backends/realsense/__init__.py`:

```python
    def open(self, spec: RobotSpec) -> None:
        import pyrealsense2 as rs

        self._pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
        config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        self._pipeline.start(config)
```

- [ ] **Step 4: Run test (expect PASS 2/2)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_realsense_open_mocked.py -v
```

- [ ] **Step 5: Commit (Task 10)**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/backends/realsense/__init__.py cli/tests/backends/test_realsense_open_mocked.py
git commit -m "feat(sp3): RealsenseBackend.open()/.close() — pyrealsense2 pipeline"
```

---

### Task 11: Add `perceive.rgb` capability handler

**Files:**
- Create: `cli/src/robot_md/backends/realsense/perception.py`
- Modify: `cli/src/robot_md/backends/realsense/capabilities.py`
- Test: `cli/tests/backends/test_realsense_perceive_rgb.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/backends/test_realsense_perceive_rgb.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.realsense import RealsenseBackend


def test_perceive_rgb_returns_frame_bytes() -> None:
    color_frame = MagicMock()
    color_frame.get_data.return_value = b"FAKE_RGB_BYTES"
    frames = MagicMock()
    frames.get_color_frame.return_value = color_frame
    pipeline = MagicMock()
    pipeline.wait_for_frames.return_value = frames

    b = RealsenseBackend()
    b._pipeline = pipeline
    result = b.execute("perceive.rgb", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    payload = result.events[-1].data
    assert payload["frame_bytes"] == b"FAKE_RGB_BYTES"
    assert payload["format"] == "bgr8"


def test_perceive_rgb_dry_run_short_circuits() -> None:
    b = RealsenseBackend()
    b._pipeline = MagicMock()  # would raise if called
    result = b.execute("perceive.rgb", {}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert result.events[-1].kind == "dry_run"
    b._pipeline.wait_for_frames.assert_not_called()
```

- [ ] **Step 2: Run test (expect FAIL with not_implemented)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_realsense_perceive_rgb.py -v
```

- [ ] **Step 3: Add the handler**

Create `cli/src/robot_md/backends/realsense/perception.py`:

```python
from __future__ import annotations

from robot_md.backends.base import ExecutionEvent, ExecutionResult


def perceive_rgb(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    if dry_run:
        return ExecutionResult(
            status="ok",
            trajectory=None,
            events=[ExecutionEvent(kind="dry_run", data={"capability": "perceive.rgb"})],
            error=None,
        )
    frames = backend._pipeline.wait_for_frames(timeout_ms=1000)
    color = frames.get_color_frame()
    data = bytes(color.get_data()) if color is not None else b""
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[ExecutionEvent(kind="frame", data={"frame_bytes": data, "format": "bgr8"})],
        error=None,
    )
```

Replace `cli/src/robot_md/backends/realsense/capabilities.py`:

```python
"""RealSense capability dispatch."""

from __future__ import annotations

from robot_md.backends.base import ExecutionResult
from robot_md.backends.realsense.perception import perceive_rgb


HANDLERS = {
    "perceive.rgb": perceive_rgb,
}


def dispatch(backend, *, capability: str, args: dict, dry_run: bool, estop) -> ExecutionResult:
    handler = HANDLERS.get(capability)
    if handler is None:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": "not_implemented", "detail": f"capability {capability!r}"},
        )
    return handler(backend, args, dry_run=dry_run, estop=estop)
```

- [ ] **Step 4: Run test (expect PASS 2/2)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_realsense_perceive_rgb.py -v
```

- [ ] **Step 5: Commit (Task 11)**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/backends/realsense/perception.py cli/src/robot_md/backends/realsense/capabilities.py cli/tests/backends/test_realsense_perceive_rgb.py
git commit -m "feat(sp3): perceive.rgb handler in RealsenseBackend"
```

---

### Task 12: Add `perceive.depth` handler

**Files:**
- Modify: `cli/src/robot_md/backends/realsense/perception.py`, `capabilities.py`
- Test: `cli/tests/backends/test_realsense_perceive_depth.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/backends/test_realsense_perceive_depth.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.realsense import RealsenseBackend


def test_perceive_depth_returns_z16_bytes() -> None:
    depth_frame = MagicMock()
    depth_frame.get_data.return_value = b"FAKE_DEPTH_BYTES"
    frames = MagicMock()
    frames.get_depth_frame.return_value = depth_frame
    pipeline = MagicMock()
    pipeline.wait_for_frames.return_value = frames

    b = RealsenseBackend()
    b._pipeline = pipeline
    result = b.execute("perceive.depth", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    payload = result.events[-1].data
    assert payload["frame_bytes"] == b"FAKE_DEPTH_BYTES"
    assert payload["format"] == "z16"
```

- [ ] **Step 2: Run test (expect FAIL with not_implemented)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_realsense_perceive_depth.py -v
```

- [ ] **Step 3: Append `perceive_depth` to perception.py**

```python
def perceive_depth(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    if dry_run:
        return ExecutionResult(
            status="ok",
            trajectory=None,
            events=[ExecutionEvent(kind="dry_run", data={"capability": "perceive.depth"})],
            error=None,
        )
    frames = backend._pipeline.wait_for_frames(timeout_ms=1000)
    depth = frames.get_depth_frame()
    data = bytes(depth.get_data()) if depth is not None else b""
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[ExecutionEvent(kind="frame", data={"frame_bytes": data, "format": "z16"})],
        error=None,
    )
```

Update `capabilities.py` HANDLERS:

```python
from robot_md.backends.realsense.perception import perceive_rgb, perceive_depth

HANDLERS = {
    "perceive.rgb": perceive_rgb,
    "perceive.depth": perceive_depth,
}
```

- [ ] **Step 4: Run test (expect PASS)**

- [ ] **Step 5: Commit (Task 12)**

```bash
git add cli/src/robot_md/backends/realsense/perception.py cli/src/robot_md/backends/realsense/capabilities.py cli/tests/backends/test_realsense_perceive_depth.py
git commit -m "feat(sp3): perceive.depth handler in RealsenseBackend"
```

---

### Task 13: Implement `RealsenseBackend.scene_describe()`

**Files:**
- Modify: `cli/src/robot_md/backends/realsense/__init__.py`
- Test: `cli/tests/backends/test_realsense_scene_describe_mocked.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/backends/test_realsense_scene_describe_mocked.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.realsense import RealsenseBackend


def test_scene_describe_returns_snapshot_with_color_bytes() -> None:
    color_frame = MagicMock()
    color_frame.get_data.return_value = b"COLOR_BYTES"
    frames = MagicMock()
    frames.get_color_frame.return_value = color_frame
    pipeline = MagicMock()
    pipeline.wait_for_frames.return_value = frames

    b = RealsenseBackend()
    b._pipeline = pipeline
    snap = b.scene_describe()
    assert snap.frame == b"COLOR_BYTES"
    assert snap.detections == ()
    assert snap.joint_state == {}


def test_scene_describe_with_no_pipeline_returns_empty() -> None:
    b = RealsenseBackend()
    snap = b.scene_describe()
    assert snap.frame is None
```

- [ ] **Step 2: Run tests (expect 1 PASS + 1 FAIL)**

- [ ] **Step 3: Implement scene_describe**

Replace stub in `__init__.py`:

```python
    def scene_describe(self) -> SceneSnapshot:
        import time

        if self._pipeline is None:
            return SceneSnapshot.empty()
        frames = self._pipeline.wait_for_frames(timeout_ms=1000)
        color = frames.get_color_frame()
        data = bytes(color.get_data()) if color is not None else None
        return SceneSnapshot(frame=data, detections=(), joint_state={}, ts=time.time())
```

- [ ] **Step 4: Run test (expect PASS 2/2)**

- [ ] **Step 5: Commit (Task 13)**

```bash
git add cli/src/robot_md/backends/realsense/__init__.py cli/tests/backends/test_realsense_scene_describe_mocked.py
git commit -m "feat(sp3): RealsenseBackend.scene_describe()"
```

---

### Task 14: `realsense.aligned_depth` vendor capability

**Files:**
- Modify: `cli/src/robot_md/backends/realsense/perception.py`, `capabilities.py`
- Test: `cli/tests/backends/test_realsense_aligned_depth.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/backends/test_realsense_aligned_depth.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.realsense import RealsenseBackend


def test_aligned_depth_uses_align_processor() -> None:
    aligned_depth = MagicMock()
    aligned_depth.get_data.return_value = b"ALIGNED_DEPTH"
    align_processor = MagicMock()
    align_processor.process.return_value.get_depth_frame.return_value = aligned_depth
    frames = MagicMock()
    pipeline = MagicMock()
    pipeline.wait_for_frames.return_value = frames

    b = RealsenseBackend()
    b._pipeline = pipeline
    b._align_processor = align_processor
    result = b.execute("realsense.aligned_depth", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    payload = result.events[-1].data
    assert payload["frame_bytes"] == b"ALIGNED_DEPTH"
    assert payload["aligned_to"] == "color"
    align_processor.process.assert_called_once_with(frames)
```

- [ ] **Step 2: Run test (expect FAIL with not_implemented)**

- [ ] **Step 3: Append `realsense_aligned_depth` to perception.py**

```python
def realsense_aligned_depth(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    if dry_run:
        return ExecutionResult(
            status="ok",
            trajectory=None,
            events=[ExecutionEvent(kind="dry_run", data={"capability": "realsense.aligned_depth"})],
            error=None,
        )
    align = _ensure_align(backend)
    frames = backend._pipeline.wait_for_frames(timeout_ms=1000)
    aligned_frames = align.process(frames)
    aligned = aligned_frames.get_depth_frame()
    data = bytes(aligned.get_data()) if aligned is not None else b""
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[ExecutionEvent(kind="frame", data={"frame_bytes": data, "format": "z16", "aligned_to": "color"})],
        error=None,
    )


def _ensure_align(backend):
    if getattr(backend, "_align_processor", None) is None:
        import pyrealsense2 as rs
        backend._align_processor = rs.align(rs.stream.color)
    return backend._align_processor
```

Update `capabilities.py`:

```python
from robot_md.backends.realsense.perception import perceive_rgb, perceive_depth, realsense_aligned_depth

HANDLERS = {
    "perceive.rgb": perceive_rgb,
    "perceive.depth": perceive_depth,
    "realsense.aligned_depth": realsense_aligned_depth,
}
```

- [ ] **Step 4: Run test (expect PASS)**

- [ ] **Step 5: Commit (Task 14)**

```bash
git add cli/src/robot_md/backends/realsense/perception.py cli/src/robot_md/backends/realsense/capabilities.py cli/tests/backends/test_realsense_aligned_depth.py
git commit -m "feat(sp3): realsense.aligned_depth vendor capability"
```

---

### Task 15: Lock the no-arm contract

**Files:**
- Test only: `cli/tests/backends/test_realsense_no_arm_capability.py`

- [ ] **Step 1: Write the lock test**

```python
# cli/tests/backends/test_realsense_no_arm_capability.py
from __future__ import annotations

from robot_md.backends.realsense import RealsenseBackend


def test_arm_pick_returns_not_implemented() -> None:
    b = RealsenseBackend()
    result = b.execute("arm.pick", {"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "error"
    assert result.error["reason"] == "not_implemented"


def test_gripper_open_returns_not_implemented() -> None:
    b = RealsenseBackend()
    result = b.execute("gripper.open", {}, dry_run=True, estop=None)
    assert result.status == "error"
    assert result.error["reason"] == "not_implemented"
```

- [ ] **Step 2: Run test (expect PASS — dispatch already returns not_implemented)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_realsense_*.py -v
```

Expected: ALL RealSense tests PASS — Phase B locked.

- [ ] **Step 3: Commit (Task 15)**

```bash
git add cli/tests/backends/test_realsense_no_arm_capability.py
git commit -m "test(sp3): lock RealsenseBackend rejects arm.* / gripper.* calls"
```

---

## Phase C — LeRobot backend (motion + camera)

Heavier than RealSense. All `lerobot` SDK calls go through mocks so the test suite runs without the LeRobot package installed.

### Task 16: Stub `LerobotBackend` class + class-attr tests

**Files:**
- Create: `cli/src/robot_md/backends/lerobot/__init__.py`, `cli/src/robot_md/backends/lerobot/capabilities.py`
- Test: `cli/tests/backends/test_lerobot_backend_protocols.py`, `cli/tests/backends/test_lerobot_backend_capabilities_valid.py`

- [ ] **Step 1: Write the protocols test**

```python
# cli/tests/backends/test_lerobot_backend_protocols.py
from __future__ import annotations

from robot_md.backends.lerobot import LerobotBackend


def test_name_and_protocols() -> None:
    b = LerobotBackend()
    assert b.name == "lerobot"
    assert b.protocols == frozenset({"feetech", "dynamixel"})


def test_read_only_capabilities_marks_perception() -> None:
    b = LerobotBackend()
    assert b.read_only_capabilities == frozenset({"perceive.rgb", "perceive.depth"})
```

- [ ] **Step 2: Write the capabilities-pass-validator test**

```python
# cli/tests/backends/test_lerobot_backend_capabilities_valid.py
from __future__ import annotations

from robot_md.backends.lerobot import LerobotBackend
from robot_md.backends.registry import _validate_capability_namespace


def test_all_declared_capabilities_pass_tier_validator() -> None:
    b = LerobotBackend()
    _validate_capability_namespace("lerobot", b.capabilities())  # raises if any malformed


def test_capabilities_set_contents() -> None:
    b = LerobotBackend()
    assert b.capabilities() == frozenset({
        "arm.pick", "arm.place", "arm.home",
        "perceive.rgb", "perceive.depth",
        "gripper.open", "gripper.close",
        "lerobot.teleop",
    })
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_lerobot_backend_protocols.py tests/backends/test_lerobot_backend_capabilities_valid.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'robot_md.backends.lerobot'`.

- [ ] **Step 4: Create the LeRobot package skeleton**

Create `cli/src/robot_md/backends/lerobot/__init__.py`:

```python
"""LeRobot adapter — motion + camera, wraps HuggingFace LeRobot SDK."""

from __future__ import annotations

from robot_md.backends.base import (
    CapabilityBackend,
    ExecutionEvent,
    ExecutionResult,
    SceneSnapshot,
)
from robot_md.robot_spec import RobotSpec


class LerobotBackend(CapabilityBackend):
    name = "lerobot"
    protocols = frozenset({"feetech", "dynamixel"})
    read_only_capabilities = frozenset({"perceive.rgb", "perceive.depth"})

    def __init__(self) -> None:
        self._robot = None

    def open(self, spec: RobotSpec) -> None:
        # Implemented in Task 18.
        raise NotImplementedError

    def close(self) -> None:
        if self._robot is not None:
            try:
                self._robot.disconnect()
            except Exception:
                pass
            self._robot = None

    def capabilities(self) -> frozenset[str]:
        return frozenset({
            "arm.pick", "arm.place", "arm.home",
            "perceive.rgb", "perceive.depth",
            "gripper.open", "gripper.close",
            "lerobot.teleop",
        })

    def execute(
        self,
        capability: str,
        args: dict,
        *,
        dry_run: bool,
        estop,
    ) -> ExecutionResult:
        from robot_md.backends.lerobot.capabilities import dispatch
        return dispatch(self, capability=capability, args=dict(args), dry_run=dry_run, estop=estop)

    def scene_describe(self) -> SceneSnapshot:
        return SceneSnapshot.empty()
```

Create `cli/src/robot_md/backends/lerobot/capabilities.py`:

```python
"""LeRobot capability dispatch — populated incrementally."""

from __future__ import annotations

from robot_md.backends.base import ExecutionResult


def dispatch(backend, *, capability: str, args: dict, dry_run: bool, estop) -> ExecutionResult:
    return ExecutionResult(
        status="error",
        trajectory=None,
        events=[],
        error={"reason": "not_implemented", "detail": f"capability {capability!r}"},
    )
```

- [ ] **Step 5: Run tests (expect PASS 4/4)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_lerobot_backend_protocols.py tests/backends/test_lerobot_backend_capabilities_valid.py -v
```

- [ ] **Step 6: Commit (Task 16)**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/backends/lerobot/__init__.py cli/src/robot_md/backends/lerobot/capabilities.py cli/tests/backends/test_lerobot_backend_protocols.py cli/tests/backends/test_lerobot_backend_capabilities_valid.py
git commit -m "feat(sp3): LerobotBackend skeleton + capability set"
```

---

### Task 17: Implement `_build_lerobot_config(spec)` for SO-ARM101

**Files:**
- Create: `cli/src/robot_md/backends/lerobot/config.py`
- Test: `cli/tests/backends/test_lerobot_build_config_so_arm101.py`

- [ ] **Step 1: Write the config-mapping test**

```python
# cli/tests/backends/test_lerobot_build_config_so_arm101.py
from __future__ import annotations

from robot_md.backends.lerobot.config import build_lerobot_config
from robot_md.robot_spec import RobotSpec, Driver


def _so_arm101_spec() -> RobotSpec:
    return RobotSpec(
        rrn="RRN-test-so-arm101",
        drivers=[
            Driver(
                id="arm_servos",
                protocol="feetech",
                backend="lerobot",
                port="/dev/ttyACM0",
                baud=1000000,
                motors=[
                    {"id": 1, "model": "sts3215", "joint": "shoulder_pan"},
                    {"id": 2, "model": "sts3215", "joint": "shoulder_lift"},
                    {"id": 3, "model": "sts3215", "joint": "elbow_flex"},
                    {"id": 4, "model": "sts3215", "joint": "wrist_flex"},
                    {"id": 5, "model": "sts3215", "joint": "wrist_roll"},
                    {"id": 6, "model": "sts3215", "joint": "gripper"},
                ],
            ),
        ],
    )


def test_build_config_extracts_six_motors() -> None:
    spec = _so_arm101_spec()
    cfg = build_lerobot_config(spec)
    assert cfg["robot_type"] == "so_arm"
    assert cfg["port"] == "/dev/ttyACM0"
    assert cfg["baud"] == 1000000
    assert len(cfg["motors"]) == 6
    assert {m["joint"] for m in cfg["motors"]} == {
        "shoulder_pan", "shoulder_lift", "elbow_flex",
        "wrist_flex", "wrist_roll", "gripper",
    }


def test_build_config_missing_motors_raises_clean_error() -> None:
    spec = RobotSpec(
        rrn="RRN-test-bad",
        drivers=[Driver(id="arm_servos", protocol="feetech", backend="lerobot", port="/dev/ttyACM0", baud=1000000, motors=[])],
    )
    import pytest
    with pytest.raises(ValueError) as exc:
        build_lerobot_config(spec)
    assert "no motors" in str(exc.value).lower()
```

(Note: this test imports `Driver` from `robot_md.robot_spec`. If the existing dataclass doesn't accept these field names, adapt to whatever the live class signature actually is — grep `class Driver` in `robot_md/robot_spec.py` first.)

- [ ] **Step 2: Run test to verify it fails**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_lerobot_build_config_so_arm101.py -v
```

Expected: FAIL — `ModuleNotFoundError: robot_md.backends.lerobot.config`.

- [ ] **Step 3: Implement `build_lerobot_config`**

Create `cli/src/robot_md/backends/lerobot/config.py`:

```python
from __future__ import annotations

from robot_md.robot_spec import RobotSpec


def build_lerobot_config(spec: RobotSpec) -> dict:
    """Translate a RobotSpec into a LeRobot make_robot() config dict.

    Pulls the first arm-shaped driver (protocol in {feetech, dynamixel}),
    its port + baud, and its motor list. Raises ValueError if no driver
    or no motors are declared.
    """
    arm_driver = next(
        (d for d in spec.drivers if d.protocol in {"feetech", "dynamixel"}),
        None,
    )
    if arm_driver is None:
        raise ValueError("RobotSpec has no feetech/dynamixel arm driver")
    if not arm_driver.motors:
        raise ValueError(f"Driver {arm_driver.id!r} has no motors declared")
    return {
        "robot_type": "so_arm",  # default; override via vendor capability if needed
        "port": arm_driver.port,
        "baud": arm_driver.baud,
        "motors": [
            {"id": m["id"], "model": m["model"], "joint": m["joint"]}
            for m in arm_driver.motors
        ],
    }
```

- [ ] **Step 4: Run test (expect PASS 2/2)**

- [ ] **Step 5: Commit (Task 17)**

```bash
git add cli/src/robot_md/backends/lerobot/config.py cli/tests/backends/test_lerobot_build_config_so_arm101.py
git commit -m "feat(sp3): _build_lerobot_config(spec) translates RobotSpec → LeRobot config dict"
```

---

### Task 18: Implement `LerobotBackend.open()` with mocked `make_robot`

**Files:**
- Modify: `cli/src/robot_md/backends/lerobot/__init__.py` (real `open()`)
- Test: `cli/tests/backends/test_lerobot_backend_open_mocked.py`

- [ ] **Step 1: Write the open-with-mocked-make_robot test**

```python
# cli/tests/backends/test_lerobot_backend_open_mocked.py
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def _install_fake_lerobot(monkeypatch) -> tuple[MagicMock, MagicMock]:
    """Stand up enough of the lerobot package tree so the lazy import
    inside open() resolves cleanly without the real SDK installed."""
    fake_robot = MagicMock(name="lerobot_robot_instance")
    make_robot = MagicMock(name="make_robot", return_value=fake_robot)

    factory_mod = types.ModuleType("lerobot.common.robot_devices.robots.factory")
    factory_mod.make_robot = make_robot

    common_mod = types.ModuleType("lerobot.common")
    common_mod.robot_devices = types.ModuleType("lerobot.common.robot_devices")
    common_mod.robot_devices.robots = types.ModuleType("lerobot.common.robot_devices.robots")
    common_mod.robot_devices.robots.factory = factory_mod

    root = types.ModuleType("lerobot")
    root.common = common_mod

    monkeypatch.setitem(sys.modules, "lerobot", root)
    monkeypatch.setitem(sys.modules, "lerobot.common", common_mod)
    monkeypatch.setitem(sys.modules, "lerobot.common.robot_devices", common_mod.robot_devices)
    monkeypatch.setitem(sys.modules, "lerobot.common.robot_devices.robots", common_mod.robot_devices.robots)
    monkeypatch.setitem(sys.modules, "lerobot.common.robot_devices.robots.factory", factory_mod)
    return fake_robot, make_robot


def _so_arm101_spec_for_open():
    # Reuse Task 17's helper if practical; otherwise inline a minimal spec here.
    from tests.backends.test_lerobot_build_config_so_arm101 import _so_arm101_spec  # noqa: PLC0415
    return _so_arm101_spec()


def test_open_calls_make_robot_then_connect(monkeypatch) -> None:
    fake_robot, make_robot = _install_fake_lerobot(monkeypatch)
    b = LerobotBackend()
    b.open(_so_arm101_spec_for_open())

    make_robot.assert_called_once()
    cfg = make_robot.call_args[0][0]
    assert cfg["port"] == "/dev/ttyACM0"
    assert len(cfg["motors"]) == 6
    fake_robot.connect.assert_called_once()
    assert b._robot is fake_robot
```

- [ ] **Step 2: Run test (expect FAIL with NotImplementedError)**

- [ ] **Step 3: Implement `open()`**

Replace the stub `open()` in `cli/src/robot_md/backends/lerobot/__init__.py`:

```python
    def open(self, spec: RobotSpec) -> None:
        from lerobot.common.robot_devices.robots.factory import make_robot
        from robot_md.backends.lerobot.config import build_lerobot_config

        cfg = build_lerobot_config(spec)
        self._robot = make_robot(cfg)
        self._robot.connect()
```

- [ ] **Step 4: Run test (expect PASS)**

- [ ] **Step 5: Commit (Task 18)**

```bash
git add cli/src/robot_md/backends/lerobot/__init__.py cli/tests/backends/test_lerobot_backend_open_mocked.py
git commit -m "feat(sp3): LerobotBackend.open() — make_robot + connect"
```

---

### Task 19: `arm.pick` handler

**Files:**
- Create: `cli/src/robot_md/backends/lerobot/motion.py`
- Modify: `cli/src/robot_md/backends/lerobot/capabilities.py`
- Test: `cli/tests/backends/test_lerobot_execute_arm_pick_mocked.py`

- [ ] **Step 1: Write the arm.pick test**

```python
# cli/tests/backends/test_lerobot_execute_arm_pick_mocked.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def _backend_with_robot() -> tuple[LerobotBackend, MagicMock]:
    b = LerobotBackend()
    robot = MagicMock(name="lerobot_robot")
    b._robot = robot
    return b, robot


def test_arm_pick_dry_run_emits_trajectory_no_writes() -> None:
    b, robot = _backend_with_robot()
    result = b.execute("arm.pick", {"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert result.trajectory is not None
    robot.send_action.assert_not_called()


def test_arm_pick_live_invokes_send_action() -> None:
    b, robot = _backend_with_robot()
    result = b.execute("arm.pick", {"target": "red_lego"}, dry_run=False, estop=None)
    assert result.status == "ok"
    robot.send_action.assert_called()
    # The first send_action should target the approach pose.
    first_call_args = robot.send_action.call_args_list[0].args[0]
    assert "approach" in str(first_call_args).lower() or "joints" in first_call_args


def test_arm_pick_missing_target_returns_error() -> None:
    b, _ = _backend_with_robot()
    result = b.execute("arm.pick", {}, dry_run=True, estop=None)
    assert result.status == "error"
    assert result.error["reason"] in {"missing_args", "schema_violation"}
```

- [ ] **Step 2: Run test (expect FAIL — not_implemented)**

- [ ] **Step 3: Implement `arm.pick` handler**

Create `cli/src/robot_md/backends/lerobot/motion.py`:

```python
"""LeRobot arm.* / gripper.* handlers — wraps the connected robot's
send_action interface with simple per-capability action plans.

These plans are intentionally generic: a real adapter would compute IK
or invoke a learned policy. For SP3, the goal is to prove the dispatch
plumbing — actual trajectory quality is out of scope.
"""

from __future__ import annotations

from robot_md.backends.base import ExecutionEvent, ExecutionResult


def _validate_pick_args(args: dict) -> ExecutionResult | None:
    if "target" not in args:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": "missing_args", "detail": "arm.pick requires 'target'"},
        )
    if not isinstance(args["target"], str):
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": "schema_violation", "detail": "'target' must be string"},
        )
    return None


def arm_pick(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    bad = _validate_pick_args(args)
    if bad is not None:
        return bad
    target = args["target"]
    approach_height_mm = float(args.get("approach_height_mm", 50))
    plan = [
        {"phase": "approach", "joints": [0.0, -0.3, 0.6, 0.0, 0.0, 0.0], "approach_height_mm": approach_height_mm, "target": target},
        {"phase": "descend", "joints": [0.0, -0.5, 0.4, 0.0, 0.0, 0.0]},
        {"phase": "grasp",   "joints": [0.0, -0.5, 0.4, 0.0, 0.0, 0.6]},
        {"phase": "lift",    "joints": [0.0, -0.3, 0.6, 0.0, 0.0, 0.6]},
    ]
    if dry_run:
        return ExecutionResult(
            status="ok",
            trajectory=plan,
            events=[ExecutionEvent(kind="dry_run", data={"capability": "arm.pick", "target": target})],
            error=None,
        )
    for step in plan:
        backend._robot.send_action(step)
    return ExecutionResult(
        status="ok",
        trajectory=plan,
        events=[ExecutionEvent(kind="motion_complete", data={"capability": "arm.pick", "target": target})],
        error=None,
    )
```

Update `capabilities.py`:

```python
from robot_md.backends.lerobot.motion import arm_pick


HANDLERS = {
    "arm.pick": arm_pick,
}


def dispatch(backend, *, capability: str, args: dict, dry_run: bool, estop) -> ExecutionResult:
    handler = HANDLERS.get(capability)
    if handler is None:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": "not_implemented", "detail": f"capability {capability!r}"},
        )
    return handler(backend, args, dry_run=dry_run, estop=estop)
```

- [ ] **Step 4: Run test (expect PASS 3/3)**

- [ ] **Step 5: Commit (Task 19)**

```bash
git add cli/src/robot_md/backends/lerobot/motion.py cli/src/robot_md/backends/lerobot/capabilities.py cli/tests/backends/test_lerobot_execute_arm_pick_mocked.py
git commit -m "feat(sp3): arm.pick handler in LerobotBackend"
```

---

### Task 20: `arm.place` and `arm.home` handlers

**Files:**
- Modify: `cli/src/robot_md/backends/lerobot/motion.py`, `capabilities.py`
- Test: `cli/tests/backends/test_lerobot_arm_place_home.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/backends/test_lerobot_arm_place_home.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def _backend() -> tuple[LerobotBackend, MagicMock]:
    b = LerobotBackend()
    b._robot = MagicMock()
    return b, b._robot


def test_arm_place_dry_run_returns_trajectory() -> None:
    b, robot = _backend()
    result = b.execute("arm.place", {"destination": "drop_zone"}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert result.trajectory is not None
    robot.send_action.assert_not_called()


def test_arm_place_missing_destination() -> None:
    b, _ = _backend()
    result = b.execute("arm.place", {}, dry_run=True, estop=None)
    assert result.status == "error"


def test_arm_home_no_args_succeeds() -> None:
    b, robot = _backend()
    result = b.execute("arm.home", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    robot.send_action.assert_called()
```

- [ ] **Step 2: Run test (expect FAIL — not_implemented)**

- [ ] **Step 3: Add `arm_place` and `arm_home` to motion.py**

```python
def arm_place(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    if "destination" not in args:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": "missing_args", "detail": "arm.place requires 'destination'"},
        )
    plan = [
        {"phase": "transport", "joints": [0.5, -0.3, 0.6, 0.0, 0.0, 0.6], "destination": args["destination"]},
        {"phase": "release",   "joints": [0.5, -0.5, 0.4, 0.0, 0.0, 0.0]},
        {"phase": "retract",   "joints": [0.0, -0.3, 0.6, 0.0, 0.0, 0.0]},
    ]
    if dry_run:
        return ExecutionResult(
            status="ok", trajectory=plan,
            events=[ExecutionEvent(kind="dry_run", data={"capability": "arm.place"})],
            error=None,
        )
    for step in plan:
        backend._robot.send_action(step)
    return ExecutionResult(
        status="ok", trajectory=plan,
        events=[ExecutionEvent(kind="motion_complete", data={"capability": "arm.place"})],
        error=None,
    )


_HOME_JOINTS = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def arm_home(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    plan = [{"phase": "home", "joints": _HOME_JOINTS}]
    if dry_run:
        return ExecutionResult(
            status="ok", trajectory=plan,
            events=[ExecutionEvent(kind="dry_run", data={"capability": "arm.home"})],
            error=None,
        )
    backend._robot.send_action(plan[0])
    return ExecutionResult(
        status="ok", trajectory=plan,
        events=[ExecutionEvent(kind="motion_complete", data={"capability": "arm.home"})],
        error=None,
    )
```

Update HANDLERS in `capabilities.py`:

```python
from robot_md.backends.lerobot.motion import arm_pick, arm_place, arm_home

HANDLERS = {
    "arm.pick": arm_pick,
    "arm.place": arm_place,
    "arm.home": arm_home,
}
```

- [ ] **Step 4: Run test (expect PASS 3/3)**

- [ ] **Step 5: Commit (Task 20)**

```bash
git add cli/src/robot_md/backends/lerobot/motion.py cli/src/robot_md/backends/lerobot/capabilities.py cli/tests/backends/test_lerobot_arm_place_home.py
git commit -m "feat(sp3): arm.place + arm.home handlers in LerobotBackend"
```

---

### Task 21: `gripper.open` and `gripper.close` handlers

**Files:**
- Modify: `cli/src/robot_md/backends/lerobot/motion.py`, `capabilities.py`
- Test: `cli/tests/backends/test_lerobot_gripper.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/backends/test_lerobot_gripper.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def _backend() -> tuple[LerobotBackend, MagicMock]:
    b = LerobotBackend()
    b._robot = MagicMock()
    return b, b._robot


def test_gripper_open_sends_open_command() -> None:
    b, robot = _backend()
    result = b.execute("gripper.open", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    robot.send_action.assert_called_once()
    sent = robot.send_action.call_args.args[0]
    assert sent.get("gripper") == "open"


def test_gripper_close_sends_close_command() -> None:
    b, robot = _backend()
    result = b.execute("gripper.close", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    sent = robot.send_action.call_args.args[0]
    assert sent.get("gripper") == "close"
```

- [ ] **Step 2: Run test (expect FAIL — not_implemented)**

- [ ] **Step 3: Add gripper handlers**

```python
def gripper_open(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    cmd = {"phase": "gripper.open", "gripper": "open"}
    if dry_run:
        return ExecutionResult(status="ok", trajectory=[cmd],
                               events=[ExecutionEvent(kind="dry_run", data={"capability": "gripper.open"})],
                               error=None)
    backend._robot.send_action(cmd)
    return ExecutionResult(status="ok", trajectory=[cmd],
                           events=[ExecutionEvent(kind="motion_complete", data={"capability": "gripper.open"})],
                           error=None)


def gripper_close(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    cmd = {"phase": "gripper.close", "gripper": "close"}
    if dry_run:
        return ExecutionResult(status="ok", trajectory=[cmd],
                               events=[ExecutionEvent(kind="dry_run", data={"capability": "gripper.close"})],
                               error=None)
    backend._robot.send_action(cmd)
    return ExecutionResult(status="ok", trajectory=[cmd],
                           events=[ExecutionEvent(kind="motion_complete", data={"capability": "gripper.close"})],
                           error=None)
```

Add to HANDLERS:

```python
HANDLERS = {
    "arm.pick": arm_pick,
    "arm.place": arm_place,
    "arm.home": arm_home,
    "gripper.open": gripper_open,
    "gripper.close": gripper_close,
}
```

- [ ] **Step 4: Run test (expect PASS 2/2)**

- [ ] **Step 5: Commit (Task 21)**

```bash
git add cli/src/robot_md/backends/lerobot/motion.py cli/src/robot_md/backends/lerobot/capabilities.py cli/tests/backends/test_lerobot_gripper.py
git commit -m "feat(sp3): gripper.open + gripper.close handlers in LerobotBackend"
```

---

### Task 22: `perceive.rgb` and `perceive.depth` via LeRobot's camera pipeline

**Files:**
- Create: `cli/src/robot_md/backends/lerobot/perception.py`
- Modify: `cli/src/robot_md/backends/lerobot/capabilities.py`
- Test: `cli/tests/backends/test_lerobot_perception.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/backends/test_lerobot_perception.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def test_perceive_rgb_pulls_from_robot_capture() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    robot.capture_observation.return_value = {
        "observation.images.front": b"FRAME_RGB_BYTES",
    }
    b._robot = robot
    result = b.execute("perceive.rgb", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    payload = result.events[-1].data
    assert payload["frame_bytes"] == b"FRAME_RGB_BYTES"


def test_perceive_depth_returns_no_depth_when_camera_absent() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    robot.capture_observation.return_value = {
        "observation.images.front": b"COLOR_ONLY",  # no depth key
    }
    b._robot = robot
    result = b.execute("perceive.depth", {}, dry_run=False, estop=None)
    assert result.status == "error"
    assert result.error["reason"] == "no_depth_camera"
```

- [ ] **Step 2: Run test (expect FAIL — not_implemented)**

- [ ] **Step 3: Implement perception handlers**

Create `cli/src/robot_md/backends/lerobot/perception.py`:

```python
from __future__ import annotations

from robot_md.backends.base import ExecutionEvent, ExecutionResult


def _first_image_key(obs: dict, *prefixes: str) -> str | None:
    for k in obs:
        for p in prefixes:
            if k.startswith(p):
                return k
    return None


def perceive_rgb(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    if dry_run:
        return ExecutionResult(status="ok", trajectory=None,
                               events=[ExecutionEvent(kind="dry_run", data={"capability": "perceive.rgb"})],
                               error=None)
    obs = backend._robot.capture_observation()
    key = _first_image_key(obs, "observation.images.")
    if key is None:
        return ExecutionResult(status="error", trajectory=None, events=[],
                               error={"reason": "no_camera", "detail": "no observation.images.* in observation dict"})
    return ExecutionResult(status="ok", trajectory=None,
                           events=[ExecutionEvent(kind="frame", data={"frame_bytes": obs[key], "format": "bgr8", "source": key})],
                           error=None)


def perceive_depth(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    if dry_run:
        return ExecutionResult(status="ok", trajectory=None,
                               events=[ExecutionEvent(kind="dry_run", data={"capability": "perceive.depth"})],
                               error=None)
    obs = backend._robot.capture_observation()
    key = _first_image_key(obs, "observation.depth.")
    if key is None:
        return ExecutionResult(status="error", trajectory=None, events=[],
                               error={"reason": "no_depth_camera", "detail": "no observation.depth.* in observation dict"})
    return ExecutionResult(status="ok", trajectory=None,
                           events=[ExecutionEvent(kind="frame", data={"frame_bytes": obs[key], "format": "z16", "source": key})],
                           error=None)
```

Update HANDLERS:

```python
from robot_md.backends.lerobot.perception import perceive_rgb, perceive_depth

HANDLERS = {
    "arm.pick": arm_pick,
    "arm.place": arm_place,
    "arm.home": arm_home,
    "gripper.open": gripper_open,
    "gripper.close": gripper_close,
    "perceive.rgb": perceive_rgb,
    "perceive.depth": perceive_depth,
}
```

- [ ] **Step 4: Run test (expect PASS 2/2)**

- [ ] **Step 5: Commit (Task 22)**

```bash
git add cli/src/robot_md/backends/lerobot/perception.py cli/src/robot_md/backends/lerobot/capabilities.py cli/tests/backends/test_lerobot_perception.py
git commit -m "feat(sp3): perceive.rgb + perceive.depth via LeRobot capture_observation"
```

---

### Task 23: `lerobot.teleop` vendor capability

**Files:**
- Modify: `cli/src/robot_md/backends/lerobot/motion.py`, `capabilities.py`
- Test: `cli/tests/backends/test_lerobot_teleop.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/backends/test_lerobot_teleop.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def test_teleop_loop_streams_leader_to_follower() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    leader_states = [
        {"joints": [0.1, 0.0, 0.0, 0.0, 0.0, 0.0]},
        {"joints": [0.2, 0.0, 0.0, 0.0, 0.0, 0.0]},
        None,  # sentinel — leader disconnected
    ]
    robot.read_leader_state.side_effect = leader_states
    b._robot = robot
    result = b.execute("lerobot.teleop", {"max_steps": 2}, dry_run=False, estop=None)
    assert result.status == "ok"
    assert robot.send_action.call_count == 2


def test_teleop_dry_run_does_not_call_robot() -> None:
    b = LerobotBackend()
    b._robot = MagicMock()
    result = b.execute("lerobot.teleop", {"max_steps": 5}, dry_run=True, estop=None)
    assert result.status == "ok"
    b._robot.send_action.assert_not_called()
```

- [ ] **Step 2: Run test (expect FAIL — not_implemented)**

- [ ] **Step 3: Add `lerobot_teleop` to motion.py**

```python
def lerobot_teleop(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    max_steps = int(args.get("max_steps", 100))
    if dry_run:
        return ExecutionResult(status="ok", trajectory=None,
                               events=[ExecutionEvent(kind="dry_run",
                                                       data={"capability": "lerobot.teleop", "max_steps": max_steps})],
                               error=None)
    streamed = 0
    for _ in range(max_steps):
        state = backend._robot.read_leader_state()
        if state is None:
            break
        backend._robot.send_action(state)
        streamed += 1
    return ExecutionResult(status="ok", trajectory=None,
                           events=[ExecutionEvent(kind="teleop_complete", data={"steps": streamed})],
                           error=None)
```

Add to HANDLERS in `capabilities.py`:

```python
from robot_md.backends.lerobot.motion import (
    arm_pick, arm_place, arm_home, gripper_open, gripper_close, lerobot_teleop,
)

HANDLERS = {
    "arm.pick": arm_pick,
    "arm.place": arm_place,
    "arm.home": arm_home,
    "gripper.open": gripper_open,
    "gripper.close": gripper_close,
    "perceive.rgb": perceive_rgb,
    "perceive.depth": perceive_depth,
    "lerobot.teleop": lerobot_teleop,
}
```

- [ ] **Step 4: Run test (expect PASS 2/2)**

- [ ] **Step 5: Commit (Task 23)**

```bash
git add cli/src/robot_md/backends/lerobot/motion.py cli/src/robot_md/backends/lerobot/capabilities.py cli/tests/backends/test_lerobot_teleop.py
git commit -m "feat(sp3): lerobot.teleop vendor capability"
```

---

### Task 24: Lock the not-implemented contract + dry-run trajectory contract

**Files:**
- Test only: `cli/tests/backends/test_lerobot_execute_unknown_capability.py`, `cli/tests/backends/test_lerobot_dry_run.py`, `cli/tests/backends/test_lerobot_capabilities_schema_compliance.py`

- [ ] **Step 1: Write the unknown-capability test**

```python
# cli/tests/backends/test_lerobot_execute_unknown_capability.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def test_unknown_capability_returns_not_implemented() -> None:
    b = LerobotBackend()
    b._robot = MagicMock()
    result = b.execute("arm.dance", {}, dry_run=True, estop=None)
    assert result.status == "error"
    assert result.error["reason"] == "not_implemented"
```

- [ ] **Step 2: Write the dry-run trajectory test**

```python
# cli/tests/backends/test_lerobot_dry_run.py
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def test_dry_run_arm_pick_populates_trajectory_and_skips_writes() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    b._robot = robot
    result = b.execute("arm.pick", {"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert isinstance(result.trajectory, list)
    assert len(result.trajectory) >= 2  # at least approach + descend
    robot.send_action.assert_not_called()
```

- [ ] **Step 3: Write the schema-compliance test**

```python
# cli/tests/backends/test_lerobot_capabilities_schema_compliance.py
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from robot_md.backends.lerobot import LerobotBackend


_SCHEMA_PATH = Path(__file__).parents[2] / "src" / "robot_md" / "schemas" / "capabilities.json"


def test_minimal_valid_args_per_core_capability_pass_validation() -> None:
    schema = json.loads(_SCHEMA_PATH.read_text())
    defs = schema["definitions"]
    minimal_args = {
        "arm.pick": {"target": "red_lego"},
        "arm.place": {"destination": "drop_zone"},
        "arm.home": {},
        "perceive.rgb": {},
        "perceive.depth": {},
        "gripper.open": {},
        "gripper.close": {},
    }
    backend_caps = LerobotBackend().capabilities()
    for cap in backend_caps:
        if cap not in defs:
            continue  # vendor capability — not in capabilities.json
        jsonschema.validate(minimal_args[cap], defs[cap])
```

- [ ] **Step 4: Run all three tests (expect PASS — all driven by behavior already implemented)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_lerobot_execute_unknown_capability.py tests/backends/test_lerobot_dry_run.py tests/backends/test_lerobot_capabilities_schema_compliance.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run the entire LeRobot test suite to lock the phase**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_lerobot_*.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit (Task 24)**

```bash
git add cli/tests/backends/test_lerobot_execute_unknown_capability.py cli/tests/backends/test_lerobot_dry_run.py cli/tests/backends/test_lerobot_capabilities_schema_compliance.py
git commit -m "test(sp3): lock LerobotBackend dispatch + dry-run + schema-compliance contracts"
```

---

## Phase D — Wiring (pyproject + entry-points + presets)

This is when the new backends become live in the registry. Until Tasks 25-27, the LeRobot and RealSense adapters exist as code but are NOT discoverable via `entry_points(group="robot_md.backends")`.

### Task 25: Add `[hardware]`, `[lerobot]`, `[realsense]` extras to `cli/pyproject.toml`

**Files:**
- Modify: `cli/pyproject.toml`
- Test: install + import smoke (manual + CI surface).

Pin set comes from `docs/superpowers/specs/2026-04-27-sp1-5-simplification-revisions.md` Revision 3.

- [ ] **Step 1: Inspect existing optional-dependencies block**

```bash
grep -n -A 20 "\[project.optional-dependencies\]" cli/pyproject.toml | head -40
```

- [ ] **Step 2: Add the three extras**

Edit `cli/pyproject.toml`. Inside the `[project.optional-dependencies]` table, add (preserving any existing extras like `dev`, `test`):

```toml
[project.optional-dependencies]
# ... existing extras preserved ...

# SP3: meta-extra pulling all common backends (per simplification-revisions Rev 3).
hardware = [
    "lerobot>=0.5,<0.8",
    "pyrealsense2>=2.55",
    "depthai>=2.24",
    "feetech-servo-sdk>=1.0",
    "pyserial>=3.5",
    "opencv-python>=4.8",
]
# SP3: granular per-backend extras (advanced / minimal installs).
lerobot = [
    "lerobot>=0.5,<0.8",
    "pyserial>=3.5",
]
realsense = [
    "pyrealsense2>=2.55",
]
```

- [ ] **Step 3: Verify the dependency surface installs cleanly (smoke)**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
python -m venv /tmp/sp3-extras-smoke && source /tmp/sp3-extras-smoke/bin/activate
pip install -e 'cli[realsense]'
python -c "import pyrealsense2; print('ok')"
deactivate && rm -rf /tmp/sp3-extras-smoke
```

Expected: `ok`. The `lerobot` extra also installs but pulls PyTorch (~1.5 GB) — skip in this smoke unless verifying on a beefy machine.

- [ ] **Step 4: Run the existing test suite to confirm no regression from the toml edits**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/spatial_eval -x
```

Expected: all PASS.

- [ ] **Step 5: Commit (Task 25)**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/pyproject.toml
git commit -m "$(cat <<'EOF'
feat(sp3): add [hardware] meta-extra + [lerobot] / [realsense] granular extras

Per simplification-revisions Rev 3: [hardware] is the default install
hint across all docs; granular extras stay for advanced/minimal installs.

Pin set: lerobot>=0.5,<0.8 + pyrealsense2>=2.55 + depthai>=2.24 +
feetech-servo-sdk>=1.0 + pyserial>=3.5 + opencv-python>=4.8.

Entry-point declarations follow in Task 26.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 26: Add `lerobot` and `realsense` entry-point declarations

**Files:**
- Modify: `cli/pyproject.toml`
- Test: `cli/tests/backends/test_entry_points_register_sp3_backends.py`

- [ ] **Step 1: Write the entry-point registration test**

```python
# cli/tests/backends/test_entry_points_register_sp3_backends.py
from __future__ import annotations

from importlib.metadata import entry_points


def test_lerobot_and_realsense_entry_points_registered() -> None:
    eps = entry_points(group="robot_md.backends")
    names = {ep.name for ep in eps}
    assert "feetech_depthai" in names  # baseline
    assert "lerobot" in names
    assert "realsense" in names
```

- [ ] **Step 2: Run test (expect FAIL — names missing)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_entry_points_register_sp3_backends.py -v
```

- [ ] **Step 3: Add the entry-point declarations**

Edit `cli/pyproject.toml`. Find the `[project.entry-points."robot_md.backends"]` block (existing `feetech_depthai = ...` line) and add:

```toml
[project.entry-points."robot_md.backends"]
feetech_depthai = "robot_md.backends.feetech_depthai:FeetechDepthaiBackend"
lerobot         = "robot_md.backends.lerobot:LerobotBackend"
realsense       = "robot_md.backends.realsense:RealsenseBackend"
```

- [ ] **Step 4: Reinstall in editable mode so entry-point metadata refreshes**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter/cli
pip install -e .
```

Expected: clean install. (Verify with `pip show robot-md` if needed.)

- [ ] **Step 5: Run the entry-point test**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_entry_points_register_sp3_backends.py -v
```

Expected: PASS.

- [ ] **Step 6: Smoke `robot-md describe-capabilities` end-to-end**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
PYTHONPATH=cli/src python -m robot_md describe-capabilities
```

Expected output: now shows three sections (`feetech_depthai`, `lerobot`, `realsense`), each with their capabilities.

- [ ] **Step 7: Commit (Task 26)**

```bash
git add cli/pyproject.toml cli/tests/backends/test_entry_points_register_sp3_backends.py
git commit -m "$(cat <<'EOF'
feat(sp3): register lerobot + realsense backends via entry-points

Backends are now discoverable via importlib.metadata.entry_points
(group="robot_md.backends"). robot-md describe-capabilities surfaces
all three. Tier validator runs on each at discovery time; both pass
(arm.* / perceive.* / gripper.* are core; lerobot.teleop and
realsense.aligned_depth are vendor-shaped).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 27: Update SO-ARM presets to declare `preferred_backend: lerobot`

**Files:**
- Modify: `cli/src/robot_md/presets/so_arm101.yaml`, `so_arm101_leader.yaml`, `koch_arm.yaml`, `aloha2.yaml`
- Test: `cli/tests/backends/test_presets_preferred_backend_lerobot.py`

- [ ] **Step 1: Inspect one preset to confirm shape**

```bash
cat cli/src/robot_md/presets/so_arm101.yaml
```

Note the structure (`drivers:` list with `id`, `protocol`, etc.). The new field goes inside the arm-servos driver entry.

- [ ] **Step 2: Write the preferred-backend test**

```python
# cli/tests/backends/test_presets_preferred_backend_lerobot.py
from __future__ import annotations

from pathlib import Path

import yaml


_PRESETS_DIR = Path(__file__).parents[2] / "src" / "robot_md" / "presets"


def _load(preset: str) -> dict:
    return yaml.safe_load((_PRESETS_DIR / preset).read_text())


def _arm_driver_of(data: dict) -> dict:
    for drv in data.get("drivers", []):
        if drv.get("protocol") in {"feetech", "dynamixel"}:
            return drv
    raise AssertionError(f"no arm driver in preset: {data}")


def test_so_arm_presets_prefer_lerobot() -> None:
    for preset in ("so_arm101.yaml", "so_arm101_leader.yaml", "koch_arm.yaml", "aloha2.yaml"):
        data = _load(preset)
        arm = _arm_driver_of(data)
        assert arm.get("preferred_backend") == "lerobot", (
            f"{preset} arm driver missing or wrong preferred_backend (got {arm.get('preferred_backend')!r})"
        )
```

- [ ] **Step 3: Run test (expect FAIL — field missing)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_presets_preferred_backend_lerobot.py -v
```

- [ ] **Step 4: Edit each preset**

For each of `so_arm101.yaml`, `so_arm101_leader.yaml`, `koch_arm.yaml`, `aloha2.yaml`: locate the arm-servos driver entry (the one with `protocol: feetech` or `protocol: dynamixel`) and add `preferred_backend: lerobot` as a sibling key.

Example (so_arm101.yaml):

```yaml
drivers:
  - id: arm_servos
    protocol: feetech
    preferred_backend: lerobot          # NEW
    port: /dev/ttyACM0
    baud: 1000000
    motors:
      # ... existing motor list ...
```

Per simplification-revisions Revision 6: this field is **preset-internal only** — it MUST NOT appear in the `manifest` ROBOT.md schema written by `init`. Verify the manifest writer doesn't accidentally copy it through (the existing test in SP2 should catch this; if not, this is a follow-up).

- [ ] **Step 5: Run the preset test (expect PASS)**

- [ ] **Step 6: Run the full test suite to catch any preset-loader regressions**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/spatial_eval -x
```

Expected: all PASS.

- [ ] **Step 7: Commit (Task 27)**

```bash
git add cli/src/robot_md/presets/so_arm101.yaml cli/src/robot_md/presets/so_arm101_leader.yaml cli/src/robot_md/presets/koch_arm.yaml cli/src/robot_md/presets/aloha2.yaml cli/tests/backends/test_presets_preferred_backend_lerobot.py
git commit -m "$(cat <<'EOF'
feat(sp3): SO-ARM presets prefer lerobot backend

so_arm101 / so_arm101_leader / koch_arm / aloha2 arm drivers now declare
preferred_backend: lerobot. SP2's try_resolve picks this hint when
multiple backends could drive the protocol (lerobot wins over
feetech_depthai when both installed).

preferred_backend is preset-internal per simplification-revisions Rev 6;
NOT copied to the operator-visible manifest.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase E — Authoring guide + backend template

### Task 28: Write `docs/authoring-a-backend.md`

**Files:**
- Create: `docs/authoring-a-backend.md`
- Test: deferred to Task 30 (extracted code-block compile check).

- [ ] **Step 1: Draft the 8-section guide**

Create `docs/authoring-a-backend.md` with the structure from SP3 spec § 7. Target ~2000 words. Each section MUST contain only working code (Task 30 will compile-check every Python block).

```markdown
# Authoring a robot-md backend

This guide walks through writing a new `robot-md` backend — an adapter
that lets `robot-md` drive your robot's hardware via your vendor SDK,
exposed through `CapabilityBackend` and registered via Python
entry-points.

## 1. What is a backend?

A backend is a Python class implementing the `CapabilityBackend` ABC
(`from robot_md.backends import CapabilityBackend`). At runtime the
operator's manifest (`ROBOT.md`) names a backend per driver; the
runtime resolves the name to your class via `entry_points(group="robot_md.backends")`,
instantiates it, and calls `open(spec)` followed by `execute(capability, args)`.

The relationship:

```
ROBOT.md → BackendRegistry.resolve(spec) → your_backend_instance
                                              ↓
                                          execute("arm.pick", {...})
                                              ↓
                                          your_dispatch_table["arm.pick"]
```

## 2. The 30-minute path: copy the template

The fastest start is `examples/backend-template/`. Copy it, rename, edit:

(see Task 29 — the template has its own README.)

## 3. Implementing CapabilityBackend

Five required methods plus one optional:

```python
from robot_md.backends import CapabilityBackend, ExecutionResult

class MyBackend(CapabilityBackend):
    name = "my_vendor"
    protocols = frozenset({"my_protocol"})
    read_only_capabilities = frozenset({"perceive.rgb"})

    def open(self, spec):
        # connect to hardware
        ...

    def close(self):
        # disconnect
        ...

    def capabilities(self):
        return frozenset({"arm.pick", "my_vendor.special"})

    def execute(self, capability, args, *, dry_run, estop):
        # dispatch to handler
        ...

    # optional override — default impl walks capabilities.json
    # def describe_capabilities(self):
    #     ...
```

## 4. Capability namespacing

Use **core prefixes** (`arm.*`, `nav.*`, `perceive.*`, `gripper.*`,
`safety.*`) when your capability matches a standard one defined in
`cli/src/robot_md/schemas/capabilities.json`. Use **vendor namespacing**
(`<vendor>.<capability>`) for anything your SDK exposes that doesn't
fit a core prefix.

The tier validator at registration enforces this:

- core: must start with one of the prefixes above.
- vendor: must match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*$`.

Backends with malformed names are skipped at discovery — your adapter
won't load if you accidentally typo `Arm.Pick`.

## 5. Testing without hardware

Mock the SDK. The pattern from `feetech_depthai`:

```python
from unittest.mock import MagicMock
from my_backend import MyBackend


def test_open_calls_connect():
    b = MyBackend()
    b._sdk = MagicMock()  # short-circuit lazy import
    b.open(some_spec)
    b._sdk.connect.assert_called_once()
```

For SDKs that import slow C extensions, install a fake module via
`sys.modules` before instantiating:

```python
import sys, types
fake = types.ModuleType("my_vendor_sdk")
fake.connect = lambda port: object()
sys.modules["my_vendor_sdk"] = fake
```

## 6. Packaging + entry-point declaration

In your package's `pyproject.toml`:

```toml
[project.entry-points."robot_md.backends"]
my_vendor = "my_backend:MyBackend"
```

After `pip install -e .`, `robot-md describe-capabilities` will list your backend.

## 7. Contributing first-party vs publishing third-party

| Path | Where source lives | Reviewed by | Trust |
|------|-------------------|-------------|-------|
| First-party | `cli/src/robot_md/backends/<vendor>/` | `robot-md` maintainers | Audited |
| Third-party | Your own PyPI package `robot-md-backend-<vendor>` | You | Operator's risk |

Operators distinguish via `pip show <pkg>` and the publisher metadata.

## 8. Versioning + ABC stability

The `CapabilityBackend` ABC follows additive evolution:
- New optional methods land with concrete defaults; existing adapters keep
  working without changes.
- Breaking changes get a major-version bump on `robot-md` plus a 6-month
  deprecation window.
- `capabilities()` and the four originally-abstract methods (`open`,
  `close`, `execute`, `capabilities`) are stable.
```

(The above is condensed for the plan — write it out to ~2000 words in the actual doc with more examples, diagnostics tips, etc.)

- [ ] **Step 2: Save and visually inspect**

Run a syntax-only Markdown lint if the project has one (`pre-commit run -a` or similar). Fix any heading-hierarchy or list-indent issues.

- [ ] **Step 3: Commit (Task 28)**

```bash
git add docs/authoring-a-backend.md
git commit -m "docs(sp3): authoring-a-backend guide"
```

---

### Task 29: Backend template scaffold under `examples/backend-template/`

**Files:**
- Create: `examples/backend-template/README.md`, `pyproject.toml`, `src/my_backend/__init__.py`, `src/my_backend/capabilities.py`, `src/my_backend/motion.py`, `tests/test_my_backend.py`
- Test: `cli/tests/backends/test_backend_template_scaffolds.py`, `test_backend_template_tests_pass.py`, `test_backend_template_validates_namespace.py`

- [ ] **Step 1: Write the scaffold-and-install test**

```python
# cli/tests/backends/test_backend_template_scaffolds.py
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


_TEMPLATE_ROOT = Path(__file__).parents[3] / "examples" / "backend-template"


def test_template_files_exist() -> None:
    expected = [
        _TEMPLATE_ROOT / "README.md",
        _TEMPLATE_ROOT / "pyproject.toml",
        _TEMPLATE_ROOT / "src" / "my_backend" / "__init__.py",
        _TEMPLATE_ROOT / "src" / "my_backend" / "capabilities.py",
        _TEMPLATE_ROOT / "src" / "my_backend" / "motion.py",
        _TEMPLATE_ROOT / "tests" / "test_my_backend.py",
    ]
    for path in expected:
        assert path.exists(), f"template missing {path}"


def test_template_pip_installs_into_temp_env(tmp_path: Path) -> None:
    """Copy template to tmp, pip-install in editable mode, verify the
    entry-point appears in the installed metadata."""
    dest = tmp_path / "backend"
    shutil.copytree(_TEMPLATE_ROOT, dest)

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", str(dest), "--quiet"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    # Verify entry-point registered. (Use a subprocess so we don't pollute
    # the parent's importlib.metadata cache.)
    check = subprocess.run(
        [sys.executable, "-c", "from importlib.metadata import entry_points; print({ep.name for ep in entry_points(group='robot_md.backends')})"],
        capture_output=True, text=True,
    )
    assert "my_backend" in check.stdout, check.stdout
```

- [ ] **Step 2: Write the template-tests-pass and validates-namespace tests**

```python
# cli/tests/backends/test_backend_template_tests_pass.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_TEMPLATE_ROOT = Path(__file__).parents[3] / "examples" / "backend-template"


def test_template_pytests_pass() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(_TEMPLATE_ROOT / "tests"), "-q"],
        capture_output=True, text=True, cwd=_TEMPLATE_ROOT,
    )
    # NotImplementedError stubs are xfail; suite as a whole returns 0 when
    # all pass + any xfail are handled cleanly.
    assert result.returncode == 0, result.stdout + result.stderr
```

```python
# cli/tests/backends/test_backend_template_validates_namespace.py
from __future__ import annotations

from pathlib import Path
import importlib.util


_INIT = Path(__file__).parents[3] / "examples" / "backend-template" / "src" / "my_backend" / "__init__.py"


def test_template_capabilities_pass_tier_validator() -> None:
    spec = importlib.util.spec_from_file_location("template_my_backend", _INIT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    backend = mod.MyBackend()
    from robot_md.backends.registry import _validate_capability_namespace
    _validate_capability_namespace("my_backend", backend.capabilities())
```

- [ ] **Step 3: Run tests (expect FAIL — files don't exist yet)**

- [ ] **Step 4: Create template files**

`examples/backend-template/README.md`:

```markdown
# robot-md backend template — 5-step bring-up

1. `cp -r examples/backend-template ~/robot-md-backend-myvendor`
2. `cd ~/robot-md-backend-myvendor`
3. Edit `pyproject.toml` — change `name`, the entry-point key (`my_backend`), and the maintainer.
4. Edit `src/my_backend/__init__.py` — set `name`, `protocols`, fill in `open()`, `close()`, `execute()`.
5. `pip install -e . && pytest`

Then verify your backend appears: `robot-md describe-capabilities`.

See `docs/authoring-a-backend.md` for full guidance.
```

`examples/backend-template/pyproject.toml`:

```toml
[project]
name = "robot-md-backend-template"
version = "0.0.1"
requires-python = ">=3.10"
dependencies = ["robot-md"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_backend"]

[project.entry-points."robot_md.backends"]
my_backend = "my_backend:MyBackend"
```

`examples/backend-template/src/my_backend/__init__.py`:

```python
"""Template backend — copy, rename, edit, install, test."""

from __future__ import annotations

from robot_md.backends import CapabilityBackend, ExecutionResult


class MyBackend(CapabilityBackend):
    name = "my_backend"
    protocols = frozenset({"my_protocol"})
    read_only_capabilities = frozenset()

    def open(self, spec) -> None:
        # TODO: connect to your hardware here.
        raise NotImplementedError

    def close(self) -> None:
        # TODO: disconnect.
        pass

    def capabilities(self) -> frozenset[str]:
        return frozenset({"arm.pick", "my_backend.example"})

    def execute(self, capability: str, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
        from my_backend.capabilities import dispatch
        return dispatch(self, capability=capability, args=dict(args), dry_run=dry_run, estop=estop)
```

`examples/backend-template/src/my_backend/capabilities.py`:

```python
from __future__ import annotations

from robot_md.backends import ExecutionResult
from my_backend.motion import arm_pick, my_backend_example


HANDLERS = {
    "arm.pick": arm_pick,
    "my_backend.example": my_backend_example,
}


def dispatch(backend, *, capability: str, args: dict, dry_run: bool, estop) -> ExecutionResult:
    handler = HANDLERS.get(capability)
    if handler is None:
        return ExecutionResult(status="error", trajectory=None, events=[],
                               error={"reason": "not_implemented", "detail": f"capability {capability!r}"})
    return handler(backend, args, dry_run=dry_run, estop=estop)
```

`examples/backend-template/src/my_backend/motion.py`:

```python
from __future__ import annotations

from robot_md.backends import ExecutionEvent, ExecutionResult


def arm_pick(backend, args, *, dry_run, estop) -> ExecutionResult:
    # TODO: replace with real motion using your SDK.
    raise NotImplementedError("arm.pick not yet implemented")


def my_backend_example(backend, args, *, dry_run, estop) -> ExecutionResult:
    # TODO: implement your vendor capability.
    raise NotImplementedError("my_backend.example not yet implemented")
```

`examples/backend-template/tests/test_my_backend.py`:

```python
from __future__ import annotations

import pytest

from my_backend import MyBackend


def test_class_attrs() -> None:
    b = MyBackend()
    assert b.name == "my_backend"
    assert "my_protocol" in b.protocols


def test_capabilities_pass_tier_validator() -> None:
    from robot_md.backends.registry import _validate_capability_namespace
    _validate_capability_namespace("my_backend", MyBackend().capabilities())


@pytest.mark.xfail(strict=True, reason="template stub — implement before shipping")
def test_arm_pick_executes() -> None:
    b = MyBackend()
    result = b.execute("arm.pick", {"target": "x"}, dry_run=True, estop=None)
    assert result.status == "ok"
```

- [ ] **Step 5: Run tests (expect PASS)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_backend_template_*.py -v
```

Expected: all PASS — scaffolds exist, install works, namespace validator accepts the template's capabilities, template tests pass with the `xfail` for the stub motion handler.

- [ ] **Step 6: Commit (Task 29)**

```bash
git add examples/backend-template/ cli/tests/backends/test_backend_template_scaffolds.py cli/tests/backends/test_backend_template_tests_pass.py cli/tests/backends/test_backend_template_validates_namespace.py
git commit -m "$(cat <<'EOF'
feat(sp3): examples/backend-template — copy-paste backend skeleton

5-step bring-up (cp + rename + edit + install + test) targeting under
60 seconds end-to-end. Skeleton's __init__.py raises NotImplementedError
at each abstract method with TODO comments; the stub handler in the
template's tests is xfail-strict so the suite is green out of the box
yet flips green-to-fail the moment the implementer wires the real
handler.

Three CI tests pin the template's invariants: scaffold present,
`pip install -e .` registers the entry-point, capabilities pass the
tier validator.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 30: Code-block-extraction test for `docs/authoring-a-backend.md`

**Files:**
- Create: `cli/tests/docs/test_docs_authoring_examples_executable.py`

- [ ] **Step 1: Write the compile-check test**

```python
# cli/tests/docs/test_docs_authoring_examples_executable.py
from __future__ import annotations

import re
from pathlib import Path


_DOC = Path(__file__).parents[3] / "docs" / "authoring-a-backend.md"
_PY_BLOCK_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def test_every_python_code_block_compiles() -> None:
    blocks = _PY_BLOCK_RE.findall(_DOC.read_text())
    assert blocks, "no ```python code blocks found in authoring guide"
    for i, block in enumerate(blocks):
        # Skip blocks marked as illustrative-only with `# pseudo:` first line.
        if block.lstrip().startswith("# pseudo:"):
            continue
        try:
            compile(block, f"<authoring-a-backend.md block {i}>", "exec")
        except SyntaxError as e:
            raise AssertionError(f"block {i} has syntax errors: {e}\n{block}") from e
```

- [ ] **Step 2: Run test (expect PASS — Task 28's blocks are all valid)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/docs/test_docs_authoring_examples_executable.py -v
```

If a block fails to compile, fix the doc until the test passes (or mark the offending block with `# pseudo:` if it's deliberately illustrative).

- [ ] **Step 3: Commit (Task 30)**

```bash
git add cli/tests/docs/test_docs_authoring_examples_executable.py
git commit -m "test(sp3): every python block in authoring-a-backend.md compiles"
```

---

## Phase F — Integration tests, schema sync, hardware-test stubs

These tasks stitch SP3 into SP1's `init` flow + SP2's `try_resolve` and lock the runtime dispatch contract.

### Task 31: Integration: `init` resolves SO-ARM101 to lerobot when both backends installed

**Files:**
- Create: `cli/tests/integration/test_init_sp3_lerobot_resolves.py`

- [ ] **Step 1: Inspect SP1/SP2 init test patterns**

```bash
ls cli/tests/integration/ | head -20
grep -l "preferred_backend\|try_resolve" cli/tests/integration/*.py 2>/dev/null
```

Reuse whatever fixtures the existing init integration tests have (e.g., `tmp_path` + a controlled entry-point monkey-patch).

- [ ] **Step 2: Write the test**

```python
# cli/tests/integration/test_init_sp3_lerobot_resolves.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from robot_md.backends.lerobot import LerobotBackend
from robot_md.backends.feetech_depthai import FeetechDepthaiBackend


def _fake_entry_points(group: str):
    assert group == "robot_md.backends"
    le_ep = MagicMock(); le_ep.name = "lerobot"; le_ep.load.return_value = LerobotBackend
    fd_ep = MagicMock(); fd_ep.name = "feetech_depthai"; fd_ep.load.return_value = FeetechDepthaiBackend
    return [le_ep, fd_ep]


@pytest.mark.skipif(
    not Path("/dev/ttyACM0").exists(),
    reason="serial autodetect path requires /dev or strong mocking — keep this test skip-safe",
)
def test_init_sp3_lerobot_resolves_so_arm101_with_preset_hint(tmp_path: Path) -> None:
    """When both lerobot and feetech_depthai are registered AND the SO-ARM101
    preset declares preferred_backend: lerobot, init's try_resolve picks lerobot."""
    # ... follow existing init-integration fixture conventions:
    #     1. patch entry_points to return both backends
    #     2. patch autodetect to return SO-ARM101 candidate
    #     3. invoke init in tmp_path with --yes
    #     4. read the written ROBOT.md
    #     5. assert drivers[0].backend == "lerobot"
    with patch("robot_md.backends.registry.entry_points", _fake_entry_points):
        # The actual init invocation depends on the project's existing
        # integration test scaffolding (see test_init_e2e_*.py for shape).
        # Outline:
        from robot_md.cli.init import init_command  # adjust import to the real symbol
        manifest_path = tmp_path / "ROBOT.md"
        init_command(target=tmp_path, preset_name="so_arm101", yes=True)
        text = manifest_path.read_text()
        # Manifest should declare backend: lerobot for the arm driver.
        assert "backend: lerobot" in text
        # And per simplification-revisions Rev 6, NOT preferred_backend:
        assert "preferred_backend:" not in text
```

(Note: the imports + invocation pattern depend on the existing init scaffolding. If `init_command` isn't the real symbol, replace with whatever Typer command runner the existing integration tests use — typically `from typer.testing import CliRunner`. Adapt before running.)

- [ ] **Step 3: Run test, fix imports/patch targets until it passes**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/integration/test_init_sp3_lerobot_resolves.py -v
```

Expected: PASS once init flow is correctly invoked + entry-points patched.

- [ ] **Step 4: Commit (Task 31)**

```bash
git add cli/tests/integration/test_init_sp3_lerobot_resolves.py
git commit -m "test(sp3): init resolves SO-ARM101 + preset hint → lerobot"
```

---

### Task 32: Integration: RealSense-only rig → LOW tier with camera pre-filled

**Files:**
- Create: `cli/tests/integration/test_init_sp3_realsense_camera_only.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/integration/test_init_sp3_realsense_camera_only.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from robot_md.backends.realsense import RealsenseBackend


def _fake_entry_points(group: str):
    assert group == "robot_md.backends"
    rs_ep = MagicMock(); rs_ep.name = "realsense"; rs_ep.load.return_value = RealsenseBackend
    return [rs_ep]


@pytest.mark.skipif(True, reason="needs autodetect mock harness; left as stub for SP3 implementation")
def test_realsense_only_rig_writes_low_tier_manifest_with_camera_prefilled(tmp_path: Path) -> None:
    """No arm preset matches; only a RealSense D435 detected. init writes a
    LOW-tier manifest with drivers[0] = realsense camera driver pre-filled
    + physics.cameras[0] = realsense_d435 placeholder."""
    with patch("robot_md.backends.registry.entry_points", _fake_entry_points):
        # Outline (depends on autodetect mock fixtures):
        # 1. patch autodetect to return: no arm bus, RealSense D435.
        # 2. invoke init with --yes in tmp_path.
        # 3. read manifest:
        #    - drivers contains a vision driver with backend: realsense
        #    - physics.cameras[0] exists with realsense_d435 hint
        #    - TODO markers on metadata.manufacturer / physics.dof
        # 4. assert all of the above.
        pass  # see SP1's init.py + autodetect mock harness for the fixture shape
```

(This integration test is left as a runnable stub — the SP3 implementation must replace the `pass` body with real assertions once the autodetect fixture surface is understood by the implementer. The `skipif(True)` marker prevents false greens; remove once filled in.)

- [ ] **Step 2: Run (expect SKIP)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/integration/test_init_sp3_realsense_camera_only.py -v
```

Expected: SKIPPED — the implementer should remove the `skipif(True)` and fill in the body during this task's execution.

- [ ] **Step 3: Implement the test body**

Drive the existing autodetect harness to return only a RealSense D435 (no arm bus). Confirm the manifest:

- has `drivers:` with one entry, `protocol: realsense`, `backend: realsense`
- has `physics.cameras[0]` pre-filled with the RealSense D435 hint
- has TODO markers on `metadata.manufacturer` and `physics.dof`

If the existing autodetect path doesn't yet support the no-arm/camera-only case, this task absorbs that small extension.

- [ ] **Step 4: Run test (expect PASS)**

- [ ] **Step 5: Commit (Task 32)**

```bash
git add cli/tests/integration/test_init_sp3_realsense_camera_only.py
git commit -m "test(sp3): RealSense-only rig → LOW tier manifest with camera pre-filled"
```

---

### Task 33: Integration: runtime dispatches to the explicit `backend:` field

**Files:**
- Create: `cli/tests/integration/test_runtime_dispatches_to_correct_backend.py`, `cli/tests/integration/test_runtime_two_backends_same_protocol_explicit_wins.py`

- [ ] **Step 1: Write the dispatch test**

```python
# cli/tests/integration/test_runtime_dispatches_to_correct_backend.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

from robot_md.backends.lerobot import LerobotBackend
from robot_md.backends.realsense import RealsenseBackend
from robot_md.backends.registry import BackendRegistry
from robot_md.robot_spec import RobotSpec, Driver


def test_explicit_backend_field_wins() -> None:
    spec = RobotSpec(
        rrn="RRN-test",
        drivers=[Driver(id="arm_servos", protocol="feetech", backend="lerobot",
                        port="/dev/ttyACM0", baud=1000000, motors=[{"id": 1, "model": "sts3215", "joint": "shoulder_pan"}])],
    )
    reg = BackendRegistry(backends=[LerobotBackend(), RealsenseBackend()])
    resolved = reg.resolve(spec)
    assert isinstance(resolved["arm_servos"], LerobotBackend)


def test_no_explicit_backend_alphabetical_first_wins() -> None:
    spec = RobotSpec(
        rrn="RRN-test",
        drivers=[Driver(id="arm_servos", protocol="feetech", backend=None,
                        port="/dev/ttyACM0", baud=1000000, motors=[])],
    )
    # Both lerobot and feetech_depthai claim "feetech"; alphabetical → feetech_depthai.
    from robot_md.backends.feetech_depthai import FeetechDepthaiBackend
    reg = BackendRegistry(backends=[LerobotBackend(), FeetechDepthaiBackend()])
    resolved = reg.resolve(spec)
    # Note: BackendRegistry.resolve sorts by .name; "feetech_depthai" < "lerobot".
    assert resolved["arm_servos"].name == "feetech_depthai"
```

```python
# cli/tests/integration/test_runtime_two_backends_same_protocol_explicit_wins.py
from __future__ import annotations

from robot_md.backends.lerobot import LerobotBackend
from robot_md.backends.feetech_depthai import FeetechDepthaiBackend
from robot_md.backends.registry import BackendRegistry
from robot_md.robot_spec import RobotSpec, Driver


def test_explicit_feetech_depthai_overrides_alphabetical() -> None:
    spec = RobotSpec(
        rrn="RRN-test",
        drivers=[Driver(id="arm_servos", protocol="feetech", backend="feetech_depthai",
                        port="/dev/ttyACM0", baud=1000000, motors=[])],
    )
    reg = BackendRegistry(backends=[LerobotBackend(), FeetechDepthaiBackend()])
    resolved = reg.resolve(spec)
    assert resolved["arm_servos"].name == "feetech_depthai"
```

- [ ] **Step 2: Run tests (expect PASS — `BackendRegistry.resolve` already implements this)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/integration/test_runtime_dispatches_to_correct_backend.py tests/integration/test_runtime_two_backends_same_protocol_explicit_wins.py -v
```

Expected: PASS (3/3).

- [ ] **Step 3: Commit (Task 33)**

```bash
git add cli/tests/integration/test_runtime_dispatches_to_correct_backend.py cli/tests/integration/test_runtime_two_backends_same_protocol_explicit_wins.py
git commit -m "test(sp3): lock runtime backend resolution — explicit wins, alphabetical fallback"
```

---

### Task 34: Schema sync — TS bundle mirror of `capabilities.json`

**Files:**
- Modify: existing schema-sync script (whichever exists — `scripts/sync-schema.mjs` or `cli/scripts/sync-schema.py` per the SP6 plan's pattern)
- Test: `cli/tests/backends/test_capabilities_schema_sync_ts.py`

- [ ] **Step 1: Find the existing schema-sync mechanism**

```bash
ls scripts/ cli/scripts/ 2>/dev/null
grep -rn "schema.json\|sync-schema\|robot.schema" Makefile package.json site/package.json 2>/dev/null | head -10
```

The SP6 plan's T1 / T34 set the precedent that `schema/v1/robot.schema.json` is canonical with byte-identical mirrors elsewhere. SP3's `capabilities.json` follows the same pattern.

- [ ] **Step 2: Decide canonical path**

Canonical: `cli/src/robot_md/schemas/capabilities.json` (Python-side). Mirror destinations (one or both, depending on what already exists):

- `schema/v1/capabilities.json` (top-level canonical mirror, if `schema/` directory exists per SP6 precedent).
- `site/static/schemas/capabilities.json` (web mirror, if `site/` exists).

- [ ] **Step 3: Write the byte-identical-mirror test**

```python
# cli/tests/backends/test_capabilities_schema_sync_ts.py
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).parents[3]
_CANONICAL = _REPO_ROOT / "cli" / "src" / "robot_md" / "schemas" / "capabilities.json"


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_schema_v1_mirror_matches_canonical() -> None:
    mirror = _REPO_ROOT / "schema" / "v1" / "capabilities.json"
    if not mirror.exists():
        pytest.skip("schema/v1/capabilities.json mirror not configured for this repo")
    assert _sha256(_CANONICAL) == _sha256(mirror), (
        f"capabilities.json drift: canonical {_sha256(_CANONICAL)} vs mirror {_sha256(mirror)}; "
        f"run scripts/sync-schema to refresh."
    )


def test_site_mirror_matches_canonical() -> None:
    mirror = _REPO_ROOT / "site" / "static" / "schemas" / "capabilities.json"
    if not mirror.exists():
        pytest.skip("site/static/schemas/capabilities.json mirror not configured for this repo")
    assert _sha256(_CANONICAL) == _sha256(mirror)
```

- [ ] **Step 4: Update the sync script + run it**

Find the existing sync script (one is expected to exist from SP6/RCAN work). Add `capabilities.json` to its file list. Run it:

```bash
# Whatever the existing invocation is — examples:
node scripts/sync-schema.mjs
# or
python cli/scripts/sync-schema.py
```

Expected: produces `schema/v1/capabilities.json` and/or `site/.../capabilities.json` byte-identical to canonical.

- [ ] **Step 5: Run the test (expect PASS or SKIP, no FAIL)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/backends/test_capabilities_schema_sync_ts.py -v
```

- [ ] **Step 6: Commit (Task 34)**

```bash
git add cli/src/robot_md/schemas/capabilities.json schema/v1/capabilities.json site/static/schemas/capabilities.json scripts/sync-schema.* cli/tests/backends/test_capabilities_schema_sync_ts.py
git commit -m "$(cat <<'EOF'
chore(sp3): mirror capabilities.json to schema/v1 + site/

Canonical lives at cli/src/robot_md/schemas/capabilities.json. Mirrors
are byte-identical, refreshed via the existing schema sync script. Test
locks the byte-equivalence so CI catches drift.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

(If the repo has only one of the two mirror locations, the test's other branch SKIPs cleanly — the commit can omit the missing path.)

---

### Task 35: Hardware-test stubs (skipped in CI; runnable on bob)

**Files:**
- Create: `cli/tests/hardware/test_sp3_lerobot_so_arm101_pick.py`, `cli/tests/hardware/test_sp3_realsense_d435_perceive.py`
- Manual smoke: `cli/tests/manual/sp3_adapter_smoke.md`

- [ ] **Step 1: Write the LeRobot hardware test stub**

```python
# cli/tests/hardware/test_sp3_lerobot_so_arm101_pick.py
from __future__ import annotations

import pytest


pytestmark = pytest.mark.hardware


def test_lerobot_arm_pick_red_lego_on_bob() -> None:
    """End-to-end: LeRobot adapter drives bob's SO-ARM101 to pick the red lego.

    Compares roughly to feetech_depthai's trajectory shape (does NOT require
    bit-identical paths — different SDKs).
    """
    from robot_md.backends.lerobot import LerobotBackend
    from robot_md.robot_spec import RobotSpec
    # Load bob's actual ROBOT.md.
    spec = RobotSpec.load_from("/home/craigm26/bob/ROBOT.md")
    backend = LerobotBackend()
    backend.open(spec)
    try:
        result = backend.execute("arm.pick", {"target": "red_lego"}, dry_run=False, estop=None)
        assert result.status == "ok"
        assert result.trajectory is not None
        assert len(result.trajectory) >= 2
    finally:
        backend.close()
```

- [ ] **Step 2: Write the RealSense hardware test stub**

```python
# cli/tests/hardware/test_sp3_realsense_d435_perceive.py
from __future__ import annotations

import pytest


pytestmark = pytest.mark.hardware


def test_realsense_d435_perceive_rgb_returns_nonempty_frame() -> None:
    from robot_md.backends.realsense import RealsenseBackend
    from robot_md.robot_spec import RobotSpec

    spec = RobotSpec.empty(rrn="RRN-realsense-only")
    backend = RealsenseBackend()
    backend.open(spec)
    try:
        result = backend.execute("perceive.rgb", {}, dry_run=False, estop=None)
        assert result.status == "ok"
        payload = result.events[-1].data
        assert len(payload["frame_bytes"]) > 0
    finally:
        backend.close()


def test_realsense_d435_perceive_depth_returns_nonempty_frame() -> None:
    from robot_md.backends.realsense import RealsenseBackend
    from robot_md.robot_spec import RobotSpec

    spec = RobotSpec.empty(rrn="RRN-realsense-only")
    backend = RealsenseBackend()
    backend.open(spec)
    try:
        result = backend.execute("perceive.depth", {}, dry_run=False, estop=None)
        assert result.status == "ok"
        payload = result.events[-1].data
        assert len(payload["frame_bytes"]) > 0
    finally:
        backend.close()
```

- [ ] **Step 3: Verify they're skipped in default CI run**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/hardware/test_sp3_*.py -v
```

Expected: SKIPPED (because `@pytest.mark.hardware` and the conftest skips this marker unless `--run-hardware` or equivalent is passed; verify against `cli/tests/conftest.py`).

- [ ] **Step 4: Write the manual smoke checklist**

Create `cli/tests/manual/sp3_adapter_smoke.md`:

```markdown
# SP3 adapter smoke — manual checks on bob

Run on the Pi5 with bob's ROBOT.md present in cwd.

1. **LeRobot adapter on bob:** install + init + drive
   ```
   pip uninstall -y robot-md  # cleanup any prior local install
   pip install -e 'cli[lerobot]'
   robot-md init --yes
   ```
   Confirm `ROBOT.md`'s arm driver has `backend: lerobot`. Run `claude` and ask
   "find the red lego" — verify motion via the LeRobot path.

2. **Two adapters installed, preset hint disambiguates:**
   ```
   pip install -e 'cli[hardware]'   # both lerobot + feetech-depthai installed
   robot-md init bob
   ```
   Init's closing line should mention preset hint → lerobot. Manifest gets
   `backend: lerobot` (NOT preferred_backend — see Rev 6).

3. **RealSense camera-only rig:** plug a D435, no arm.
   ```
   robot-md init scanrig --yes
   ```
   Manifest is LOW tier with `physics.cameras[0]` pre-filled and no arm
   driver. TODO markers on `metadata.manufacturer` and `physics.dof`.

4. **Template author flow:**
   ```
   cp -r examples/backend-template ~/foo
   cd ~/foo && pip install -e . && pytest
   ```
   Entry-point registered, template tests pass with stub xfail.

5. **describe-capabilities CLI:**
   ```
   robot-md describe-capabilities
   robot-md describe-capabilities --json | jq '. | length'
   ```
   Shows three sections; JSON output has length 3.

Each step's pass/fail goes in the commit message of the PR landing this plan.
```

- [ ] **Step 5: Commit (Task 35)**

```bash
git add cli/tests/hardware/test_sp3_lerobot_so_arm101_pick.py cli/tests/hardware/test_sp3_realsense_d435_perceive.py cli/tests/manual/sp3_adapter_smoke.md
git commit -m "$(cat <<'EOF'
test(sp3): hardware stubs (@pytest.mark.hardware) + manual smoke checklist

LeRobot SO-ARM101 pick + RealSense D435 perceive — skipped in CI per
existing conftest hardware-marker policy; runnable on bob via the
project's hardware-suite invocation.

Manual smoke covers the five operator-visible flows: lerobot install +
init, two-backends-installed preset disambiguation, RealSense-only LOW
tier, backend-template copy + install, and the describe-capabilities CLI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Implementation Order Summary

```
Phase A — capability metadata foundation
  1. capabilities.json (core schema)
  2. capability tier validator
  3. wire validator into discover_backends()
  4. Capability dataclass + derive_namespace
  5. describe_capabilities() default impl
  6. BackendRegistry.iter_classes()
  7. enumerate_capabilities(registry) walker
  8. robot-md describe-capabilities CLI

Phase B — RealSense backend (camera-only)
  9. RealsenseBackend class skeleton
 10. open() with mocked pyrealsense2 pipeline
 11. perceive.rgb handler
 12. perceive.depth handler
 13. scene_describe()
 14. realsense.aligned_depth vendor cap
 15. lock no-arm contract

Phase C — LeRobot backend (motion + camera)
 16. LerobotBackend skeleton + class-attr tests
 17. _build_lerobot_config(spec) for SO-ARM101
 18. open() with mocked make_robot
 19. arm.pick handler
 20. arm.place + arm.home handlers
 21. gripper.open + gripper.close handlers
 22. perceive.rgb + perceive.depth via capture_observation
 23. lerobot.teleop vendor cap
 24. lock unknown-cap + dry-run + schema-compliance contracts

Phase D — wiring
 25. [hardware] / [lerobot] / [realsense] extras
 26. entry-point declarations for new backends
 27. SO-ARM presets prefer lerobot

Phase E — authoring guide + template
 28. docs/authoring-a-backend.md
 29. examples/backend-template/ scaffold
 30. compile-check every Python block in the guide

Phase F — integration + schema sync + hardware
 31. integration: init resolves SO-ARM101 → lerobot
 32. integration: RealSense-only rig → LOW tier
 33. integration: runtime backend dispatch
 34. schema sync (capabilities.json mirrors)
 35. hardware-test stubs + manual smoke checklist
```

---

## Success Criteria

SP3 is done when:

- [ ] All 35 tasks are merged.
- [ ] Test count: ~50+ unit tests across `cli/tests/backends/`, ~5 integration tests, 3 hardware tests (skipped in CI).
- [ ] `robot-md describe-capabilities` lists all three backends + their capability metadata, both human-readable and `--json`.
- [ ] `pip install 'cli[hardware]'` installs cleanly on Linux + macOS.
- [ ] `feetech_depthai` ships green — no edits to its source; all its capabilities (core arm.* and vendor vision./status.) flow through the new tier validator and `describe_capabilities()` default unchanged.
- [ ] Manual smoke checklist (`cli/tests/manual/sp3_adapter_smoke.md`) passes 5/5 on bob.
- [ ] Hardware tests pass on bob (LeRobot SO-ARM101 pick + RealSense D435 perceive).
- [ ] Demo dry-run: a stock SO-100 with `pip install 'robot-md[hardware]'` + `robot-md init` + `claude` → "find a red lego" → motion via LeRobot. End-to-end with no RRF-specific config.

---

## Notes for the implementer

- **TDD discipline:** every code-producing task has its tests written FIRST and run-and-failed BEFORE the implementation. Don't skip the failure-verification step — it's how you know the test actually exercises the code path.
- **`feetech_depthai` declares vision.describe + status.report** — these don't match `CORE_CAPABILITY_PREFIXES`. Both pass the vendor regex (look like `<vendor>.<name>`), so the validator accepts them. **Do not "fix" the prefix list** — it's RRF-canonical for core only.
- **Mock the SDKs.** The `lerobot` and `pyrealsense2` packages are heavy / platform-specific. All tests in Phases B/C use `sys.modules` monkey-patching or `MagicMock` fixtures. Real-SDK paths run only in the hardware suite (Task 35).
- **Per simplification-revisions Rev 6:** `preferred_backend` is preset-internal; never copied to operator-visible `ROBOT.md`. SP2's manifest writer should already drop it; if Task 31's integration test fails because the manifest has `preferred_backend:`, file a follow-up to fix the writer (don't paper over it in this plan).
- **Each task ends with a commit.** Plan execution is incremental — at any point an external reviewer should be able to look at HEAD and understand what just landed.



# feetech_depthai real backend — Phase 1 implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-18-feetech-depthai-real-backend-design.md`

**Scope:** **Phase 1 only.** Ports the working `examples/tier0/*.py` hardware code into the `feetech_depthai` backend modules, replacing the v0.3.1 stubs. Capability handlers actuate real servos and the OAK-D; `arm.pick` and `arm.place` replay one hardcoded "first-demo" trajectory embedded directly in the capability handler. Skills-from-sidecar (P2), perception-gate (P3), hand-eye (P4), and memory-sync (P5) are explicitly out of scope and get their own plans.

**Goal:** Ship v0.4.0 such that, on Bob (SO-ARM101 + OAK-D + Feetech bus on `/dev/ttyACM0`), running `execute_task("pick the lego")` via the Python MCP server moves real servos and grabs a real camera frame.

**Architecture:** Four backend modules (`servo.py`, `perception.py`, `motion.py`, `capabilities.py`) each take one concern from tier0. `servo.py` wraps `feetech_servo_sdk` PortHandler+PacketHandler. `perception.py` wraps the depthai pipeline. `motion.py` is a thin trajectory driver. `capabilities.py` glues them via a hardcoded pick-and-place waypoint sequence that the next phase replaces with skill-store lookup.

**Tech Stack:** Python 3.10+, `feetech-servo-sdk` (new — added to `feetech-depthai` extra), `depthai`, `opencv-python`, `numpy`, `pytest` (+ mocks). Hardware tests gated by `--run-hardware`.

---

## File structure

### Modify
```
cli/pyproject.toml                                        # add feetech-servo-sdk to extra; bump to 0.4.0
cli/src/robot_md/__init__.py                              # bump __version__
cli/src/robot_md/backends/feetech_depthai/servo.py        # stub → real
cli/src/robot_md/backends/feetech_depthai/perception.py   # stub → real
cli/src/robot_md/backends/feetech_depthai/motion.py       # stub → real
cli/src/robot_md/backends/feetech_depthai/capabilities.py # stubs → real (hardcoded pick/place)
CHANGELOG.md                                              # v0.4.0 entry
```

### Create
```
cli/tests/unit/test_feetech_depthai_servo.py
cli/tests/unit/test_feetech_depthai_motion.py
cli/tests/unit/test_feetech_depthai_perception.py
cli/tests/unit/test_feetech_depthai_capabilities.py
cli/tests/hardware/test_teach_replay_roundtrip.py
```

### Key conventions (read before every task)

- Tests run via `/home/craigm26/opencastor/venv/bin/python3 -m pytest` (this is the editable-install Python; system pytest can't find `robot_md.*`).
- `from __future__ import annotations` at the top of every new module.
- Hardware deps (`feetech_servo_sdk`, `depthai`, `cv2`, `numpy`) are lazy-imported inside methods where feasible so unit tests can run without them installed. Where lazy-import is unnatural (e.g., numpy arrays used at module scope), protect module-level imports with `try/except ImportError` and skip cleanly.
- Servo register addresses (from tier0): `ADDR_TORQUE_ENABLE=40`, `ADDR_GOAL_POSITION=42`, `ADDR_PRESENT_POSITION=56`. Feetech bus convention: servo IDs `1..6` map to joint names `shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper`.
- The hardcoded Phase 1 "first-demo" trajectory lives inline in `capabilities.py::_HARDCODED_PICK_WAYPOINTS`. It is deliberately short and safe (small joint deltas around zero pose) — this is a smoke-level proof, not a real Lego grasp. Real grasps arrive in P2 with the skill store.
- Commits: per task, single commit. Messages use `feat:`, `test:`, `refactor:`, `docs:` prefixes. No `Co-Authored-By` line unless the repo's existing history already uses one.

---

## Task 1: Add `feetech-servo-sdk` to extras

**Files:**
- Modify: `cli/pyproject.toml`

- [ ] **Step 1: Add the dep to the existing `feetech-depthai` extra**

Current block in `cli/pyproject.toml`:
```toml
feetech-depthai = [
    "pyserial>=3.5",
    "depthai>=2.24",
    "opencv-python>=4.8",
    "numpy>=1.24",
]
```

Change to:
```toml
feetech-depthai = [
    "pyserial>=3.5",
    "depthai>=2.24",
    "opencv-python>=4.8",
    "numpy>=1.24",
    "feetech-servo-sdk>=1.0",
]
```

- [ ] **Step 2: Reinstall the extra into the venv**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pip install -e ".[feetech-depthai]" --quiet 2>&1 | tail -3
```

- [ ] **Step 3: Verify the import works**

```bash
/home/craigm26/opencastor/venv/bin/python3 -c "from feetech_servo_sdk import PacketHandler, PortHandler; print('ok')"
```

Expected: `ok`. If the PyPI package name differs (e.g., `feetech-sdk` vs `feetech-servo-sdk`), verify tier0 uses it successfully (it does — `01_read_positions.py` imports `from feetech_servo_sdk import ...`) and correct the extra accordingly.

- [ ] **Step 4: Commit**

```bash
cd /home/craigm26/robot-md && git add cli/pyproject.toml
git commit -m "feat(deps): add feetech-servo-sdk to feetech-depthai extra"
```

---

## Task 2: Port `servo.py` — real STS3215 wire protocol

**Files:**
- Modify: `cli/src/robot_md/backends/feetech_depthai/servo.py`
- Create: `cli/tests/unit/test_feetech_depthai_servo.py`

### TDD flow

- [ ] **Step 1: Write the failing unit tests**

File `cli/tests/unit/test_feetech_depthai_servo.py`:

```python
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec


def _spec(fixtures_dir):
    return RobotSpec.from_parsed(parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml"))


def _install_fake_sdk(monkeypatch):
    fake_sdk = MagicMock()
    fake_port = MagicMock()
    fake_port.openPort.return_value = True
    fake_port.setBaudRate.return_value = True
    fake_sdk.PortHandler.return_value = fake_port
    fake_ph = MagicMock()
    # read2ByteTxRx returns (position, result, error); we default to (2048, 0, 0) per servo
    fake_ph.read2ByteTxRx.return_value = (2048, 0, 0)
    fake_sdk.PacketHandler.return_value = fake_ph
    monkeypatch.setitem(sys.modules, "feetech_servo_sdk", fake_sdk)
    return fake_sdk, fake_port, fake_ph


def test_open_from_spec_opens_port(monkeypatch, fixtures_dir):
    fake_sdk, fake_port, _ = _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()
    fake_sdk.PortHandler.assert_called_once_with(bus.port)
    fake_port.openPort.assert_called_once()
    fake_port.setBaudRate.assert_called_once_with(bus.baud)
    bus.close()


def test_read_positions_returns_named_dict(monkeypatch, fixtures_dir):
    _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()
    positions = bus.read_positions()
    assert set(positions.keys()) == {
        "shoulder_pan", "shoulder_lift", "elbow_flex",
        "wrist_flex", "wrist_roll", "gripper",
    }
    assert all(v == 2048 for v in positions.values())
    bus.close()


def test_read_positions_skips_nonresponders(monkeypatch, fixtures_dir):
    fake_sdk, _, fake_ph = _install_fake_sdk(monkeypatch)

    def _fake_read(port, sid, addr):
        if sid == 3:
            return (0, 1, 0)  # nonzero result = failure
        return (2048, 0, 0)

    fake_ph.read2ByteTxRx.side_effect = _fake_read
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()
    positions = bus.read_positions()
    assert "elbow_flex" not in positions            # servo id 3
    assert "shoulder_pan" in positions              # servo id 1
    assert len(positions) == 5
    bus.close()


def test_write_positions_sends_goal(monkeypatch, fixtures_dir):
    _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()
    bus.write_positions({"shoulder_pan": 2100, "gripper": 1700})
    from robot_md.backends.feetech_depthai.servo import ADDR_GOAL_POSITION
    calls = bus._ph.write2ByteTxRx.call_args_list
    # Two writes, to servo ids 1 and 6
    sids = sorted(c.args[1] for c in calls)
    assert sids == [1, 6]
    # All writes hit GOAL_POSITION address
    assert all(c.args[2] == ADDR_GOAL_POSITION for c in calls)
    bus.close()


def test_torque_writes_all_servos(monkeypatch, fixtures_dir):
    _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ServoBus, ADDR_TORQUE_ENABLE

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()
    bus.torque(True)
    calls = bus._ph.write1ByteTxRx.call_args_list
    assert len(calls) == 6
    assert all(c.args[2] == ADDR_TORQUE_ENABLE for c in calls)
    assert all(c.args[3] == 1 for c in calls)
    bus.close()


def test_interpolate_respects_estop(monkeypatch, fixtures_dir):
    """If estop is set mid-interpolation, we stop issuing writes."""
    _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()

    class _Estop:
        def __init__(self):
            self.calls = 0

        def is_set(self):
            self.calls += 1
            return self.calls > 3  # flips after 3 checks

    estop = _Estop()
    start = {"shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048,
             "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700}
    target = {**start, "shoulder_pan": 2200}  # ~153 steps => many ticks

    bus.interpolate(start, target, hz=200, max_steps_per_tick=5, estop=estop)
    # Without estop, ~31 ticks. With estop firing at ~3, writes should stop early.
    # Each tick writes 6 goal positions.
    assert bus._ph.write2ByteTxRx.call_count <= 6 * 4
    bus.close()


def test_interpolate_interpolates_monotonic(monkeypatch, fixtures_dir):
    _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()

    class _NoopEstop:
        def is_set(self): return False

    start = {"shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048,
             "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700}
    target = {**start, "shoulder_pan": 2200}
    bus.interpolate(start, target, hz=200, max_steps_per_tick=10, estop=_NoopEstop())

    # Collect every write to servo id 1 (shoulder_pan) — should be monotonically increasing 2048 → 2200
    shoulder_writes = [c.args[3] for c in bus._ph.write2ByteTxRx.call_args_list if c.args[1] == 1]
    assert shoulder_writes[0] > 2048 and shoulder_writes[-1] == 2200
    # Monotonic
    assert all(shoulder_writes[i] <= shoulder_writes[i + 1] for i in range(len(shoulder_writes) - 1))
    bus.close()
```

- [ ] **Step 2: Run — confirm failures**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest tests/unit/test_feetech_depthai_servo.py -v
```

Expected: every test fails (the current stub has no `open`, `torque`, `interpolate`, constants etc.).

- [ ] **Step 3: Replace `servo.py` with the real implementation**

Overwrite `cli/src/robot_md/backends/feetech_depthai/servo.py`:

```python
"""Feetech STS3215 serial I/O wrapper.

Ports the working wire-protocol usage from `examples/tier0/01_read_positions.py`,
`examples/tier0/02_gripper_wiggle.py`, `examples/tier0/03_shoulder_pan_wiggle.py`,
and the `_interpolate` helper from `examples/tier0/04_pick_place.py`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from robot_md.robot_spec import RobotSpec

# STS3215 register addresses (from tier0 examples)
ADDR_TORQUE_ENABLE = 40
ADDR_GOAL_POSITION = 42
ADDR_PRESENT_POSITION = 56

# Canonical servo_id → joint_name mapping for SO-ARM101. Ordering matches
# physics.kinematics[] in the presets and the register-address convention.
_DEFAULT_JOINT_IDS: tuple[int, ...] = (1, 2, 3, 4, 5, 6)
_DEFAULT_JOINT_NAMES: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)


@dataclass
class ServoBus:
    port: str
    baud: int
    count: int
    joint_ids: tuple[int, ...] = field(default=_DEFAULT_JOINT_IDS)
    joint_names: tuple[str, ...] = field(default=_DEFAULT_JOINT_NAMES)

    # Runtime handles — set in open(), cleared in close()
    _port: object | None = None
    _ph: object | None = None

    @classmethod
    def from_spec(cls, spec: RobotSpec) -> "ServoBus":
        drv = next((d for d in spec.drivers if d.protocol == "feetech"), None)
        if drv is None:
            raise RuntimeError("no feetech driver in spec")
        return cls(
            port=drv.port or "/dev/ttyACM0",
            baud=drv.baud_rate or 1_000_000,
            count=drv.count or len(_DEFAULT_JOINT_IDS),
        )

    def open(self) -> None:
        from feetech_servo_sdk import PacketHandler, PortHandler

        p = PortHandler(self.port)
        if not p.openPort():
            raise RuntimeError(f"cannot open {self.port}")
        if not p.setBaudRate(self.baud):
            p.closePort()
            raise RuntimeError(f"cannot set baud {self.baud} on {self.port}")
        self._port = p
        self._ph = PacketHandler(0)

    def close(self) -> None:
        if self._port is not None:
            try:
                self._port.closePort()
            except Exception:
                pass
        self._port = None
        self._ph = None

    # ------------------------------------------------------------------ reads

    def read_positions(self) -> dict[str, int]:
        """Return {joint_name: steps} for every servo that responds.

        A non-responder (result != 0 or error != 0) is silently omitted. Callers
        that need completeness must check the returned dict's keys.
        """
        if self._ph is None or self._port is None:
            raise RuntimeError("ServoBus not open")
        out: dict[str, int] = {}
        for sid, name in zip(self.joint_ids, self.joint_names, strict=True):
            pos, result, err = self._ph.read2ByteTxRx(self._port, sid, ADDR_PRESENT_POSITION)
            if result == 0 and err == 0:
                out[name] = int(pos)
        return out

    # ----------------------------------------------------------------- writes

    def write_positions(self, positions: dict[str, int]) -> None:
        """Send a one-shot goal-position write for each named joint present."""
        if self._ph is None or self._port is None:
            raise RuntimeError("ServoBus not open")
        name_to_id = dict(zip(self.joint_names, self.joint_ids, strict=True))
        for name, target in positions.items():
            sid = name_to_id.get(name)
            if sid is None:
                continue
            self._ph.write2ByteTxRx(self._port, sid, ADDR_GOAL_POSITION, int(target))

    def torque(self, on: bool) -> None:
        """Enable/disable torque on every joint."""
        if self._ph is None or self._port is None:
            raise RuntimeError("ServoBus not open")
        val = 1 if on else 0
        for sid in self.joint_ids:
            self._ph.write1ByteTxRx(self._port, sid, ADDR_TORQUE_ENABLE, val)

    # ----------------------------------------------------------- interpolate

    def interpolate(
        self,
        start: dict[str, int],
        target: dict[str, int],
        *,
        hz: int = 30,
        max_steps_per_tick: int = 12,
        estop,
    ) -> None:
        """Linearly drive joints from start → target at `hz`, bounded per-tick.

        Ported from `examples/tier0/04_pick_place.py::_interpolate`. Checks
        `estop.is_set()` before each tick; returns early if set.
        """
        if self._ph is None or self._port is None:
            raise RuntimeError("ServoBus not open")
        name_to_id = dict(zip(self.joint_names, self.joint_ids, strict=True))
        deltas: dict[str, int] = {n: target[n] - start[n] for n in start if n in target}
        max_delta = max((abs(d) for d in deltas.values()), default=0)
        if max_delta == 0:
            return
        ticks = max(1, (max_delta + max_steps_per_tick - 1) // max_steps_per_tick)
        dt = 1.0 / hz
        for i in range(1, ticks + 1):
            if estop.is_set():
                return
            alpha = i / ticks
            for n, d in deltas.items():
                sid = name_to_id.get(n)
                if sid is None:
                    continue
                val = int(round(start[n] + alpha * d))
                self._ph.write2ByteTxRx(self._port, sid, ADDR_GOAL_POSITION, val)
            time.sleep(dt)
```

- [ ] **Step 4: Run — confirm pass**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest tests/unit/test_feetech_depthai_servo.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Regression check**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest 2>&1 | tail -5
```

Expected: all unit + integration green; 2 hardware skipped.

- [ ] **Step 6: Commit**

```bash
cd /home/craigm26/robot-md && git add cli/src/robot_md/backends/feetech_depthai/servo.py cli/tests/unit/test_feetech_depthai_servo.py
git commit -m "feat(backend): real STS3215 servo bus"
```

---

## Task 3: Port `motion.py` — trajectory replay

**Files:**
- Modify: `cli/src/robot_md/backends/feetech_depthai/motion.py`
- Create: `cli/tests/unit/test_feetech_depthai_motion.py`

### TDD flow

- [ ] **Step 1: Write the failing test**

File `cli/tests/unit/test_feetech_depthai_motion.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.feetech_depthai.motion import Motion, Waypoint
from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec


def _spec(fixtures_dir):
    return RobotSpec.from_parsed(parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml"))


def test_replay_calls_interpolate_per_segment(fixtures_dir):
    """Given 3 waypoints, replay issues 2 interpolate() calls (wp0→wp1, wp1→wp2)."""
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    estop = MagicMock()
    estop.is_set.return_value = False

    wp0 = Waypoint(t=0.0, joints={"shoulder_pan": 2048, "shoulder_lift": 2048,
                                   "elbow_flex": 2048, "wrist_flex": 2048,
                                   "wrist_roll": 2048, "gripper": 1700})
    wp1 = Waypoint(t=0.5, joints={**wp0.joints, "shoulder_pan": 2100})
    wp2 = Waypoint(t=1.0, joints={**wp1.joints, "gripper": 1200})

    motion.replay([wp0, wp1, wp2], servo_bus=bus, estop=estop)
    assert bus.interpolate.call_count == 2
    first_call = bus.interpolate.call_args_list[0]
    assert first_call.args[0] == wp0.joints
    assert first_call.args[1] == wp1.joints


def test_replay_empty_trajectory_is_noop(fixtures_dir):
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    estop = MagicMock()
    estop.is_set.return_value = False

    motion.replay([], servo_bus=bus, estop=estop)
    bus.interpolate.assert_not_called()


def test_replay_single_waypoint_writes_positions_once(fixtures_dir):
    """A one-waypoint trajectory is a position command, not an interpolation."""
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    estop = MagicMock()
    estop.is_set.return_value = False

    wp = Waypoint(t=0.0, joints={"shoulder_pan": 2200})
    motion.replay([wp], servo_bus=bus, estop=estop)
    bus.interpolate.assert_not_called()
    bus.write_positions.assert_called_once_with({"shoulder_pan": 2200})


def test_replay_respects_hz_from_trajectory(fixtures_dir):
    """Motion uses the per-trajectory hz when the caller does not override."""
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    estop = MagicMock()
    estop.is_set.return_value = False

    wp0 = Waypoint(t=0.0, joints={"shoulder_pan": 2048})
    wp1 = Waypoint(t=0.5, joints={"shoulder_pan": 2100})

    motion.replay([wp0, wp1], servo_bus=bus, estop=estop, hz=60)
    assert bus.interpolate.call_args.kwargs.get("hz") == 60
```

- [ ] **Step 2: Run — confirm failures**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest tests/unit/test_feetech_depthai_motion.py -v
```

Expected: all fail (current `motion.py` has only a stub `Motion` with `forward/inverse/plan_trajectory` — not `replay`).

- [ ] **Step 3: Replace `motion.py` with the real implementation**

Overwrite `cli/src/robot_md/backends/feetech_depthai/motion.py`:

```python
"""Trajectory replay + (future-P4) pose-adjust and forward kinematics.

Phase 1 scope: `replay(waypoints, servo_bus, estop)` — iterates consecutive
waypoint pairs and calls servo_bus.interpolate between them. Single-waypoint
trajectories are treated as one-shot position commands.

Forward kinematics and pose-adjust are Phase 4 (hand-eye).
"""

from __future__ import annotations

from dataclasses import dataclass

from robot_md.backends.feetech_depthai.servo import ServoBus
from robot_md.robot_spec import RobotSpec


@dataclass(frozen=True)
class Waypoint:
    t: float                       # seconds from trajectory start (informational)
    joints: dict[str, int]         # servo positions in steps


@dataclass
class Motion:
    spec: RobotSpec

    @classmethod
    def from_spec(cls, spec: RobotSpec) -> "Motion":
        return cls(spec=spec)

    def replay(
        self,
        waypoints: list[Waypoint],
        *,
        servo_bus: ServoBus,
        estop,
        hz: int = 30,
        max_steps_per_tick: int = 12,
    ) -> None:
        """Drive `servo_bus` through consecutive waypoint pairs.

        - 0 waypoints → no-op.
        - 1 waypoint → single `write_positions` call.
        - ≥2 waypoints → `interpolate` per consecutive pair, in order.

        Returns early if `estop.is_set()` at any check boundary.
        """
        if not waypoints:
            return
        if len(waypoints) == 1:
            servo_bus.write_positions(waypoints[0].joints)
            return
        for i in range(len(waypoints) - 1):
            if estop.is_set():
                return
            start = waypoints[i].joints
            target = waypoints[i + 1].joints
            servo_bus.interpolate(
                start, target,
                hz=hz, max_steps_per_tick=max_steps_per_tick, estop=estop,
            )
```

- [ ] **Step 4: Run — confirm pass**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest tests/unit/test_feetech_depthai_motion.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Regression**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest 2>&1 | tail -5
```

Expected: all green modulo hardware skips.

- [ ] **Step 6: Commit**

```bash
cd /home/craigm26/robot-md && git add cli/src/robot_md/backends/feetech_depthai/motion.py cli/tests/unit/test_feetech_depthai_motion.py
git commit -m "feat(backend): trajectory replay in Motion"
```

---

## Task 4: Port `perception.py` — OAK-D pipeline + frame capture

**Files:**
- Modify: `cli/src/robot_md/backends/feetech_depthai/perception.py`
- Create: `cli/tests/unit/test_feetech_depthai_perception.py`

### TDD flow

- [ ] **Step 1: Write the failing test**

File `cli/tests/unit/test_feetech_depthai_perception.py`:

```python
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec


def _spec(fixtures_dir):
    return RobotSpec.from_parsed(parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml"))


def _install_fakes(monkeypatch):
    """Stand-in for depthai + cv2 + numpy, just enough for perception tests."""
    import numpy as np

    fake_dai = MagicMock()
    # Calibration readout: return an intrinsic matrix
    fake_cal = MagicMock()
    fake_cal.getCameraIntrinsics.return_value = [
        [860.0, 0.0, 640.0],
        [0.0, 860.0, 360.0],
        [0.0, 0.0, 1.0],
    ]
    fake_cal_device = MagicMock()
    fake_cal_device.readCalibration.return_value = fake_cal
    fake_dai.Device.return_value.__enter__.return_value = fake_cal_device
    fake_dai.Device.return_value.__exit__.return_value = False
    fake_dai.CameraBoardSocket.CAM_A = "CAM_A"

    # Pipeline context manager
    fake_rgb_msg = MagicMock()
    fake_rgb_msg.getCvFrame.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
    fake_depth_msg = MagicMock()
    fake_depth_msg.getFrame.return_value = np.full((720, 1280), 400, dtype=np.uint16)

    fake_rgb_q = MagicMock()
    fake_rgb_q.get.return_value = fake_rgb_msg
    fake_depth_q = MagicMock()
    fake_depth_q.get.return_value = fake_depth_msg

    fake_pipe = MagicMock()
    fake_pipe.__enter__.return_value = fake_pipe
    fake_pipe.__exit__.return_value = False
    fake_pipe.start.return_value = None

    fake_rgb_cam = MagicMock()
    fake_rgb_cam_out = MagicMock()
    fake_rgb_cam_out.createOutputQueue.return_value = fake_rgb_q
    fake_rgb_cam.requestOutput.return_value = fake_rgb_cam_out
    fake_rgb_cam.build.return_value = fake_rgb_cam

    fake_cam_left = MagicMock()
    fake_cam_right = MagicMock()
    fake_cam_left.build.return_value = fake_cam_left
    fake_cam_right.build.return_value = fake_cam_right
    fake_cam_left_out = MagicMock()
    fake_cam_right_out = MagicMock()
    fake_cam_left.requestOutput.return_value = fake_cam_left_out
    fake_cam_right.requestOutput.return_value = fake_cam_right_out

    fake_stereo = MagicMock()
    fake_stereo_depth = MagicMock()
    fake_stereo_depth.createOutputQueue.return_value = fake_depth_q
    fake_stereo.depth = fake_stereo_depth

    # pipe.create() returns different things based on the node type requested.
    # We stub by having sequential return values: [rgb_cam, left, right, stereo]
    fake_pipe.create.side_effect = [fake_rgb_cam, fake_cam_left, fake_cam_right, fake_stereo]

    fake_dai.Pipeline.return_value = fake_pipe
    fake_dai.node = MagicMock()
    fake_dai.node.Camera = MagicMock()
    fake_dai.node.StereoDepth = MagicMock()
    fake_dai.node.StereoDepth.PresetMode.FAST_ACCURACY = "FAST_ACCURACY"
    fake_dai.ImgFrame.Type.NV12 = "NV12"

    monkeypatch.setitem(sys.modules, "depthai", fake_dai)
    return fake_dai


def test_open_reads_intrinsics(monkeypatch, fixtures_dir):
    _install_fakes(monkeypatch)
    from robot_md.backends.feetech_depthai.perception import Perception

    p = Perception.from_spec(_spec(fixtures_dir))
    p.open()
    assert p.K is not None
    assert p.K.shape == (3, 3)
    assert p.K[0, 0] == 860.0
    p.close()


def test_grab_frame_returns_rgb_depth_k(monkeypatch, fixtures_dir):
    import numpy as np
    _install_fakes(monkeypatch)
    from robot_md.backends.feetech_depthai.perception import Perception

    p = Perception.from_spec(_spec(fixtures_dir))
    p.open()
    rgb, depth, K = p.grab_frame()
    assert isinstance(rgb, np.ndarray) and rgb.shape == (720, 1280, 3)
    assert isinstance(depth, np.ndarray) and depth.shape == (720, 1280)
    assert K.shape == (3, 3)
    p.close()


def test_pixel_to_3d_math():
    """Back-projection math is deterministic; verify a known case."""
    import numpy as np
    from robot_md.backends.feetech_depthai.perception import _pixel_to_3d

    K = np.array([[860.0, 0.0, 640.0], [0.0, 860.0, 360.0], [0.0, 0.0, 1.0]])
    # Depth 500 mm at the principal point → (0, 0, 500)
    x, y, z = _pixel_to_3d(640, 360, 500.0, K)
    assert abs(x) < 1e-6 and abs(y) < 1e-6 and z == 500.0

    # 200 px right of principal point at depth 1000 → x = 200 * 1000 / 860 ≈ 232.56
    x, y, z = _pixel_to_3d(840, 360, 1000.0, K)
    assert abs(x - 200 * 1000 / 860) < 1e-3


def test_pixel_to_3d_zero_depth_is_nan():
    import math
    from robot_md.backends.feetech_depthai.perception import _pixel_to_3d
    import numpy as np
    K = np.eye(3)
    x, y, z = _pixel_to_3d(10, 10, 0.0, K)
    assert math.isnan(x) and math.isnan(y) and math.isnan(z)


def test_open_without_depthai_raises_clean_error(monkeypatch, fixtures_dir):
    monkeypatch.setitem(sys.modules, "depthai", None)
    from robot_md.backends.feetech_depthai.perception import Perception

    p = Perception.from_spec(_spec(fixtures_dir))
    with pytest.raises(RuntimeError, match="depthai"):
        p.open()
```

- [ ] **Step 2: Run — confirm failures**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest tests/unit/test_feetech_depthai_perception.py -v
```

Expected: all fail (current stub has no `open`, `K`, `grab_frame`, no `_pixel_to_3d`).

- [ ] **Step 3: Replace `perception.py` with the real implementation**

Overwrite `cli/src/robot_md/backends/feetech_depthai/perception.py`:

```python
"""OAK-D perception pipeline + 3D back-projection.

Ports the depthai usage from `examples/tier0/05_scene_snapshot.py`:
- Reads RGB intrinsics via `readCalibration()` (device temporarily opened).
- Builds a single Pipeline with RGB + stereo-depth aligned to RGB.
- Grabs one warmed-up frame pair.

Phase 1 scope: grab_frame + 3D back-projection math (`_pixel_to_3d`).
Detectors (VLM, color-blob) arrive in Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from robot_md.robot_spec import RobotSpec

if TYPE_CHECKING:
    import numpy as np  # noqa

RGB_SIZE = (1280, 720)           # width, height
DEPTH_SIZE = (640, 400)
WARMUP_FRAMES = 20


@dataclass
class Perception:
    driver_id: str
    K: Any = None                # 3×3 np.ndarray after open()
    _pipe: Any = None            # active dai.Pipeline context
    _rgb_q: Any = None
    _depth_q: Any = None
    _rgb_w: int = RGB_SIZE[0]
    _rgb_h: int = RGB_SIZE[1]

    @classmethod
    def from_spec(cls, spec: RobotSpec) -> "Perception":
        cam = next(iter(spec.physics.cameras), None)
        return cls(driver_id=cam.driver_id if cam else "none")

    def open(self) -> None:
        try:
            import depthai as dai
            import numpy as np
        except Exception as e:
            raise RuntimeError(f"depthai (or numpy) not available: {e}")

        # Read calibration first (device must be exclusive during this call).
        with dai.Device() as cal_dev:
            mat = cal_dev.readCalibration().getCameraIntrinsics(
                dai.CameraBoardSocket.CAM_A, self._rgb_w, self._rgb_h,
            )
        self.K = np.array(mat, dtype=np.float64)

        # Build the pipeline we hold open for grab_frame().
        pipe = dai.Pipeline()
        pipe.__enter__()
        try:
            rgb_cam = pipe.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
            rgb_out = rgb_cam.requestOutput(size=RGB_SIZE, type=dai.ImgFrame.Type.NV12)
            self._rgb_q = rgb_out.createOutputQueue()

            left = pipe.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
            right = pipe.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)
            left_out = left.requestOutput(size=DEPTH_SIZE, type=dai.ImgFrame.Type.NV12)
            right_out = right.requestOutput(size=DEPTH_SIZE, type=dai.ImgFrame.Type.NV12)

            stereo = pipe.create(dai.node.StereoDepth)
            stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
            stereo.setOutputSize(self._rgb_w, self._rgb_h)
            stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.FAST_ACCURACY)
            left_out.link(stereo.left)
            right_out.link(stereo.right)
            self._depth_q = stereo.depth.createOutputQueue()

            pipe.start()
            self._pipe = pipe
        except Exception:
            pipe.__exit__(None, None, None)
            raise

    def close(self) -> None:
        if self._pipe is not None:
            try:
                self._pipe.__exit__(None, None, None)
            except Exception:
                pass
        self._pipe = None
        self._rgb_q = None
        self._depth_q = None
        self.K = None

    def grab_frame(self) -> tuple[Any, Any, Any]:
        """Capture one warmed-up aligned RGB+depth pair.

        Returns (rgb_ndarray, depth_ndarray, K). depth is uint16, millimeters.
        """
        if self._rgb_q is None or self._depth_q is None:
            raise RuntimeError("Perception not open")
        rgb_frame = None
        depth_frame = None
        for _ in range(WARMUP_FRAMES):
            rgb_msg = self._rgb_q.get()
            depth_msg = self._depth_q.get()
            if rgb_msg is not None:
                rgb_frame = rgb_msg.getCvFrame()
            if depth_msg is not None:
                depth_frame = depth_msg.getFrame()
        if rgb_frame is None or depth_frame is None:
            raise RuntimeError("failed to capture frame from OAK-D")
        return rgb_frame, depth_frame, self.K


def _pixel_to_3d(u: int, v: int, depth_mm: float, K: Any) -> tuple[float, float, float]:
    """Back-project a pixel + depth into camera-frame XYZ (mm).

    Uses the standard pinhole model. Returns NaN triple when depth<=0.
    """
    if depth_mm <= 0:
        return (float("nan"), float("nan"), float("nan"))
    fx, fy = float(K[0, 0]), float(K[1, 1])
    cx, cy = float(K[0, 2]), float(K[1, 2])
    z = float(depth_mm)
    x = (u - cx) * z / fx
    y = (v - cy) * z / fy
    return (x, y, z)
```

- [ ] **Step 4: Run — confirm pass**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest tests/unit/test_feetech_depthai_perception.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Regression**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
cd /home/craigm26/robot-md && git add cli/src/robot_md/backends/feetech_depthai/perception.py cli/tests/unit/test_feetech_depthai_perception.py
git commit -m "feat(backend): real OAK-D perception pipeline + 3D back-projection"
```

---

## Task 5: Port `capabilities.py` — hardcoded pick/place + real vision/status

**Files:**
- Modify: `cli/src/robot_md/backends/feetech_depthai/capabilities.py`
- Modify: `cli/src/robot_md/backends/feetech_depthai/__init__.py` (ensure `scene_describe` uses new `Perception.grab_frame` cleanly)
- Create: `cli/tests/unit/test_feetech_depthai_capabilities.py`

### TDD flow

- [ ] **Step 1: Write the failing test**

File `cli/tests/unit/test_feetech_depthai_capabilities.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from robot_md.backends.base import ExecutionResult
from robot_md.backends.feetech_depthai.capabilities import dispatch


def _backend(capability_set=None):
    """Build a minimal backend double with the attrs capabilities.py touches."""
    class _FakeSpec:
        class metadata:
            robot_name = "test-bot"

    b = MagicMock()
    b._spec = _FakeSpec()
    b._servo_bus = MagicMock()
    b._servo_bus.read_positions.return_value = {
        "shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048,
        "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700,
    }
    b._perception = MagicMock()
    b._perception.grab_frame.return_value = (b"rgb", b"depth", None)
    b._motion = MagicMock()
    return b


def _estop():
    e = MagicMock()
    e.is_set.return_value = False
    return e


def test_unknown_capability_returns_error():
    res = dispatch(_backend(), capability="arm.throw", args={}, dry_run=False, estop=_estop())
    assert res.status == "error"
    assert res.error["reason"] == "not_implemented"


def test_arm_pick_invokes_motion_replay():
    b = _backend()
    res = dispatch(b, capability="arm.pick", args={"object": "lego"}, dry_run=False, estop=_estop())
    assert res.status == "ok"
    b._motion.replay.assert_called_once()
    _, kwargs = b._motion.replay.call_args
    assert kwargs["servo_bus"] is b._servo_bus


def test_arm_pick_dry_run_does_not_actuate():
    b = _backend()
    dispatch(b, capability="arm.pick", args={}, dry_run=True, estop=_estop())
    b._motion.replay.assert_not_called()
    b._servo_bus.torque.assert_not_called()


def test_arm_place_invokes_motion_replay():
    b = _backend()
    res = dispatch(b, capability="arm.place", args={}, dry_run=False, estop=_estop())
    assert res.status == "ok"
    b._motion.replay.assert_called_once()


def test_status_report_returns_current_positions():
    b = _backend()
    res = dispatch(b, capability="status.report", args={}, dry_run=False, estop=_estop())
    assert res.status == "ok"
    events = [e for e in res.events if e.kind == "done"]
    assert events
    assert "shoulder_pan" in events[0].data["joints"]


def test_vision_describe_grabs_a_frame():
    b = _backend()
    res = dispatch(b, capability="vision.describe", args={}, dry_run=False, estop=_estop())
    assert res.status == "ok"
    b._perception.grab_frame.assert_called_once()


def test_arm_pick_torque_on_then_off():
    """Live replay enables torque, runs motion, disables torque in a finally."""
    b = _backend()
    dispatch(b, capability="arm.pick", args={}, dry_run=False, estop=_estop())
    torque_calls = [c.args[0] for c in b._servo_bus.torque.call_args_list]
    assert torque_calls == [True, False]
```

- [ ] **Step 2: Run — confirm failures**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest tests/unit/test_feetech_depthai_capabilities.py -v
```

Expected: all fail (current handlers are stubs returning fake events).

- [ ] **Step 3: Replace `capabilities.py` with the real implementation**

Overwrite `cli/src/robot_md/backends/feetech_depthai/capabilities.py`:

```python
"""Capability dispatch: arm.pick / arm.place / arm.reach / vision.describe / status.report.

Phase 1 scope: `arm.pick` and `arm.place` replay a hardcoded first-demo
trajectory. Skill-store lookup arrives in Phase 2; perception-driven grasping
in Phase 3/4. For now these capabilities prove the wiring end-to-end.
"""

from __future__ import annotations

from robot_md.backends.base import ExecutionEvent, ExecutionResult
from robot_md.backends.feetech_depthai.motion import Waypoint


# Hardcoded first-demo waypoints. Intentionally SMALL deltas around the
# preset's zero-pose (2048 on all arm joints; gripper 1700 open / 1200 closed).
# Swap for skill-store lookup in Phase 2.
_ZERO = {
    "shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048,
    "wrist_flex": 2048, "wrist_roll": 2048,
}
_PICK_OPEN = {**_ZERO, "gripper": 1700}
_PICK_CLOSED = {**_ZERO, "gripper": 1200}
_PICK_LIFTED = {**_ZERO, "shoulder_lift": 1928, "gripper": 1200}  # 120 steps up

_HARDCODED_PICK_WAYPOINTS: list[Waypoint] = [
    Waypoint(t=0.0, joints=_PICK_OPEN),
    Waypoint(t=0.5, joints=_PICK_OPEN),      # approach
    Waypoint(t=1.1, joints=_PICK_CLOSED),    # grasp
    Waypoint(t=1.7, joints=_PICK_LIFTED),    # lift
]

_PLACE_LEFT = {**_ZERO, "shoulder_pan": 2148}  # 100 steps left-ish (depends on sign)
_PLACE_LEFT_LIFTED = {**_PLACE_LEFT, "shoulder_lift": 1928, "gripper": 1200}
_PLACE_LEFT_DOWN = {**_PLACE_LEFT, "gripper": 1200}
_PLACE_LEFT_RELEASE = {**_PLACE_LEFT, "gripper": 1700}

_HARDCODED_PLACE_WAYPOINTS: list[Waypoint] = [
    Waypoint(t=0.0, joints=_PICK_LIFTED),
    Waypoint(t=0.7, joints=_PLACE_LEFT_LIFTED),
    Waypoint(t=1.3, joints=_PLACE_LEFT_DOWN),
    Waypoint(t=1.8, joints=_PLACE_LEFT_RELEASE),
    Waypoint(t=2.4, joints=_PICK_OPEN),   # return to start-open
]


def dispatch(backend, *, capability: str, args: dict, dry_run: bool, estop) -> ExecutionResult:
    handler = _HANDLERS.get(capability)
    if handler is None:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": "not_implemented", "capability": capability},
        )
    return handler(backend, args=args, dry_run=dry_run, estop=estop)


def _do_replay(backend, *, waypoints, label: str, args, dry_run, estop) -> ExecutionResult:
    """Common pattern for arm.pick / arm.place: torque-on → replay → torque-off."""
    events: list[ExecutionEvent] = [
        ExecutionEvent(kind="plan", data={"capability": label, "args": args,
                                           "waypoint_count": len(waypoints)}),
    ]
    trajectory = [{"t": wp.t, "joints": wp.joints} for wp in waypoints]

    if dry_run:
        events.append(ExecutionEvent(kind="done", data={"dry_run": True}))
        return ExecutionResult(status="ok", trajectory=trajectory, events=events, error=None)

    # Real actuation: torque on, replay, torque off in a finally so the arm never
    # gets stuck holding torque after an error.
    bus = backend._servo_bus
    motion = backend._motion
    try:
        bus.torque(True)
        motion.replay(waypoints, servo_bus=bus, estop=estop)
    finally:
        bus.torque(False)

    events.append(ExecutionEvent(kind="done", data={"label": label}))
    return ExecutionResult(status="ok", trajectory=trajectory, events=events, error=None)


def _arm_pick(backend, *, args, dry_run, estop) -> ExecutionResult:
    return _do_replay(
        backend, waypoints=_HARDCODED_PICK_WAYPOINTS, label="arm.pick",
        args=args, dry_run=dry_run, estop=estop,
    )


def _arm_place(backend, *, args, dry_run, estop) -> ExecutionResult:
    return _do_replay(
        backend, waypoints=_HARDCODED_PLACE_WAYPOINTS, label="arm.place",
        args=args, dry_run=dry_run, estop=estop,
    )


def _arm_reach(backend, *, args, dry_run, estop) -> ExecutionResult:
    # Move to the zero-open pose. Single-waypoint trajectory.
    wps = [Waypoint(t=0.0, joints=_PICK_OPEN)]
    return _do_replay(
        backend, waypoints=wps, label="arm.reach",
        args=args, dry_run=dry_run, estop=estop,
    )


def _vision_describe(backend, *, args, dry_run, estop) -> ExecutionResult:
    if backend._perception is None:
        return ExecutionResult(
            status="error", trajectory=None, events=[],
            error={"reason": "no_perception"},
        )
    rgb, depth, K = backend._perception.grab_frame()
    rgb_shape = tuple(rgb.shape) if hasattr(rgb, "shape") else None
    depth_shape = tuple(depth.shape) if hasattr(depth, "shape") else None
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[ExecutionEvent(kind="frame", data={
            "rgb_shape": rgb_shape, "depth_shape": depth_shape,
        })],
        error=None,
    )


def _status_report(backend, *, args, dry_run, estop) -> ExecutionResult:
    robot_name = ""
    if backend._spec is not None:
        robot_name = backend._spec.metadata.robot_name
    joints = backend._servo_bus.read_positions() if backend._servo_bus is not None else {}
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[ExecutionEvent(kind="done", data={"robot": robot_name, "joints": joints})],
        error=None,
    )


_HANDLERS = {
    "arm.pick": _arm_pick,
    "arm.place": _arm_place,
    "arm.reach": _arm_reach,
    "vision.describe": _vision_describe,
    "status.report": _status_report,
}
```

- [ ] **Step 4: Wire `Motion` into the backend**

`capabilities.py` references `backend._motion`. Ensure `FeetechDepthaiBackend.open()` constructs it.

Modify `cli/src/robot_md/backends/feetech_depthai/__init__.py`. Find the `open()` method and replace with:

```python
    def open(self, spec: RobotSpec) -> None:
        from robot_md.backends.feetech_depthai.motion import Motion
        from robot_md.backends.feetech_depthai.perception import Perception
        from robot_md.backends.feetech_depthai.servo import ServoBus

        if spec.safety.max_joint_velocity_dps is None:
            raise RuntimeError(
                "feetech_depthai backend refuses to open: "
                "safety.max_joint_velocity_dps is required"
            )
        self._spec = spec
        self._servo_bus = ServoBus.from_spec(spec)
        self._servo_bus.open()
        self._motion = Motion.from_spec(spec)
        self._perception = None
        # Only open perception if a camera is declared with the depthai protocol.
        if any(d.protocol == "depthai" for d in spec.drivers):
            try:
                self._perception = Perception.from_spec(spec)
                self._perception.open()
            except Exception:
                # No camera connected — perception stays None; vision.describe
                # returns a no_perception error instead of crashing startup.
                self._perception = None
```

And replace `close()` with:

```python
    def close(self) -> None:
        if self._servo_bus is not None:
            try: self._servo_bus.close()
            except Exception: pass
        if self._perception is not None:
            try: self._perception.close()
            except Exception: pass
        self._servo_bus = None
        self._perception = None
        self._motion = None
        self._spec = None
```

Also update the `__init__` of `FeetechDepthaiBackend` to include `_motion: Any = None`:

```python
    def __init__(self) -> None:
        self._spec: RobotSpec | None = None
        self._servo_bus = None
        self._perception = None
        self._motion = None
```

- [ ] **Step 5: Run — confirm pass**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest tests/unit/test_feetech_depthai_capabilities.py -v
```

Expected: 7 PASS.

- [ ] **Step 6: Regression — earlier tests that constructed the backend directly**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest 2>&1 | tail -10
```

Expected: all green modulo hardware skips. `test_feetech_depthai_safety.py::test_opens_with_max_joint_velocity` may now try to actually open a servo port during `backend.open(spec)` — because ServoBus.open() now does real I/O. Two ways to handle:

Either (a) the test already monkeypatches the SDK (verify — the test file was written in T16 of v0.3.0; check if it uses a fake), OR (b) update the test to monkeypatch `feetech_servo_sdk` the same way as `test_feetech_depthai_servo.py` does. Pick (b) if the test hits a real port and fails.

If a new monkeypatch is needed, add this helper to `test_feetech_depthai_safety.py` and call it before `backend.open(spec)`:

```python
from unittest.mock import MagicMock
import sys

def _install_fake_feetech(monkeypatch):
    fake = MagicMock()
    fp = MagicMock(); fp.openPort.return_value = True; fp.setBaudRate.return_value = True
    fake.PortHandler.return_value = fp
    fake.PacketHandler.return_value = MagicMock()
    monkeypatch.setitem(sys.modules, "feetech_servo_sdk", fake)
```

Document any test-file mutations as part of this commit.

- [ ] **Step 7: Commit**

```bash
cd /home/craigm26/robot-md && git add cli/src/robot_md/backends/feetech_depthai/ cli/tests/unit/test_feetech_depthai_capabilities.py
# If the safety test needed a monkeypatch helper, include it:
git add -u cli/tests/unit/test_feetech_depthai_safety.py
git commit -m "feat(backend): real capability dispatch with hardcoded pick/place demo"
```

---

## Task 6: Hardware smoke — teach/replay roundtrip

**Files:**
- Create: `cli/tests/hardware/test_teach_replay_roundtrip.py`

### TDD flow

- [ ] **Step 1: Write the hardware test**

File `cli/tests/hardware/test_teach_replay_roundtrip.py`:

```python
"""Bob hardware smoke: open ServoBus against /dev/ttyACM0, read all 6 servos,
do a tiny ±1-step wiggle on shoulder_pan, verify positions returned to start.

Gated by `--run-hardware`. Skipped otherwise."""

from __future__ import annotations

import os
import time

import pytest

pytestmark = pytest.mark.hardware

pytest.importorskip("feetech_servo_sdk")


class _NoopEstop:
    def is_set(self): return False


def _bus():
    from robot_md.backends.feetech_depthai.servo import ServoBus
    return ServoBus(port="/dev/ttyACM0", baud=1_000_000, count=6)


def test_read_all_six_servos():
    if not os.path.exists("/dev/ttyACM0"):
        pytest.skip("no /dev/ttyACM0")
    bus = _bus()
    bus.open()
    try:
        positions = bus.read_positions()
        assert len(positions) == 6, f"expected 6 responders, got {positions}"
    finally:
        bus.close()


def test_shoulder_pan_one_step_wiggle():
    """Nudges shoulder_pan ±1 step. Operator should see no visible motion but
    the bus should accept the writes without error."""
    if not os.path.exists("/dev/ttyACM0"):
        pytest.skip("no /dev/ttyACM0")
    bus = _bus()
    bus.open()
    try:
        start = bus.read_positions()
        assert "shoulder_pan" in start
        sp = start["shoulder_pan"]
        bus.torque(True)
        try:
            target = dict(start)
            target["shoulder_pan"] = sp + 1
            bus.interpolate(start, target, hz=30, max_steps_per_tick=1, estop=_NoopEstop())
            time.sleep(0.1)
            bus.interpolate(target, start, hz=30, max_steps_per_tick=1, estop=_NoopEstop())
            time.sleep(0.1)
        finally:
            bus.torque(False)
        end = bus.read_positions()
        assert abs(end["shoulder_pan"] - sp) <= 2   # 1-step nudge, tolerance 2 steps
    finally:
        bus.close()


def test_depthai_frame_capture():
    """Grab one aligned RGB+depth frame from the connected OAK-D."""
    pytest.importorskip("depthai")
    from robot_md.backends.feetech_depthai.perception import Perception
    from robot_md.parser import parse_file
    from robot_md.robot_spec import RobotSpec

    fixtures = os.path.join(os.path.dirname(__file__), "..", "fixtures")
    parsed = parse_file(os.path.join(fixtures, "robot_md_oak_d_factory_cal.yaml"))
    spec = RobotSpec.from_parsed(parsed)

    p = Perception.from_spec(spec)
    try:
        p.open()
    except RuntimeError as e:
        pytest.skip(f"depthai device not available: {e}")
    try:
        rgb, depth, K = p.grab_frame()
        assert rgb is not None and depth is not None
        assert K is not None and K.shape == (3, 3)
    finally:
        p.close()
```

- [ ] **Step 2: Verify tests skip by default**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest tests/hardware/test_teach_replay_roundtrip.py -v
```

Expected: 3 SKIPPED with "hardware tests require --run-hardware".

- [ ] **Step 3: Verify tests run (but may hardware-skip) with the flag**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest tests/hardware/test_teach_replay_roundtrip.py --run-hardware -v
```

On a dev box without Bob connected: all 3 inner-skipped with "no /dev/ttyACM0" / "depthai device not available". On Bob: all 3 pass.

- [ ] **Step 4: Commit**

```bash
cd /home/craigm26/robot-md && git add cli/tests/hardware/test_teach_replay_roundtrip.py
git commit -m "test(hardware): teach/replay roundtrip smoke for servo + OAK-D"
```

---

## Task 7: Release — v0.4.0 CHANGELOG + version bump

**Files:**
- Modify: `cli/pyproject.toml`
- Modify: `cli/src/robot_md/__init__.py`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Bump versions**

`cli/pyproject.toml`:
```toml
version = "0.4.0"
```

`cli/src/robot_md/__init__.py`:
```python
__version__ = "0.4.0"
```

- [ ] **Step 2: CHANGELOG entry**

Prepend to `CHANGELOG.md`, above the v0.3.1 entry:

```markdown
## [0.4.0] - 2026-04-18

Phase 1 of the adaptive backend plan (spec:
`docs/superpowers/specs/2026-04-18-feetech-depthai-real-backend-design.md`).
The `feetech_depthai` backend goes from stubs to real hardware drivers.

### Added

- **Real STS3215 wire protocol** in `backends/feetech_depthai/servo.py` —
  ports the proven code from `examples/tier0/01..04`. ServoBus supports
  `open/close`, `read_positions` (skips non-responders), `write_positions`,
  `torque(on/off)`, and `interpolate(start, target, hz, max_steps_per_tick,
  estop)` with per-tick E-stop checks.
- **Real OAK-D pipeline** in `backends/feetech_depthai/perception.py` —
  ports `examples/tier0/05_scene_snapshot.py`. Reads factory intrinsics,
  builds an RGB + stereo-depth pipeline aligned to RGB, exposes
  `grab_frame() → (rgb, depth, K)`. 3D back-projection helper `_pixel_to_3d`.
- **Trajectory replay** in `backends/feetech_depthai/motion.py` — iterates
  consecutive waypoint pairs, calling `ServoBus.interpolate` between them.
  Single-waypoint trajectories dispatch as one-shot position commands.
- **Real capability handlers** for `arm.pick`, `arm.place`, `arm.reach`,
  `vision.describe`, `status.report`. `arm.pick` / `arm.place` replay a
  hardcoded first-demo trajectory (small joint deltas around zero pose) —
  swapped for skill-store lookup in Phase 2.
- **Hardware smoke tests** (`--run-hardware`) for servo read + nudge and
  OAK-D frame capture.

### Added dependency

- `feetech-servo-sdk>=1.0` joins the `feetech-depthai` optional extra.
  Install with `pip install robot-md[feetech-depthai]`.

### Scope note

`arm.pick`/`arm.place` in v0.4.0 replay a hardcoded trajectory embedded in
the capability handler. Real grasps arrive in v0.5.0 (Phase 2 — skill store).
Perception is opened but not yet consulted during motion (Phase 3);
pose-adjust and hand-eye are Phase 4. See the spec for the full rollout.

---
```

- [ ] **Step 3: Final regression + build sanity**

```bash
cd /home/craigm26/robot-md/cli && /home/craigm26/opencastor/venv/bin/python3 -m pytest 2>&1 | tail -5
cd /home/craigm26/robot-md/cli && rm -rf dist/ && /home/craigm26/opencastor/venv/bin/python3 -m build 2>&1 | tail -4
```

Expected: test summary ends with `passed` line; build emits `robot_md-0.4.0.tar.gz` and `robot_md-0.4.0-py3-none-any.whl`.

- [ ] **Step 4: Commit**

```bash
cd /home/craigm26/robot-md && git add CHANGELOG.md cli/pyproject.toml cli/src/robot_md/__init__.py
git commit -m "chore(release): v0.4.0 — real feetech_depthai backend"
```

---

## Self-review

**Spec coverage:**

| Spec §Phase 1 item | Covered by |
|---|---|
| Port `examples/tier0/*` into `servo.py` | Task 2 |
| Port tier0 depthai pipeline into `perception.py` | Task 4 |
| Port `_interpolate` helper into motion | Task 2 (into `ServoBus.interpolate`) + Task 3 (`Motion.replay` drives it) |
| Capability handlers call real code | Task 5 |
| Hardcoded first-demo trajectory | Task 5 (`_HARDCODED_PICK_WAYPOINTS` / `_HARDCODED_PLACE_WAYPOINTS`) |
| Safety: torque clamp, estop propagation | Task 2 (interpolate checks estop) + Task 5 (torque-on/off in `_do_replay` finally) |
| Hardware tests gated by --run-hardware | Task 6 |
| v0.4.0 version bump + CHANGELOG | Task 7 |

Phases 2-5 are **explicitly out of scope** per spec and this plan.

**Placeholder scan:** no TBDs/TODOs in plan steps. One deliberate note in Task 5 Step 6 about potentially monkeypatching `test_feetech_depthai_safety.py` depending on how it constructs its fake; the plan gives the fallback snippet if needed.

**Type consistency:** `Waypoint` introduced in Task 3 (motion.py) is imported in Task 5 (capabilities.py) — same module, same dataclass. `ServoBus.interpolate` signature `(start, target, *, hz, max_steps_per_tick, estop)` matches across Task 2 impl, Task 3 Motion.replay call, and Task 6 hardware test. `_pixel_to_3d` signature `(u, v, depth_mm, K)` consistent in Task 4 impl + test.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-18-p1-feetech-depthai-real-backend.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?

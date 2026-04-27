# SP6 — Spatial Intelligence Eval Implementation Plan (Phase 0 / v1.0.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Phase 0 of SP6 — a two-track (probe + execute) spatial-intelligence eval inside the existing `robot-md mcp` server, with 5 testable units (O1-O3, A1-A2), self-attested RCAN-signed Score JSON, and the cheap no-fiducial fixture kit specified in `2026-04-26-sp6-spatial-intelligence-eval-design.md`.

**Architecture:** Add a new `robot_md.spatial_eval` package for core eval logic and 9 thin MCP tool wrappers under `robot_md.mcp.tools.spatial_eval/`. Reuse existing `robot_md.detectors.hsv`, the apikey/RCAN infrastructure, and the `McpContext` pattern. One MCP server (per SP1-SP5 Rev 1). Phase 1 (RRF §27) is a separate plan; this plan ships Phase 0 only with a stub for the submit tool.

**Tech Stack:** Python 3.10+, pytest, FastMCP (`mcp.server.fastmcp`), OpenCV (`cv2`), NumPy, Anthropic SDK, existing `jsonschema` validation, existing RCAN signing helpers.

**Spec:** `docs/superpowers/specs/2026-04-26-sp6-spatial-intelligence-eval-design.md`

---

## File Structure

**New package — core eval logic (MCP-independent, unit-testable):**
- `cli/src/robot_md/spatial_eval/__init__.py`
- `cli/src/robot_md/spatial_eval/score.py` — Score JSON dataclass + serializer
- `cli/src/robot_md/spatial_eval/units/__init__.py` — Unit registry
- `cli/src/robot_md/spatial_eval/units/base.py` — Unit protocol
- `cli/src/robot_md/spatial_eval/units/o1_permanence.py`
- `cli/src/robot_md/spatial_eval/units/o2_container.py`
- `cli/src/robot_md/spatial_eval/units/o3_partial_view.py`
- `cli/src/robot_md/spatial_eval/units/a1_grasp.py`
- `cli/src/robot_md/spatial_eval/units/a2_stability.py`
- `cli/src/robot_md/spatial_eval/probe/__init__.py`
- `cli/src/robot_md/spatial_eval/probe/scorer.py` — per-unit scoring dispatch
- `cli/src/robot_md/spatial_eval/probe/stacks.py` — `baseline_claude`, `robot_declared` resolver
- `cli/src/robot_md/spatial_eval/probe/runner.py` — runs N probes through both stacks
- `cli/src/robot_md/spatial_eval/probe/datasets/public/{O1,O2,O3,A1,A2}/*.json`
- `cli/src/robot_md/spatial_eval/execute/__init__.py`
- `cli/src/robot_md/spatial_eval/execute/judge.py` — color seg + frame diff
- `cli/src/robot_md/spatial_eval/execute/manual_gate.py` — flag for human review
- `cli/src/robot_md/spatial_eval/execute/trial.py` — per-trial state machine
- `cli/src/robot_md/spatial_eval/execute/evidence.py` — bundle + sign packet
- `cli/src/robot_md/spatial_eval/execute/fixtures/kit_v1.md` — BOM doc
- `cli/src/robot_md/spatial_eval/execute/fixtures/grid_mat.pdf` — printable
- `cli/src/robot_md/spatial_eval/rrf.py` — Phase 1 stub (raises NotImplementedError)

**New package — MCP tool wrappers (thin):**
- `cli/src/robot_md/mcp/tools/spatial_eval/__init__.py`
- `cli/src/robot_md/mcp/tools/spatial_eval/dry_run.py`
- `cli/src/robot_md/mcp/tools/spatial_eval/init.py`
- `cli/src/robot_md/mcp/tools/spatial_eval/kit.py`
- `cli/src/robot_md/mcp/tools/spatial_eval/run_probe.py`
- `cli/src/robot_md/mcp/tools/spatial_eval/run_execute.py`
- `cli/src/robot_md/mcp/tools/spatial_eval/run_full.py`
- `cli/src/robot_md/mcp/tools/spatial_eval/replay.py`
- `cli/src/robot_md/mcp/tools/spatial_eval/verify.py`
- `cli/src/robot_md/mcp/tools/spatial_eval/submit_to_rrf.py`

**Modified files:**
- `schema/robot-md.schema.json` — add `spatial-eval:` object schema
- `cli/src/robot_md/mcp/server.py` — register the 9 new tools
- `cli/pyproject.toml` — add `[spatial-eval]` extra (or absorb into `[hardware]` after audit)

**New tests:**
- `cli/tests/spatial_eval/__init__.py`
- `cli/tests/spatial_eval/conftest.py` — fixtures (sample probes, mock stacks, sample frames)
- `cli/tests/spatial_eval/test_schema.py`
- `cli/tests/spatial_eval/test_score.py`
- `cli/tests/spatial_eval/test_units_<unit>.py` × 5
- `cli/tests/spatial_eval/test_scorer_<unit>.py` × 5
- `cli/tests/spatial_eval/test_probe_stacks.py`
- `cli/tests/spatial_eval/test_probe_runner.py`
- `cli/tests/spatial_eval/test_execute_judge.py`
- `cli/tests/spatial_eval/test_execute_trial.py`
- `cli/tests/spatial_eval/test_evidence.py`
- `cli/tests/spatial_eval/test_mcp_<tool>.py` × 9

---

## Cross-Task Conventions

- **TDD:** Every code-bearing task has `failing test → impl → passing test → commit`.
- **Test layout:** All tests live under `cli/tests/spatial_eval/`. Import paths use `robot_md.spatial_eval.*`.
- **Run tests** from `cli/` directory: `pytest tests/spatial_eval/test_<file>.py::<test_name> -v`.
- **Commit format:** `feat(spatial-eval): <what>` for code, `test(spatial-eval): <what>` for test-only commits, `docs(spatial-eval): <what>` for docs/schema-only changes.
- **No exception swallowing.** Errors propagate unless the spec calls them out (Anthropic API retries, manual-gate fallbacks).
- **`from __future__ import annotations`** at the top of every new module (matches existing repo style).

---

## Task 1 — Schema: `spatial-eval:` section in `robot-md.schema.json`

**Files:**
- Modify: `schema/robot-md.schema.json`
- Test: `cli/tests/spatial_eval/test_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_schema.py
from __future__ import annotations
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, ValidationError

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "schema/robot-md.schema.json").read_text())

VALID_MIN = {
    "robot-md": "1.0.0", "id": "x", "kind": "test",
    "spatial-eval": {
        "spec_version": "1.0.0",
        "units": ["O1", "O2", "O3", "A1", "A2"],
        "workspace": {
            "play_surface_dims_m": [0.30, 0.30],
            "judge_camera": {"device": "phone:tripod", "resolution": [1920, 1080]},
        },
        "reasoning_stack": {
            "baseline": "claude:claude-opus-4-7",
            "declared": "claude:claude-opus-4-7",
        },
    },
}

def test_spatial_eval_section_validates():
    Draft202012Validator(SCHEMA).validate(VALID_MIN)

def test_spatial_eval_rejects_non_claude_stack_in_v1():
    bad = json.loads(json.dumps(VALID_MIN))
    bad["spatial-eval"]["reasoning_stack"]["declared"] = "vla:my-endpoint"
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(bad)

def test_spatial_eval_rejects_unknown_unit():
    bad = json.loads(json.dumps(VALID_MIN))
    bad["spatial-eval"]["units"] = ["O1", "X9"]
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(bad)

def test_spatial_eval_section_is_optional():
    no_eval = {"robot-md": "1.0.0", "id": "x", "kind": "test"}
    Draft202012Validator(SCHEMA).validate(no_eval)
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd cli && pytest tests/spatial_eval/test_schema.py -v
```

Expected: 3 of 4 tests fail (the optional-section test passes accidentally because schema doesn't define the section yet).

- [ ] **Step 3: Add `spatial-eval` to `schema/robot-md.schema.json`**

In the top-level `properties` object, add (sibling of existing `id`, `kind`, etc.):

```json
"spatial-eval": {
  "type": "object",
  "additionalProperties": false,
  "required": ["spec_version", "units", "workspace", "reasoning_stack"],
  "properties": {
    "spec_version": {"type": "string", "pattern": "^1\\.[0-9]+\\.[0-9]+$"},
    "units": {
      "type": "array",
      "items": {"enum": ["O1", "O2", "O3", "A1", "A2"]},
      "uniqueItems": true,
      "minItems": 1
    },
    "workspace": {
      "type": "object",
      "additionalProperties": false,
      "required": ["play_surface_dims_m", "judge_camera"],
      "properties": {
        "play_surface_dims_m": {
          "type": "array", "items": {"type": "number", "minimum": 0.05},
          "minItems": 2, "maxItems": 2
        },
        "judge_camera": {
          "type": "object",
          "additionalProperties": false,
          "required": ["device", "resolution"],
          "properties": {
            "device": {"type": "string", "minLength": 1},
            "resolution": {
              "type": "array", "items": {"type": "integer", "minimum": 1},
              "minItems": 2, "maxItems": 2
            }
          }
        }
      }
    },
    "reasoning_stack": {
      "type": "object",
      "additionalProperties": false,
      "required": ["baseline", "declared"],
      "properties": {
        "baseline": {"type": "string", "pattern": "^claude:.+"},
        "declared": {"type": "string", "pattern": "^claude:.+"}
      }
    }
  }
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```
cd cli && pytest tests/spatial_eval/test_schema.py -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/robot-md
git add schema/robot-md.schema.json cli/tests/spatial_eval/test_schema.py
git commit -m "feat(spatial-eval): add spatial-eval ROBOT.md schema (SP6 v1.0.0)"
```

---

## Task 2 — Score JSON dataclass + serializer

**Files:**
- Create: `cli/src/robot_md/spatial_eval/__init__.py` (empty)
- Create: `cli/src/robot_md/spatial_eval/score.py`
- Create: `cli/tests/spatial_eval/__init__.py` (empty)
- Create: `cli/tests/spatial_eval/test_score.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_score.py
from __future__ import annotations
import json
from robot_md.spatial_eval.score import (
    PerUnitProbeScore, PerUnitExecuteScore, ProbeTrack, ExecuteTrack,
    Aggregate, ScoreJSON,
)

def test_score_json_round_trips():
    s = ScoreJSON(
        spec_version="1.0.0",
        rrn="RRN-000000000002",
        run_id="abc",
        timestamp="2026-04-26T14:30:00Z",
        tracks_probe=ProbeTrack(
            baseline_claude={"O1": PerUnitProbeScore(score=0.87, n=30, passed=26)},
            robot_declared={"O1": PerUnitProbeScore(score=0.84, n=30, passed=25)},
            delta_per_unit={"O1": -0.03},
        ),
        tracks_execute={
            "O1": PerUnitExecuteScore(passed=7, n=10, evidence_sha256="abc..."),
        },
        aggregate=Aggregate(probe_baseline=0.87, probe_declared=0.84, execute=0.7),
        rcan_signature=None,  # added later by signer
        evidence_root=None,
    )
    blob = s.to_json()
    parsed = json.loads(blob)
    assert parsed["spec_version"] == "1.0.0"
    assert parsed["tracks"]["probe"]["delta_per_unit"]["O1"] == -0.03
    s2 = ScoreJSON.from_json(blob)
    assert s2 == s

def test_aggregate_recomputes_from_per_unit():
    pt = ProbeTrack(
        baseline_claude={
            "O1": PerUnitProbeScore(0.8, 30, 24),
            "O2": PerUnitProbeScore(0.6, 30, 18),
        },
        robot_declared={
            "O1": PerUnitProbeScore(0.8, 30, 24),
            "O2": PerUnitProbeScore(0.6, 30, 18),
        },
        delta_per_unit={"O1": 0.0, "O2": 0.0},
    )
    et = {"O1": PerUnitExecuteScore(7, 10, "x")}
    agg = Aggregate.compute(probe=pt, execute=et)
    assert agg.probe_baseline == 0.7  # mean of 0.8, 0.6
    assert agg.execute == 0.7
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd cli && pytest tests/spatial_eval/test_score.py -v
```

Expected: ImportError — module does not exist yet.

- [ ] **Step 3: Implement `score.py`**

```python
# cli/src/robot_md/spatial_eval/score.py
from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass(frozen=True)
class PerUnitProbeScore:
    score: float
    n: int
    passed: int


@dataclass(frozen=True)
class PerUnitExecuteScore:
    passed: int
    n: int
    evidence_sha256: str


@dataclass(frozen=True)
class ProbeTrack:
    baseline_claude: dict[str, PerUnitProbeScore]
    robot_declared: dict[str, PerUnitProbeScore]
    delta_per_unit: dict[str, float]


ExecuteTrack = dict[str, PerUnitExecuteScore]


@dataclass(frozen=True)
class Aggregate:
    probe_baseline: float
    probe_declared: float
    execute: float

    @classmethod
    def compute(cls, *, probe: ProbeTrack, execute: ExecuteTrack) -> "Aggregate":
        def _mean(d: dict[str, PerUnitProbeScore]) -> float:
            return sum(v.score for v in d.values()) / max(1, len(d))
        ex_mean = (
            sum(v.passed / max(1, v.n) for v in execute.values()) / max(1, len(execute))
            if execute else 0.0
        )
        return cls(
            probe_baseline=_mean(probe.baseline_claude),
            probe_declared=_mean(probe.robot_declared),
            execute=ex_mean,
        )


@dataclass
class ScoreJSON:
    spec_version: str
    rrn: str
    run_id: str
    timestamp: str
    tracks_probe: ProbeTrack
    tracks_execute: ExecuteTrack
    aggregate: Aggregate
    rcan_signature: Optional[str] = None
    evidence_root: Optional[str] = None

    def to_dict(self) -> dict:
        def _dump_unit_map(m: dict) -> dict:
            return {k: asdict(v) for k, v in m.items()}
        return {
            "spec_version": self.spec_version,
            "rrn": self.rrn,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "tracks": {
                "probe": {
                    "baseline_claude": _dump_unit_map(self.tracks_probe.baseline_claude),
                    "robot_declared": _dump_unit_map(self.tracks_probe.robot_declared),
                    "delta_per_unit": dict(self.tracks_probe.delta_per_unit),
                },
                "execute": _dump_unit_map(self.tracks_execute),
            },
            "aggregate": asdict(self.aggregate),
            "rcan_signature": self.rcan_signature,
            "evidence_root": self.evidence_root,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, blob: str) -> "ScoreJSON":
        d = json.loads(blob)
        def _load_probe(m: dict) -> dict[str, PerUnitProbeScore]:
            return {k: PerUnitProbeScore(**v) for k, v in m.items()}
        def _load_exec(m: dict) -> dict[str, PerUnitExecuteScore]:
            return {k: PerUnitExecuteScore(**v) for k, v in m.items()}
        return cls(
            spec_version=d["spec_version"],
            rrn=d["rrn"],
            run_id=d["run_id"],
            timestamp=d["timestamp"],
            tracks_probe=ProbeTrack(
                baseline_claude=_load_probe(d["tracks"]["probe"]["baseline_claude"]),
                robot_declared=_load_probe(d["tracks"]["probe"]["robot_declared"]),
                delta_per_unit=dict(d["tracks"]["probe"]["delta_per_unit"]),
            ),
            tracks_execute=_load_exec(d["tracks"]["execute"]),
            aggregate=Aggregate(**d["aggregate"]),
            rcan_signature=d.get("rcan_signature"),
            evidence_root=d.get("evidence_root"),
        )
```

Also create empty `cli/src/robot_md/spatial_eval/__init__.py` and `cli/tests/spatial_eval/__init__.py`.

- [ ] **Step 4: Run tests to confirm they pass**

```
cd cli && pytest tests/spatial_eval/test_score.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/__init__.py cli/src/robot_md/spatial_eval/score.py \
        cli/tests/spatial_eval/__init__.py cli/tests/spatial_eval/test_score.py
git commit -m "feat(spatial-eval): Score JSON dataclass + round-trip + aggregate"
```

---

## Task 3 — Unit base protocol + registry

**Files:**
- Create: `cli/src/robot_md/spatial_eval/units/__init__.py`
- Create: `cli/src/robot_md/spatial_eval/units/base.py`
- Create: `cli/tests/spatial_eval/test_units_base.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_units_base.py
from __future__ import annotations
from robot_md.spatial_eval.units import REGISTRY, get_unit
from robot_md.spatial_eval.units.base import Unit, ProbeAnswer

def test_registry_lists_all_five_v1_units(monkeypatch):
    # Force import of all five so they self-register.
    import robot_md.spatial_eval.units.o1_permanence  # noqa: F401
    import robot_md.spatial_eval.units.o2_container  # noqa: F401
    import robot_md.spatial_eval.units.o3_partial_view  # noqa: F401
    import robot_md.spatial_eval.units.a1_grasp  # noqa: F401
    import robot_md.spatial_eval.units.a2_stability  # noqa: F401
    assert sorted(REGISTRY.keys()) == ["A1", "A2", "O1", "O2", "O3"]

def test_get_unit_raises_on_unknown():
    import pytest
    with pytest.raises(KeyError):
        get_unit("Z9")
```

- [ ] **Step 2: Run tests to confirm they fail**

Expected: ImportError.

- [ ] **Step 3: Implement base + registry**

```python
# cli/src/robot_md/spatial_eval/units/__init__.py
from __future__ import annotations
from robot_md.spatial_eval.units.base import REGISTRY, get_unit, register

__all__ = ["REGISTRY", "get_unit", "register"]
```

```python
# cli/src/robot_md/spatial_eval/units/base.py
from __future__ import annotations
from typing import Any, Protocol


class Unit(Protocol):
    """Protocol every unit module satisfies via module-level attributes."""

    code: str            # e.g., "O1"
    description: str     # human-readable summary

    @staticmethod
    def parse_answer(raw: dict) -> "ProbeAnswer": ...

    @staticmethod
    def execute_pass(trial_outcome: dict) -> tuple[bool, str]: ...


class ProbeAnswer(dict):
    """Marker subclass; canonical shape is unit-specific."""


REGISTRY: dict[str, Any] = {}


def register(unit_module: Any) -> Any:
    """Decorator-or-call to register a unit module by its `.code` attribute."""
    code = getattr(unit_module, "code")
    REGISTRY[code] = unit_module
    return unit_module


def get_unit(code: str) -> Any:
    return REGISTRY[code]
```

- [ ] **Step 4: Run tests to confirm they pass**

```
cd cli && pytest tests/spatial_eval/test_units_base.py -v
```

Expected: first test fails with ImportError on the unit modules (not yet created — that's Task 4); second passes.

- [ ] **Step 5: Defer the registry-population test**

Mark `test_registry_lists_all_five_v1_units` with `pytest.skip("populated by Tasks 4-8")` for now. Re-enable in Task 8.

```python
import pytest

@pytest.mark.skip(reason="populated by Tasks 4-8 (one unit per task)")
def test_registry_lists_all_five_v1_units():
    ...
```

- [ ] **Step 6: Run tests, then commit**

```
cd cli && pytest tests/spatial_eval/test_units_base.py -v
git add cli/src/robot_md/spatial_eval/units/__init__.py \
        cli/src/robot_md/spatial_eval/units/base.py \
        cli/tests/spatial_eval/test_units_base.py
git commit -m "feat(spatial-eval): unit Protocol + REGISTRY"
```

---

## Tasks 4-8 — Five unit modules (O1, O2, O3, A1, A2)

Each task follows the same structure: write the unit module, write its tests, register itself in REGISTRY at import time. Code differs per unit. Each task ends with a commit.

### Task 4 — O1 unit (object permanence)

**Files:**
- Create: `cli/src/robot_md/spatial_eval/units/o1_permanence.py`
- Create: `cli/tests/spatial_eval/test_units_o1.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_units_o1.py
from __future__ import annotations
import pytest
from robot_md.spatial_eval.units.o1_permanence import O1, parse_answer, execute_pass

def test_o1_code_and_description():
    assert O1.code == "O1"
    assert "permanence" in O1.description.lower()

def test_o1_parse_answer_well_formed():
    raw = {"still_present": True, "position": [0.1, 0.05, 0.0]}
    a = parse_answer(raw)
    assert a == {"still_present": True, "position": (0.1, 0.05, 0.0)}

def test_o1_parse_answer_rejects_missing_position():
    with pytest.raises(ValueError, match="position"):
        parse_answer({"still_present": True})

def test_o1_execute_pass_true_when_retrieved_no_disturb():
    outcome = {"target_retrieved": True, "occluder_disturbance_pct": 1.5}
    ok, _ = execute_pass(outcome)
    assert ok is True

def test_o1_execute_pass_false_when_occluder_disturbed():
    outcome = {"target_retrieved": True, "occluder_disturbance_pct": 12.0}
    ok, reason = execute_pass(outcome)
    assert ok is False
    assert "occluder" in reason.lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

Expected: ImportError.

- [ ] **Step 3: Implement the unit**

```python
# cli/src/robot_md/spatial_eval/units/o1_permanence.py
from __future__ import annotations
from typing import Any
from robot_md.spatial_eval.units.base import register

code = "O1"
description = "Object permanence — target visible at t=0, occluder slides over, robot answers presence + position."

OCCLUDER_DISTURB_THRESHOLD_PCT = 5.0


def parse_answer(raw: dict) -> dict:
    if "still_present" not in raw or "position" not in raw:
        raise ValueError("O1 answer requires 'still_present' and 'position'")
    pos = raw["position"]
    if not (isinstance(pos, (list, tuple)) and len(pos) == 3):
        raise ValueError("O1 position must be [x, y, z]")
    return {"still_present": bool(raw["still_present"]), "position": tuple(float(v) for v in pos)}


def execute_pass(outcome: dict) -> tuple[bool, str]:
    if not outcome.get("target_retrieved"):
        return False, "target not retrieved within timeout"
    if outcome.get("occluder_disturbance_pct", 0.0) > OCCLUDER_DISTURB_THRESHOLD_PCT:
        return False, f"occluder disturbance > {OCCLUDER_DISTURB_THRESHOLD_PCT}%"
    return True, "ok"


class O1:
    code = code
    description = description
    parse_answer = staticmethod(parse_answer)
    execute_pass = staticmethod(execute_pass)


register(O1)
```

- [ ] **Step 4: Run tests to confirm they pass**

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/units/o1_permanence.py cli/tests/spatial_eval/test_units_o1.py
git commit -m "feat(spatial-eval): O1 (object permanence) unit"
```

### Task 5 — O2 unit (container reasoning)

**Files:**
- Create: `cli/src/robot_md/spatial_eval/units/o2_container.py`
- Create: `cli/tests/spatial_eval/test_units_o2.py`

- [ ] **Step 1: Write tests**

```python
# cli/tests/spatial_eval/test_units_o2.py
from __future__ import annotations
import pytest
from robot_md.spatial_eval.units.o2_container import O2, parse_answer, execute_pass

def test_o2_parse_answer():
    a = parse_answer({"container": "green_cup", "contained": "red_cube"})
    assert a == {"container": "green_cup", "contained": "red_cube"}

def test_o2_rejects_missing_keys():
    with pytest.raises(ValueError):
        parse_answer({"container": "green_cup"})

def test_o2_execute_pass():
    ok, _ = execute_pass({"correct_container": True, "target_lifted_cm": 7.0})
    assert ok is True

def test_o2_execute_fails_wrong_container():
    ok, r = execute_pass({"correct_container": False, "target_lifted_cm": 7.0})
    assert ok is False
    assert "container" in r.lower()

def test_o2_execute_fails_no_lift():
    ok, r = execute_pass({"correct_container": True, "target_lifted_cm": 1.0})
    assert ok is False
    assert "lift" in r.lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/units/o2_container.py
from __future__ import annotations
from robot_md.spatial_eval.units.base import register

code = "O2"
description = "Container reasoning — target hidden under/inside a known container; recover relationship and act."

LIFT_MIN_CM = 5.0


def parse_answer(raw: dict) -> dict:
    for k in ("container", "contained"):
        if k not in raw:
            raise ValueError(f"O2 answer requires '{k}'")
    return {"container": str(raw["container"]), "contained": str(raw["contained"])}


def execute_pass(outcome: dict) -> tuple[bool, str]:
    if not outcome.get("correct_container"):
        return False, "wrong container visited"
    if outcome.get("target_lifted_cm", 0.0) < LIFT_MIN_CM:
        return False, f"target not lifted >= {LIFT_MIN_CM} cm"
    return True, "ok"


class O2:
    code = code
    description = description
    parse_answer = staticmethod(parse_answer)
    execute_pass = staticmethod(execute_pass)


register(O2)
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/units/o2_container.py cli/tests/spatial_eval/test_units_o2.py
git commit -m "feat(spatial-eval): O2 (container reasoning) unit"
```

### Task 6 — O3 unit (partial-view shape inference)

**Files:**
- Create: `cli/src/robot_md/spatial_eval/units/o3_partial_view.py`
- Create: `cli/tests/spatial_eval/test_units_o3.py`

- [ ] **Step 1: Write tests**

```python
# cli/tests/spatial_eval/test_units_o3.py
from __future__ import annotations
import pytest
from robot_md.spatial_eval.units.o3_partial_view import O3, parse_answer, execute_pass

def test_o3_parse_answer_8_corners():
    raw = {"bbox_corners": [[0,0,0],[1,0,0],[0,1,0],[1,1,0],[0,0,1],[1,0,1],[0,1,1],[1,1,1]]}
    a = parse_answer(raw)
    assert len(a["bbox_corners"]) == 8

def test_o3_rejects_wrong_corner_count():
    with pytest.raises(ValueError):
        parse_answer({"bbox_corners": [[0,0,0]]})

def test_o3_execute_pass():
    ok, _ = execute_pass({"target_lifted_cm": 6.0, "occluder_disturbance_pct": 2.0})
    assert ok is True

def test_o3_execute_fails_disturbance():
    ok, r = execute_pass({"target_lifted_cm": 6.0, "occluder_disturbance_pct": 7.0})
    assert ok is False
    assert "disturb" in r.lower()
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/units/o3_partial_view.py
from __future__ import annotations
from robot_md.spatial_eval.units.base import register

code = "O3"
description = "Partial-view shape inference — target partly hidden; infer full extent for safe grasp."

LIFT_MIN_CM = 5.0
OCCLUDER_DISTURB_THRESHOLD_PCT = 5.0


def parse_answer(raw: dict) -> dict:
    corners = raw.get("bbox_corners")
    if not (isinstance(corners, list) and len(corners) == 8):
        raise ValueError("O3 answer requires 8 bbox_corners")
    return {"bbox_corners": [tuple(float(v) for v in c) for c in corners]}


def execute_pass(outcome: dict) -> tuple[bool, str]:
    if outcome.get("target_lifted_cm", 0.0) < LIFT_MIN_CM:
        return False, f"target not lifted >= {LIFT_MIN_CM} cm"
    if outcome.get("occluder_disturbance_pct", 0.0) > OCCLUDER_DISTURB_THRESHOLD_PCT:
        return False, f"occluder disturbance > {OCCLUDER_DISTURB_THRESHOLD_PCT}%"
    return True, "ok"


class O3:
    code = code
    description = description
    parse_answer = staticmethod(parse_answer)
    execute_pass = staticmethod(execute_pass)


register(O3)
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/units/o3_partial_view.py cli/tests/spatial_eval/test_units_o3.py
git commit -m "feat(spatial-eval): O3 (partial-view shape) unit"
```

### Task 7 — A1 unit (graspable region)

**Files:**
- Create: `cli/src/robot_md/spatial_eval/units/a1_grasp.py`
- Create: `cli/tests/spatial_eval/test_units_a1.py`

- [ ] **Step 1: Write tests**

```python
# cli/tests/spatial_eval/test_units_a1.py
from __future__ import annotations
import pytest
from robot_md.spatial_eval.units.a1_grasp import A1, parse_answer, execute_pass

def test_a1_parse_ranked_grasps():
    raw = {"grasps": [
        {"position": [0.1, 0.0, 0.05], "orientation": [0,0,0,1], "score": 0.9},
        {"position": [0.0, 0.1, 0.05], "orientation": [0,0,0,1], "score": 0.5},
    ]}
    a = parse_answer(raw)
    assert len(a["grasps"]) == 2
    assert a["grasps"][0]["score"] >= a["grasps"][1]["score"]

def test_a1_rejects_empty_grasp_list():
    with pytest.raises(ValueError):
        parse_answer({"grasps": []})

def test_a1_execute_pass_lift_and_hold():
    ok, _ = execute_pass({"object_lifted_cm": 6.0, "held_seconds": 2.5, "dropped": False})
    assert ok is True

def test_a1_execute_fails_drop():
    ok, r = execute_pass({"object_lifted_cm": 6.0, "held_seconds": 2.5, "dropped": True})
    assert ok is False
    assert "drop" in r.lower()
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/units/a1_grasp.py
from __future__ import annotations
from robot_md.spatial_eval.units.base import register

code = "A1"
description = "Graspable region on novel objects — identify graspable region(s) and pick orientation."

LIFT_MIN_CM = 5.0
HOLD_MIN_S = 2.0


def parse_answer(raw: dict) -> dict:
    grasps = raw.get("grasps")
    if not isinstance(grasps, list) or not grasps:
        raise ValueError("A1 answer requires non-empty 'grasps' list")
    parsed = []
    for g in grasps:
        if not all(k in g for k in ("position", "orientation", "score")):
            raise ValueError("each grasp requires position, orientation, score")
        parsed.append({
            "position": tuple(float(v) for v in g["position"]),
            "orientation": tuple(float(v) for v in g["orientation"]),
            "score": float(g["score"]),
        })
    parsed.sort(key=lambda g: g["score"], reverse=True)
    return {"grasps": parsed}


def execute_pass(outcome: dict) -> tuple[bool, str]:
    if outcome.get("dropped"):
        return False, "object dropped"
    if outcome.get("object_lifted_cm", 0.0) < LIFT_MIN_CM:
        return False, f"object not lifted >= {LIFT_MIN_CM} cm"
    if outcome.get("held_seconds", 0.0) < HOLD_MIN_S:
        return False, f"object not held >= {HOLD_MIN_S} s"
    return True, "ok"


class A1:
    code = code
    description = description
    parse_answer = staticmethod(parse_answer)
    execute_pass = staticmethod(execute_pass)


register(A1)
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/units/a1_grasp.py cli/tests/spatial_eval/test_units_a1.py
git commit -m "feat(spatial-eval): A1 (graspable region) unit"
```

### Task 8 — A2 unit (stability-aware placement) + re-enable registry test

**Files:**
- Create: `cli/src/robot_md/spatial_eval/units/a2_stability.py`
- Create: `cli/tests/spatial_eval/test_units_a2.py`
- Modify: `cli/tests/spatial_eval/test_units_base.py` (remove the skip from Task 3)

- [ ] **Step 1: Write tests for A2**

```python
# cli/tests/spatial_eval/test_units_a2.py
from __future__ import annotations
import pytest
from robot_md.spatial_eval.units.a2_stability import A2, parse_answer, execute_pass

def test_a2_parse_pose():
    a = parse_answer({"pose": {"x": 0.1, "y": -0.05, "yaw_rad": 1.2}})
    assert a["pose"] == {"x": 0.1, "y": -0.05, "yaw_rad": 1.2}

def test_a2_rejects_missing_yaw():
    with pytest.raises(ValueError):
        parse_answer({"pose": {"x": 0.1, "y": -0.05}})

def test_a2_execute_pass_stable():
    ok, _ = execute_pass({"post_release_diff_pct": 1.0})
    assert ok is True

def test_a2_execute_fails_unstable():
    ok, r = execute_pass({"post_release_diff_pct": 5.0})
    assert ok is False
    assert "unstable" in r.lower() or "stab" in r.lower()
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement A2**

```python
# cli/src/robot_md/spatial_eval/units/a2_stability.py
from __future__ import annotations
from robot_md.spatial_eval.units.base import register

code = "A2"
description = "Stability-aware placement — choose a placement pose where the object stays put."

POST_RELEASE_DIFF_THRESHOLD_PCT = 2.0


def parse_answer(raw: dict) -> dict:
    pose = raw.get("pose") or {}
    for k in ("x", "y", "yaw_rad"):
        if k not in pose:
            raise ValueError(f"A2 pose requires '{k}'")
    return {"pose": {k: float(pose[k]) for k in ("x", "y", "yaw_rad")}}


def execute_pass(outcome: dict) -> tuple[bool, str]:
    diff = outcome.get("post_release_diff_pct", 0.0)
    if diff > POST_RELEASE_DIFF_THRESHOLD_PCT:
        return False, f"unstable: post-release diff {diff:.1f}% > {POST_RELEASE_DIFF_THRESHOLD_PCT}%"
    return True, "ok"


class A2:
    code = code
    description = description
    parse_answer = staticmethod(parse_answer)
    execute_pass = staticmethod(execute_pass)


register(A2)
```

- [ ] **Step 4: Re-enable the registry-population test in `test_units_base.py`**

Remove the `@pytest.mark.skip` decorator from `test_registry_lists_all_five_v1_units` so it runs again.

- [ ] **Step 5: Run tests to confirm they pass**

```
cd cli && pytest tests/spatial_eval/test_units_a2.py tests/spatial_eval/test_units_base.py -v
```

Expected: all PASS, registry now has 5 units.

- [ ] **Step 6: Commit**

```bash
git add cli/src/robot_md/spatial_eval/units/a2_stability.py \
        cli/tests/spatial_eval/test_units_a2.py \
        cli/tests/spatial_eval/test_units_base.py
git commit -m "feat(spatial-eval): A2 (stability placement) unit + registry complete"
```

---

## Tasks 9-13 — Probe scorers (one per unit)

Each scorer is a pure function `score(answer, ground_truth) -> (passed: bool, score: float)`. Score is in [0, 1]; pass is the binary cut for `n_passed`.

### Task 9 — Probe scorer dispatcher

**Files:**
- Create: `cli/src/robot_md/spatial_eval/probe/__init__.py` (empty)
- Create: `cli/src/robot_md/spatial_eval/probe/scorer.py`
- Create: `cli/tests/spatial_eval/test_scorer_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_scorer_dispatch.py
from __future__ import annotations
import pytest
from robot_md.spatial_eval.probe.scorer import score_answer

def test_dispatch_to_unit_scorer_o1():
    answer = {"still_present": True, "position": (0.1, 0.05, 0.0)}
    truth =  {"still_present": True, "position": (0.10, 0.05, 0.01)}
    passed, score = score_answer("O1", answer, truth)
    assert passed is True
    assert score == pytest.approx(1.0)

def test_dispatch_unknown_unit_raises():
    with pytest.raises(KeyError):
        score_answer("Z9", {}, {})
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement dispatcher**

```python
# cli/src/robot_md/spatial_eval/probe/scorer.py
from __future__ import annotations
from typing import Callable

# Imported lazily by callers as scorers are added per unit.
_SCORERS: dict[str, Callable[[dict, dict], tuple[bool, float]]] = {}


def register_scorer(unit_code: str, fn: Callable[[dict, dict], tuple[bool, float]]) -> None:
    _SCORERS[unit_code] = fn


def score_answer(unit_code: str, answer: dict, truth: dict) -> tuple[bool, float]:
    if unit_code not in _SCORERS:
        raise KeyError(f"no scorer registered for unit {unit_code!r}")
    return _SCORERS[unit_code](answer, truth)


def _bootstrap() -> None:
    """Force-import unit scorer modules so they self-register."""
    from robot_md.spatial_eval.probe import scorers  # noqa: F401


# Tests that depend on registered scorers should call _bootstrap() in conftest.
```

Also create `cli/src/robot_md/spatial_eval/probe/scorers/__init__.py` that imports each scorer module:

```python
# cli/src/robot_md/spatial_eval/probe/scorers/__init__.py
from __future__ import annotations
from robot_md.spatial_eval.probe.scorers import o1, o2, o3, a1, a2  # noqa: F401
```

For Task 9, only `o1.py` is implemented (below). Tasks 10-13 add the rest.

```python
# cli/src/robot_md/spatial_eval/probe/scorers/o1.py
from __future__ import annotations
import math
from robot_md.spatial_eval.probe.scorer import register_scorer

POSITION_TOLERANCE_M = 0.02


def _score_o1(answer: dict, truth: dict) -> tuple[bool, float]:
    if answer.get("still_present") != truth.get("still_present"):
        return False, 0.0
    if not answer.get("still_present"):
        return True, 1.0  # both agree absent
    a = answer["position"]; t = truth["position"]
    d = math.sqrt(sum((float(a[i]) - float(t[i])) ** 2 for i in range(3)))
    if d <= POSITION_TOLERANCE_M:
        return True, 1.0
    return False, max(0.0, 1.0 - d / 0.10)  # decays to 0 at 10cm


register_scorer("O1", _score_o1)
```

Update the test conftest to call `_bootstrap()`:

```python
# cli/tests/spatial_eval/conftest.py
from __future__ import annotations
import pytest
from robot_md.spatial_eval.probe.scorer import _bootstrap

@pytest.fixture(autouse=True, scope="session")
def _bootstrap_scorers():
    _bootstrap()
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/probe/__init__.py \
        cli/src/robot_md/spatial_eval/probe/scorer.py \
        cli/src/robot_md/spatial_eval/probe/scorers/__init__.py \
        cli/src/robot_md/spatial_eval/probe/scorers/o1.py \
        cli/tests/spatial_eval/conftest.py \
        cli/tests/spatial_eval/test_scorer_dispatch.py
git commit -m "feat(spatial-eval): probe scorer dispatcher + O1 scorer"
```

### Task 10 — O2 scorer (graph match)

**Files:**
- Create: `cli/src/robot_md/spatial_eval/probe/scorers/o2.py`
- Create: `cli/tests/spatial_eval/test_scorer_o2.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_scorer_o2.py
from __future__ import annotations
from robot_md.spatial_eval.probe.scorer import score_answer

def test_o2_exact_match():
    a = {"container": "green_cup", "contained": "red_cube"}
    t = {"container": "green_cup", "contained": "red_cube"}
    p, s = score_answer("O2", a, t)
    assert p is True and s == 1.0

def test_o2_wrong_container():
    a = {"container": "blue_cup", "contained": "red_cube"}
    t = {"container": "green_cup", "contained": "red_cube"}
    p, s = score_answer("O2", a, t)
    assert p is False and s == 0.0
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/probe/scorers/o2.py
from __future__ import annotations
from robot_md.spatial_eval.probe.scorer import register_scorer


def _score_o2(answer: dict, truth: dict) -> tuple[bool, float]:
    ok = (
        answer.get("container") == truth.get("container")
        and answer.get("contained") == truth.get("contained")
    )
    return (ok, 1.0 if ok else 0.0)


register_scorer("O2", _score_o2)
```

Add `from . import o2  # noqa: F401` to `scorers/__init__.py`.

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/probe/scorers/o2.py \
        cli/src/robot_md/spatial_eval/probe/scorers/__init__.py \
        cli/tests/spatial_eval/test_scorer_o2.py
git commit -m "feat(spatial-eval): O2 graph-match scorer"
```

### Task 11 — O3 scorer (3D bbox IoU)

**Files:**
- Create: `cli/src/robot_md/spatial_eval/probe/scorers/o3.py`
- Create: `cli/tests/spatial_eval/test_scorer_o3.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_scorer_o3.py
from __future__ import annotations
import pytest
from robot_md.spatial_eval.probe.scorer import score_answer

UNIT_CUBE = [(0,0,0),(1,0,0),(0,1,0),(1,1,0),(0,0,1),(1,0,1),(0,1,1),(1,1,1)]

def test_o3_perfect_match_iou_1():
    a = {"bbox_corners": UNIT_CUBE}
    t = {"bbox_corners": UNIT_CUBE}
    p, s = score_answer("O3", a, t)
    assert p is True and s == pytest.approx(1.0)

def test_o3_disjoint_iou_0():
    a = {"bbox_corners": UNIT_CUBE}
    t = {"bbox_corners": [(10+x, y, z) for (x,y,z) in UNIT_CUBE]}
    p, s = score_answer("O3", a, t)
    assert p is False
    assert s == pytest.approx(0.0)

def test_o3_pass_threshold_iou_05():
    # Half overlap along x: AABBs (0..1) vs (0.5..1.5).
    half = [(0.5+x*0.5, y, z) for (x,y,z) in UNIT_CUBE]
    p, s = score_answer("O3", {"bbox_corners": UNIT_CUBE}, {"bbox_corners": half})
    # half-overlap volume = 0.5; union = 1 + 0.5 = 1.5? Actually each is unit cube,
    # union = 1 + 0.5 = 1.5 (intersection 0.5), so iou ~ 0.33. Below 0.5 threshold.
    assert p is False
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/probe/scorers/o3.py
from __future__ import annotations
from robot_md.spatial_eval.probe.scorer import register_scorer

PASS_IOU = 0.5


def _aabb(corners: list[tuple]) -> tuple[float, float, float, float, float, float]:
    xs = [c[0] for c in corners]; ys = [c[1] for c in corners]; zs = [c[2] for c in corners]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _iou(a, b) -> float:
    ax1, ay1, az1, ax2, ay2, az2 = a
    bx1, by1, bz1, bx2, by2, bz2 = b
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    iz = max(0.0, min(az2, bz2) - max(az1, bz1))
    inter = ix * iy * iz
    va = (ax2 - ax1) * (ay2 - ay1) * (az2 - az1)
    vb = (bx2 - bx1) * (by2 - by1) * (bz2 - bz1)
    union = va + vb - inter
    return 0.0 if union <= 0 else inter / union


def _score_o3(answer: dict, truth: dict) -> tuple[bool, float]:
    iou = _iou(_aabb(answer["bbox_corners"]), _aabb(truth["bbox_corners"]))
    return (iou >= PASS_IOU, iou)


register_scorer("O3", _score_o3)
```

Add `from . import o3  # noqa: F401` to `scorers/__init__.py`.

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/probe/scorers/o3.py \
        cli/src/robot_md/spatial_eval/probe/scorers/__init__.py \
        cli/tests/spatial_eval/test_scorer_o3.py
git commit -m "feat(spatial-eval): O3 3D-bbox IoU scorer"
```

### Task 12 — A1 scorer (top-K grasp ranking)

**Files:**
- Create: `cli/src/robot_md/spatial_eval/probe/scorers/a1.py`
- Create: `cli/tests/spatial_eval/test_scorer_a1.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_scorer_a1.py
from __future__ import annotations
from robot_md.spatial_eval.probe.scorer import score_answer

def _g(p, score):
    return {"position": list(p), "orientation": [0,0,0,1], "score": score}

def test_a1_top1_match():
    a = {"grasps": [_g((0.1, 0.0, 0.05), 0.9), _g((0.2, 0.0, 0.05), 0.5)]}
    t = {"gold_grasps_top_k": [_g((0.10, 0.0, 0.05), 1.0)], "k": 3, "tolerance_m": 0.02}
    p, s = score_answer("A1", a, t)
    assert p is True and s == 1.0

def test_a1_no_top_match():
    a = {"grasps": [_g((1.0, 1.0, 1.0), 0.9)]}
    t = {"gold_grasps_top_k": [_g((0.0, 0.0, 0.0), 1.0)], "k": 3, "tolerance_m": 0.02}
    p, s = score_answer("A1", a, t)
    assert p is False and s == 0.0
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/probe/scorers/a1.py
from __future__ import annotations
import math
from robot_md.spatial_eval.probe.scorer import register_scorer


def _l2(a, b) -> float:
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def _score_a1(answer: dict, truth: dict) -> tuple[bool, float]:
    grasps = answer.get("grasps", [])
    gold = truth.get("gold_grasps_top_k", [])
    k = int(truth.get("k", 3))
    tol = float(truth.get("tolerance_m", 0.02))
    if not grasps or not gold:
        return False, 0.0
    top_k = grasps[:k]
    for g in top_k:
        for gg in gold:
            if _l2(g["position"], gg["position"]) <= tol:
                return True, 1.0
    return False, 0.0


register_scorer("A1", _score_a1)
```

Add to `scorers/__init__.py`.

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/probe/scorers/a1.py \
        cli/src/robot_md/spatial_eval/probe/scorers/__init__.py \
        cli/tests/spatial_eval/test_scorer_a1.py
git commit -m "feat(spatial-eval): A1 top-K grasp scorer"
```

### Task 13 — A2 scorer (labeled-gold lookup for v1)

**Files:**
- Create: `cli/src/robot_md/spatial_eval/probe/scorers/a2.py`
- Create: `cli/tests/spatial_eval/test_scorer_a2.py`

A2 ground truth is labeled — the held-out probe set carries `gold_stable_regions` (list of stable (x, y, yaw_rad) clusters with tolerance). v1 does not run a physics simulator; v2 may.

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_scorer_a2.py
from __future__ import annotations
from robot_md.spatial_eval.probe.scorer import score_answer

def test_a2_within_stable_cluster():
    a = {"pose": {"x": 0.1, "y": 0.05, "yaw_rad": 1.2}}
    t = {
        "gold_stable_clusters": [
            {"x": 0.10, "y": 0.05, "yaw_rad": 1.2, "xy_tolerance_m": 0.02, "yaw_tolerance_rad": 0.3}
        ]
    }
    p, s = score_answer("A2", a, t)
    assert p is True and s == 1.0

def test_a2_outside_all_clusters():
    a = {"pose": {"x": 1.0, "y": 1.0, "yaw_rad": 0.0}}
    t = {
        "gold_stable_clusters": [
            {"x": 0.0, "y": 0.0, "yaw_rad": 0.0, "xy_tolerance_m": 0.02, "yaw_tolerance_rad": 0.3}
        ]
    }
    p, s = score_answer("A2", a, t)
    assert p is False and s == 0.0
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/probe/scorers/a2.py
from __future__ import annotations
import math
from robot_md.spatial_eval.probe.scorer import register_scorer


def _score_a2(answer: dict, truth: dict) -> tuple[bool, float]:
    pose = answer.get("pose", {})
    if not pose:
        return False, 0.0
    for c in truth.get("gold_stable_clusters", []):
        dx = pose["x"] - c["x"]
        dy = pose["y"] - c["y"]
        d_xy = math.sqrt(dx * dx + dy * dy)
        d_yaw = abs(((pose["yaw_rad"] - c["yaw_rad"]) + math.pi) % (2 * math.pi) - math.pi)
        if d_xy <= c["xy_tolerance_m"] and d_yaw <= c["yaw_tolerance_rad"]:
            return True, 1.0
    return False, 0.0


register_scorer("A2", _score_a2)
```

Add to `scorers/__init__.py`.

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/probe/scorers/a2.py \
        cli/src/robot_md/spatial_eval/probe/scorers/__init__.py \
        cli/tests/spatial_eval/test_scorer_a2.py
git commit -m "feat(spatial-eval): A2 labeled-cluster scorer (v1)"
```

---

## Task 14 — Probe stack: baseline_claude (Anthropic SDK) + stack resolver

**Files:**
- Create: `cli/src/robot_md/spatial_eval/probe/stacks.py`
- Create: `cli/tests/spatial_eval/test_probe_stacks.py`

The stack accepts a probe dict, returns a parsed answer (unit's shape). Production calls Anthropic; tests use a `FakeStack`. The resolver decides which stack to call based on `reasoning_stack.{baseline,declared}`.

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_probe_stacks.py
from __future__ import annotations
import pytest
from robot_md.spatial_eval.probe.stacks import (
    FakeStack, resolve_stack, BaselineClaudeStack,
)

def test_fake_stack_returns_canned_answer():
    stack = FakeStack(answers={"o1-x": {"still_present": True, "position": [0,0,0]}})
    out = stack.answer({"id": "o1-x", "unit": "O1"})
    assert out == {"still_present": True, "position": [0, 0, 0]}

def test_resolve_stack_claude_only_in_v1():
    stack = resolve_stack("claude:claude-opus-4-7")
    assert isinstance(stack, BaselineClaudeStack)

def test_resolve_stack_rejects_non_claude_in_v1():
    with pytest.raises(ValueError, match="claude:"):
        resolve_stack("vla:my-endpoint")
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/probe/stacks.py
from __future__ import annotations
import json
import os
from typing import Protocol


class Stack(Protocol):
    def answer(self, probe: dict) -> dict: ...


class FakeStack:
    """Deterministic stack used by tests. Maps probe id -> answer dict."""

    def __init__(self, answers: dict[str, dict]) -> None:
        self._answers = answers

    def answer(self, probe: dict) -> dict:
        pid = probe["id"]
        if pid not in self._answers:
            raise KeyError(f"FakeStack has no canned answer for {pid!r}")
        return self._answers[pid]


class BaselineClaudeStack:
    """Calls Anthropic SDK; uses prompt caching for the system prompt + scenario header."""

    def __init__(self, model: str) -> None:
        self.model = model
        # Lazy import so tests without the SDK installed still import this module.
        from anthropic import Anthropic
        self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def answer(self, probe: dict) -> dict:
        from anthropic import Anthropic  # noqa: F401  (kept lazy)
        # System prompt cached; per-probe content is the variable part.
        system_blocks = [
            {"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        ]
        user_content = [
            {"type": "text", "text": probe["scenario_header"]},
            *_frames_as_content(probe.get("frames", [])),
            {"type": "text", "text": json.dumps(probe["question"])},
        ]
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_blocks,
            messages=[{"role": "user", "content": user_content}],
        )
        # Expect single text block with JSON body.
        text = "".join(b.text for b in msg.content if b.type == "text")
        return json.loads(text)


_SYSTEM_PROMPT = """You are evaluating spatial-intelligence probes for an embodied robot benchmark.
Each probe asks a structured question about a scene. Respond with ONE JSON object matching the
question's required shape, no prose, no markdown fence."""


def _frames_as_content(frames: list[str]) -> list[dict]:
    out = []
    for f in frames:
        out.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": f}})
    return out


def resolve_stack(identifier: str) -> Stack:
    if not identifier.startswith("claude:"):
        raise ValueError(f"v1 supports only 'claude:<model>' identifiers; got {identifier!r}")
    model = identifier.split(":", 1)[1]
    return BaselineClaudeStack(model)
```

- [ ] **Step 4: Run tests to confirm they pass.**

```
cd cli && pytest tests/spatial_eval/test_probe_stacks.py -v
```

The `BaselineClaudeStack` constructor will fail in tests if `ANTHROPIC_API_KEY` is unset; the tests above only construct via `resolve_stack` and rely on it raising or returning the type. To avoid eager Anthropic-client construction when only checking the type, refactor the constructor to defer client creation until first `.answer()` call. Update:

```python
class BaselineClaudeStack:
    def __init__(self, model: str) -> None:
        self.model = model
        self._client = None

    def _client_now(self):
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def answer(self, probe: dict) -> dict:
        client = self._client_now()
        # ... (rest as above, replacing self._client with client)
```

Re-run; expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/probe/stacks.py cli/tests/spatial_eval/test_probe_stacks.py
git commit -m "feat(spatial-eval): probe stacks (FakeStack, BaselineClaudeStack, resolver)"
```

---

## Task 15 — Probe runner with side-by-side delta

**Files:**
- Create: `cli/src/robot_md/spatial_eval/probe/runner.py`
- Create: `cli/tests/spatial_eval/test_probe_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_probe_runner.py
from __future__ import annotations
from robot_md.spatial_eval.probe.runner import run_probes
from robot_md.spatial_eval.probe.stacks import FakeStack

def _probe(pid: str, unit: str, scenario: str, question: dict, truth: dict) -> dict:
    return {"id": pid, "unit": unit, "scenario_header": scenario,
            "frames": [], "question": question, "ground_truth": truth}

def test_runner_side_by_side_with_delta():
    probes = [
        _probe("o1-1", "O1", "scene", {"type": "object_location"},
               {"still_present": True, "position": (0.0, 0.0, 0.0)}),
        _probe("o1-2", "O1", "scene", {"type": "object_location"},
               {"still_present": True, "position": (0.1, 0.0, 0.0)}),
    ]
    baseline = FakeStack({
        "o1-1": {"still_present": True, "position": [0.0, 0.0, 0.0]},
        "o1-2": {"still_present": True, "position": [0.1, 0.0, 0.0]},
    })
    declared = FakeStack({
        "o1-1": {"still_present": True, "position": [0.5, 0.5, 0.5]},  # bad
        "o1-2": {"still_present": True, "position": [0.1, 0.0, 0.0]},  # good
    })
    result = run_probes(probes, baseline=baseline, declared=declared)
    assert result.baseline_per_unit["O1"].passed == 2
    assert result.declared_per_unit["O1"].passed == 1
    assert result.delta_per_unit["O1"] == result.declared_per_unit["O1"].score - result.baseline_per_unit["O1"].score
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/probe/runner.py
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from robot_md.spatial_eval.probe.scorer import score_answer
from robot_md.spatial_eval.probe.stacks import Stack
from robot_md.spatial_eval.score import PerUnitProbeScore
from robot_md.spatial_eval.units import get_unit


@dataclass(frozen=True)
class ProbeRunResult:
    baseline_per_unit: dict[str, PerUnitProbeScore]
    declared_per_unit: dict[str, PerUnitProbeScore]
    delta_per_unit: dict[str, float]
    per_probe: list[dict]  # raw per-probe records for evidence packet


def _score_one(unit: str, raw_answer: dict, truth: dict) -> tuple[bool, float]:
    parsed = get_unit(unit).parse_answer(raw_answer)
    return score_answer(unit, parsed, truth)


def run_probes(
    probes: Iterable[dict],
    *,
    baseline: Stack,
    declared: Optional[Stack] = None,
    progress_cb=None,
) -> ProbeRunResult:
    by_unit_baseline: dict[str, list[tuple[bool, float]]] = defaultdict(list)
    by_unit_declared: dict[str, list[tuple[bool, float]]] = defaultdict(list)
    per_probe: list[dict] = []
    probes_list = list(probes)
    total = len(probes_list)
    for i, p in enumerate(probes_list):
        unit = p["unit"]
        truth = p["ground_truth"]
        b_raw = baseline.answer(p)
        b_pass, b_score = _score_one(unit, b_raw, truth)
        by_unit_baseline[unit].append((b_pass, b_score))

        d_pass, d_score = (b_pass, b_score)
        d_raw = b_raw
        if declared is not None and declared is not baseline:
            d_raw = declared.answer(p)
            d_pass, d_score = _score_one(unit, d_raw, truth)
        by_unit_declared[unit].append((d_pass, d_score))

        per_probe.append({
            "id": p["id"], "unit": unit,
            "baseline": {"answer": b_raw, "passed": b_pass, "score": b_score},
            "declared": {"answer": d_raw, "passed": d_pass, "score": d_score},
        })
        if progress_cb is not None:
            progress_cb(i + 1, total, unit)

    def _aggregate(by_unit: dict[str, list[tuple[bool, float]]]) -> dict[str, PerUnitProbeScore]:
        out: dict[str, PerUnitProbeScore] = {}
        for unit, rows in by_unit.items():
            n = len(rows)
            passed = sum(1 for ok, _ in rows if ok)
            score = sum(s for _, s in rows) / max(1, n)
            out[unit] = PerUnitProbeScore(score=score, n=n, passed=passed)
        return out

    base = _aggregate(by_unit_baseline)
    decl = _aggregate(by_unit_declared)
    delta = {u: decl[u].score - base[u].score for u in base}
    return ProbeRunResult(
        baseline_per_unit=base,
        declared_per_unit=decl,
        delta_per_unit=delta,
        per_probe=per_probe,
    )
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/probe/runner.py cli/tests/spatial_eval/test_probe_runner.py
git commit -m "feat(spatial-eval): probe runner (side-by-side, per-probe trace)"
```

---

## Task 16 — Public probe dataset format + sample probes

**Files:**
- Create: `cli/src/robot_md/spatial_eval/probe/datasets/__init__.py`
- Create: `cli/src/robot_md/spatial_eval/probe/datasets/loader.py`
- Create: `cli/src/robot_md/spatial_eval/probe/datasets/public/{O1,O2,O3,A1,A2}/probe-001.json` (3 sample probes per unit, 15 total)
- Create: `cli/tests/spatial_eval/test_dataset_loader.py`

This task ships the *format* and 3 sample probes per unit. Authoring the full 30-per-unit public split (and the held-out split) is a content task tracked separately under SP6-content (out of scope for this plan; the loader and format are the deliverable here).

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_dataset_loader.py
from __future__ import annotations
from robot_md.spatial_eval.probe.datasets.loader import load_public_split

def test_loader_returns_probes_for_each_unit():
    by_unit = load_public_split()
    assert set(by_unit.keys()) == {"O1", "O2", "O3", "A1", "A2"}
    for unit, probes in by_unit.items():
        assert len(probes) >= 3
        for p in probes:
            assert p["unit"] == unit
            assert "ground_truth" in p
            assert "scenario_header" in p
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement loader and stub probe files**

```python
# cli/src/robot_md/spatial_eval/probe/datasets/__init__.py
# (empty)
```

```python
# cli/src/robot_md/spatial_eval/probe/datasets/loader.py
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "public"


def load_public_split() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for unit_dir in sorted(ROOT.iterdir()):
        if not unit_dir.is_dir():
            continue
        unit = unit_dir.name
        probes = []
        for p in sorted(unit_dir.glob("*.json")):
            probes.append(json.loads(p.read_text()))
        out[unit] = probes
    return out
```

Create 3 sample probes per unit with realistic ground truth shapes. Example for O1:

```json
// cli/src/robot_md/spatial_eval/probe/datasets/public/O1/probe-001.json
{
  "id": "o1-public-001",
  "unit": "O1",
  "scenario_header": "A red cube sits on a table at center. A green opaque cup is then slid over it from the left, fully covering it. Question: is the cube still present, and where?",
  "frames": [],
  "question": {"type": "object_location", "target": "red_cube"},
  "ground_truth": {"still_present": true, "position": [0.0, 0.0, 0.0]}
}
```

Three per unit, varying scene parameters. **Frames are left empty for sample probes** — full probe content (real captures + synthetic renders) is authored in the SP6-content track. Code paths are validated end-to-end with the FakeStack in tests.

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/probe/datasets/
git add cli/tests/spatial_eval/test_dataset_loader.py
git commit -m "feat(spatial-eval): public-split probe loader + 3 stub probes/unit"
```

---

## Task 17 — Execute judge: HSV color centroid

**Files:**
- Create: `cli/src/robot_md/spatial_eval/execute/__init__.py` (empty)
- Create: `cli/src/robot_md/spatial_eval/execute/judge.py`
- Create: `cli/tests/spatial_eval/test_execute_judge.py`

Reuses the existing `robot_md.detectors.hsv` primitives where possible.

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_execute_judge.py
from __future__ import annotations
import numpy as np
from robot_md.spatial_eval.execute.judge import (
    color_centroid, frame_diff_pct, ColorParams,
)

RED = ColorParams(h_ranges=[(0, 10), (170, 180)], s_min=120, v_min=80)


def _solid_red_image(h=240, w=320, blob_xy=(160, 120), radius=20) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    import cv2
    cv2.circle(img, blob_xy, radius, (0, 0, 255), thickness=-1)  # BGR red
    return img


def test_color_centroid_finds_red_blob():
    img = _solid_red_image()
    c = color_centroid(img, RED)
    assert c is not None
    u, v, area = c
    assert abs(u - 160) < 4
    assert abs(v - 120) < 4
    assert area > 100


def test_color_centroid_none_when_absent():
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    assert color_centroid(img, RED) is None


def test_frame_diff_pct_zero_for_identical_frames():
    img = _solid_red_image()
    assert frame_diff_pct(img, img.copy()) == 0.0


def test_frame_diff_pct_high_for_disjoint_frames():
    a = _solid_red_image(blob_xy=(50, 50))
    b = _solid_red_image(blob_xy=(250, 200))
    assert frame_diff_pct(a, b) > 1.0
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/execute/judge.py
from __future__ import annotations
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ColorParams:
    h_ranges: list[tuple[int, int]]
    s_min: int = 0
    s_max: int = 255
    v_min: int = 0
    v_max: int = 255
    min_area: int = 200


def color_centroid(bgr: np.ndarray, params: ColorParams) -> tuple[int, int, int] | None:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = None
    for lo, hi in params.h_ranges:
        m = cv2.inRange(hsv, (int(lo), params.s_min, params.v_min),
                              (int(hi), params.s_max, params.v_max))
        mask = m if mask is None else cv2.bitwise_or(mask, m)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    big = max(contours, key=cv2.contourArea)
    area = int(cv2.contourArea(big))
    if area < params.min_area:
        return None
    M = cv2.moments(big)
    if M["m00"] == 0:
        return None
    return int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]), area


def frame_diff_pct(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute difference as a percentage of full-scale."""
    if a.shape != b.shape:
        raise ValueError(f"frame shapes differ: {a.shape} vs {b.shape}")
    diff = cv2.absdiff(a, b)
    return float(diff.mean()) / 255.0 * 100.0
```

- [ ] **Step 4: Run tests to confirm they pass.**

```
cd cli && pytest tests/spatial_eval/test_execute_judge.py -v
```

Expected: 4 PASS. (If `cv2` isn't installed in the test env, this test is gated by the `[spatial-eval]` extra installed in Task 27.)

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/execute/__init__.py \
        cli/src/robot_md/spatial_eval/execute/judge.py \
        cli/tests/spatial_eval/test_execute_judge.py
git commit -m "feat(spatial-eval): execute judge (HSV centroid + frame diff)"
```

---

## Task 18 — Execute manual review gate

**Files:**
- Create: `cli/src/robot_md/spatial_eval/execute/manual_gate.py`
- Create: `cli/tests/spatial_eval/test_manual_gate.py`

A trial whose auto-scoring confidence drops below threshold is flagged for manual review. The gate stores the trial under a `pending_review/` queue with the recorded video path; `spatial_eval_replay` later re-scores after the operator submits a verdict file.

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_manual_gate.py
from __future__ import annotations
from pathlib import Path
from robot_md.spatial_eval.execute.manual_gate import (
    flag_for_review, list_pending_reviews, resolve_review,
)

def test_flag_and_resolve(tmp_path: Path):
    flag_for_review(
        run_dir=tmp_path, trial_id="o1-trial-3",
        video_path=tmp_path / "trial.mp4",
        auto_outcome={"target_retrieved": True, "occluder_disturbance_pct": 4.8},
        confidence=0.4, threshold=0.6,
    )
    pending = list_pending_reviews(tmp_path)
    assert len(pending) == 1
    assert pending[0]["trial_id"] == "o1-trial-3"

    resolve_review(tmp_path, trial_id="o1-trial-3", verdict_passed=True, reviewer="craig")
    assert list_pending_reviews(tmp_path) == []
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/execute/manual_gate.py
from __future__ import annotations
import json
from pathlib import Path


def flag_for_review(
    *, run_dir: Path, trial_id: str, video_path: Path,
    auto_outcome: dict, confidence: float, threshold: float,
) -> None:
    pending = run_dir / "pending_review"
    pending.mkdir(parents=True, exist_ok=True)
    (pending / f"{trial_id}.json").write_text(json.dumps({
        "trial_id": trial_id,
        "video_path": str(video_path),
        "auto_outcome": auto_outcome,
        "confidence": confidence,
        "threshold": threshold,
    }, indent=2))


def list_pending_reviews(run_dir: Path) -> list[dict]:
    pending = run_dir / "pending_review"
    if not pending.is_dir():
        return []
    return [json.loads(p.read_text()) for p in sorted(pending.glob("*.json"))]


def resolve_review(run_dir: Path, *, trial_id: str, verdict_passed: bool, reviewer: str) -> None:
    pending = run_dir / "pending_review"
    f = pending / f"{trial_id}.json"
    if not f.is_file():
        raise FileNotFoundError(f"no pending review for {trial_id}")
    record = json.loads(f.read_text())
    record["resolved"] = {"passed": verdict_passed, "reviewer": reviewer}
    resolved = run_dir / "resolved_review"
    resolved.mkdir(parents=True, exist_ok=True)
    (resolved / f"{trial_id}.json").write_text(json.dumps(record, indent=2))
    f.unlink()
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/execute/manual_gate.py \
        cli/tests/spatial_eval/test_manual_gate.py
git commit -m "feat(spatial-eval): manual review gate"
```

---

## Task 19 — Execute trial state machine

**Files:**
- Create: `cli/src/robot_md/spatial_eval/execute/trial.py`
- Create: `cli/tests/spatial_eval/test_execute_trial.py`

The trial state machine is hardware-aware but injectable: tests pass a fake `Robot` and fake judge frames; production wires the existing `execute_capability` path.

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_execute_trial.py
from __future__ import annotations
from pathlib import Path
import numpy as np
from robot_md.spatial_eval.execute.trial import run_trial, FakeRobot, FakeJudgeCamera

def _bgr(color):
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    img[:, :] = color
    return img

def test_o1_pass_when_target_retrieved_and_occluder_steady(tmp_path: Path):
    robot = FakeRobot(actions=["pick_target_color:red_cube"])
    cam = FakeJudgeCamera(frames=[
        _bgr((0, 0, 255)),    # t0: red present
        _bgr((0, 200, 0)),    # t1: green occluder (red hidden)
        _bgr((0, 0, 255)),    # t2: red retrieved (post-action)
    ])
    outcome = run_trial(unit="O1", trial_id="o1-1", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is True

def test_o1_fail_when_target_not_retrieved(tmp_path: Path):
    robot = FakeRobot(actions=["miss"])
    cam = FakeJudgeCamera(frames=[
        _bgr((0, 0, 255)),
        _bgr((0, 200, 0)),
        _bgr((0, 200, 0)),  # never reappears
    ])
    outcome = run_trial(unit="O1", trial_id="o1-2", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is False
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/execute/trial.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from robot_md.spatial_eval.execute.judge import (
    ColorParams, color_centroid, frame_diff_pct,
)
from robot_md.spatial_eval.units import get_unit


class Robot(Protocol):
    def execute_action(self, action: str) -> None: ...


class JudgeCamera(Protocol):
    def capture(self) -> np.ndarray: ...


@dataclass
class FakeRobot:
    actions: list[str]
    executed: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        self.executed = []

    def execute_action(self, action: str) -> None:
        self.executed.append(action)


@dataclass
class FakeJudgeCamera:
    frames: list[np.ndarray]
    idx: int = 0

    def capture(self) -> np.ndarray:
        f = self.frames[self.idx]
        self.idx = min(self.idx + 1, len(self.frames) - 1)
        return f


# Per-unit color parameters (v1 — bound to standard kit).
TARGET_COLORS = {
    "red_cube": ColorParams(h_ranges=[(0, 10), (170, 180)], s_min=120, v_min=80),
    "green_cup": ColorParams(h_ranges=[(40, 80)], s_min=80, v_min=80),
    "blue_bottle": ColorParams(h_ranges=[(100, 130)], s_min=80, v_min=80),
}


def run_trial(*, unit: str, trial_id: str, robot: Robot, judge_camera: JudgeCamera,
              run_dir: Path) -> dict:
    """Execute one trial. Returns outcome dict (unit-specific) + pass/fail."""
    # Pre-action snapshot.
    f_before = judge_camera.capture()
    # Mid-action snapshot (occluder phase, where applicable).
    f_during = judge_camera.capture()
    # Action.
    if isinstance(robot, FakeRobot):
        for a in robot.actions:
            robot.execute_action(a)
    else:
        # Production wires through robot_md.execute_task / execute_capability;
        # branch handled in the MCP tool layer.
        pass
    # Post-action snapshot.
    f_after = judge_camera.capture()

    outcome = _score_unit(unit, f_before, f_during, f_after)
    passed, reason = get_unit(unit).execute_pass(outcome)
    outcome.update({"passed": passed, "reason": reason, "trial_id": trial_id})
    return outcome


def _score_unit(unit: str, f_before, f_during, f_after) -> dict:
    if unit == "O1":
        target = "red_cube"
        c_before = color_centroid(f_before, TARGET_COLORS[target])
        c_after = color_centroid(f_after, TARGET_COLORS[target])
        return {
            "target_retrieved": c_before is not None and c_after is not None,
            "occluder_disturbance_pct": frame_diff_pct(f_before, f_after),
        }
    if unit == "O2":
        # Did the gripper visit the correct container? Was target lifted?
        # Simplified v1: target color appears in `f_after` at expected lift height region.
        target = "red_cube"
        c_after = color_centroid(f_after, TARGET_COLORS[target])
        lifted_cm = 6.0 if c_after else 0.0
        return {
            "correct_container": c_after is not None,
            "target_lifted_cm": lifted_cm,
        }
    if unit == "O3":
        target = "red_cube"
        c_after = color_centroid(f_after, TARGET_COLORS[target])
        return {
            "target_lifted_cm": 6.0 if c_after else 0.0,
            "occluder_disturbance_pct": frame_diff_pct(f_before, f_after),
        }
    if unit == "A1":
        c_after = color_centroid(f_after, TARGET_COLORS["red_cube"])
        return {
            "object_lifted_cm": 6.0 if c_after else 0.0,
            "held_seconds": 2.5 if c_after else 0.0,
            "dropped": c_after is None,
        }
    if unit == "A2":
        return {
            "post_release_diff_pct": frame_diff_pct(f_during, f_after),
        }
    raise KeyError(f"unsupported unit {unit!r}")
```

This v1 implementation maps a small set of judge primitives to per-unit outcome dicts. Full kinematics-aware lift detection (z-axis from gripper telemetry) is added in v2 once the MCP tool wiring is in place.

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/execute/trial.py \
        cli/tests/spatial_eval/test_execute_trial.py
git commit -m "feat(spatial-eval): execute trial state machine + fake hardware"
```

---

## Task 20 — Evidence packet builder + RCAN signing

**Files:**
- Create: `cli/src/robot_md/spatial_eval/execute/evidence.py`
- Create: `cli/tests/spatial_eval/test_evidence.py`

The evidence packet is a directory with `manifest.json` (per-trial outcomes), `Score.json` (full Score JSON), and bundled video files. The packet's root hash is `sha256(sorted-tree-hash)`. Signing uses the existing apikey/RCAN helpers — exact module path is determined at implementation time by inspecting `cli/src/robot_md/apikey_request.py` and any sibling RCAN signer.

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_evidence.py
from __future__ import annotations
import json
from pathlib import Path
from robot_md.spatial_eval.execute.evidence import (
    write_evidence_packet, packet_root_sha256,
)
from robot_md.spatial_eval.score import (
    ScoreJSON, ProbeTrack, PerUnitProbeScore, PerUnitExecuteScore, Aggregate,
)

def _stub_score() -> ScoreJSON:
    pt = ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={})
    return ScoreJSON(
        spec_version="1.0.0", rrn="RRN-x", run_id="r-1", timestamp="t",
        tracks_probe=pt, tracks_execute={"O1": PerUnitExecuteScore(7, 10, "ev")},
        aggregate=Aggregate(0, 0, 0.7),
    )

def test_packet_writes_files_and_hash_is_deterministic(tmp_path: Path):
    trials = [{"trial_id": "t1", "passed": True, "reason": "ok"}]
    write_evidence_packet(
        run_dir=tmp_path, trials=trials, score=_stub_score(), videos={"t1": b"\x00\x01"},
    )
    assert (tmp_path / "manifest.json").is_file()
    assert (tmp_path / "Score.json").is_file()
    assert (tmp_path / "videos/t1.mp4").is_file()
    h1 = packet_root_sha256(tmp_path)
    h2 = packet_root_sha256(tmp_path)
    assert h1 == h2
    assert len(h1) == 64
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/execute/evidence.py
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from robot_md.spatial_eval.score import ScoreJSON


def write_evidence_packet(
    *, run_dir: Path, trials: list[dict], score: ScoreJSON, videos: dict[str, bytes],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps({"trials": trials}, sort_keys=True, indent=2))
    (run_dir / "Score.json").write_text(score.to_json())
    vdir = run_dir / "videos"
    vdir.mkdir(exist_ok=True)
    for trial_id, blob in videos.items():
        (vdir / f"{trial_id}.mp4").write_bytes(blob)


def packet_root_sha256(run_dir: Path) -> str:
    """Deterministic hash over (relative path, file bytes) for all files in run_dir."""
    h = hashlib.sha256()
    files = sorted(run_dir.rglob("*"))
    for f in files:
        if not f.is_file():
            continue
        rel = f.relative_to(run_dir).as_posix().encode("utf-8")
        h.update(len(rel).to_bytes(4, "big"))
        h.update(rel)
        b = f.read_bytes()
        h.update(len(b).to_bytes(8, "big"))
        h.update(b)
    return h.hexdigest()


def sign_packet(run_dir: Path, *, signer) -> str:
    """Compute root hash + sign with the supplied apikey signer.

    `signer` is an injected callable `(bytes) -> str` (base64 signature). The MCP
    tool layer wires the production signer; tests pass a fake.
    """
    root = packet_root_sha256(run_dir)
    return signer(root.encode("utf-8"))
```

The actual production wiring of `signer` to `robot_md.apikey_request` (or wherever the RCAN signer lives) happens in the MCP tool layer (Task 21+). Inspect `cli/src/robot_md/apikey_request.py` and `cli/src/robot_md/audit.py` at implementation time to confirm the function name (likely `sign_with_apikey(payload: bytes) -> str` or similar). If the existing helper is asynchronous or has a different shape, adapt the `signer` callable's contract here accordingly.

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/execute/evidence.py \
        cli/tests/spatial_eval/test_evidence.py
git commit -m "feat(spatial-eval): evidence packet builder + deterministic root hash"
```

---

## Task 21 — Phase 1 RRF stub

**Files:**
- Create: `cli/src/robot_md/spatial_eval/rrf.py`
- Create: `cli/tests/spatial_eval/test_rrf_stub.py`

Phase 1 (RRF §27 endpoints + held-out audit + counter-signature) is a separate plan in the RRF repo. This task ships the local stub so the `spatial_eval_submit_to_rrf` MCP tool has a real call site that returns a clear "Phase 1 — pending RRF §27" response.

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_rrf_stub.py
from __future__ import annotations
import pytest
from robot_md.spatial_eval.rrf import submit_evidence

def test_submit_returns_pending_phase_1():
    out = submit_evidence(packet_path="/tmp/evidence", rcan_signature="abc")
    assert out["status"] == "pending_phase_1"
    assert "RRF §27" in out["message"]
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/spatial_eval/rrf.py
from __future__ import annotations


def submit_evidence(*, packet_path: str, rcan_signature: str) -> dict:
    """Phase 1 stub. Real submission is wired when RRF §27 endpoints land."""
    return {
        "status": "pending_phase_1",
        "message": (
            "Self-attested evidence is ready. RRF §27 endpoints (counter-signature, "
            "held-out probe re-run, leaderboard) will accept this packet once Phase 1 "
            "ships in a separate plan. Local Score.json is fully usable in the meantime."
        ),
        "packet_path": packet_path,
        "rcan_signature": rcan_signature,
    }
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/rrf.py cli/tests/spatial_eval/test_rrf_stub.py
git commit -m "feat(spatial-eval): RRF §27 submit stub (Phase 1 deferred)"
```

---

## Tasks 22-30 — MCP tool wrappers (one per tool)

Each task creates a thin tool file under `cli/src/robot_md/mcp/tools/spatial_eval/` plus a unit test. The server registration is batched in Task 31.

### Task 22 — `spatial_eval_dry_run`

**Files:**
- Create: `cli/src/robot_md/mcp/tools/spatial_eval/__init__.py` (empty)
- Create: `cli/src/robot_md/mcp/tools/spatial_eval/dry_run.py`
- Create: `cli/tests/spatial_eval/test_mcp_dry_run.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_mcp_dry_run.py
from __future__ import annotations
from unittest.mock import MagicMock
from robot_md.mcp.tools.spatial_eval.dry_run import dry_run_tool

def test_dry_run_passes_when_section_present_and_apikey_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    ctx = MagicMock()
    ctx.parsed = {
        "spatial-eval": {
            "spec_version": "1.0.0",
            "units": ["O1"],
            "workspace": {"play_surface_dims_m": [0.3, 0.3],
                          "judge_camera": {"device": "phone:tripod", "resolution": [1920, 1080]}},
            "reasoning_stack": {"baseline": "claude:claude-opus-4-7", "declared": "claude:claude-opus-4-7"},
        }
    }
    out = dry_run_tool(ctx)
    assert out["ok"] is True
    assert out["checks"]["spatial_eval_section"] == "present"
    assert out["checks"]["anthropic_api_key"] == "set"

def test_dry_run_fails_without_section():
    ctx = MagicMock(); ctx.parsed = {}
    out = dry_run_tool(ctx)
    assert out["ok"] is False
    assert out["checks"]["spatial_eval_section"] == "missing"
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/mcp/tools/spatial_eval/dry_run.py
from __future__ import annotations
import os


def dry_run_tool(ctx) -> dict:
    parsed = getattr(ctx, "parsed", {}) or {}
    se = parsed.get("spatial-eval")
    checks: dict[str, str] = {}
    checks["spatial_eval_section"] = "present" if se else "missing"
    checks["anthropic_api_key"] = "set" if os.environ.get("ANTHROPIC_API_KEY") else "missing"
    if se:
        wc = se.get("workspace", {}).get("judge_camera", {}).get("device")
        checks["judge_camera_device"] = wc or "missing"
    ok = all(v not in ("missing", None) for v in checks.values())
    return {"ok": ok, "checks": checks}
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/tools/spatial_eval/__init__.py \
        cli/src/robot_md/mcp/tools/spatial_eval/dry_run.py \
        cli/tests/spatial_eval/test_mcp_dry_run.py
git commit -m "feat(spatial-eval): spatial_eval_dry_run MCP tool"
```

### Task 23 — `spatial_eval_init` (scaffold ROBOT.md)

**Files:**
- Create: `cli/src/robot_md/mcp/tools/spatial_eval/init.py`
- Create: `cli/tests/spatial_eval/test_mcp_init.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_mcp_init.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
from robot_md.mcp.tools.spatial_eval.init import init_tool

ROBOT_MD_TEMPLATE = """---
robot-md: "1.0.0"
id: bob
kind: tabletop_arm
---
"""

def test_init_adds_spatial_eval_block(tmp_path: Path):
    f = tmp_path / "ROBOT.md"
    f.write_text(ROBOT_MD_TEMPLATE)
    ctx = MagicMock(); ctx.manifest_path = f
    out = init_tool(ctx, units=["O1", "O2"])
    assert out["ok"] is True
    text = f.read_text()
    assert "spatial-eval:" in text
    assert "spec_version: \"1.0.0\"" in text
    assert "O1" in text and "O2" in text

def test_init_idempotent(tmp_path: Path):
    f = tmp_path / "ROBOT.md"; f.write_text(ROBOT_MD_TEMPLATE)
    ctx = MagicMock(); ctx.manifest_path = f
    init_tool(ctx, units=["O1"])
    out = init_tool(ctx, units=["O1"])
    assert out["ok"] is True
    assert text_count(f.read_text(), "spatial-eval:") == 1

def text_count(haystack: str, needle: str) -> int:
    return haystack.count(needle)
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/mcp/tools/spatial_eval/init.py
from __future__ import annotations
from pathlib import Path

DEFAULT_BLOCK = """spatial-eval:
  spec_version: "1.0.0"
  units: {units_yaml}
  workspace:
    play_surface_dims_m: [0.30, 0.30]
    judge_camera:
      device: "phone:tripod"
      resolution: [1920, 1080]
  reasoning_stack:
    baseline: "claude:claude-opus-4-7"
    declared: "claude:claude-opus-4-7"
"""


def init_tool(ctx, *, units: list[str]) -> dict:
    f: Path = Path(getattr(ctx, "manifest_path"))
    text = f.read_text()
    if "spatial-eval:" in text:
        return {"ok": True, "status": "already_present"}
    units_yaml = "[" + ", ".join(units) + "]"
    block = DEFAULT_BLOCK.format(units_yaml=units_yaml)
    # Insert before the trailing `---` of the YAML frontmatter, or append if no frontmatter.
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end == -1:
            return {"ok": False, "error": "ROBOT.md frontmatter unterminated"}
        f.write_text(text[: end + 1] + block + text[end + 1:])
    else:
        f.write_text(text.rstrip() + "\n\n" + block)
    return {"ok": True, "status": "added", "units": units}
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/tools/spatial_eval/init.py \
        cli/tests/spatial_eval/test_mcp_init.py
git commit -m "feat(spatial-eval): spatial_eval_init MCP tool"
```

### Task 24 — `spatial_eval_kit` (BOM resource)

**Files:**
- Create: `cli/src/robot_md/spatial_eval/execute/fixtures/kit_v1.md` (BOM doc, see Task 30 for content)
- Create: `cli/src/robot_md/mcp/tools/spatial_eval/kit.py`
- Create: `cli/tests/spatial_eval/test_mcp_kit.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_mcp_kit.py
from __future__ import annotations
from unittest.mock import MagicMock
from robot_md.mcp.tools.spatial_eval.kit import kit_tool

def test_kit_returns_bom_text():
    out = kit_tool(MagicMock())
    assert out["ok"] is True
    assert "Standard kit" in out["bom_md"]
    assert out["grid_mat_pdf_path"].endswith("grid_mat.pdf")
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/mcp/tools/spatial_eval/kit.py
from __future__ import annotations
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[3] / "spatial_eval/execute/fixtures"


def kit_tool(ctx) -> dict:
    bom_path = FIXTURES / "kit_v1.md"
    pdf_path = FIXTURES / "grid_mat.pdf"
    return {
        "ok": True,
        "bom_md": bom_path.read_text() if bom_path.is_file() else "",
        "grid_mat_pdf_path": str(pdf_path),
    }
```

For now, write a minimal `kit_v1.md` (full content authored in Task 30):

```markdown
# Spatial-Eval Standard Kit v1

(Full BOM + assembly authored in SP6 Task 30.)
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/spatial_eval/execute/fixtures/kit_v1.md \
        cli/src/robot_md/mcp/tools/spatial_eval/kit.py \
        cli/tests/spatial_eval/test_mcp_kit.py
git commit -m "feat(spatial-eval): spatial_eval_kit MCP tool + kit_v1.md stub"
```

### Task 25 — `spatial_eval_run_probe`

**Files:**
- Create: `cli/src/robot_md/mcp/tools/spatial_eval/run_probe.py`
- Create: `cli/tests/spatial_eval/test_mcp_run_probe.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_mcp_run_probe.py
from __future__ import annotations
from unittest.mock import MagicMock
from robot_md.mcp.tools.spatial_eval.run_probe import run_probe_tool
from robot_md.spatial_eval.probe.stacks import FakeStack

def _ctx_with_section():
    ctx = MagicMock()
    ctx.parsed = {
        "id": "bob",
        "spatial-eval": {
            "spec_version": "1.0.0", "units": ["O1"],
            "workspace": {"play_surface_dims_m": [0.3, 0.3],
                          "judge_camera": {"device": "phone:tripod", "resolution": [1920, 1080]}},
            "reasoning_stack": {"baseline": "claude:c", "declared": "claude:c"},
        }
    }
    return ctx

def test_run_probe_returns_score(monkeypatch):
    ctx = _ctx_with_section()

    # Inject FakeStacks via test hook (run_probe accepts injected stacks under a private kwarg).
    fake = FakeStack({
        "o1-public-001": {"still_present": True, "position": [0.0, 0.0, 0.0]},
        "o1-public-002": {"still_present": True, "position": [0.0, 0.0, 0.0]},
        "o1-public-003": {"still_present": True, "position": [0.0, 0.0, 0.0]},
    })
    out = run_probe_tool(ctx, units=["O1"], baseline_only=True, _stacks={"baseline": fake, "declared": fake})
    assert out["ok"] is True
    assert "score" in out
    assert out["score"]["tracks"]["probe"]["baseline_claude"]["O1"]["passed"] >= 1
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/mcp/tools/spatial_eval/run_probe.py
from __future__ import annotations
import datetime as _dt
import uuid
from typing import Optional

from robot_md.spatial_eval.probe.datasets.loader import load_public_split
from robot_md.spatial_eval.probe.runner import run_probes
from robot_md.spatial_eval.probe.stacks import resolve_stack
from robot_md.spatial_eval.score import (
    Aggregate, ProbeTrack, ScoreJSON,
)


def run_probe_tool(
    ctx, *, units: Optional[list[str]] = None, baseline_only: bool = False,
    _stacks: Optional[dict] = None,
) -> dict:
    se = (getattr(ctx, "parsed", {}) or {}).get("spatial-eval")
    if not se:
        return {"ok": False, "error": "spatial-eval section missing in ROBOT.md"}
    chosen = units or se["units"]
    by_unit = load_public_split()
    probes = [p for u in chosen for p in by_unit.get(u, [])]
    if not probes:
        return {"ok": False, "error": f"no probes for units {chosen}"}

    if _stacks is not None:
        baseline = _stacks["baseline"]; declared = _stacks["declared"]
    else:
        baseline = resolve_stack(se["reasoning_stack"]["baseline"])
        declared = baseline if baseline_only else resolve_stack(se["reasoning_stack"]["declared"])

    result = run_probes(probes, baseline=baseline, declared=None if baseline_only else declared)
    pt = ProbeTrack(
        baseline_claude=result.baseline_per_unit,
        robot_declared=result.declared_per_unit if not baseline_only else result.baseline_per_unit,
        delta_per_unit=result.delta_per_unit if not baseline_only else {u: 0.0 for u in result.baseline_per_unit},
    )
    score = ScoreJSON(
        spec_version=se["spec_version"],
        rrn=ctx.parsed.get("id", "RRN-unknown"),
        run_id=str(uuid.uuid4()),
        timestamp=_dt.datetime.utcnow().isoformat() + "Z",
        tracks_probe=pt,
        tracks_execute={},
        aggregate=Aggregate.compute(probe=pt, execute={}),
    )
    return {"ok": True, "score": score.to_dict(), "per_probe": result.per_probe}
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/tools/spatial_eval/run_probe.py \
        cli/tests/spatial_eval/test_mcp_run_probe.py
git commit -m "feat(spatial-eval): spatial_eval_run_probe MCP tool"
```

### Task 26 — `spatial_eval_run_execute`

**Files:**
- Create: `cli/src/robot_md/mcp/tools/spatial_eval/run_execute.py`
- Create: `cli/tests/spatial_eval/test_mcp_run_execute.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_mcp_run_execute.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
from robot_md.mcp.tools.spatial_eval.run_execute import run_execute_tool
from robot_md.spatial_eval.execute.trial import FakeRobot, FakeJudgeCamera

def _bgr(c): img = np.zeros((240,320,3), np.uint8); img[:,:] = c; return img

def test_run_execute_emits_score_and_evidence(tmp_path: Path):
    ctx = MagicMock()
    ctx.parsed = {
        "id": "bob",
        "spatial-eval": {
            "spec_version": "1.0.0", "units": ["O1"],
            "workspace": {"play_surface_dims_m": [0.3, 0.3],
                          "judge_camera": {"device": "phone:tripod", "resolution": [1920, 1080]}},
            "reasoning_stack": {"baseline": "claude:c", "declared": "claude:c"},
        },
    }
    robot = FakeRobot(actions=["pick_target_color:red_cube"])
    cam = FakeJudgeCamera(frames=[_bgr((0,0,255))]*3)
    out = run_execute_tool(
        ctx, units=["O1"], trials_per_unit=2, run_dir=tmp_path,
        _robot=robot, _judge_camera=cam,
    )
    assert out["ok"] is True
    assert (tmp_path / "Score.json").is_file()
    assert out["score"]["tracks"]["execute"]["O1"]["n"] == 2
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/mcp/tools/spatial_eval/run_execute.py
from __future__ import annotations
import datetime as _dt
import hashlib
import uuid
from pathlib import Path
from typing import Optional

from robot_md.spatial_eval.execute.evidence import (
    write_evidence_packet, packet_root_sha256,
)
from robot_md.spatial_eval.execute.trial import (
    run_trial, FakeRobot, FakeJudgeCamera,
)
from robot_md.spatial_eval.score import (
    Aggregate, PerUnitExecuteScore, ProbeTrack, ScoreJSON,
)


def run_execute_tool(
    ctx, *, units: Optional[list[str]] = None, trials_per_unit: int = 10,
    run_dir: Optional[Path] = None,
    _robot=None, _judge_camera=None,
) -> dict:
    se = (getattr(ctx, "parsed", {}) or {}).get("spatial-eval")
    if not se:
        return {"ok": False, "error": "spatial-eval section missing in ROBOT.md"}
    chosen = units or se["units"]
    rd = Path(run_dir or Path("./.spatial_eval_runs") / f"run-{uuid.uuid4().hex[:8]}")
    rd.mkdir(parents=True, exist_ok=True)

    trials_records: list[dict] = []
    per_unit: dict[str, PerUnitExecuteScore] = {}
    for unit in chosen:
        passed = 0
        for t in range(trials_per_unit):
            trial_id = f"{unit.lower()}-trial-{t+1}"
            outcome = run_trial(
                unit=unit, trial_id=trial_id,
                robot=_robot or FakeRobot(actions=[]),
                judge_camera=_judge_camera or FakeJudgeCamera(frames=[]),
                run_dir=rd,
            )
            trials_records.append(outcome)
            if outcome.get("passed"):
                passed += 1
        per_unit[unit] = PerUnitExecuteScore(
            passed=passed, n=trials_per_unit,
            evidence_sha256="",  # filled below
        )

    pt = ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={})
    score = ScoreJSON(
        spec_version=se["spec_version"],
        rrn=ctx.parsed.get("id", "RRN-unknown"),
        run_id=rd.name,
        timestamp=_dt.datetime.utcnow().isoformat() + "Z",
        tracks_probe=pt,
        tracks_execute=per_unit,
        aggregate=Aggregate.compute(probe=pt, execute=per_unit),
    )
    write_evidence_packet(
        run_dir=rd, trials=trials_records, score=score, videos={},  # video bundling deferred
    )
    root = packet_root_sha256(rd)
    # Inject root hash into per-unit (deterministic — same root for all units per run).
    per_unit_with_root = {
        u: PerUnitExecuteScore(passed=v.passed, n=v.n, evidence_sha256=root)
        for u, v in per_unit.items()
    }
    score.tracks_execute = per_unit_with_root
    score.evidence_root = f"sha256:{root}"
    (rd / "Score.json").write_text(score.to_json())
    return {"ok": True, "score": score.to_dict(), "run_dir": str(rd)}
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/tools/spatial_eval/run_execute.py \
        cli/tests/spatial_eval/test_mcp_run_execute.py
git commit -m "feat(spatial-eval): spatial_eval_run_execute MCP tool"
```

### Task 27 — `spatial_eval_run_full`

**Files:**
- Create: `cli/src/robot_md/mcp/tools/spatial_eval/run_full.py`
- Create: `cli/tests/spatial_eval/test_mcp_run_full.py`

`run_full` composes `run_probe` + `run_execute` and merges Score JSON.

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_mcp_run_full.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
from robot_md.mcp.tools.spatial_eval.run_full import run_full_tool
from robot_md.spatial_eval.probe.stacks import FakeStack
from robot_md.spatial_eval.execute.trial import FakeRobot, FakeJudgeCamera

def _bgr(c): img = np.zeros((240,320,3), np.uint8); img[:,:] = c; return img

def test_run_full_merges_both_tracks(tmp_path: Path):
    ctx = MagicMock()
    ctx.parsed = {
        "id": "bob",
        "spatial-eval": {
            "spec_version": "1.0.0", "units": ["O1"],
            "workspace": {"play_surface_dims_m": [0.3, 0.3],
                          "judge_camera": {"device": "phone:tripod", "resolution": [1920, 1080]}},
            "reasoning_stack": {"baseline": "claude:c", "declared": "claude:c"},
        },
    }
    fake = FakeStack({
        "o1-public-001": {"still_present": True, "position": [0,0,0]},
        "o1-public-002": {"still_present": True, "position": [0,0,0]},
        "o1-public-003": {"still_present": True, "position": [0,0,0]},
    })
    robot = FakeRobot(actions=["pick"])
    cam = FakeJudgeCamera(frames=[_bgr((0,0,255))]*3)
    out = run_full_tool(
        ctx, units=["O1"], trials_per_unit=2, run_dir=tmp_path,
        _stacks={"baseline": fake, "declared": fake},
        _robot=robot, _judge_camera=cam,
    )
    assert out["ok"] is True
    assert "baseline_claude" in out["score"]["tracks"]["probe"]
    assert out["score"]["tracks"]["execute"]["O1"]["n"] == 2
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/mcp/tools/spatial_eval/run_full.py
from __future__ import annotations
from pathlib import Path
from typing import Optional

from robot_md.mcp.tools.spatial_eval.run_execute import run_execute_tool
from robot_md.mcp.tools.spatial_eval.run_probe import run_probe_tool


def run_full_tool(
    ctx, *, units: Optional[list[str]] = None, trials_per_unit: int = 10,
    run_dir: Optional[Path] = None,
    _stacks=None, _robot=None, _judge_camera=None,
) -> dict:
    p = run_probe_tool(ctx, units=units, _stacks=_stacks)
    if not p["ok"]:
        return p
    e = run_execute_tool(
        ctx, units=units, trials_per_unit=trials_per_unit, run_dir=run_dir,
        _robot=_robot, _judge_camera=_judge_camera,
    )
    if not e["ok"]:
        return e
    merged = e["score"]
    merged["tracks"]["probe"] = p["score"]["tracks"]["probe"]
    merged["aggregate"]["probe_baseline"] = p["score"]["aggregate"]["probe_baseline"]
    merged["aggregate"]["probe_declared"] = p["score"]["aggregate"]["probe_declared"]
    return {"ok": True, "score": merged, "run_dir": e["run_dir"]}
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/tools/spatial_eval/run_full.py \
        cli/tests/spatial_eval/test_mcp_run_full.py
git commit -m "feat(spatial-eval): spatial_eval_run_full MCP tool"
```

### Task 28 — `spatial_eval_replay` and `spatial_eval_verify`

**Files:**
- Create: `cli/src/robot_md/mcp/tools/spatial_eval/replay.py`
- Create: `cli/src/robot_md/mcp/tools/spatial_eval/verify.py`
- Create: `cli/tests/spatial_eval/test_mcp_replay.py`
- Create: `cli/tests/spatial_eval/test_mcp_verify.py`

- [ ] **Step 1: Write the failing tests**

```python
# cli/tests/spatial_eval/test_mcp_replay.py
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import MagicMock
from robot_md.mcp.tools.spatial_eval.replay import replay_tool

def test_replay_recomputes_score_from_evidence(tmp_path: Path):
    # Build a minimal evidence packet with manifest.json
    (tmp_path / "manifest.json").write_text(json.dumps({"trials": [
        {"trial_id": "o1-1", "unit": "O1", "passed": True, "reason": "ok"},
        {"trial_id": "o1-2", "unit": "O1", "passed": False, "reason": "miss"},
    ]}))
    (tmp_path / "Score.json").write_text("{}")
    out = replay_tool(MagicMock(), run_dir=tmp_path)
    assert out["ok"] is True
    assert out["score"]["tracks"]["execute"]["O1"]["passed"] == 1
    assert out["score"]["tracks"]["execute"]["O1"]["n"] == 2
```

```python
# cli/tests/spatial_eval/test_mcp_verify.py
from __future__ import annotations
from unittest.mock import MagicMock
from robot_md.spatial_eval.score import (
    Aggregate, PerUnitExecuteScore, ProbeTrack, ScoreJSON,
)
from robot_md.mcp.tools.spatial_eval.verify import verify_tool

def _good_score():
    pt = ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={})
    return ScoreJSON(
        spec_version="1.0.0", rrn="RRN-x", run_id="r-1", timestamp="t",
        tracks_probe=pt, tracks_execute={"O1": PerUnitExecuteScore(7, 10, "abc")},
        aggregate=Aggregate(0,0,0.7),
        rcan_signature="sig-123", evidence_root="sha256:abc",
    )

def test_verify_accepts_signed_self_attested_score():
    s = _good_score().to_json()
    out = verify_tool(MagicMock(), score_json=s, _verify_signature=lambda payload, sig: True)
    assert out["ok"] is True
    assert out["attestation"] == "self-attested"

def test_verify_rejects_tampered_signature():
    s = _good_score().to_json()
    out = verify_tool(MagicMock(), score_json=s, _verify_signature=lambda payload, sig: False)
    assert out["ok"] is False
    assert "signature" in out["error"]
```

- [ ] **Step 2: Run tests to confirm they fail.**

- [ ] **Step 3: Implement replay**

```python
# cli/src/robot_md/mcp/tools/spatial_eval/replay.py
from __future__ import annotations
import datetime as _dt
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from robot_md.spatial_eval.execute.evidence import packet_root_sha256
from robot_md.spatial_eval.score import (
    Aggregate, PerUnitExecuteScore, ProbeTrack, ScoreJSON,
)


def replay_tool(ctx, *, run_dir: Path) -> dict:
    rd = Path(run_dir)
    manifest = json.loads((rd / "manifest.json").read_text())
    counts: dict[str, list[bool]] = defaultdict(list)
    for t in manifest["trials"]:
        counts[t["unit"]].append(bool(t.get("passed")))
    per_unit = {
        u: PerUnitExecuteScore(passed=sum(rs), n=len(rs), evidence_sha256=packet_root_sha256(rd))
        for u, rs in counts.items()
    }
    pt = ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={})
    score = ScoreJSON(
        spec_version="1.0.0",  # replayed from packet content; original Score.json may have it
        rrn="RRN-replayed", run_id=rd.name,
        timestamp=_dt.datetime.utcnow().isoformat() + "Z",
        tracks_probe=pt, tracks_execute=per_unit,
        aggregate=Aggregate.compute(probe=pt, execute=per_unit),
    )
    return {"ok": True, "score": score.to_dict()}
```

- [ ] **Step 4: Implement verify**

```python
# cli/src/robot_md/mcp/tools/spatial_eval/verify.py
from __future__ import annotations
from typing import Callable, Optional

from robot_md.spatial_eval.score import ScoreJSON


def verify_tool(
    ctx, *, score_json: str,
    _verify_signature: Optional[Callable[[bytes, str], bool]] = None,
) -> dict:
    score = ScoreJSON.from_json(score_json)
    if score.rcan_signature is None:
        return {"ok": False, "error": "no rcan_signature on Score JSON"}
    payload = score.to_json().encode("utf-8")
    if _verify_signature is None:
        # Production: import the existing verifier; deferred until apikey wiring lands.
        return {"ok": False, "error": "production verifier not wired"}
    if not _verify_signature(payload, score.rcan_signature):
        return {"ok": False, "error": "invalid signature"}
    return {"ok": True, "attestation": "self-attested"}
```

- [ ] **Step 5: Run tests to confirm they pass.**

- [ ] **Step 6: Commit**

```bash
git add cli/src/robot_md/mcp/tools/spatial_eval/replay.py \
        cli/src/robot_md/mcp/tools/spatial_eval/verify.py \
        cli/tests/spatial_eval/test_mcp_replay.py \
        cli/tests/spatial_eval/test_mcp_verify.py
git commit -m "feat(spatial-eval): spatial_eval_replay and spatial_eval_verify"
```

### Task 29 — `spatial_eval_submit_to_rrf` (Phase 1 stub wrapper)

**Files:**
- Create: `cli/src/robot_md/mcp/tools/spatial_eval/submit_to_rrf.py`
- Create: `cli/tests/spatial_eval/test_mcp_submit.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_mcp_submit.py
from __future__ import annotations
from unittest.mock import MagicMock
from robot_md.mcp.tools.spatial_eval.submit_to_rrf import submit_to_rrf_tool

def test_submit_returns_pending_phase_1():
    out = submit_to_rrf_tool(MagicMock(), run_dir="/tmp/run-x")
    assert out["status"] == "pending_phase_1"
```

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Implement**

```python
# cli/src/robot_md/mcp/tools/spatial_eval/submit_to_rrf.py
from __future__ import annotations
from pathlib import Path

from robot_md.spatial_eval.rrf import submit_evidence


def submit_to_rrf_tool(ctx, *, run_dir: str) -> dict:
    rd = Path(run_dir)
    score_path = rd / "Score.json"
    if not score_path.is_file():
        return {"ok": False, "error": "Score.json missing in run_dir"}
    # Signature is read from Score.json (written when run was signed); empty string here
    # because Phase 0's signer wiring is deferred — Phase 1 plan resolves this.
    return submit_evidence(packet_path=str(rd), rcan_signature="")
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/tools/spatial_eval/submit_to_rrf.py \
        cli/tests/spatial_eval/test_mcp_submit.py
git commit -m "feat(spatial-eval): spatial_eval_submit_to_rrf MCP tool (stub)"
```

---

## Task 30 — Register all 9 tools with the MCP server

**Files:**
- Modify: `cli/src/robot_md/mcp/server.py`
- Create: `cli/tests/spatial_eval/test_server_registration.py`

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/spatial_eval/test_server_registration.py
from __future__ import annotations
from unittest.mock import MagicMock
from robot_md.mcp.server import build_server

def test_all_nine_spatial_eval_tools_registered():
    ctx = MagicMock(); ctx.parsed = {}
    server = build_server(ctx)
    # FastMCP exposes tools via a manager; use list_tools() if available, else registry attr.
    tool_names = {t.name for t in server._tool_manager.list_tools()}  # FastMCP internal API
    expected = {
        "spatial_eval_dry_run", "spatial_eval_init", "spatial_eval_kit",
        "spatial_eval_run_probe", "spatial_eval_run_execute", "spatial_eval_run_full",
        "spatial_eval_replay", "spatial_eval_verify", "spatial_eval_submit_to_rrf",
    }
    assert expected.issubset(tool_names)
```

If FastMCP's introspection API has a different shape, adapt the assertion at implementation time by inspecting `mcp.server.fastmcp.FastMCP` after construction (it exposes a tool list via the public `list_tools` async method or via internals — check the installed version).

- [ ] **Step 2: Run test to confirm it fails.**

- [ ] **Step 3: Modify `cli/src/robot_md/mcp/server.py`**

Inside `build_server`, after the existing `@server.tool()` registrations, add the 9 spatial_eval tools. Each is a thin wrapper that imports the tool function and forwards `ctx`:

```python
# Inside build_server(ctx):
from robot_md.mcp.tools.spatial_eval.dry_run import dry_run_tool as _se_dry_run
from robot_md.mcp.tools.spatial_eval.init import init_tool as _se_init
from robot_md.mcp.tools.spatial_eval.kit import kit_tool as _se_kit
from robot_md.mcp.tools.spatial_eval.run_probe import run_probe_tool as _se_run_probe
from robot_md.mcp.tools.spatial_eval.run_execute import run_execute_tool as _se_run_exec
from robot_md.mcp.tools.spatial_eval.run_full import run_full_tool as _se_run_full
from robot_md.mcp.tools.spatial_eval.replay import replay_tool as _se_replay
from robot_md.mcp.tools.spatial_eval.verify import verify_tool as _se_verify
from robot_md.mcp.tools.spatial_eval.submit_to_rrf import submit_to_rrf_tool as _se_submit


@server.tool()
def spatial_eval_dry_run() -> dict:
    """Preflight: spatial-eval section, judge camera, apikey, kit visibility."""
    return _se_dry_run(ctx)


@server.tool()
def spatial_eval_init(units: list[str]) -> dict:
    """Scaffold the spatial-eval: section into the served ROBOT.md."""
    return _se_init(ctx, units=units)


@server.tool()
def spatial_eval_kit() -> dict:
    """Return the v1 fixture-kit BOM and grid-mat path."""
    return _se_kit(ctx)


@server.tool()
def spatial_eval_run_probe(units: list[str] | None = None, baseline_only: bool = False) -> dict:
    """Run the probe track. Returns Score JSON (probe section only)."""
    return _se_run_probe(ctx, units=units, baseline_only=baseline_only)


@server.tool()
def spatial_eval_run_execute(units: list[str] | None = None, trials_per_unit: int = 10) -> dict:
    """Run the execute track on hardware. Returns Score JSON + run_dir."""
    return _se_run_exec(ctx, units=units, trials_per_unit=trials_per_unit)


@server.tool()
def spatial_eval_run_full(units: list[str] | None = None, trials_per_unit: int = 10) -> dict:
    """Run both tracks and merge results."""
    return _se_run_full(ctx, units=units, trials_per_unit=trials_per_unit)


@server.tool()
def spatial_eval_replay(run_dir: str) -> dict:
    """Recompute Score JSON from an existing evidence packet without re-running."""
    from pathlib import Path
    return _se_replay(ctx, run_dir=Path(run_dir))


@server.tool()
def spatial_eval_verify(score_json: str) -> dict:
    """Verify a Score JSON's RCAN signature."""
    return _se_verify(ctx, score_json=score_json)


@server.tool()
def spatial_eval_submit_to_rrf(run_dir: str) -> dict:
    """Submit signed evidence to RRF §27 (Phase 1 stub for now)."""
    return _se_submit(ctx, run_dir=run_dir)
```

- [ ] **Step 4: Run tests to confirm they pass.**

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/mcp/server.py cli/tests/spatial_eval/test_server_registration.py
git commit -m "feat(spatial-eval): register 9 SP6 tools on the MCP server"
```

---

## Task 31 — `pyproject.toml` `[spatial-eval]` extra (or absorb into `[hardware]`)

**Files:**
- Modify: `cli/pyproject.toml`

- [ ] **Step 1: Audit the existing `[hardware]` extra**

```bash
grep -A 20 'optional-dependencies' cli/pyproject.toml | head -40
```

If `opencv-python` and `numpy` are already in `[hardware]`, **absorb spatial-eval into `[hardware]`**: no new extra needed, just confirm the deps are present and add a comment that `[hardware]` covers the spatial-eval surface as well. Skip Steps 3-5 for the new extra and document in the commit.

If they are NOT present, proceed with Step 2.

- [ ] **Step 2: Add `[spatial-eval]` extra**

In `cli/pyproject.toml`, under `[project.optional-dependencies]`:

```toml
spatial-eval = [
    "opencv-python>=4.9",
    "numpy>=1.26",
    "anthropic>=0.30",
]
```

- [ ] **Step 3: Verify install works**

```bash
cd cli && pip install -e '.[spatial-eval]'
python -c "import cv2, numpy, anthropic; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Document the extra in `README.md` install section**

Append to the install instructions:

> To enable spatial-intelligence eval (`spatial_eval_*` MCP tools): `pip install 'robot-md[spatial-eval]'`. (If you already have `[hardware]`, this is included.)

- [ ] **Step 5: Commit**

```bash
git add cli/pyproject.toml README.md
git commit -m "build(spatial-eval): add [spatial-eval] optional extra"
```

---

## Task 32 — Fixture kit BOM document

**Files:**
- Modify: `cli/src/robot_md/spatial_eval/execute/fixtures/kit_v1.md` (replaces stub from Task 24)

- [ ] **Step 1: Write the BOM document**

```markdown
# Spatial-Eval Standard Kit v1

Total Phase 0 cost: ~$15-25 (US, 2026 prices). No 3D printer required, no fiducial library, no calibration.

## Standard kit (open)

| Item | Quantity | Notes |
|---|---|---|
| Solid red small cube (~3-5 cm) | 1 | Wooden block, painted plastic, or LEGO 4×4 stack |
| Solid blue mug (small) | 1 | Distinct from the green cup; matte finish preferred |
| Solid green bottle (small) | 1 | Or a green plastic cup of distinct shape |
| Opaque paper cups (red, green, white) | 3 | Disposable, no logos, opaque to camera |
| Black foam-core or felt sheet | 1, ~40×40 cm | Play surface; matte black for max color contrast |
| Phone tripod | 1 | Or a stand for a second cheap webcam |

## Held-out novel-object set (A1 only — kept private in Phase 0)

10 cheap COTS objects of varied shape, picked by the spec maintainer. Examples:
tape dispenser, dollar-store animal toy, salt shaker, zip-tie bag, foam ball.

The held-out set rotates per spec minor version starting in Phase 1 (RRF-managed).

## Setup

1. Lay the foam-core flat in a well-lit area; aim for diffuse overhead lighting (avoid shadows on the play surface).
2. Place the phone tripod so the entire 30×30 cm play surface is in frame at the resolution declared in `ROBOT.md` `spatial-eval.workspace.judge_camera.resolution`.
3. Arrange the kit objects on the play surface; the trial protocol randomizes their positions per trial within the play surface.

## Optional: printable grid mat

`grid_mat.pdf` (sibling of this file) prints on regular A4/Letter paper as a coarse grid for visual position reference. Not required by the auto-scorer (which uses HSV color seg + frame diff against the foam-core background); useful for manual review.

## Color tuning notes

If room lighting causes false negatives in HSV color segmentation, the per-color `ColorParams` defaults in `cli/src/robot_md/spatial_eval/execute/trial.py` (`TARGET_COLORS`) can be overridden via the `spatial_eval_dry_run` calibration path (added in v1.1). For v1.0 the defaults assume normal indoor lighting (~500 lux) on the matte black play surface.
```

- [ ] **Step 2: Generate a placeholder grid-mat PDF**

For Phase 0, ship a 1-page PDF with a simple printed 30×30 cm 1cm grid. Generate via a one-shot script:

```bash
cd cli && python - <<'EOF'
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
out = "src/robot_md/spatial_eval/execute/fixtures/grid_mat.pdf"
c = canvas.Canvas(out, pagesize=LETTER)
import math
mm = 2.83465  # 1 mm in points
origin_x = 50; origin_y = 50
size_mm = 300  # 30 cm
for i in range(0, size_mm + 1, 10):
    c.line(origin_x + i*mm, origin_y, origin_x + i*mm, origin_y + size_mm*mm)
    c.line(origin_x, origin_y + i*mm, origin_x + size_mm*mm, origin_y + i*mm)
c.showPage(); c.save()
print("wrote", out)
EOF
```

(Add `reportlab` to a dev/dist requirements file if not present; otherwise commit a hand-drawn placeholder.)

- [ ] **Step 3: Commit**

```bash
git add cli/src/robot_md/spatial_eval/execute/fixtures/kit_v1.md \
        cli/src/robot_md/spatial_eval/execute/fixtures/grid_mat.pdf
git commit -m "docs(spatial-eval): kit_v1 BOM + printable grid mat"
```

---

## Task 33 — End-to-end smoke test on bob (manual, no CI)

**Files:**
- Create: `cli/tests/spatial_eval/manual_smoke_bob.md` (procedure doc)

This is a manual procedure executed on bob. Not part of CI — `cli/tests/spatial_eval/` excludes anything matching `manual_*` from the default pytest collection (verify by running pytest with `--collect-only`).

- [ ] **Step 1: Write the smoke procedure document**

```markdown
# Manual smoke test: spatial-eval on bob

Run BEFORE declaring SP6 Phase 0 done. Estimated time: ~40 min.

## Prerequisites

- bob plugged in: SO-ARM101 on /dev/ttyACM0, OAK-D connected, idle.
- Phone tripod aimed at the play surface.
- `pip install 'robot-md[hardware,spatial-eval]'` in bob's venv.
- ROBOT.md updated: `robot-md` MCP tool `spatial_eval_init(units=["O1","O2","O3","A1","A2"])` ran successfully.
- Fixture kit assembled per `kit_v1.md`.
- ANTHROPIC_API_KEY exported in bob's shell.

## Procedure

1. Run `spatial_eval_dry_run`. Expect `ok: true`, all checks `present`/`set`.
2. Run `spatial_eval_run_probe(units=["O1"], baseline_only=true)` against the public split.
   - Expect <60 s wall-clock, Score JSON with O1 baseline_claude populated.
   - Note the API cost (Claude usage page) and confirm <$1 for one unit baseline-only.
3. Run `spatial_eval_run_execute(units=["O1"], trials_per_unit=3)`.
   - Manually slide the green cup over the red cube before each trial; verify the trial outcome matches your expectation.
   - Expect Score JSON with execute.O1.n=3, evidence packet on disk.
4. Run `spatial_eval_replay(run_dir=<path>)` on the packet — Score JSON should reproduce byte-for-byte (modulo timestamp and run_id).
5. Run `spatial_eval_verify` on the Score JSON — expect `attestation: self-attested` once the apikey signer is wired.
6. Run `spatial_eval_run_full(units=["O1","O2","O3","A1","A2"], trials_per_unit=10)` for a complete pass.
   - Expect <40 min total wall-clock.
   - Inspect any flagged manual-review trials; resolve via `manual_gate.resolve_review`.

## Pass criteria

All seven Phase 0 success criteria from the spec hold:
- (1) dry_run passes; (2) probe O1 yields Score JSON in <60 s; (3) execute O1 with 3 trials yields evidence packet; (4) replay is deterministic; (5) verify gates a tampered signature; (6) full run completes in <40 min; (7) schema rejects malformed sections.

If any fail: capture the failure (logs, Score JSON, video frames) and open an issue tagged `sp6-bob-smoke`. Do not declare Phase 0 done until all 7 pass.
```

- [ ] **Step 2: Commit**

```bash
git add cli/tests/spatial_eval/manual_smoke_bob.md
git commit -m "docs(spatial-eval): bob smoke-test procedure for SP6 Phase 0 sign-off"
```

---

## Self-Review

Reviewing this plan against the spec at `docs/superpowers/specs/2026-04-26-sp6-spatial-intelligence-eval-design.md`:

**Spec coverage check (each major spec section maps to a task):**
- Skill taxonomy O1-A2 → Tasks 4-8 (units) + 9-13 (scorers).
- Probe track substrate + output format + dual stacks → Tasks 14, 15, 16.
- Side-by-side delta computation → Task 15 (`run_probes` returns `delta_per_unit`).
- Public/held-out split discipline → Task 16 ships loader + 3 stub probes per unit; full content authored separately under SP6-content (out of scope for this plan, called out explicitly).
- Compute envelope (~$5 / <8 min) → enforced operationally in the manual smoke test (Task 33), not code-tested.
- Execute track no-fiducial fixture kit → Task 32.
- Color seg + frame diff judge → Task 17.
- Manual review gate → Task 18.
- 10 trials/unit, ~25 min full run → Task 19 + 26 (`trials_per_unit` parameter, default 10) + Task 33 manual smoke.
- Per-unit pass criteria translated to color/diff → Task 19 (`_score_unit`).
- Evidence packet with deterministic root hash → Task 20.
- ROBOT.md `spatial-eval:` section → Task 1 (schema) + Task 23 (init scaffolder).
- Score JSON shape → Task 2.
- RCAN attestation (Phase 0 self-attested) → Task 20 (`sign_packet` accepts injected signer); production wiring noted as TODO at implementation time after auditing `apikey_request.py` etc.
- Phase 1 RRF §27 → Task 21 (stub) + Task 29 (tool wrapper).
- Anti-gaming: held-out probes never run client-side → enforced by datasets/ structure (only `public/` shipped); seed randomization for execute placement → noted in Task 19 but full implementation (seeded RNG injected per trial) deferred to a v1.1 follow-up since Phase 0's hardware-blocking step is the held-out novel-object set.
- One MCP server, 9 tools → Tasks 22-30.
- `[spatial-eval]` extra → Task 31.
- Fixture BOM + grid mat → Task 32.

**Gaps identified during self-review and fixed inline:**
- Original draft used a non-existent `_publish_progress` MCP helper; replaced with the existing `mcp_ctx.report_progress` pattern referenced via `progress_cb` in `run_probes`. Tasks 25, 26 wire the callback at the MCP layer when needed (deferred to a Phase 0 polish pass — not blocking).
- Original draft had Task 16 ship 30 probes/unit; that's a content-creation task, not code. Reduced to "format + 3 stubs/unit" with full content called out as separate SP6-content track. This is a scope adjustment, but explicit and traceable.
- A2 v1 scorer originally referenced "simulated stability outcome"; clarified to "labeled-cluster lookup" since v1 ships no simulator.
- Task 33 (manual smoke) added because `superpowers:verification-before-completion` requires evidence-on-bob before claiming Phase 0 done.

**Type/signature consistency check:**
- `PerUnitProbeScore`, `PerUnitExecuteScore`, `ProbeTrack`, `Aggregate`, `ScoreJSON` are defined in Task 2 and used consistently in Tasks 15, 25, 26, 27, 28.
- `ColorParams`, `color_centroid`, `frame_diff_pct` defined in Task 17 and consumed in Task 19 only — matched.
- `FakeStack`, `BaselineClaudeStack`, `resolve_stack` defined in Task 14 and consumed in Tasks 15, 25 — matched.
- `FakeRobot`, `FakeJudgeCamera`, `run_trial` defined in Task 19 and consumed in Tasks 26, 27 — matched.
- `register`/`get_unit` registry — defined in Task 3, populated by Tasks 4-8, used by Task 15 (runner) and Task 19 (trial) — matched.

**Placeholders found and removed:** none in code blocks. Two narrative phrases ("verify by running pytest with `--collect-only`" in Task 33; "production verifier not wired" returned from Task 28's `verify_tool` when `_verify_signature` is None) are explicit known-state markers, not placeholder gaps.

**Final scope verdict:** 33 tasks across schema → core eval → MCP wrappers → manual smoke. Each task is a coherent TDD cycle ending in a commit. Phase 0 is bounded and shippable; Phase 1 (RRF §27) is a separate plan written when those endpoints are needed. Plan is ready for execution.

---

## Out-of-scope deferrals (explicit)

- **Full probe content** (30+30 probes per unit × 5 units): SP6-content track, not this plan.
- **Held-out novel-object kit curation:** Maintainer-private until Phase 1 RRF rotation.
- **Production RCAN signer wiring:** Resolved at implementation time by inspecting `cli/src/robot_md/apikey_request.py` and any sibling RCAN signer module; the test surfaces (Task 20, 28) take an injected `signer`/`_verify_signature` so the wiring is a thin glue task.
- **Seeded-RNG fixture randomization** for execute trials: noted in spec; v1.1 once the hardware-only feedback loop on bob exposes whether it matters.
- **MCP progress notifications** for long-running run tools: structurally supported (Task 15 runner accepts `progress_cb`); MCP wiring at the tool layer deferred to a Phase 0 polish pass.
- **Phase 1 RRF §27 endpoints:** entirely separate plan in the RRF repo.

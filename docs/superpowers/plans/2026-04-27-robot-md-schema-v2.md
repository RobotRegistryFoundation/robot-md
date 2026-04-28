# Plan B — robot-md Schema v2 + Validator Gates + Migration Script

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land robot-md v2.0.0 — a breaking schema refactor that replaces the EU-shaped `compliance` block with `compliance.jurisdictions[]` (discriminated union over `regime`), implements standard-of-conduct gates for EU/R15.06/R15.08, and provides a one-shot migration script for upgrading existing manifests.

**Architecture:** Canonical schema lives at `schema/v2/robot.schema.json` (v1 is frozen at its current shape). The v2 schema is synced via `scripts/sync-schema.sh` to two consumers: `cli/src/robot_md/schemas/v2/robot.schema.json` (Python package) and `site/schema/v2/robot.schema.json` (web-served). The validator (`validate.py`) is bumped to load v2 only — v1 is no longer accepted at runtime per the breaking-change policy. Four downstream modules (`fria.py`, `eu_register.py`, `ifu.py`, `art11.py`) currently read `compliance.annex_iii_basis` and `compliance.fria_ref` flat; they migrate to read via a new `compliance_helpers.py` shim that pulls fields from `jurisdictions[]`. The migration script `scripts/migrate-compliance-v2.py` rewrites old-shape ROBOT.md files in place, with a `--add-r1506` flag for opt-in industrial-conformance declaration.

**Tech Stack:** Python 3.11+, `jsonschema` (Draft 2020-12), `ruamel.yaml` (preserves manifest formatting), `pytest`, `ruff`. Existing test fixtures live in `cli/tests/fixtures/valid/` and `cli/tests/fixtures/invalid/`.

**Spec reference:** `docs/superpowers/specs/2026-04-27-na-compliance-jurisdictions-design.md` (commit 3f5656a).

**Depends on:** Plan A (rcan-spec v3.2 alignment docs + §27) merged. The §27 cross-reference in this plan's CHANGELOG entry assumes Plan A is live.

---

## File Structure

| Path | Action | Purpose |
|---|---|---|
| `schema/v2/robot.schema.json` | Create | Canonical v2 schema. Same as v1 *except* the `compliance` block, which is fully replaced. |
| `cli/src/robot_md/schemas/v2/robot.schema.json` | Create (synced) | Packaged copy of v2 schema, loaded at runtime by `validate.py`. |
| `site/schema/v2/robot.schema.json` | Create (synced) | Web-served copy at `robotmd.dev/schema/v2/`. |
| `scripts/sync-schema.sh` | Modify | Add v2 to the sync set; v1 stays in the script (frozen but still synced for archival completeness). |
| `cli/src/robot_md/validate.py` | Modify | Switch `_load_schema()` to load v2; add validator-layer gates (regime uniqueness, edition warning, audit retention warning). |
| `cli/src/robot_md/compliance_helpers.py` | Create | Helper functions that read jurisdiction-shaped fields. Single source of truth for downstream consumers. |
| `cli/src/robot_md/fria.py` | Modify | Read `annex_iii_basis` via helper. |
| `cli/src/robot_md/eu_register.py` | Modify | Read `annex_iii_basis` and `fria_ref` via helper. |
| `cli/src/robot_md/ifu.py` | Modify | Read `annex_iii_basis` via helper. |
| `cli/src/robot_md/art11.py` | Modify | Read `annex_iii_basis` via helper. |
| `cli/tests/fixtures/valid/compliance_jurisdictions_*.json` | Create | 5 positive fixtures (EU only, R15.06 only, R15.08 PFL, R15.08 SSM, EU+R15.06). |
| `cli/tests/fixtures/invalid/compliance_*.json` | Create | 6 negative fixtures (FRIA gate, R15.06 missing integrator/edition, R15.08 PFL missing limits, R15.08 no modes, duplicate regime). |
| `cli/tests/test_compliance_jurisdictions_v2.py` | Create | Schema fixture tests + validator-layer gate tests. |
| `cli/tests/test_compliance_helpers.py` | Create | Unit tests for helper functions. |
| `cli/tests/unit/test_schema_annex_iii_basis.py` | Modify | Existing test reads flat shape; rewrite to use jurisdictions[] form. |
| `scripts/migrate-compliance-v2.py` | Create | One-shot migration script. |
| `cli/tests/test_migrate_compliance_v2.py` | Create | Unit tests for the migration script. |
| `cli/tests/integration/test_compliance_v2_roundtrip.py` | **Deferred to Plan G** | E2E test requires rcan-py 3.4.0 (Plan C) and RRF backend accepting v2 (Plan E). Lands when bob is migrated. |
| `cli/pyproject.toml` | Modify | Bump version 1.2.4 → 2.0.0. |
| `CHANGELOG.md` | Modify | Add 2.0.0 entry with `BREAKING:` marker. |

---

## Task 1: Bootstrap v2 schema directory

**Files:**
- Create: `schema/v2/robot.schema.json` (initial copy from v1)
- Create: `cli/src/robot_md/schemas/v2/` (empty dir; populated by sync)
- Create: `site/schema/v2/` (empty dir; populated by sync)
- Modify: `scripts/sync-schema.sh`

- [ ] **Step 1: Copy v1 canonical schema to v2 starting point**

```bash
mkdir -p schema/v2 cli/src/robot_md/schemas/v2 site/schema/v2
cp schema/v1/robot.schema.json schema/v2/robot.schema.json
```

- [ ] **Step 2: Bump `$id` and `title` in the new v2 schema**

Use Edit on `schema/v2/robot.schema.json`:
- Change `"$id": "https://robotmd.dev/schema/v1/robot.schema.json"` to `"$id": "https://robotmd.dev/schema/v2/robot.schema.json"`.
- Change `"title": "ROBOT.md frontmatter — v1"` to `"title": "ROBOT.md frontmatter — v2"`.

- [ ] **Step 3: Update `sync-schema.sh` to also sync v2**

Replace the current body of `scripts/sync-schema.sh` with:

```bash
#!/usr/bin/env bash
# Canonical schemas live at schema/v1/robot.schema.json (frozen) and schema/v2/robot.schema.json (current).
# Each is synced to:
#   - cli/src/robot_md/schemas/<v>/robot.schema.json   (bundled with Python package)
#   - site/schema/<v>/robot.schema.json                (served at robotmd.dev/schema/<v>/)
# Run this after editing either canonical schema. CI verifies all copies match.

set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

for v in v1 v2; do
  SRC="$REPO/schema/$v/robot.schema.json"
  if [[ -f "$SRC" ]]; then
    cp "$SRC" "$REPO/cli/src/robot_md/schemas/$v/robot.schema.json"
    cp "$SRC" "$REPO/site/schema/$v/robot.schema.json"
    echo "✓ $v schema synced"
  fi
done
```

- [ ] **Step 4: Run sync to populate the v2 mirror copies**

```bash
bash scripts/sync-schema.sh
```

Expected output:
```
✓ v1 schema synced
✓ v2 schema synced
```

- [ ] **Step 5: Verify the v2 mirror copies exist and match**

```bash
diff -q schema/v2/robot.schema.json cli/src/robot_md/schemas/v2/robot.schema.json
diff -q schema/v2/robot.schema.json site/schema/v2/robot.schema.json
```

Expected: both diffs report no differences (silent).

- [ ] **Step 6: Commit**

```bash
git add schema/v2/ cli/src/robot_md/schemas/v2/ site/schema/v2/ scripts/sync-schema.sh
git commit -m "schema(v2): bootstrap v2 directory as copy of v1"
```

---

## Task 2: Replace `compliance` block in v2 schema — top-level shape only

**Files:**
- Modify: `schema/v2/robot.schema.json`

This task swaps in the new top-level `compliance` shape. The `$defs` for jurisdictions are stubbed in this task and filled in over the next several tasks (TDD-style: each `$def` lands with its positive fixture).

- [ ] **Step 1: Locate the existing `compliance` block in `schema/v2/robot.schema.json`**

Run: `grep -n '"compliance":' schema/v2/robot.schema.json`
Expected: one match around line 468 (matching the v1 layout).

- [ ] **Step 2: Replace the entire `compliance` block**

Find the `"compliance": { ... }` block (it spans roughly lines 468–525 of the v1 layout) and replace it with:

```json
"compliance": {
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "jurisdictions": {
      "type": "array",
      "description": "Legal regimes the robot is declared conformant with. Each entry uses a discriminated union on `regime` (see §27 in rcan-spec v3.2). Order is not significant.",
      "items": {
        "oneOf": [
          { "$ref": "#/$defs/jurisdiction.eu_ai_act" },
          { "$ref": "#/$defs/jurisdiction.ansi_ria_r1506" },
          { "$ref": "#/$defs/jurisdiction.ansi_ria_r1508" }
        ]
      }
    },
    "iso_42001":   { "$ref": "#/$defs/voluntary.iso_42001" },
    "nist_ai_rmf": { "$ref": "#/$defs/voluntary.nist_ai_rmf" },
    "iec_62443":   { "$ref": "#/$defs/voluntary.iec_62443" }
  }
}
```

- [ ] **Step 3: Add empty `$defs` block at the bottom of the schema (before the closing `}`)**

If the schema does not already have a `$defs` key, add one. Otherwise extend it. The block in this task is a stub — actual contents land in subsequent tasks. Add:

```json
"$defs": {
  "uri": {
    "type": "string",
    "description": "RFC 3986 absolute URI: scheme + colon + non-empty path/authority. Pattern is portable across jsonschema installs that do or don't have rfc3987 format extras.",
    "pattern": "^[a-zA-Z][a-zA-Z0-9+.-]*:.+"
  },
  "jurisdiction.eu_ai_act":      { "type": "object", "required": ["regime"], "properties": { "regime": { "const": "eu_ai_act" } } },
  "jurisdiction.ansi_ria_r1506": { "type": "object", "required": ["regime"], "properties": { "regime": { "const": "ansi_ria_r1506" } } },
  "jurisdiction.ansi_ria_r1508": { "type": "object", "required": ["regime"], "properties": { "regime": { "const": "ansi_ria_r1508" } } },
  "voluntary.iso_42001":   { "type": "object", "additionalProperties": true },
  "voluntary.nist_ai_rmf": { "type": "object", "additionalProperties": true },
  "voluntary.iec_62443":   { "type": "object", "additionalProperties": true }
}
```

(These stubs accept any object with the right `regime` value; full validation lands in subsequent tasks.)

- [ ] **Step 4: Sync schema**

```bash
bash scripts/sync-schema.sh
```

- [ ] **Step 5: Sanity-check schema parses as valid JSON**

```bash
python -c "import json; json.load(open('schema/v2/robot.schema.json'))" && echo "OK"
```

Expected: prints `OK` with no traceback.

- [ ] **Step 6: Commit**

```bash
git add schema/v2/ cli/src/robot_md/schemas/v2/ site/schema/v2/
git commit -m "schema(v2): replace compliance block with jurisdictions[] shape (stubbed \$defs)"
```

---

## Task 3: Add full `jurisdiction.eu_ai_act` definition + FRIA gate + fixtures + test

**Files:**
- Modify: `schema/v2/robot.schema.json` (replace the stub with the full definition)
- Create: `cli/tests/fixtures/valid/compliance_jurisdictions_eu_only.json`
- Create: `cli/tests/fixtures/invalid/compliance_eu_annex_iii_no_fria.json`
- Create: `cli/tests/test_compliance_jurisdictions_v2.py`

- [ ] **Step 1: Write the failing test first**

Create `cli/tests/test_compliance_jurisdictions_v2.py` with:

```python
"""Schema fixture tests for the v2 compliance.jurisdictions[] block.

Each positive fixture is a minimal valid manifest with a specific compliance
declaration. Each negative fixture asserts the validator returns the *specific*
schema path of the violation, not just a generic failure.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
VALID_DIR = FIXTURES / "valid"
INVALID_DIR = FIXTURES / "invalid"

SCHEMA_PATH = (
    Path(__file__).parents[1] / "src" / "robot_md" / "schemas" / "v2" / "robot.schema.json"
)


def _schema():
    return json.loads(SCHEMA_PATH.read_text())


def _validate(manifest: dict):
    jsonschema.Draft202012Validator(
        _schema(),
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    ).validate(manifest)


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


# --- positive fixtures: must validate without error ---

@pytest.mark.parametrize("fixture_name", [
    "compliance_jurisdictions_eu_only.json",
])
def test_valid_compliance_fixtures(fixture_name: str):
    _validate(_load(VALID_DIR / fixture_name))


# --- negative fixtures: must fail at the documented schema path ---

@pytest.mark.parametrize("fixture_name,expected_path_fragment", [
    ("compliance_eu_annex_iii_no_fria.json", "fria_ref"),
])
def test_invalid_compliance_fixtures(fixture_name: str, expected_path_fragment: str):
    manifest = _load(INVALID_DIR / fixture_name)
    with pytest.raises(jsonschema.ValidationError) as excinfo:
        _validate(manifest)
    assert expected_path_fragment in str(excinfo.value)
```

- [ ] **Step 2: Create the positive fixture**

Create `cli/tests/fixtures/valid/compliance_jurisdictions_eu_only.json`:

```json
{
  "rcan_version": "3.2",
  "metadata": { "robot_name": "test-bot" },
  "physics": {
    "type": "arm",
    "dof": 1,
    "workspace": { "bounds_mm": { "x": [0, 100], "y": [-50, 50], "z": [0, 100] } },
    "solver": { "ik_provider": "stub" },
    "kinematics": [
      { "id": "j1", "axis": "z", "limits_deg": [-90, 90], "a_mm": 0, "d_mm": 50, "servo_id": 1, "encoder_sign": 1, "zero_pose_steps": 1500 }
    ]
  },
  "drivers": [{ "id": "arm", "protocol": "feetech", "port": "/dev/null" }],
  "safety": {
    "estop": { "software": true, "hardware": false, "response_ms": 50 },
    "max_joint_velocity_dps": 30
  },
  "compliance": {
    "jurisdictions": [
      {
        "regime": "eu_ai_act",
        "risk_assessment_ref": "https://example.org/risk.pdf",
        "annex_iii_basis": "safety_component",
        "fria_ref": "https://example.org/fria.pdf",
        "audit_retention_days": 2555
      }
    ]
  }
}
```

- [ ] **Step 3: Create the negative fixture (annex_iii without fria_ref)**

Create `cli/tests/fixtures/invalid/compliance_eu_annex_iii_no_fria.json`:

```json
{
  "rcan_version": "3.2",
  "metadata": { "robot_name": "test-bot" },
  "physics": {
    "type": "arm",
    "dof": 1,
    "workspace": { "bounds_mm": { "x": [0, 100], "y": [-50, 50], "z": [0, 100] } },
    "solver": { "ik_provider": "stub" },
    "kinematics": [
      { "id": "j1", "axis": "z", "limits_deg": [-90, 90], "a_mm": 0, "d_mm": 50, "servo_id": 1, "encoder_sign": 1, "zero_pose_steps": 1500 }
    ]
  },
  "drivers": [{ "id": "arm", "protocol": "feetech", "port": "/dev/null" }],
  "safety": {
    "estop": { "software": true, "hardware": false, "response_ms": 50 },
    "max_joint_velocity_dps": 30
  },
  "compliance": {
    "jurisdictions": [
      {
        "regime": "eu_ai_act",
        "risk_assessment_ref": "https://example.org/risk.pdf",
        "annex_iii_basis": "safety_component"
      }
    ]
  }
}
```

- [ ] **Step 4: Run tests — expect FAIL (stub def doesn't enforce FRIA gate or risk_assessment_ref)**

```bash
cd cli && pytest tests/test_compliance_jurisdictions_v2.py -v
```

Expected: at least the negative test fails (the stub `$def` accepts any object with `regime: eu_ai_act`).

- [ ] **Step 5: Replace `jurisdiction.eu_ai_act` $def with the full definition**

Edit `schema/v2/robot.schema.json`. Replace the stub `"jurisdiction.eu_ai_act": { ... }` with:

```json
"jurisdiction.eu_ai_act": {
  "type": "object",
  "additionalProperties": true,
  "required": ["regime", "risk_assessment_ref"],
  "properties": {
    "regime":              { "const": "eu_ai_act" },
    "risk_assessment_ref": { "$ref": "#/$defs/uri" },
    "annex_iii_basis": {
      "type": "string",
      "enum": ["safety_component", "biometric", "critical_infrastructure",
               "education", "employment", "essential_services",
               "law_enforcement", "migration", "administration_of_justice",
               "general_purpose_ai"]
    },
    "fria_ref":             { "$ref": "#/$defs/uri" },
    "audit_retention_days": { "type": "integer", "minimum": 0 }
  },
  "allOf": [
    {
      "description": "FRIA gate: declaring annex_iii_basis commits the operator to a Fundamental Rights Impact Assessment, so fria_ref must be present.",
      "if":   { "required": ["annex_iii_basis"] },
      "then": { "required": ["fria_ref"] }
    }
  ]
}
```

- [ ] **Step 6: Sync schema and re-run tests**

```bash
bash scripts/sync-schema.sh
cd cli && pytest tests/test_compliance_jurisdictions_v2.py -v
```

Expected: both parametrized cases pass.

- [ ] **Step 7: Commit**

```bash
git add schema/v2/ cli/src/robot_md/schemas/v2/ site/schema/v2/ \
        cli/tests/test_compliance_jurisdictions_v2.py \
        cli/tests/fixtures/valid/compliance_jurisdictions_eu_only.json \
        cli/tests/fixtures/invalid/compliance_eu_annex_iii_no_fria.json
git commit -m "schema(v2): full jurisdiction.eu_ai_act \$def + FRIA gate"
```

---

## Task 4: Add `jurisdiction.ansi_ria_r1506` + fixtures + test cases

**Files:**
- Modify: `schema/v2/robot.schema.json` (replace stub)
- Create: `cli/tests/fixtures/valid/compliance_jurisdictions_na_industrial.json`
- Create: `cli/tests/fixtures/invalid/compliance_r1506_missing_integrator.json`
- Create: `cli/tests/fixtures/invalid/compliance_r1506_missing_edition.json`
- Modify: `cli/tests/test_compliance_jurisdictions_v2.py` (add cases to parametrize lists)

- [ ] **Step 1: Add fixture cases to the existing test parametrize lists**

Edit `cli/tests/test_compliance_jurisdictions_v2.py`. Extend the positive parametrize:

```python
@pytest.mark.parametrize("fixture_name", [
    "compliance_jurisdictions_eu_only.json",
    "compliance_jurisdictions_na_industrial.json",
])
```

Extend the negative parametrize:

```python
@pytest.mark.parametrize("fixture_name,expected_path_fragment", [
    ("compliance_eu_annex_iii_no_fria.json", "fria_ref"),
    ("compliance_r1506_missing_integrator.json", "system_integrator"),
    ("compliance_r1506_missing_edition.json", "edition"),
])
```

- [ ] **Step 2: Create positive fixture**

Create `cli/tests/fixtures/valid/compliance_jurisdictions_na_industrial.json` with the same outer structure as the EU fixture (rcan_version, metadata, physics, drivers, safety) but with this `compliance` block:

```json
"compliance": {
  "jurisdictions": [
    {
      "regime": "ansi_ria_r1506",
      "edition": "2012",
      "system_integrator": "Acme Robotics Integration LLC",
      "risk_assessment_ref": "https://example.org/risk-r1506.pdf",
      "iso_10218_part1_ref": "https://example.org/iso-10218-1.pdf",
      "iso_10218_part2_ref": "https://example.org/iso-10218-2.pdf"
    }
  ]
}
```

(Copy the rest from the EU fixture; only the `compliance` block differs.)

- [ ] **Step 3: Create the two negative fixtures**

`cli/tests/fixtures/invalid/compliance_r1506_missing_integrator.json` — same as positive but with `system_integrator` removed.

`cli/tests/fixtures/invalid/compliance_r1506_missing_edition.json` — same as positive but with `edition` removed.

- [ ] **Step 4: Run tests — expect failures**

```bash
cd cli && pytest tests/test_compliance_jurisdictions_v2.py -v
```

Expected: the two new negative cases fail (the stub def doesn't enforce required fields), and the new positive case may pass (stub accepts more than valid). The contract is: after Step 5, all five cases pass.

- [ ] **Step 5: Replace `jurisdiction.ansi_ria_r1506` $def with the full definition**

Edit `schema/v2/robot.schema.json`. Replace stub with:

```json
"jurisdiction.ansi_ria_r1506": {
  "type": "object",
  "additionalProperties": true,
  "required": ["regime", "edition", "system_integrator", "risk_assessment_ref"],
  "properties": {
    "regime":              { "const": "ansi_ria_r1506" },
    "edition":             { "type": "string", "enum": ["2012", "2025"] },
    "system_integrator":   { "type": "string", "minLength": 1,
                             "description": "Legal name of the integrator declaring system-level conformance per R15.06-2." },
    "risk_assessment_ref": { "$ref": "#/$defs/uri" },
    "iso_10218_part1_ref": { "$ref": "#/$defs/uri" },
    "iso_10218_part2_ref": { "$ref": "#/$defs/uri" }
  }
}
```

- [ ] **Step 6: Sync + re-run tests**

```bash
bash scripts/sync-schema.sh
cd cli && pytest tests/test_compliance_jurisdictions_v2.py -v
```

Expected: all 5 parametrized cases pass.

- [ ] **Step 7: Commit**

```bash
git add schema/v2/ cli/src/robot_md/schemas/v2/ site/schema/v2/ \
        cli/tests/test_compliance_jurisdictions_v2.py \
        cli/tests/fixtures/valid/compliance_jurisdictions_na_industrial.json \
        cli/tests/fixtures/invalid/compliance_r1506_missing_integrator.json \
        cli/tests/fixtures/invalid/compliance_r1506_missing_edition.json
git commit -m "schema(v2): full jurisdiction.ansi_ria_r1506 \$def + integrator/edition gates"
```

---

## Task 5: Add `jurisdiction.ansi_ria_r1508` + PFL gate + fixtures + test cases

**Files:**
- Modify: `schema/v2/robot.schema.json` (replace stub)
- Create: `cli/tests/fixtures/valid/compliance_jurisdictions_na_cobot_pfl.json`
- Create: `cli/tests/fixtures/valid/compliance_jurisdictions_na_cobot_ssm.json`
- Create: `cli/tests/fixtures/invalid/compliance_r1508_pfl_missing_force_limits.json`
- Create: `cli/tests/fixtures/invalid/compliance_r1508_no_collaborative_modes.json`
- Modify: `cli/tests/test_compliance_jurisdictions_v2.py`

- [ ] **Step 1: Extend test parametrize lists**

Add the four new fixture file names to the appropriate lists (2 positive, 2 negative). For negatives, the expected path fragments are `force_limits_ref` and `collaborative_modes`.

- [ ] **Step 2: Create the four fixtures**

Positive `compliance_jurisdictions_na_cobot_pfl.json` (compliance block):

```json
"compliance": {
  "jurisdictions": [
    {
      "regime": "ansi_ria_r1508",
      "edition": "2023",
      "risk_assessment_ref": "https://example.org/risk-r1508.pdf",
      "collaborative_modes": ["power_force_limiting"],
      "force_limits_ref": "https://example.org/iso-15066-annex-a.pdf"
    }
  ]
}
```

Positive `compliance_jurisdictions_na_cobot_ssm.json` (compliance block):

```json
"compliance": {
  "jurisdictions": [
    {
      "regime": "ansi_ria_r1508",
      "edition": "2023",
      "risk_assessment_ref": "https://example.org/risk-r1508.pdf",
      "collaborative_modes": ["speed_and_separation_monitoring"]
    }
  ]
}
```

(Note: SSM mode does *not* require `force_limits_ref` — only PFL does.)

Negative `compliance_r1508_pfl_missing_force_limits.json` — same as PFL positive but with `force_limits_ref` removed.

Negative `compliance_r1508_no_collaborative_modes.json` — same as PFL positive but with `collaborative_modes` removed entirely.

- [ ] **Step 3: Run tests — negatives should fail**

```bash
cd cli && pytest tests/test_compliance_jurisdictions_v2.py -v
```

- [ ] **Step 4: Replace `jurisdiction.ansi_ria_r1508` $def**

Edit `schema/v2/robot.schema.json`. Replace stub with:

```json
"jurisdiction.ansi_ria_r1508": {
  "type": "object",
  "additionalProperties": true,
  "required": ["regime", "edition", "risk_assessment_ref", "collaborative_modes"],
  "properties": {
    "regime":               { "const": "ansi_ria_r1508" },
    "edition":              { "type": "string", "enum": ["2023"] },
    "risk_assessment_ref":  { "$ref": "#/$defs/uri" },
    "collaborative_modes": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "string",
        "enum": ["safety_rated_monitored_stop", "hand_guiding",
                 "speed_and_separation_monitoring", "power_force_limiting"]
      }
    },
    "force_limits_ref":   { "$ref": "#/$defs/uri",
                            "description": "Pointer to ISO/TS 15066 Annex A force/pressure limit declarations per body region." },
    "iso_ts_15066_ref":   { "$ref": "#/$defs/uri" }
  },
  "allOf": [
    {
      "description": "PFL gate: declaring power_force_limiting in collaborative_modes commits the operator to ISO/TS 15066 Annex A force/pressure limits.",
      "if":   { "properties": { "collaborative_modes":
                  { "contains": { "const": "power_force_limiting" } } },
                "required": ["collaborative_modes"] },
      "then": { "required": ["force_limits_ref"] }
    }
  ]
}
```

- [ ] **Step 5: Sync + re-run**

```bash
bash scripts/sync-schema.sh
cd cli && pytest tests/test_compliance_jurisdictions_v2.py -v
```

Expected: all 9 parametrized cases pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "schema(v2): full jurisdiction.ansi_ria_r1508 \$def + PFL force-limits gate"
```

---

## Task 6: Add voluntary framework $defs + EU+NA combined fixture

**Files:**
- Modify: `schema/v2/robot.schema.json` (fill in voluntary $defs)
- Create: `cli/tests/fixtures/valid/compliance_jurisdictions_eu_plus_na.json`

- [ ] **Step 1: Fill in voluntary $defs**

Edit `schema/v2/robot.schema.json`. Replace the three voluntary stubs with:

```json
"voluntary.iso_42001": {
  "type": "object",
  "additionalProperties": true,
  "properties": {
    "self_assessed": { "type": "boolean" },
    "level":         { "type": "integer", "minimum": 1, "maximum": 5 },
    "audit_ref":     { "$ref": "#/$defs/uri" }
  }
},
"voluntary.nist_ai_rmf": {
  "type": "object",
  "additionalProperties": true,
  "properties": {
    "self_assessed": { "type": "boolean" },
    "profile_ref":   { "$ref": "#/$defs/uri" }
  }
},
"voluntary.iec_62443": {
  "type": "object",
  "additionalProperties": true,
  "properties": {
    "self_assessed":  { "type": "boolean" },
    "security_level": { "type": "integer", "minimum": 1, "maximum": 4 },
    "assessment_ref": { "$ref": "#/$defs/uri" }
  }
}
```

- [ ] **Step 2: Create combined-jurisdictions fixture**

Create `cli/tests/fixtures/valid/compliance_jurisdictions_eu_plus_na.json` (compliance block):

```json
"compliance": {
  "jurisdictions": [
    {
      "regime": "eu_ai_act",
      "risk_assessment_ref": "https://example.org/risk-eu.pdf",
      "annex_iii_basis": "safety_component",
      "fria_ref": "https://example.org/fria.pdf",
      "audit_retention_days": 2555
    },
    {
      "regime": "ansi_ria_r1506",
      "edition": "2012",
      "system_integrator": "Acme Robotics Integration LLC",
      "risk_assessment_ref": "https://example.org/risk-r1506.pdf"
    }
  ],
  "iso_42001": {
    "self_assessed": true,
    "level": 3,
    "audit_ref": "https://example.org/iso42001-audit.pdf"
  },
  "nist_ai_rmf": {
    "self_assessed": true,
    "profile_ref": "https://example.org/nist-aimf-profile.pdf"
  }
}
```

- [ ] **Step 3: Add to positive fixture parametrize list**

Edit `cli/tests/test_compliance_jurisdictions_v2.py` to include `compliance_jurisdictions_eu_plus_na.json` in the positive list.

- [ ] **Step 4: Sync + run**

```bash
bash scripts/sync-schema.sh
cd cli && pytest tests/test_compliance_jurisdictions_v2.py -v
```

Expected: all positive cases pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "schema(v2): voluntary framework \$defs + EU+NA combined fixture"
```

---

## Task 7: Switch `validate.py` to load v2 schema; remove v1 from runtime path

**Files:**
- Modify: `cli/src/robot_md/validate.py`

The packaged v1 schema directory stays on disk for archival (per the plan and sync-schema.sh) but is no longer loaded at runtime.

- [ ] **Step 1: Find and update `_load_schema()`**

Run: `grep -n '_load_schema\|schemas/v1' cli/src/robot_md/validate.py`
Expected: matches at the function definition and inside it (`schemas/v1/robot.schema.json`).

- [ ] **Step 2: Edit `_load_schema()` to load v2**

Edit `cli/src/robot_md/validate.py`. Change the `_load_schema()` body:

```python
def _load_schema() -> dict[str, Any]:
    # Schema is bundled as a package resource — works in wheel, sdist, and editable installs.
    # Canonical source: robot-md repo schema/v2/robot.schema.json; CI keeps this copy in sync.
    # v1 schema is frozen; v2 is current. Validator never falls back to v1 — manifests using
    # v3.1-flat compliance shape must be migrated via scripts/migrate-compliance-v2.py.
    with (_files("robot_md").joinpath("schemas/v2/robot.schema.json")).open("r") as f:
        return json.load(f)
```

- [ ] **Step 3: Run the existing validate tests — they will fail until consumers + fixtures migrate**

```bash
cd cli && pytest tests/ -v -x 2>&1 | head -60
```

Expected: a number of existing tests fail because their fixtures are still v1-shape (flat compliance). Note the failing test names; they will be addressed in subsequent tasks.

- [ ] **Step 4: Document failing-test inventory in a temporary marker file**

```bash
cd cli && pytest tests/ --collect-only -q 2>/dev/null > /tmp/all-tests.txt
cd cli && pytest tests/ -x 2>&1 | grep -E "^FAILED|^ERROR" > /tmp/failing-tests.txt
wc -l /tmp/failing-tests.txt
```

(This is a working artifact, not committed.)

- [ ] **Step 5: Commit the validator change**

```bash
git add cli/src/robot_md/validate.py
git commit -m "validate: switch runtime to v2 schema (v1 frozen)"
```

---

## Task 8: Create `compliance_helpers.py` + tests

**Files:**
- Create: `cli/src/robot_md/compliance_helpers.py`
- Create: `cli/tests/test_compliance_helpers.py`

- [ ] **Step 1: Write failing tests first**

Create `cli/tests/test_compliance_helpers.py`:

```python
"""Unit tests for compliance_helpers — single source of truth for reading
jurisdiction-shaped compliance fields."""

from __future__ import annotations

import pytest

from robot_md.compliance_helpers import (
    get_eu_jurisdiction,
    get_jurisdiction,
    eu_annex_iii_basis,
    eu_fria_ref,
    eu_audit_retention_days,
)


def test_get_jurisdiction_returns_matching_entry():
    comp = {"jurisdictions": [
        {"regime": "eu_ai_act", "risk_assessment_ref": "https://x"},
        {"regime": "ansi_ria_r1506", "edition": "2012", "system_integrator": "X",
         "risk_assessment_ref": "https://y"},
    ]}
    assert get_jurisdiction(comp, "ansi_ria_r1506")["edition"] == "2012"


def test_get_jurisdiction_returns_none_when_absent():
    assert get_jurisdiction({"jurisdictions": []}, "eu_ai_act") is None
    assert get_jurisdiction({}, "eu_ai_act") is None


def test_get_eu_jurisdiction_shorthand():
    comp = {"jurisdictions": [{"regime": "eu_ai_act", "risk_assessment_ref": "https://x"}]}
    assert get_eu_jurisdiction(comp) is not None


def test_eu_annex_iii_basis_returns_value_when_set():
    comp = {"jurisdictions": [
        {"regime": "eu_ai_act", "risk_assessment_ref": "https://x",
         "annex_iii_basis": "safety_component"},
    ]}
    assert eu_annex_iii_basis(comp) == "safety_component"


def test_eu_annex_iii_basis_returns_empty_when_no_eu_entry():
    assert eu_annex_iii_basis({"jurisdictions": []}) == ""
    assert eu_annex_iii_basis({}) == ""


def test_eu_fria_ref_and_audit_retention():
    comp = {"jurisdictions": [
        {"regime": "eu_ai_act", "risk_assessment_ref": "https://x",
         "fria_ref": "https://fria", "audit_retention_days": 2555},
    ]}
    assert eu_fria_ref(comp) == "https://fria"
    assert eu_audit_retention_days(comp) == 2555


def test_helpers_handle_missing_compliance_block():
    assert eu_annex_iii_basis({}) == ""
    assert eu_fria_ref({}) == ""
    assert eu_audit_retention_days({}) is None
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
cd cli && pytest tests/test_compliance_helpers.py -v
```

Expected: collection error or ImportError (`compliance_helpers` doesn't exist yet).

- [ ] **Step 3: Implement helpers**

Create `cli/src/robot_md/compliance_helpers.py`:

```python
"""Helpers for reading the v2 compliance.jurisdictions[] shape.

All downstream modules (fria.py, eu_register.py, ifu.py, art11.py) MUST
read jurisdiction fields through this module rather than poking at the
compliance dict directly. This is the single source of truth.
"""

from __future__ import annotations

from typing import Any


def get_jurisdiction(compliance: dict[str, Any] | None, regime: str) -> dict[str, Any] | None:
    """Return the first jurisdictions[] entry whose `regime` matches, or None."""
    if not compliance:
        return None
    for entry in compliance.get("jurisdictions", []) or []:
        if entry.get("regime") == regime:
            return entry
    return None


def get_eu_jurisdiction(compliance: dict[str, Any] | None) -> dict[str, Any] | None:
    return get_jurisdiction(compliance, "eu_ai_act")


def eu_annex_iii_basis(compliance: dict[str, Any] | None) -> str:
    """Return annex_iii_basis from the EU jurisdiction entry, or empty string."""
    eu = get_eu_jurisdiction(compliance)
    return (eu or {}).get("annex_iii_basis", "") or ""


def eu_fria_ref(compliance: dict[str, Any] | None) -> str:
    eu = get_eu_jurisdiction(compliance)
    return (eu or {}).get("fria_ref", "") or ""


def eu_audit_retention_days(compliance: dict[str, Any] | None) -> int | None:
    eu = get_eu_jurisdiction(compliance)
    if not eu:
        return None
    return eu.get("audit_retention_days")
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd cli && pytest tests/test_compliance_helpers.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add cli/src/robot_md/compliance_helpers.py cli/tests/test_compliance_helpers.py
git commit -m "feat(compliance): add compliance_helpers for v2 jurisdiction reads"
```

---

## Task 9: Migrate `fria.py`, `eu_register.py`, `ifu.py`, `art11.py` to use the helper

**Files:**
- Modify: `cli/src/robot_md/fria.py`
- Modify: `cli/src/robot_md/eu_register.py`
- Modify: `cli/src/robot_md/ifu.py`
- Modify: `cli/src/robot_md/art11.py`

Each file currently does `comp.get("annex_iii_basis")` and similar flat reads. Replace with helper calls.

- [ ] **Step 1: Update `fria.py`**

Run: `grep -n 'annex_iii_basis\|fria_ref' cli/src/robot_md/fria.py`

For each occurrence: replace `comp.get("annex_iii_basis") or ""` with `eu_annex_iii_basis(comp)`. Add `from robot_md.compliance_helpers import eu_annex_iii_basis, eu_fria_ref` at the top of the file.

- [ ] **Step 2: Update `eu_register.py`**

Run: `grep -n 'annex_iii_basis\|fria_ref' cli/src/robot_md/eu_register.py`

The line `basis = (comp.get("annex_iii_basis") or "").strip()` becomes `basis = eu_annex_iii_basis(comp).strip()`. Imports: add `from robot_md.compliance_helpers import eu_annex_iii_basis, eu_fria_ref, eu_audit_retention_days`. Replace any `fria_ref=...` reads with the helper too.

- [ ] **Step 3: Update `ifu.py`**

Same pattern: `comp.get("annex_iii_basis") or ""` → `eu_annex_iii_basis(comp)`.

- [ ] **Step 4: Update `art11.py`**

Same pattern.

- [ ] **Step 5: Update existing test fixtures that exercise these modules**

Run: `grep -rln "compliance:\|compliance =" cli/tests/ | head -10`

For tests that use `BOB_MIN`-style inline-YAML fixtures with the old `compliance: { fria_ref: ..., annex_iii_basis: ... }` shape, rewrite the fixture's compliance block to:

```yaml
compliance:
  jurisdictions:
    - regime: eu_ai_act
      risk_assessment_ref: "https://example.org/risk.pdf"
      annex_iii_basis: "safety_component"
      fria_ref: "https://example.org/fria.pdf"
      audit_retention_days: 2555
```

The known files needing this update are: `test_fria.py`, `test_eu_register.py`, `test_ifu.py`, `test_art11.py`, `test_compliance_status.py`, `cli/tests/unit/test_schema_annex_iii_basis.py`, and any fixture YAMLs under `cli/tests/fixtures/`. Use grep to confirm coverage.

- [ ] **Step 6: Run the full test suite**

```bash
cd cli && pytest tests/ -x 2>&1 | tail -40
```

Expected: all tests pass. If any still fail with `'annex_iii_basis'`-shaped errors, those fixtures haven't been migrated yet — find and update them.

- [ ] **Step 7: Commit**

```bash
git add cli/src/robot_md/fria.py cli/src/robot_md/eu_register.py \
        cli/src/robot_md/ifu.py cli/src/robot_md/art11.py \
        cli/tests/
git commit -m "refactor(compliance): consumers + tests read jurisdictions[] via helper"
```

---

## Task 10: Add validator-layer gates (regime uniqueness + retention warning)

(The "edition not yet published" friendly-error case is implicitly covered by the schema-level enum on `edition` — `2025` for R15.06 will pass the enum once published; until then, validators using a 2026-vintage schema accept it. No separate validator-layer enforcement needed beyond the enum.)


**Files:**
- Modify: `cli/src/robot_md/validate.py`
- Modify: `cli/tests/test_compliance_jurisdictions_v2.py` (add validator-layer tests)
- Create: `cli/tests/fixtures/invalid/compliance_jurisdictions_duplicate_regime.json`

- [ ] **Step 1: Write failing test for duplicate-regime gate**

Add to `cli/tests/test_compliance_jurisdictions_v2.py`:

```python
def test_duplicate_regime_rejected_by_validator():
    """Validator-layer (not schema-layer) gate: each regime appears at most once."""
    from robot_md.validate import validate
    from robot_md.parser import ParsedRobotMd

    fm = _load(INVALID_DIR / "compliance_jurisdictions_duplicate_regime.json")
    parsed = ParsedRobotMd(frontmatter=fm, body="# x\n## Identity\n\n## Safety Gates\n")
    result = validate(parsed)
    assert result.code != 0
    assert any("duplicate" in e.lower() and "regime" in e.lower() for e in result.errors)


def test_audit_retention_under_365_warns():
    from robot_md.validate import validate
    from robot_md.parser import ParsedRobotMd

    fm = _load(VALID_DIR / "compliance_jurisdictions_eu_only.json")
    fm["compliance"]["jurisdictions"][0]["audit_retention_days"] = 30
    parsed = ParsedRobotMd(frontmatter=fm, body="# x\n## Identity\n\n## Safety Gates\n")
    result = validate(parsed)
    assert any("audit_retention_days" in w for w in result.warnings)
```

- [ ] **Step 2: Create the duplicate-regime negative fixture**

Create `cli/tests/fixtures/invalid/compliance_jurisdictions_duplicate_regime.json` — same outer shape as the EU-only fixture but with the `compliance` block declaring `eu_ai_act` twice.

- [ ] **Step 3: Run tests — expect FAIL**

```bash
cd cli && pytest tests/test_compliance_jurisdictions_v2.py::test_duplicate_regime_rejected_by_validator tests/test_compliance_jurisdictions_v2.py::test_audit_retention_under_365_warns -v
```

Expected: both fail (no validator-layer gates yet).

- [ ] **Step 4: Add gates to `validate.py`**

After the schema-validation block in `validate(parsed)`, add:

```python
# Validator-layer gates for compliance.jurisdictions[]
fm = parsed.frontmatter
comp = fm.get("compliance") or {}
jurisdictions = comp.get("jurisdictions") or []
seen_regimes: set[str] = set()
for idx, entry in enumerate(jurisdictions):
    regime = entry.get("regime", "")
    if regime in seen_regimes:
        errors.append(
            f"compliance.jurisdictions[{idx}]: duplicate regime '{regime}' "
            f"— each regime may appear at most once."
        )
    seen_regimes.add(regime)

# Soft warning for low audit_retention_days on EU entry
from robot_md.compliance_helpers import eu_audit_retention_days
retention = eu_audit_retention_days(comp)
if retention is not None and retention < 365:
    warnings.append(
        f"compliance.jurisdictions[*].audit_retention_days={retention} "
        f"is below the 365-day de facto floor for EU AI Act audit records."
    )
```

(Make sure `warnings` is in scope; if it isn't, declare `warnings: list[str] = []` near `errors`.)

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd cli && pytest tests/test_compliance_jurisdictions_v2.py -v
```

Expected: all tests pass, including the two new ones.

- [ ] **Step 6: Commit**

```bash
git add cli/src/robot_md/validate.py \
        cli/tests/test_compliance_jurisdictions_v2.py \
        cli/tests/fixtures/invalid/compliance_jurisdictions_duplicate_regime.json
git commit -m "validate: regime-uniqueness gate + audit_retention warning"
```

---

## Task 11: Migration script — pure transform function

**Files:**
- Create: `scripts/migrate_compliance_v2.py` (note: filename uses underscores so it's importable as a module)
- Create: `cli/tests/test_migrate_compliance_v2.py`

- [ ] **Step 1: Write the failing transform-function tests**

Create `cli/tests/test_migrate_compliance_v2.py`:

```python
"""Unit tests for the v1→v2 compliance migration transform."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from migrate_compliance_v2 import migrate_compliance, is_already_v2


def test_migrates_eu_flat_to_jurisdictions_array():
    old = {
        "compliance": {
            "fria_ref": "https://example.org/fria.pdf",
            "annex_iii_basis": "safety_component",
            "eu_ai_act": {"audit_retention_days": 2555},
            "iso_42001": {"self_assessed": True},
        }
    }
    new = migrate_compliance(old, risk_assessment_ref="https://example.org/risk.pdf")
    assert new["compliance"]["jurisdictions"] == [
        {
            "regime": "eu_ai_act",
            "risk_assessment_ref": "https://example.org/risk.pdf",
            "annex_iii_basis": "safety_component",
            "fria_ref": "https://example.org/fria.pdf",
            "audit_retention_days": 2555,
        }
    ]
    assert new["compliance"]["iso_42001"] == {"self_assessed": True}
    assert "eu_ai_act" not in new["compliance"]
    assert "fria_ref" not in new["compliance"]
    assert "annex_iii_basis" not in new["compliance"]


def test_migrate_handles_missing_eu_audit_retention():
    old = {"compliance": {"fria_ref": "https://example.org/fria.pdf",
                          "annex_iii_basis": "safety_component"}}
    new = migrate_compliance(old, risk_assessment_ref="https://example.org/risk.pdf")
    entry = new["compliance"]["jurisdictions"][0]
    assert "audit_retention_days" not in entry


def test_migrate_handles_no_compliance_block():
    old = {"metadata": {"robot_name": "x"}}
    new = migrate_compliance(old, risk_assessment_ref="https://example.org/risk.pdf")
    assert new == old


def test_migrate_optional_add_r1506():
    old = {"compliance": {"fria_ref": "https://example.org/fria.pdf",
                          "annex_iii_basis": "safety_component"}}
    new = migrate_compliance(
        old,
        risk_assessment_ref="https://example.org/risk.pdf",
        add_r1506={"edition": "2012", "system_integrator": "Acme",
                   "risk_assessment_ref": "https://example.org/r1506-risk.pdf"},
    )
    regimes = [j["regime"] for j in new["compliance"]["jurisdictions"]]
    assert regimes == ["eu_ai_act", "ansi_ria_r1506"]


def test_is_already_v2_detects_jurisdictions_key():
    assert is_already_v2({"compliance": {"jurisdictions": []}}) is True
    assert is_already_v2({"compliance": {"fria_ref": "x"}}) is False
    assert is_already_v2({}) is False
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd cli && pytest tests/test_migrate_compliance_v2.py -v
```

Expected: ImportError (script doesn't exist).

- [ ] **Step 3: Implement the transform function**

Create `scripts/migrate_compliance_v2.py`:

```python
#!/usr/bin/env python3
"""Migrate ROBOT.md compliance block from v1 (flat EU shape) to v2 (jurisdictions[]).

Usage:
    python scripts/migrate_compliance_v2.py PATH_TO_ROBOT_MD [--risk-assessment-ref URI] [--add-r1506] [--dry-run]

This is a one-shot rewrite. There is no rollback; the v1 schema is frozen and the
ecosystem assumes manifests have been migrated. Bob is the only known deployment.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any


def is_already_v2(frontmatter: dict[str, Any]) -> bool:
    return "jurisdictions" in (frontmatter.get("compliance") or {})


def migrate_compliance(
    frontmatter: dict[str, Any],
    risk_assessment_ref: str,
    add_r1506: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure transform: take a v1-shape frontmatter dict, return a v2-shape copy.

    Idempotent if the input is already v2 (returns a deep copy unchanged).
    """
    out = copy.deepcopy(frontmatter)
    comp = out.get("compliance")
    if not comp:
        return out
    if "jurisdictions" in comp:
        return out  # already v2

    eu_entry: dict[str, Any] = {
        "regime": "eu_ai_act",
        "risk_assessment_ref": risk_assessment_ref,
    }
    if "annex_iii_basis" in comp:
        eu_entry["annex_iii_basis"] = comp.pop("annex_iii_basis")
    if "fria_ref" in comp:
        eu_entry["fria_ref"] = comp.pop("fria_ref")
    eu_block = comp.pop("eu_ai_act", None)
    if eu_block and "audit_retention_days" in eu_block:
        eu_entry["audit_retention_days"] = eu_block["audit_retention_days"]

    jurisdictions: list[dict[str, Any]] = [eu_entry]

    if add_r1506:
        r1506_entry = {"regime": "ansi_ria_r1506", **add_r1506}
        jurisdictions.append(r1506_entry)

    comp["jurisdictions"] = jurisdictions
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Migrate ROBOT.md compliance block to v2.")
    p.add_argument("path", help="Path to ROBOT.md")
    p.add_argument("--risk-assessment-ref", required=True,
                   help="Absolute URI to your risk assessment artifact (mandatory under v2).")
    p.add_argument("--add-r1506", action="store_true",
                   help="Also append an ANSI/RIA R15.06 jurisdiction entry (prompts for required fields).")
    p.add_argument("--dry-run", action="store_true", help="Print diff and exit without writing.")
    args = p.parse_args(argv)

    try:
        from ruamel.yaml import YAML
    except ImportError:
        print("error: ruamel.yaml is required (pip install ruamel.yaml)", file=sys.stderr)
        return 2

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    path = Path(args.path)
    text = path.read_text()
    if not text.startswith("---"):
        print(f"error: {path} does not start with YAML frontmatter '---'", file=sys.stderr)
        return 2
    _, fm_text, body = text.split("---", 2)
    fm = yaml.load(fm_text)

    if is_already_v2(fm):
        print(f"{path}: already v2 (no changes)")
        return 0

    add_r1506_data: dict[str, Any] | None = None
    if args.add_r1506:
        print("R15.06 declaration requires three fields:")
        edition = input("  edition (2012 or 2025): ").strip() or "2012"
        integrator = input("  system_integrator (legal name): ").strip()
        r1506_risk = input("  risk_assessment_ref (URI): ").strip()
        add_r1506_data = {
            "edition": edition,
            "system_integrator": integrator,
            "risk_assessment_ref": r1506_risk,
        }

    new_fm = migrate_compliance(fm, args.risk_assessment_ref, add_r1506_data)

    import io
    new_fm_buf = io.StringIO()
    yaml.dump(new_fm, new_fm_buf)
    new_text = "---" + new_fm_buf.getvalue() + "---" + body

    if args.dry_run:
        print(new_text)
        return 0

    confirm = input(f"Rewrite {path}? [y/N]: ").strip().lower()
    if confirm != "y":
        print("aborted.")
        return 1

    path.write_text(new_text)
    print(f"✓ {path} migrated. Next: re-emit FRIA / benchmarks / IFU / eu-register and resubmit to RRF.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run unit tests — expect PASS**

```bash
cd cli && pytest tests/test_migrate_compliance_v2.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Smoke-test the CLI end-to-end against a synthetic ROBOT.md**

```bash
cat > /tmp/test-robot.md <<'EOF'
---
rcan_version: "3.2"
metadata:
  robot_name: smoketest
compliance:
  fria_ref: "https://example.org/fria.pdf"
  annex_iii_basis: "safety_component"
  eu_ai_act:
    audit_retention_days: 2555
  iso_42001:
    self_assessed: true
---
# smoketest
EOF
python scripts/migrate_compliance_v2.py /tmp/test-robot.md \
    --risk-assessment-ref https://example.org/risk.pdf \
    --dry-run
```

Expected: prints a v2-shape ROBOT.md to stdout. Confirm `jurisdictions:` appears under `compliance:`.

- [ ] **Step 6: Commit**

```bash
git add scripts/migrate_compliance_v2.py cli/tests/test_migrate_compliance_v2.py
git commit -m "feat(scripts): add migrate_compliance_v2.py — one-shot v1→v2 migration"
```

---

## Task 12: Bump version + CHANGELOG + final test sweep

**Files:**
- Modify: `cli/pyproject.toml`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Bump version**

Edit `cli/pyproject.toml`. Change `version = "1.2.4"` to `version = "2.0.0"`.

- [ ] **Step 2: Add CHANGELOG entry**

Prepend below the current top-of-file header:

```markdown
## v2.0.0 — 2026-04-27

### BREAKING

The `compliance` block in ROBOT.md has been refactored to a multi-jurisdiction shape. The flat EU-only fields (`compliance.fria_ref`, `compliance.annex_iii_basis`, `compliance.eu_ai_act`) are removed; their replacements live inside `compliance.jurisdictions[]` keyed by `regime`. Manifests using the v1 shape MUST be migrated via `scripts/migrate_compliance_v2.py` before validation will pass.

See rcan-spec v3.2 §27 for the normative declaration shape.

### Added

- New canonical schema at `schema/v2/robot.schema.json`. v1 is frozen.
- `compliance.jurisdictions[]` discriminated union over `regime`:
  - `eu_ai_act` (existing fields, new home)
  - `ansi_ria_r1506` (new — industrial robot safety, US adoption of ISO 10218)
  - `ansi_ria_r1508` (new — collaborative robot safety, US adoption of ISO/TS 15066)
- Standard-of-conduct gates:
  - EU FRIA gate (preserved): `annex_iii_basis` set → `fria_ref` required.
  - EU risk-assessment: `regime: eu_ai_act` declared → `risk_assessment_ref` required.
  - R15.06: `system_integrator` + `edition` + `risk_assessment_ref` required.
  - R15.08: `collaborative_modes[]` (≥1) + `risk_assessment_ref` + `edition` required.
  - R15.08 PFL: `power_force_limiting` in `collaborative_modes` → `force_limits_ref` required.
- New voluntary-framework flat blocks: `compliance.iso_42001`, `compliance.nist_ai_rmf`, `compliance.iec_62443`.
- Validator-layer gates: regime uniqueness (error), low audit retention (warning).
- `scripts/migrate_compliance_v2.py` — one-shot migration tool with `--dry-run` and `--add-r1506` flags.
- `compliance_helpers.py` — single source of truth for downstream consumers reading jurisdiction fields.
- Schema fixture coverage: 5 positive + 6 negative fixtures (incl. the existing FRIA-gate regression).

### Changed

- `validate.py` now loads v2 schema only. v1 manifests fail validation; migrate first.
- `fria.py`, `eu_register.py`, `ifu.py`, `art11.py` now read EU compliance fields via `compliance_helpers.py`.
- `compliance.additionalProperties` is now `false` at the top level — typos are caught early.

### Migration

Run `python scripts/migrate_compliance_v2.py path/to/ROBOT.md --risk-assessment-ref <URI>` before upgrading. After migration, re-emit FRIA / benchmarks / IFU / eu-register and re-submit to RRF per the runtime-change protocol.
```

- [ ] **Step 3: Run the full test suite**

```bash
cd cli && pytest tests/ 2>&1 | tail -10
```

Expected: all tests pass; no errors. If anything fails, fix it before the next step.

- [ ] **Step 4: Run lint**

```bash
cd cli && ruff check src/ tests/
```

Expected: no errors.

- [ ] **Step 5: Confirm packaged schemas match canonical**

```bash
diff -q schema/v1/robot.schema.json cli/src/robot_md/schemas/v1/robot.schema.json
diff -q schema/v2/robot.schema.json cli/src/robot_md/schemas/v2/robot.schema.json
```

Expected: silent (matches).

- [ ] **Step 6: Commit**

```bash
git add cli/pyproject.toml CHANGELOG.md
git commit -m "chore(release): robot-md v2.0.0 — compliance.jurisdictions[] refactor (BREAKING)"
```

- [ ] **Step 7: Tag (only after user confirms release)**

```bash
git tag v2.0.0
```

(Do NOT push the tag without user confirmation. Pushing triggers PyPI publication via the existing release workflow — see `feedback_robotmd_release_workflow_no_ci.md` memory for the gotcha that the workflow ships without CI gating; verify CI is green before pushing.)

---

## Plan completion check

- [ ] v2 schema directory bootstrapped + sync script updated
- [ ] All three jurisdiction $defs land with positive + negative fixtures
- [ ] FRIA gate preserved; PFL gate added; integrator + edition gates enforced
- [ ] Voluntary framework $defs (iso_42001, nist_ai_rmf, iec_62443) added
- [ ] `validate.py` loads v2 only
- [ ] `compliance_helpers.py` is the single source of truth for jurisdiction reads
- [ ] `fria.py`, `eu_register.py`, `ifu.py`, `art11.py` consume the helper
- [ ] Validator-layer gates: regime uniqueness + audit-retention warning
- [ ] Migration script with `--dry-run` and `--add-r1506`
- [ ] All tests pass; lint clean
- [ ] CHANGELOG + version bump committed
- [ ] (User-gated) tag pushed; release workflow ships v2.0.0 to PyPI

When all boxes are checked, Plan B is complete. Plans C (rcan-py builders), D (rcan-ts builders), E (RRF backend, blocked on RRF #72), F (opencastor bump), and G (bob migration) follow.

# Release D1: rcan-ts 3.2.0 compliance builders — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port rcan-py 3.1.1's 4 compliance builders (§23-26) to TypeScript with byte-parity cross-language testing via rcan-spec fixture.

**Architecture:** One rcan-spec fixture commit (Wave 0) + one rcan-ts 3.2.0 npm release (Waves 1-2). rcan-ts `src/compliance.ts` expands from types-only to types + builders + constants; 4 new builder functions (`buildSafetyBenchmark`, `buildIfu`, `buildIncidentReport`, `buildEuRegisterEntry`) produce output whose `canonicalJson(...)` is byte-identical to rcan-py's. §22-26 interfaces rewritten to match rcan-py wire format; no existing TS consumers affected.

**Tech Stack:** TypeScript (strict mode), vitest test runner, rcan-py 3.1.1 as the byte-parity reference, rcan-spec fixture file pattern (mirrors `canonical-json-v1.json`).

**Working directories (single-branch direct-commit by solo maintainer; no worktrees):**
- rcan-spec: `/home/craigm26/rcan-spec` on branch `master`
- rcan-ts: `/home/craigm26/rcan-ts` on branch `main` (publishes to npm as `rcan-ts` via OIDC Trusted Publisher on tag push)

**Spec:** `/home/craigm26/robot-md/docs/superpowers/specs/2026-04-23-release-d1-rcan-ts-3.2.0-compliance-builders-design.md` (HEAD at `d6bfd7f`).

**Out of scope (reject any task that drifts into these):**
- `build_fria` in rcan-ts (rcan-py has no such builder — wait for upstream).
- Compliance-specific signing helpers (docs sign via generic `signBody`).
- Any rcan-py, opencastor, robot-md, robot-md-mcp, or RRF code changes.
- RRF compliance intake endpoints (Release D2, separate brainstorm).
- rcan-ts CLAUDE.md refresh (known follow-up).
- Runtime severity validation (rcan-py silently ignores unknown; mirror that).
- rcan-py top-level re-exports of schema constants (Release B known follow-up #3).

---

## Release sequencing

**Wave 0 (Task 1):** generate + commit `rcan-spec/fixtures/compliance-v1.json` using a scratch Python script against rcan-py 3.1.1.
**Wave 1 (Tasks 2-11):** rcan-ts implementation — pre-flight, triage existing `compliance.test.ts`, copy fixture, write failing fixture test, replace types, add constants, add builders, add re-exports, write behavioral tests, run full suite.
**Wave 2 (Tasks 12-14):** rcan-ts 3.2.0 publish — version bump, CHANGELOG, tag + push, verify live, smoke test.

---

## Wave 0 — rcan-spec fixture

### Task 1: Generate + commit `compliance-v1.json`

**Files:**
- Create: `/home/craigm26/rcan-spec/fixtures/compliance-v1.json`
- Scratch (not committed): `/tmp/gen_compliance_fixture.py`

- [ ] **Step 1: Pre-flight rcan-spec tree**

Run:
```bash
cd /home/craigm26/rcan-spec
git status
git branch --show-current
git pull --ff-only origin master
```
Expected: clean, on `master`, fast-forward (or already up to date). If not clean or not on master, report BLOCKED.

- [ ] **Step 2: Verify rcan-py 3.1.1 is installable in a scratch venv**

Run:
```bash
python3 -m venv /tmp/rcan-fixture-venv
source /tmp/rcan-fixture-venv/bin/activate
pip install --no-cache-dir 'rcan==3.1.1' 2>&1 | tail -3
python -c "import rcan; print('rcan:', rcan.__version__); from rcan.compliance import build_safety_benchmark, build_ifu, build_incident_report, build_eu_register_entry; print('4 builders importable')"
```
Expected: `rcan: 3.1.1` and `4 builders importable`. Keep the venv alive (don't deactivate) — used by Step 3.

- [ ] **Step 3: Write the fixture generator script**

Write `/tmp/gen_compliance_fixture.py`:

```python
"""One-shot fixture generator for rcan-spec/fixtures/compliance-v1.json.

Run with: python3 /tmp/gen_compliance_fixture.py > /home/craigm26/rcan-spec/fixtures/compliance-v1.json
Requires: rcan==3.1.1 installed in the active venv.

Produces 8 test cases — 2 per builder — covering: minimal shapes,
unicode in strings, unknown severity ignoring, default fallbacks.
"""
from __future__ import annotations

import base64
import json
from typing import Any

import rcan
from rcan.compliance import (
    ART13_COVERAGE,
    CONFORMITY_STATUS_DECLARED,
    SUBMISSION_INSTRUCTIONS,
    build_eu_register_entry,
    build_ifu,
    build_incident_report,
    build_safety_benchmark,
)

# All generated cases share a frozen timestamp for reproducibility.
T = "2026-04-23T00:00:00Z"

# Plausible 8 IFU sections. One non-ASCII character in provider name
# exercises rcan-py's canonical_json ensure_ascii=False path.
IFU_PROVIDER_MIN = {"name": "Test Provider", "contact": "test@example.com"}
IFU_PROVIDER_FULL = {"name": "Crème Brûlée Robotics", "contact": "hi@creme.example", "eori": "EU-123"}
IFU_OBJ_MIN = {"note": "placeholder"}

def case_build_safety_benchmark_minimal() -> dict[str, Any]:
    return {
        "name": "safety_benchmark_minimal",
        "builder": "build_safety_benchmark",
        "input": {
            "iterations": 1,
            "thresholds": {},
            "results": {},
            "mode": "synthetic",
            "generated_at": T,
            "overall_pass": True,
        },
    }

def case_build_safety_benchmark_full() -> dict[str, Any]:
    return {
        "name": "safety_benchmark_full",
        "builder": "build_safety_benchmark",
        "input": {
            "iterations": 1000,
            "thresholds": {"arm_move_p95_ms": 250, "gripper_close_p95_ms": 120},
            "results": {
                "arm_move": {"min_ms": 10, "mean_ms": 85, "p95_ms": 240, "p99_ms": 300, "max_ms": 410, "pass": True},
                "gripper_close": {"min_ms": 5, "mean_ms": 40, "p95_ms": 150, "p99_ms": 180, "max_ms": 200, "pass": False},
            },
            "mode": "hardware",
            "generated_at": T,
            "overall_pass": False,
        },
    }

def case_build_ifu_minimal() -> dict[str, Any]:
    return {
        "name": "ifu_minimal",
        "builder": "build_ifu",
        "input": {
            "provider_identity": IFU_PROVIDER_MIN,
            "intended_purpose": IFU_OBJ_MIN,
            "capabilities_and_limitations": IFU_OBJ_MIN,
            "accuracy_and_performance": IFU_OBJ_MIN,
            "human_oversight_measures": IFU_OBJ_MIN,
            "known_risks_and_misuse": IFU_OBJ_MIN,
            "expected_lifetime": IFU_OBJ_MIN,
            "maintenance_requirements": IFU_OBJ_MIN,
            "generated_at": T,
        },
    }

def case_build_ifu_full_unicode() -> dict[str, Any]:
    return {
        "name": "ifu_full_unicode",
        "builder": "build_ifu",
        "input": {
            "provider_identity": IFU_PROVIDER_FULL,
            "intended_purpose": {"summary": "Teleoperated pick-and-place assistance"},
            "capabilities_and_limitations": {"max_payload_kg": 2.5, "reach_m": 0.6},
            "accuracy_and_performance": {"position_accuracy_mm": 1.5},
            "human_oversight_measures": {"hitl_required": True, "fail_safe": "estop_on_force_limit"},
            "known_risks_and_misuse": {"pinch_points": ["wrist_flex", "gripper"]},
            "expected_lifetime": {"years": 5, "cycles": 1_000_000},
            "maintenance_requirements": {"lubrication": "quarterly"},
            "generated_at": T,
        },
    }

def case_build_incident_report_zero() -> dict[str, Any]:
    return {
        "name": "incident_report_zero",
        "builder": "build_incident_report",
        "input": {
            "rrn": "RRN-000000000001",
            "incidents": [],
            "generated_at": T,
        },
    }

def case_build_incident_report_mixed_with_unknown() -> dict[str, Any]:
    return {
        "name": "incident_report_mixed_with_unknown",
        "builder": "build_incident_report",
        "input": {
            "rrn": "RRN-000000000001",
            "incidents": [
                {"incident_id": "I-001", "severity": "life_health", "description": "wrist stalled during pick", "occurred_at": T, "reported_at": T},
                {"incident_id": "I-002", "severity": "other", "description": "calibration drift", "occurred_at": T, "reported_at": T},
                {"incident_id": "I-003", "severity": "life_health", "description": "gripper over-torque", "occurred_at": T, "reported_at": T},
                {"incident_id": "I-004", "severity": "low", "description": "unknown severity — should be ignored", "occurred_at": T, "reported_at": T},
            ],
            "generated_at": T,
        },
    }

def case_build_eu_register_entry_defaults_omitted() -> dict[str, Any]:
    return {
        "name": "eu_register_entry_defaults_omitted",
        "builder": "build_eu_register_entry",
        "input": {
            "fria_ref": "bob-fria-v1.json",
            "provider": {"name": "craigm26", "contact": "craigm26@gmail.com"},
            "system": {
                "rrn": "RRN-000000000001",
                "rrn_uri": "rrn://craigm26/robot/opencastor-rpi5-hailo-soarm101/bob-001",
                "robot_name": "Bob",
                "rcan_version": "3.0",
                "opencastor_version": "2026.4.23.0",
            },
            "annex_iii_basis": "Annex III §5(b) — critical infrastructure management",
            "generated_at": T,
        },
    }

def case_build_eu_register_entry_defaults_provided() -> dict[str, Any]:
    return {
        "name": "eu_register_entry_defaults_provided",
        "builder": "build_eu_register_entry",
        "input": {
            "fria_ref": "bob-fria-v1.json",
            "provider": {"name": "craigm26", "contact": "craigm26@gmail.com"},
            "system": {
                "rrn": "RRN-000000000001",
                "robot_name": "Bob",
                "rcan_version": "3.0",
            },
            "annex_iii_basis": "Annex III §5(b)",
            "generated_at": T,
            "conformity_status": "provisional",
            "submission_instructions": "Custom instructions for testing the override path.",
        },
    }

CASES = [
    case_build_safety_benchmark_minimal(),
    case_build_safety_benchmark_full(),
    case_build_ifu_minimal(),
    case_build_ifu_full_unicode(),
    case_build_incident_report_zero(),
    case_build_incident_report_mixed_with_unknown(),
    case_build_eu_register_entry_defaults_omitted(),
    case_build_eu_register_entry_defaults_provided(),
]

BUILDERS = {
    "build_safety_benchmark": build_safety_benchmark,
    "build_ifu": build_ifu,
    "build_incident_report": build_incident_report,
    "build_eu_register_entry": build_eu_register_entry,
}

out_cases: list[dict[str, Any]] = []
for c in CASES:
    builder = BUILDERS[c["builder"]]
    output = builder(**c["input"])
    canonical_bytes = rcan.canonical_json(output)
    out_cases.append({
        "name": c["name"],
        "builder": c["builder"],
        "input": c["input"],
        "expected_output": output,
        "expected_bytes_base64": base64.b64encode(canonical_bytes).decode("ascii"),
    })

fixture = {
    "format": "rcan-compliance-fixture-v1",
    "description": "Byte-level invariants for RCAN compliance builders (§23-26). Both rcan-py and rcan-ts MUST produce builder outputs whose canonical_json is byte-identical to expected_bytes_base64.",
    "rcan_py_version": rcan.__version__,
    "cases": out_cases,
}

print(json.dumps(fixture, indent=2, ensure_ascii=False))
```

- [ ] **Step 4: Run the generator and save to the fixture file**

Run (from the scratch venv with rcan 3.1.1 active):
```bash
python3 /tmp/gen_compliance_fixture.py > /home/craigm26/rcan-spec/fixtures/compliance-v1.json
```
Expected: file created with `rcan_py_version: "3.1.1"` and 8 cases. No stderr output.

- [ ] **Step 5: Sanity gate — verify every case round-trips**

Run (still in the scratch venv):
```bash
cd /home/craigm26/rcan-spec
python3 -c "
import base64, json, rcan
f = json.load(open('fixtures/compliance-v1.json'))
assert f['format'] == 'rcan-compliance-fixture-v1'
assert f['rcan_py_version'] == '3.1.1'
assert len(f['cases']) == 8
names = {c['name'] for c in f['cases']}
expected_names = {'safety_benchmark_minimal', 'safety_benchmark_full', 'ifu_minimal', 'ifu_full_unicode', 'incident_report_zero', 'incident_report_mixed_with_unknown', 'eu_register_entry_defaults_omitted', 'eu_register_entry_defaults_provided'}
assert names == expected_names, f'missing/extra cases: {names ^ expected_names}'
for c in f['cases']:
    got = rcan.canonical_json(c['expected_output'])
    expected = base64.b64decode(c['expected_bytes_base64'])
    assert got == expected, c['name']
print('all 8 cases: expected_output canonicalizes to expected_bytes_base64')
"
```
Expected: `all 8 cases: expected_output canonicalizes to expected_bytes_base64`.

- [ ] **Step 6: Confirm the unicode case round-trips a non-ASCII character**

Run:
```bash
cd /home/craigm26/rcan-spec
python3 -c "
import base64, json
f = json.load(open('fixtures/compliance-v1.json'))
uc = next(c for c in f['cases'] if c['name'] == 'ifu_full_unicode')
bytes_ = base64.b64decode(uc['expected_bytes_base64'])
assert b'Cr\xc3\xa8me' in bytes_, 'Crème should round-trip as UTF-8 bytes'
print('unicode: Crème round-trips as 0xC3 0xA8')
"
```
Expected: `unicode: Crème round-trips as 0xC3 0xA8`.

- [ ] **Step 7: Commit + push**

```bash
cd /home/craigm26/rcan-spec
git add fixtures/compliance-v1.json
git commit -m "fixtures: add compliance-v1 for cross-language byte parity (§23-26)

Locks rcan-py 3.1.1's build_safety_benchmark, build_ifu,
build_incident_report, build_eu_register_entry output bytes for
Release D1 (rcan-ts 3.2.0). 8 cases including unicode (Crème Brûlée
provider name) and unknown-severity-ignoring.

Matches the canonical-json-v1.json pattern from Release B.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push origin master
```

- [ ] **Step 8: Clean up the scratch venv**

```bash
deactivate 2>/dev/null || true
rm -rf /tmp/rcan-fixture-venv /tmp/gen_compliance_fixture.py
```

---

## Wave 1 — rcan-ts implementation

### Task 2: Pre-flight rcan-ts working tree

**Files:** read-only.

- [ ] **Step 1: Confirm tree clean and on main**

```bash
cd /home/craigm26/rcan-ts
git status
git branch --show-current
git pull --ff-only origin main
```
Expected: clean, on `main`, fast-forward or up to date. If not, report BLOCKED.

- [ ] **Step 2: Record current compliance surface baseline**

```bash
cd /home/craigm26/rcan-ts
wc -l src/compliance.ts
grep -n "^export" src/compliance.ts
grep -n '"version"' package.json | head -1
ls tests/compliance*.ts 2>/dev/null
```
Expected output (for the record):
- `src/compliance.ts` ~141 lines
- ~6 exports (FriaSigningKey, FriaConformance, FriaDocument, SafetyBenchmark, InstructionsForUse, IncidentSeverity, IncidentStatus, PostMarketIncident, EuComplianceStatus, EuRegisterEntry)
- `"version": "3.1.1",`
- `tests/compliance.test.ts` already exists (will be triaged in Task 3)

No commit.

---

### Task 3: Triage existing `tests/compliance.test.ts`

**Files:**
- Read: `/home/craigm26/rcan-ts/tests/compliance.test.ts`
- Possibly modify or delete: `/home/craigm26/rcan-ts/tests/compliance.test.ts`

- [ ] **Step 1: Read the file and categorize**

```bash
cd /home/craigm26/rcan-ts
wc -l tests/compliance.test.ts
head -60 tests/compliance.test.ts
```
Record:
- Does it test **§22 FRIA types** (those we're keeping)? → leave as-is.
- Does it test **§23-26 types** that we're replacing (e.g., `SafetyBenchmark.protocol`, `PostMarketIncident.severity === "low"`)? → this code will no longer type-check after Task 6 replaces the interfaces. Two options:
  - a. Update its §23-26 assertions to use the new wire-format shapes. Add to Task 6's commit.
  - b. Delete the whole file if ALL tests target the now-removed types (add Task 6 will subsume the coverage via behavioral tests).
- Does it test behavioral invariants that should be preserved? → migrate into `tests/compliance-builders.test.ts` in Task 10.

- [ ] **Step 2: Run the existing test to see current state**

```bash
cd /home/craigm26/rcan-ts
npm test -- tests/compliance.test.ts 2>&1 | tail -15
```
Expected: PASS (current state). Record the number of tests for later comparison.

- [ ] **Step 3: Decide + document**

Write a one-paragraph decision to the terminal (not committed — just for your own Task 7 commit message):
- "Keeping `tests/compliance.test.ts` — tests §22 FRIA types only" OR
- "Deleting `tests/compliance.test.ts` — all N tests target now-removed §23-26 types; coverage replaced by fixture + behavioral tests in Tasks 9+10" OR
- "Updating `tests/compliance.test.ts` inline — M of N tests target removable types, M rewritten to use new wire-format types"

Whichever decision, it will be executed in Task 7 (type replacements), not now.

No commit.

---

### Task 4: Copy fixture into rcan-ts bundled tests

**Files:**
- Create: `/home/craigm26/rcan-ts/tests/fixtures/compliance-v1.json`

- [ ] **Step 1: Copy the fixture**

```bash
cp /home/craigm26/rcan-spec/fixtures/compliance-v1.json /home/craigm26/rcan-ts/tests/fixtures/compliance-v1.json
```

- [ ] **Step 2: Verify byte-for-byte identical to upstream**

```bash
diff /home/craigm26/rcan-spec/fixtures/compliance-v1.json /home/craigm26/rcan-ts/tests/fixtures/compliance-v1.json
echo "exit: $?"
```
Expected: `exit: 0` (no output, files identical).

- [ ] **Step 3: Quick structural check**

```bash
cd /home/craigm26/rcan-ts
node -e "
const f = JSON.parse(require('fs').readFileSync('tests/fixtures/compliance-v1.json', 'utf8'));
console.log('format:', f.format);
console.log('rcan_py_version:', f.rcan_py_version);
console.log('cases:', f.cases.length);
console.log('names:', f.cases.map(c => c.name).join(', '));
"
```
Expected:
- `format: rcan-compliance-fixture-v1`
- `rcan_py_version: 3.1.1`
- `cases: 8`
- All 8 case names listed.

- [ ] **Step 4: Commit the bundled fixture**

```bash
cd /home/craigm26/rcan-ts
git add tests/fixtures/compliance-v1.json
git commit -m "test(fixtures): bundle compliance-v1 from rcan-spec

Byte-identical copy of rcan-spec/fixtures/compliance-v1.json — the
cross-language parity fixture for Release D1. Bundling matches the
pattern used for the canonical-json fixture: rcan-ts's CI runs in a
single-repo checkout and can't fetch a sibling, so the bundled copy
is the working source for vitest.

When the upstream fixture updates, re-run \`cp\` from rcan-spec and
re-commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Write the failing byte-parity fixture test

**Files:**
- Create: `/home/craigm26/rcan-ts/tests/compliance-fixture.test.ts`

- [ ] **Step 1: Inspect existing vitest import style**

```bash
cd /home/craigm26/rcan-ts
head -15 tests/encoding.test.ts tests/hybrid.test.ts 2>&1 | head -30
```
Record the `import` style used — should be `import { describe, it, expect } from "vitest"` with Node builtins like `readFileSync` from `node:fs`.

- [ ] **Step 2: Create the fixture test file**

Write `/home/craigm26/rcan-ts/tests/compliance-fixture.test.ts`:

```typescript
/**
 * Cross-language byte-parity tests for Release D1 compliance builders.
 *
 * Loads the bundled fixture at tests/fixtures/compliance-v1.json (sourced
 * from rcan-spec) and asserts that every case's canonicalJson(builder(input))
 * is byte-identical to the fixture's expected_bytes_base64 (decoded).
 *
 * Failure of any case means either:
 *   (a) the rcan-ts builder doesn't match rcan-py 3.1.1 — fix the builder, OR
 *   (b) canonicalJson has regressed — that would be a Release B regression.
 * Do NOT weaken the fixture; regenerate from rcan-py if the Python reference
 * has legitimately moved.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildSafetyBenchmark,
  buildIfu,
  buildIncidentReport,
  buildEuRegisterEntry,
  canonicalJson,
} from "../src/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixturePath = resolve(here, "fixtures", "compliance-v1.json");
const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));

type Case = {
  name: string;
  builder: string;
  input: Record<string, unknown>;
  expected_output: Record<string, unknown>;
  expected_bytes_base64: string;
};

const builders: Record<string, (opts: Record<string, unknown>) => Record<string, unknown>> = {
  build_safety_benchmark: buildSafetyBenchmark as never,
  build_ifu: buildIfu as never,
  build_incident_report: buildIncidentReport as never,
  build_eu_register_entry: buildEuRegisterEntry as never,
};

describe("compliance-v1 cross-language byte parity", () => {
  it("fixture loads and has 8 cases for rcan-py 3.1.1", () => {
    expect(fixture.format).toBe("rcan-compliance-fixture-v1");
    expect(fixture.rcan_py_version).toBe("3.1.1");
    expect(fixture.cases).toHaveLength(8);
  });

  for (const c of fixture.cases as Case[]) {
    it(c.name, () => {
      const builder = builders[c.builder];
      expect(builder).toBeDefined();
      const output = builder(c.input);
      const actualBytes = canonicalJson(output);
      const expectedBytes = new Uint8Array(Buffer.from(c.expected_bytes_base64, "base64"));
      expect(actualBytes).toEqual(expectedBytes);
    });
  }
});
```

- [ ] **Step 3: Run the test suite — expect import failures**

```bash
cd /home/craigm26/rcan-ts
npm test -- tests/compliance-fixture.test.ts 2>&1 | tail -30
```
Expected: FAIL with import errors (the 4 builders don't exist yet in `src/index.js`, so `import { buildSafetyBenchmark, ... }` resolves to `undefined` or triggers a compile error).

If the test file itself fails to compile due to TypeScript strict mode resolving `undefined` imports, that's also RED — acceptable. Record which specific error you see.

- [ ] **Step 4: Commit the failing test**

```bash
cd /home/craigm26/rcan-ts
git add tests/compliance-fixture.test.ts
git commit -m "test(compliance): add fixture byte-parity tests (RED step)

Release D1 TDD red step. Tests the 4 compliance builders (which don't
exist yet) against the bundled rcan-spec fixture. Will pass once
src/compliance.ts adds buildSafetyBenchmark, buildIfu, buildIncidentReport,
buildEuRegisterEntry + re-exports from src/index.ts in subsequent commits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Replace §23-26 type interfaces in `src/compliance.ts`

**Files:**
- Modify: `/home/craigm26/rcan-ts/src/compliance.ts` (the §23-26 interfaces)

- [ ] **Step 1: Read the current content**

```bash
cd /home/craigm26/rcan-ts
cat src/compliance.ts
```
Record which lines contain the §22, §23, §24, §25, §26 blocks (section headers should be obvious — `// ── §22: FRIA ...`, etc.). The §22 block (FRIA) MUST NOT be changed.

- [ ] **Step 2: Rewrite the §23 SafetyBenchmark interface**

Find the `// ── §23: Safety Benchmark Protocol ──` section and the existing `SafetyBenchmark` interface. Replace the interface body (from `export interface SafetyBenchmark {` through the matching `}`) with:

```typescript
/** Output of `buildSafetyBenchmark` — §23 rcan-safety-benchmark-v1 envelope. */
export interface SafetyBenchmark {
  /** Schema identifier — always `SAFETY_BENCHMARK_SCHEMA` ("rcan-safety-benchmark-v1"). */
  readonly schema: string;
  /** ISO-8601 timestamp when the benchmark was generated. */
  readonly generated_at: string;
  /** Run mode, e.g. "synthetic" or "hardware". */
  readonly mode: string;
  /** Number of samples per path. */
  readonly iterations: number;
  /** Threshold map keyed by `{path}_p95_ms` (caller pre-names). */
  readonly thresholds: Record<string, number>;
  /** Path name → stats object ({ min_ms, mean_ms, p95_ms, p99_ms, max_ms, pass }). */
  readonly results: Record<string, unknown>;
  /** Whether every path passed its threshold. */
  readonly overall_pass: boolean;
}
```

- [ ] **Step 3: Rewrite the §24 InstructionsForUse interface**

Replace the existing `InstructionsForUse` interface body with:

```typescript
/** Output of `buildIfu` — §24 rcan-ifu-v1 envelope (EU AI Act Art. 13(3)). */
export interface InstructionsForUse {
  /** Schema identifier — always `IFU_SCHEMA` ("rcan-ifu-v1"). */
  readonly schema: string;
  /** ISO-8601 timestamp of issuance. */
  readonly generated_at: string;
  /** The 8 Art. 13(3) section field names in canonical order. */
  readonly art13_coverage: readonly string[];
  /** Art. 13(3)(a) provider identity block. */
  readonly provider_identity: Record<string, unknown>;
  /** Art. 13(3)(b) intended purpose block. */
  readonly intended_purpose: Record<string, unknown>;
  /** Art. 13(3)(c) capabilities and limitations. */
  readonly capabilities_and_limitations: Record<string, unknown>;
  /** Art. 13(3)(d) accuracy and performance. */
  readonly accuracy_and_performance: Record<string, unknown>;
  /** Art. 13(3)(e) human oversight measures. */
  readonly human_oversight_measures: Record<string, unknown>;
  /** Art. 13(3)(f) known risks and misuse. */
  readonly known_risks_and_misuse: Record<string, unknown>;
  /** Art. 13(3)(g) expected lifetime. */
  readonly expected_lifetime: Record<string, unknown>;
  /** Art. 13(3)(h) maintenance requirements. */
  readonly maintenance_requirements: Record<string, unknown>;
}
```

- [ ] **Step 4: Rewrite §25 types (severity + incident report)**

Replace the existing `IncidentSeverity`, `IncidentStatus`, and `PostMarketIncident` definitions with:

```typescript
/** EU AI Act Art. 72 serious-incident categories — used by §25 post-market reports. */
export type IncidentSeverity = "life_health" | "other";

/** Output of `buildIncidentReport` — §25 rcan-incidents-v1 envelope (EU AI Act Art. 72). */
export interface PostMarketIncidentReport {
  /** Schema identifier — always `INCIDENT_REPORT_SCHEMA` ("rcan-incidents-v1"). */
  readonly schema: string;
  /** ISO-8601 timestamp when the report was generated. */
  readonly generated_at: string;
  /** Robot Registration Number this report covers. */
  readonly rrn: string;
  /** `incidents.length` — auto-computed by the builder. */
  readonly total_incidents: number;
  /** `{ life_health: N, other: M }` — auto-computed. Unknown severities silently ignored. */
  readonly incidents_by_severity: Record<IncidentSeverity, number>;
  /** Per-severity reporting deadline strings from `REPORTING_DEADLINES`. */
  readonly reporting_deadlines: Record<string, string>;
  /** The Art. 72 provider-obligation note from `ART72_NOTE`. */
  readonly art72_note: string;
  /** The raw incident entries passed to the builder. */
  readonly incidents: readonly Record<string, unknown>[];
}
```

**Remove** the old `IncidentStatus` type union entirely (`"open" | "under_review" | "resolved"`) — it has no rcan-py counterpart and is not part of any builder output.

- [ ] **Step 5: Rewrite the §26 EuRegisterEntry interface**

Replace the existing `EuRegisterEntry` interface body with:

```typescript
/** Output of `buildEuRegisterEntry` — §26 rcan-eu-register-v1 envelope (EU AI Act Art. 49). */
export interface EuRegisterEntry {
  /** Schema identifier — always `EU_REGISTER_SCHEMA` ("rcan-eu-register-v1"). */
  readonly schema: string;
  /** ISO-8601 timestamp of entry generation. */
  readonly generated_at: string;
  /** Basename of the signed rcan-fria-v1 JSON attached. */
  readonly fria_ref: string;
  /** Provider block — `{ name, contact, ... }`. */
  readonly provider: Record<string, unknown>;
  /** System block — `{ rrn, rrn_uri, robot_name, rcan_version, opencastor_version, ... }`. */
  readonly system: Record<string, unknown>;
  /** The Annex III high-risk category string. */
  readonly annex_iii_basis: string;
  /** Defaults to `CONFORMITY_STATUS_DECLARED` ("declared") unless overridden. */
  readonly conformity_status: string;
  /** Defaults to the `SUBMISSION_INSTRUCTIONS` blurb unless overridden. */
  readonly submission_instructions: string;
}
```

**Remove** the old `EuComplianceStatus` type union (`"compliant" | "provisional" | "non_compliant" | "no_fria"`) — it has no rcan-py counterpart. `conformity_status` is now a free-form string matching rcan-py's shape.

- [ ] **Step 6: Verify §22 FRIA types are unchanged**

```bash
cd /home/craigm26/rcan-ts
grep -nE "interface FriaSigningKey|interface FriaConformance|interface FriaDocument" src/compliance.ts
```
Expected: all three definitions still present, unchanged from Task 2 baseline.

- [ ] **Step 7: Triage `tests/compliance.test.ts` per Task 3 decision**

Apply the decision recorded in Task 3 Step 3:
- If "keep": no action.
- If "delete": `rm tests/compliance.test.ts`.
- If "update": edit the file in place — rewrite §23-26 assertions to use the new field names (e.g., `SafetyBenchmark.schema` instead of `SafetyBenchmark.protocol`; `PostMarketIncidentReport.incidents_by_severity` instead of `PostMarketIncident.severity`).

- [ ] **Step 8: Compile check**

```bash
cd /home/craigm26/rcan-ts
npx tsc --noEmit 2>&1 | tail -30
```
Expected: no errors. If the compiler complains about removed types (`IncidentStatus` / `EuComplianceStatus`) being referenced elsewhere, grep for them and fix consumers:
```bash
grep -rn "IncidentStatus\|EuComplianceStatus" src/ tests/
```

- [ ] **Step 9: Commit**

```bash
cd /home/craigm26/rcan-ts
git add src/compliance.ts tests/compliance.test.ts 2>/dev/null || true
git add -u tests/compliance.test.ts 2>/dev/null || true
git add src/compliance.ts
git commit -m "feat(compliance)!: rewrite §23-26 types to match rcan-py wire format

BREAKING: SafetyBenchmark, InstructionsForUse, PostMarketIncident
(renamed to PostMarketIncidentReport), and EuRegisterEntry interfaces
are now shaped to match what rcan.build_* functions emit on the wire
(per rcan-spec/fixtures/compliance-v1.json, bundled at tests/fixtures/).

- §23 SafetyBenchmark: { schema, generated_at, mode, iterations,
  thresholds, results, overall_pass }
- §24 InstructionsForUse: 8 Art. 13(3) sections at top level +
  art13_coverage + schema + generated_at
- §25 PostMarketIncidentReport (renamed from PostMarketIncident):
  auto-computed total_incidents + incidents_by_severity
- §26 EuRegisterEntry: schema + generated_at + fria_ref + provider +
  system + annex_iii_basis + conformity_status + submission_instructions

IncidentSeverity tightened to \"life_health\" | \"other\" (EU AI Act
Art. 72 categories per rcan-py VALID_SEVERITIES).

Removed: IncidentStatus union, EuComplianceStatus union — no rcan-py
counterpart, no consumers.

§22 FRIA types unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Add schema + spec-domain constants to `src/compliance.ts`

**Files:**
- Modify: `/home/craigm26/rcan-ts/src/compliance.ts`

- [ ] **Step 1: Append the constants block**

At the END of `src/compliance.ts` (after all the interface definitions), append:

```typescript

// ═════════════════════════════════════════════════════════════════════
// Schema identifiers + spec-domain constants
//
// Values copied from rcan-py 3.1.1 rcan/compliance.py. These MUST stay
// byte-identical to rcan-py — the compliance-v1 fixture proves it.
// ═════════════════════════════════════════════════════════════════════

/** §23 schema identifier. */
export const SAFETY_BENCHMARK_SCHEMA = "rcan-safety-benchmark-v1";
/** §24 schema identifier. */
export const IFU_SCHEMA = "rcan-ifu-v1";
/** §25 schema identifier. */
export const INCIDENT_REPORT_SCHEMA = "rcan-incidents-v1";
/** §26 schema identifier. */
export const EU_REGISTER_SCHEMA = "rcan-eu-register-v1";

/**
 * §24 Art. 13(3) — the 8 IFU sections EU AI Act mandates, in canonical order.
 * buildIfu emits this list as the `art13_coverage` field.
 */
export const ART13_COVERAGE: readonly string[] = [
  "provider_identity",
  "intended_purpose",
  "capabilities_and_limitations",
  "accuracy_and_performance",
  "human_oversight_measures",
  "known_risks_and_misuse",
  "expected_lifetime",
  "maintenance_requirements",
] as const;

/** §25 Art. 72 — post-market incident severity categories. */
export const VALID_SEVERITIES: readonly IncidentSeverity[] = ["life_health", "other"] as const;

/** §25 Art. 72 — reporting deadlines per severity. */
export const REPORTING_DEADLINES: Readonly<Record<string, string>> = {
  life_health: "15 days from incident timestamp",
  other: "90 days from incident timestamp",
};

/** §25 Art. 72 provider-obligation note embedded in every incident report. */
export const ART72_NOTE: string =
  "Providers must report serious incidents to the relevant national " +
  "authority within the applicable deadline per EU AI Act Art. 72.";

/** §26 Art. 49 default conformity status. */
export const CONFORMITY_STATUS_DECLARED = "declared";

/** §26 Art. 49 default submission instructions. */
export const SUBMISSION_INSTRUCTIONS: string =
  "Submit this package to the EU AI Act database at " +
  "https://ec.europa.eu/digital-strategy/en/policies/european-ai-act. " +
  "Include the referenced rcan-fria-v1 JSON as an attachment.";
```

- [ ] **Step 2: Verify all constants present**

```bash
cd /home/craigm26/rcan-ts
grep -nE "^export const (SAFETY_BENCHMARK_SCHEMA|IFU_SCHEMA|INCIDENT_REPORT_SCHEMA|EU_REGISTER_SCHEMA|ART13_COVERAGE|VALID_SEVERITIES|REPORTING_DEADLINES|ART72_NOTE|CONFORMITY_STATUS_DECLARED|SUBMISSION_INSTRUCTIONS)" src/compliance.ts
```
Expected: 10 matches.

- [ ] **Step 3: Compile check**

```bash
cd /home/craigm26/rcan-ts
npx tsc --noEmit 2>&1 | tail -10
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /home/craigm26/rcan-ts
git add src/compliance.ts
git commit -m "feat(compliance): add §23-26 schema + spec-domain constants

Ten constants matching rcan-py 3.1.1 exactly:
- SAFETY_BENCHMARK_SCHEMA, IFU_SCHEMA, INCIDENT_REPORT_SCHEMA,
  EU_REGISTER_SCHEMA — schema identifiers used by the builders
- ART13_COVERAGE — the 8 Art. 13(3) IFU section names in canonical
  order
- VALID_SEVERITIES — (\"life_health\", \"other\") per Art. 72
- REPORTING_DEADLINES — per-severity deadline strings
- ART72_NOTE — the Art. 72 provider-obligation note text
- CONFORMITY_STATUS_DECLARED, SUBMISSION_INSTRUCTIONS — §26 defaults

Values are byte-identical to rcan-py. Fixture-parity test (Task 11)
confirms end-to-end.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Implement the 4 builder functions

**Files:**
- Modify: `/home/craigm26/rcan-ts/src/compliance.ts`

- [ ] **Step 1: Append the builders block**

At the END of `src/compliance.ts` (after the constants from Task 7), append:

```typescript

// ═════════════════════════════════════════════════════════════════════
// Builders — v3.1 spec-shaped envelopes ready to canonicalize + sign
//
// Each builder is a pure function: takes snake_case kwargs matching
// rcan-py's build_* signature, returns a plain object whose
// canonicalJson() is byte-identical to rcan-py's output.
//
// Do NOT translate keys or add fields — the compliance-v1 fixture
// enforces exact parity.
// ═════════════════════════════════════════════════════════════════════

/**
 * Build a §23 rcan-safety-benchmark-v1 envelope.
 *
 * @param opts.iterations - Number of samples per path.
 * @param opts.thresholds - Threshold map keyed by `{path}_p95_ms` (caller-named).
 * @param opts.results - Path name → stats object (min_ms/mean_ms/p95_ms/p99_ms/max_ms/pass).
 * @param opts.mode - Run mode, e.g. "synthetic" or "hardware".
 * @param opts.generated_at - ISO-8601 UTC timestamp (caller formats).
 * @param opts.overall_pass - Whether every path passed its threshold.
 * @returns Envelope ready to serialize via canonicalJson and sign via signBody.
 */
export function buildSafetyBenchmark(opts: {
  iterations: number;
  thresholds: Record<string, number>;
  results: Record<string, unknown>;
  mode: string;
  generated_at: string;
  overall_pass: boolean;
}): SafetyBenchmark {
  return {
    schema: SAFETY_BENCHMARK_SCHEMA,
    generated_at: opts.generated_at,
    mode: opts.mode,
    iterations: opts.iterations,
    thresholds: opts.thresholds,
    results: opts.results,
    overall_pass: opts.overall_pass,
  };
}

/**
 * Build a §24 rcan-ifu-v1 envelope (EU AI Act Art. 13(3)).
 *
 * All 8 Art. 13(3) sections are required. `art13_coverage` is emitted
 * automatically from the `ART13_COVERAGE` constant.
 */
export function buildIfu(opts: {
  provider_identity: Record<string, unknown>;
  intended_purpose: Record<string, unknown>;
  capabilities_and_limitations: Record<string, unknown>;
  accuracy_and_performance: Record<string, unknown>;
  human_oversight_measures: Record<string, unknown>;
  known_risks_and_misuse: Record<string, unknown>;
  expected_lifetime: Record<string, unknown>;
  maintenance_requirements: Record<string, unknown>;
  generated_at: string;
}): InstructionsForUse {
  return {
    schema: IFU_SCHEMA,
    generated_at: opts.generated_at,
    art13_coverage: [...ART13_COVERAGE],
    provider_identity: opts.provider_identity,
    intended_purpose: opts.intended_purpose,
    capabilities_and_limitations: opts.capabilities_and_limitations,
    accuracy_and_performance: opts.accuracy_and_performance,
    human_oversight_measures: opts.human_oversight_measures,
    known_risks_and_misuse: opts.known_risks_and_misuse,
    expected_lifetime: opts.expected_lifetime,
    maintenance_requirements: opts.maintenance_requirements,
  };
}

/**
 * Build a §25 rcan-incidents-v1 envelope (EU AI Act Art. 72 post-market).
 *
 * Auto-computes `total_incidents = opts.incidents.length` and
 * `incidents_by_severity` (seeded with VALID_SEVERITIES keys at 0,
 * incremented for each known severity). Unknown severities are silently
 * ignored — mirrors rcan-py behavior.
 */
export function buildIncidentReport(opts: {
  rrn: string;
  incidents: readonly Record<string, unknown>[];
  generated_at: string;
}): PostMarketIncidentReport {
  const bySeverity: Record<IncidentSeverity, number> = { life_health: 0, other: 0 };
  for (const entry of opts.incidents) {
    const sev = entry.severity;
    if (sev === "life_health" || sev === "other") {
      bySeverity[sev] += 1;
    }
  }
  return {
    schema: INCIDENT_REPORT_SCHEMA,
    generated_at: opts.generated_at,
    rrn: opts.rrn,
    total_incidents: opts.incidents.length,
    incidents_by_severity: bySeverity,
    reporting_deadlines: { ...REPORTING_DEADLINES },
    art72_note: ART72_NOTE,
    incidents: [...opts.incidents],
  };
}

/**
 * Build a §26 rcan-eu-register-v1 envelope (EU AI Act Art. 49).
 *
 * `conformity_status` defaults to `CONFORMITY_STATUS_DECLARED` ("declared")
 * and `submission_instructions` defaults to `SUBMISSION_INSTRUCTIONS` when
 * omitted or `undefined`.
 */
export function buildEuRegisterEntry(opts: {
  fria_ref: string;
  provider: Record<string, unknown>;
  system: Record<string, unknown>;
  annex_iii_basis: string;
  generated_at: string;
  conformity_status?: string;
  submission_instructions?: string;
}): EuRegisterEntry {
  return {
    schema: EU_REGISTER_SCHEMA,
    generated_at: opts.generated_at,
    fria_ref: opts.fria_ref,
    provider: opts.provider,
    system: opts.system,
    annex_iii_basis: opts.annex_iii_basis,
    conformity_status: opts.conformity_status ?? CONFORMITY_STATUS_DECLARED,
    submission_instructions: opts.submission_instructions ?? SUBMISSION_INSTRUCTIONS,
  };
}
```

- [ ] **Step 2: Compile check**

```bash
cd /home/craigm26/rcan-ts
npx tsc --noEmit 2>&1 | tail -15
```
Expected: no errors.

- [ ] **Step 3: Don't run vitest yet** — the builders are not re-exported from `src/index.ts` yet (Task 9). Fixture test will still fail on import. Commit and proceed.

- [ ] **Step 4: Commit**

```bash
cd /home/craigm26/rcan-ts
git add src/compliance.ts
git commit -m "feat(compliance): add §23-26 wire-format builders

Four new functions producing envelope dicts whose canonicalJson is
byte-identical to rcan-py 3.1.1's build_* output:

- buildSafetyBenchmark(opts) → SafetyBenchmark
- buildIfu(opts) → InstructionsForUse
- buildIncidentReport(opts) → PostMarketIncidentReport
  (auto-computes total_incidents + incidents_by_severity; unknown
   severities silently ignored)
- buildEuRegisterEntry(opts) → EuRegisterEntry
  (defaults conformity_status and submission_instructions from
   re-exported constants when kwargs omitted)

Input keys are snake_case to mirror the wire format 1:1 — no
translation shim. Per Release B doctrine: rcan-spec is the authority,
no drift in downstream SDKs.

Callers serialize + sign via the existing canonicalJson + signBody.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Re-export builders + constants + types from `src/index.ts`

**Files:**
- Modify: `/home/craigm26/rcan-ts/src/index.ts`

- [ ] **Step 1: Inspect current compliance exports in index.ts**

```bash
cd /home/craigm26/rcan-ts
grep -n "compliance" src/index.ts
```
Record what's already re-exported from `./compliance.js` (likely the §22 FRIA types plus the defunct §23-26 types).

- [ ] **Step 2: Update the export block**

Find the existing `export { ... } from "./compliance.js"` block (or similar `export type` block) and replace with:

```typescript
export {
  // §22 FRIA types
  type FriaSigningKey,
  type FriaConformance,
  type FriaDocument,
  // §23-26 wire-format types
  type SafetyBenchmark,
  type InstructionsForUse,
  type IncidentSeverity,
  type PostMarketIncidentReport,
  type EuRegisterEntry,
  // §23-26 schema identifiers
  SAFETY_BENCHMARK_SCHEMA,
  IFU_SCHEMA,
  INCIDENT_REPORT_SCHEMA,
  EU_REGISTER_SCHEMA,
  // §23-26 spec-domain constants
  ART13_COVERAGE,
  VALID_SEVERITIES,
  REPORTING_DEADLINES,
  ART72_NOTE,
  CONFORMITY_STATUS_DECLARED,
  SUBMISSION_INSTRUCTIONS,
  // §23-26 builders
  buildSafetyBenchmark,
  buildIfu,
  buildIncidentReport,
  buildEuRegisterEntry,
} from "./compliance.js";
```

**Important:** delete any pre-existing re-export lines for `PostMarketIncident` (renamed), `IncidentStatus` (removed), `EuComplianceStatus` (removed). Grep to confirm they're gone:
```bash
grep -nE "PostMarketIncident[^R]|IncidentStatus|EuComplianceStatus" src/index.ts
```
Expected: no matches (the regex `PostMarketIncident[^R]` matches the old name but NOT the new `PostMarketIncidentReport`).

- [ ] **Step 3: Compile check**

```bash
cd /home/craigm26/rcan-ts
npx tsc --noEmit 2>&1 | tail -15
```
Expected: no errors.

- [ ] **Step 4: Run the fixture test — expect GREEN**

```bash
cd /home/craigm26/rcan-ts
npm test -- tests/compliance-fixture.test.ts 2>&1 | tail -25
```
Expected: all 9 tests pass (1 metadata check + 8 cases).

If any case FAILS with a byte mismatch, STOP and investigate:
- Inspect the actual vs expected bytes diff. Common causes: (a) a builder field order misordered (shouldn't matter under canonical JSON, but verify), (b) a default value drift (check `CONFORMITY_STATUS_DECLARED` / `SUBMISSION_INSTRUCTIONS` string content), (c) unicode not round-tripping (verify `canonicalJson` still uses ensure_ascii=false equivalent).
- Do NOT edit the fixture. If the fixture itself is wrong, regenerate via Task 1's script.

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/rcan-ts
git add src/index.ts
git commit -m "feat(index): re-export §23-26 compliance builders + constants

Top-level API surface for Release D1. All 4 builders, 10 constants,
and 8 type names (including FRIA) now importable via:

  import {
    buildSafetyBenchmark, VALID_SEVERITIES, SafetyBenchmark,
  } from \"rcan-ts\";

Removed defunct re-exports: PostMarketIncident (renamed to
PostMarketIncidentReport), IncidentStatus, EuComplianceStatus.

Fixture byte-parity test now green.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Add behavioral tests for builder invariants

**Files:**
- Create: `/home/craigm26/rcan-ts/tests/compliance-builders.test.ts`

- [ ] **Step 1: Create the test file**

Write `/home/craigm26/rcan-ts/tests/compliance-builders.test.ts`:

```typescript
/**
 * Behavioral tests for the Release D1 compliance builders — cover the
 * invariants that aren't directly captured by the fixture (auto-computed
 * totals, default fallbacks, schema field correctness).
 *
 * These tests are redundant with compliance-fixture.test.ts for byte
 * parity but document the human-readable intent of each builder.
 */

import { describe, it, expect } from "vitest";
import {
  ART13_COVERAGE,
  ART72_NOTE,
  CONFORMITY_STATUS_DECLARED,
  EU_REGISTER_SCHEMA,
  IFU_SCHEMA,
  INCIDENT_REPORT_SCHEMA,
  REPORTING_DEADLINES,
  SAFETY_BENCHMARK_SCHEMA,
  SUBMISSION_INSTRUCTIONS,
  VALID_SEVERITIES,
  buildEuRegisterEntry,
  buildIfu,
  buildIncidentReport,
  buildSafetyBenchmark,
} from "../src/index.js";

const T = "2026-04-23T00:00:00Z";

describe("buildSafetyBenchmark", () => {
  it("output includes schema === SAFETY_BENCHMARK_SCHEMA", () => {
    const out = buildSafetyBenchmark({
      iterations: 1, thresholds: {}, results: {}, mode: "synthetic",
      generated_at: T, overall_pass: true,
    });
    expect(out.schema).toBe(SAFETY_BENCHMARK_SCHEMA);
    expect(out.schema).toBe("rcan-safety-benchmark-v1");
  });

  it("passes through iterations, thresholds, results, mode, overall_pass unchanged", () => {
    const out = buildSafetyBenchmark({
      iterations: 42, thresholds: { x_p95_ms: 100 }, results: { x: { pass: true } },
      mode: "hardware", generated_at: T, overall_pass: false,
    });
    expect(out.iterations).toBe(42);
    expect(out.thresholds).toEqual({ x_p95_ms: 100 });
    expect(out.results).toEqual({ x: { pass: true } });
    expect(out.mode).toBe("hardware");
    expect(out.overall_pass).toBe(false);
  });
});

describe("buildIfu", () => {
  const minInput = {
    provider_identity: { name: "P" },
    intended_purpose: { note: "x" },
    capabilities_and_limitations: { note: "x" },
    accuracy_and_performance: { note: "x" },
    human_oversight_measures: { note: "x" },
    known_risks_and_misuse: { note: "x" },
    expected_lifetime: { note: "x" },
    maintenance_requirements: { note: "x" },
    generated_at: T,
  };

  it("output includes schema === IFU_SCHEMA", () => {
    expect(buildIfu(minInput).schema).toBe(IFU_SCHEMA);
  });

  it("emits art13_coverage matching ART13_COVERAGE constant", () => {
    expect(buildIfu(minInput).art13_coverage).toEqual([...ART13_COVERAGE]);
  });

  it("output contains all 8 Art. 13(3) section fields at top level", () => {
    const out = buildIfu(minInput);
    for (const key of ART13_COVERAGE) {
      expect(out).toHaveProperty(key);
    }
  });
});

describe("buildIncidentReport", () => {
  it("auto-computes total_incidents === incidents.length", () => {
    const out = buildIncidentReport({
      rrn: "RRN-000000000001",
      incidents: [
        { severity: "life_health" },
        { severity: "other" },
        { severity: "life_health" },
      ],
      generated_at: T,
    });
    expect(out.total_incidents).toBe(3);
  });

  it("incidents_by_severity has all VALID_SEVERITIES keys initialized to 0", () => {
    const out = buildIncidentReport({
      rrn: "RRN-000000000001",
      incidents: [],
      generated_at: T,
    });
    for (const sev of VALID_SEVERITIES) {
      expect(out.incidents_by_severity[sev]).toBe(0);
    }
  });

  it("incidents_by_severity counts known severities", () => {
    const out = buildIncidentReport({
      rrn: "RRN-000000000001",
      incidents: [
        { severity: "life_health" },
        { severity: "life_health" },
        { severity: "other" },
      ],
      generated_at: T,
    });
    expect(out.incidents_by_severity).toEqual({ life_health: 2, other: 1 });
  });

  it("silently ignores unknown severities (no throw, no count)", () => {
    const out = buildIncidentReport({
      rrn: "RRN-000000000001",
      incidents: [
        { severity: "life_health" },
        { severity: "low" },        // unknown — ignored
        { severity: "critical" },   // unknown — ignored
        { severity: "other" },
      ],
      generated_at: T,
    });
    // total_incidents still counts all 4 entries
    expect(out.total_incidents).toBe(4);
    // but by_severity only counts the 2 known ones
    expect(out.incidents_by_severity).toEqual({ life_health: 1, other: 1 });
  });

  it("output includes schema, reporting_deadlines, art72_note from constants", () => {
    const out = buildIncidentReport({
      rrn: "RRN-000000000001",
      incidents: [],
      generated_at: T,
    });
    expect(out.schema).toBe(INCIDENT_REPORT_SCHEMA);
    expect(out.reporting_deadlines).toEqual({ ...REPORTING_DEADLINES });
    expect(out.art72_note).toBe(ART72_NOTE);
  });
});

describe("buildEuRegisterEntry", () => {
  const minInput = {
    fria_ref: "fria.json",
    provider: { name: "craigm26" },
    system: { rrn: "RRN-000000000001" },
    annex_iii_basis: "Annex III §5(b)",
    generated_at: T,
  };

  it("output includes schema === EU_REGISTER_SCHEMA", () => {
    expect(buildEuRegisterEntry(minInput).schema).toBe(EU_REGISTER_SCHEMA);
  });

  it("uses CONFORMITY_STATUS_DECLARED when conformity_status is omitted", () => {
    expect(buildEuRegisterEntry(minInput).conformity_status).toBe(CONFORMITY_STATUS_DECLARED);
  });

  it("uses SUBMISSION_INSTRUCTIONS when submission_instructions is omitted", () => {
    expect(buildEuRegisterEntry(minInput).submission_instructions).toBe(SUBMISSION_INSTRUCTIONS);
  });

  it("respects explicit conformity_status override", () => {
    const out = buildEuRegisterEntry({ ...minInput, conformity_status: "provisional" });
    expect(out.conformity_status).toBe("provisional");
  });

  it("respects explicit submission_instructions override", () => {
    const out = buildEuRegisterEntry({ ...minInput, submission_instructions: "Custom." });
    expect(out.submission_instructions).toBe("Custom.");
  });
});
```

- [ ] **Step 2: Run the new test file**

```bash
cd /home/craigm26/rcan-ts
npm test -- tests/compliance-builders.test.ts 2>&1 | tail -25
```
Expected: all tests PASS (expected count: ~15 tests across 4 describe blocks).

- [ ] **Step 3: Run the full suite**

```bash
cd /home/craigm26/rcan-ts
npm test 2>&1 | tail -15
```
Expected: full suite green. Test count should be **at least 627 existing + ~24 new (9 fixture + ~15 behavioral) = ~651 total**, minus any tests removed in Task 6 Step 7 (if `tests/compliance.test.ts` was deleted).

- [ ] **Step 4: Commit**

```bash
cd /home/craigm26/rcan-ts
git add tests/compliance-builders.test.ts
git commit -m "test(compliance): add behavioral tests for the 4 builders

15+ vitest cases covering:
- schema field correctness (schema === {SCHEMA_NAME} for each builder)
- auto-computed total_incidents + incidents_by_severity in
  buildIncidentReport
- unknown-severity silent ignoring
- CONFORMITY_STATUS_DECLARED / SUBMISSION_INSTRUCTIONS fallback and
  explicit override paths in buildEuRegisterEntry
- art13_coverage emission matching ART13_COVERAGE in buildIfu

Redundant with compliance-fixture.test.ts for byte parity but
documents human-readable intent. Fixture is the byte-level gate;
these are the behavioral spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Build check + dist regression guard

**Files:** no file edits.

- [ ] **Step 1: Build the package**

```bash
cd /home/craigm26/rcan-ts
rm -rf dist/
npm run build 2>&1 | tail -15
```
Expected: tsup completes without errors, produces `dist/index.mjs`, `dist/index.cjs`, `dist/index.d.ts`, etc.

- [ ] **Step 2: Assert Release B crypto indirection did not regress**

```bash
cd /home/craigm26/rcan-ts
grep -nE 'import\("crypto"\)' dist/*.mjs dist/*.cjs 2>&1 | head -5
echo "exit: $?"
```
Expected: `exit: 1` (grep found no matches — the `node:crypto` prefix survived). If exit is 0 (matches found), STOP — that's a Release B regression; the `const cryptoModule = "node:crypto"; await import(cryptoModule)` pattern in `src/hybrid.ts` / `src/multimodal.ts` / `src/transport.ts` has been lost. Do NOT publish.

- [ ] **Step 3: Verify the new builders are in the dist .d.ts**

```bash
cd /home/craigm26/rcan-ts
grep -E "buildSafetyBenchmark|buildIfu|buildIncidentReport|buildEuRegisterEntry" dist/index.d.ts | head -10
```
Expected: each builder signature present.

- [ ] **Step 4: Verify constants are exported in dist**

```bash
cd /home/craigm26/rcan-ts
grep -E "VALID_SEVERITIES|SAFETY_BENCHMARK_SCHEMA|ART13_COVERAGE" dist/index.d.ts | head -5
```
Expected: declarations present.

- [ ] **Step 5: No commit** — build artifacts are in `.gitignore`. Proceed to Task 12.

---

## Wave 2 — publish

### Task 12: Version bump + CHANGELOG

**Files:**
- Modify: `/home/craigm26/rcan-ts/package.json`
- Modify: `/home/craigm26/rcan-ts/CHANGELOG.md`

- [ ] **Step 1: Bump package.json version**

Edit `/home/craigm26/rcan-ts/package.json`, change `"version": "3.1.1"` to `"version": "3.2.0"`.

Verify:
```bash
cd /home/craigm26/rcan-ts
grep '"version"' package.json | head -1
```
Expected: `"version": "3.2.0",`.

- [ ] **Step 2: Add CHANGELOG entry**

Insert the following block at the TOP of `/home/craigm26/rcan-ts/CHANGELOG.md` (above the existing `## [3.1.1] — 2026-04-23` entry):

```markdown
## [3.2.0] — 2026-04-23

### Added

- **4 §22-26 compliance builders** (new, ported from rcan-py 3.1.1):
  - `buildSafetyBenchmark(opts)` → `SafetyBenchmark` envelope (§23)
  - `buildIfu(opts)` → `InstructionsForUse` envelope (§24, EU AI Act Art. 13(3))
  - `buildIncidentReport(opts)` → `PostMarketIncidentReport` (§25, Art. 72) — auto-computes `total_incidents` + `incidents_by_severity`; unknown severities silently ignored
  - `buildEuRegisterEntry(opts)` → `EuRegisterEntry` (§26, Art. 49) — defaults `conformity_status` and `submission_instructions` from re-exported constants
- **10 new constants** re-exported: `SAFETY_BENCHMARK_SCHEMA`, `IFU_SCHEMA`, `INCIDENT_REPORT_SCHEMA`, `EU_REGISTER_SCHEMA`, `ART13_COVERAGE`, `VALID_SEVERITIES`, `REPORTING_DEADLINES`, `ART72_NOTE`, `CONFORMITY_STATUS_DECLARED`, `SUBMISSION_INSTRUCTIONS`.

### Changed (internal — no shipping TS consumers affected)

- Rewrote `§23 SafetyBenchmark`, `§24 InstructionsForUse`, `§25 PostMarketIncidentReport` (renamed from `PostMarketIncident`), `§26 EuRegisterEntry` type interfaces in `src/compliance.ts` to match the rcan-py 3.1.1 wire format. Byte parity enforced via `rcan-spec/fixtures/compliance-v1.json` (bundled at `tests/fixtures/`).
- `IncidentSeverity` tightened to `"life_health" | "other"` (EU AI Act Art. 72 serious-incident categories per rcan-py `VALID_SEVERITIES`).
- §22 `FriaDocument`, `FriaSigningKey`, `FriaConformance` types unchanged.

### Removed

- Defunct type unions `IncidentStatus` and `EuComplianceStatus` — no rcan-py counterpart and no known consumers.

### Cross-language parity

Byte-identical builder output to rcan-py 3.1.1 for all 8 fixture cases (3 minimal, 3 populated, 1 unicode, 1 unknown-severity-ignoring) per `tests/fixtures/compliance-v1.json`.

---

```

- [ ] **Step 3: Rebuild so dist picks up the new version**

```bash
cd /home/craigm26/rcan-ts
npm run build 2>&1 | tail -5
```
Expected: clean build. The VERSION constant in `src/version.ts` or dist-embedded metadata picks up 3.2.0 on next build (if the package has a runtime VERSION export — verify below).

- [ ] **Step 4: Commit**

```bash
cd /home/craigm26/rcan-ts
git add package.json CHANGELOG.md
git commit -m "release: v3.2.0 — §23-26 compliance builders + constants

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Dry-run, push, tag, publish

**Files:** no file edits.

- [ ] **Step 1: npm publish dry-run**

```bash
cd /home/craigm26/rcan-ts
npm publish --dry-run 2>&1 | tail -30
```
Expected: prints tarball contents and target version `3.2.0`. No errors.

- [ ] **Step 2: Push main**

```bash
cd /home/craigm26/rcan-ts
git push origin main
```

- [ ] **Step 3: Tag + push tag (triggers release.yml)**

```bash
cd /home/craigm26/rcan-ts
git tag v3.2.0
git push origin v3.2.0
```

- [ ] **Step 4: Watch the release workflow**

```bash
gh run list --workflow release.yml -R continuonai/rcan-ts --limit 3
```
Identify the run id triggered by the tag push (status `queued` or `in_progress`), then:
```bash
gh run watch <run-id> -R continuonai/rcan-ts --exit-status
```
Expected: green. OIDC Trusted Publisher path same as 3.1.1.

If workflow fails transiently (npm flaky), rerun ONCE: `gh run rerun <run-id> -R continuonai/rcan-ts`. If it fails twice, report BLOCKED.

---

### Task 14: Verify live on npm + smoke test

**Files:** no file edits.

- [ ] **Step 1: npm view**

```bash
npm view rcan-ts version
```
Expected: `3.2.0`.

- [ ] **Step 2: Fresh-install smoke test**

```bash
rm -rf /tmp/rcan-ts-smoke
mkdir /tmp/rcan-ts-smoke
cd /tmp/rcan-ts-smoke
npm init -y >/dev/null 2>&1
npm install rcan-ts@3.2.0 2>&1 | tail -3
node --input-type=module -e "
import { buildSafetyBenchmark, canonicalJson, VALID_SEVERITIES } from 'rcan-ts';
const out = buildSafetyBenchmark({
  iterations: 10, thresholds: {}, results: {}, mode: 'quick',
  generated_at: '2026-04-23T00:00:00Z', overall_pass: true,
});
console.log('schema:', out.schema);
console.log('bytes:', canonicalJson(out).length);
console.log('VALID_SEVERITIES:', VALID_SEVERITIES);
"
```
Expected output (approximately):
- `schema: rcan-safety-benchmark-v1`
- `bytes: 142` (or similar non-zero number)
- `VALID_SEVERITIES: [ 'life_health', 'other' ]`

- [ ] **Step 3: Clean up**

```bash
rm -rf /tmp/rcan-ts-smoke
```

- [ ] **Step 4: Declare Release D1 shipped**

If Steps 1-3 pass, D1 is complete. Update the auto-memory at `/home/craigm26/.claude/projects/-home-craigm26/memory/project_robot_md_v080_state.md` to reflect rcan-ts 3.2.0 on npm + the compliance-v1 fixture on rcan-spec master (quick edit, one-line addition to "Live on registries" section).

---

## Completion criteria

Release D1 is DONE when **all of the following hold**:

1. `rcan-spec/fixtures/compliance-v1.json` committed on master, all 8 cases round-trip per the sanity gate.
2. `rcan-ts` on npm at `3.2.0` with 4 builders + 10 constants + 8 type names exported (including `PostMarketIncidentReport` renamed from `PostMarketIncident`; defunct `IncidentStatus` / `EuComplianceStatus` removed).
3. `npm test` passes: fixture test 9 green (1 metadata + 8 cases), behavioral test 15+ green, full suite (~651 tests) green.
4. `grep 'import("crypto")' dist/*.mjs` returns empty — Release B crypto indirection preserved.
5. Fresh-install smoke test prints expected schema, non-zero byte count, correct `VALID_SEVERITIES`.

## Known follow-ups (non-blocking, explicitly deferred)

- **D2** — RRF compliance intake endpoints (separate brainstorm; Bob is first planned producer).
- **rcan-ts CLAUDE.md refresh** — describes v0.8.0 / spec 1.9.0 / 447 tests; reality after D1 is 3.2.0 / spec 3.0 / ~651 tests. Dedicated future cleanup.
- **rcan-py top-level re-exports** of `SAFETY_BENCHMARK_SCHEMA` / `IFU_SCHEMA` / etc. (Release B known follow-up #3).
- **Fixture drift check** in rcan-ts (optional `tests/check-fixture-drift.test.ts` comparing bundled sha256 to canonical) — low priority.

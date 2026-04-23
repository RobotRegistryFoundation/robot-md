# Release C: opencastor RCAN 3.0 alignment + ecosystem drift sweep — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make RCAN 3.0 the hard minimum across opencastor + robot-md-mcp, and sync opencastor-ops `repos.json` to clear monitor drift.

**Architecture:** Two coordinated package releases (opencastor `2026.4.23.0` + robot-md-mcp `0.2.2`) plus one direct-commit sync to opencastor-ops. No new subsystems, no new APIs adopted — this is alignment, not feature work. The opencastor change has a real behavioral diff (federation peers sending `rcan_version: "2.x"` now rejected at `is_accepted_version()`); the robot-md-mcp change is a schema drift correction that picks up already-upstream-correct canonical JSON; the opencastor-ops change is pure config.

**Tech Stack:** Python 3.10+ (opencastor, pytest), TypeScript/Node 18+ (robot-md-mcp, vitest, Ajv), JSON config (opencastor-ops).

**Working directories (all single-branch, direct-commit by solo maintainer craigm26 — no PR flow, no worktrees):**
- opencastor: `/home/craigm26/OpenCastor` on `main` (publishes to PyPI as `opencastor`; release workflow `release.yml` triggers on tag push)
- robot-md-mcp: `/home/craigm26/robot-md-mcp` on `main` (publishes to npm as `robot-md-mcp`; release workflow `release.yml` triggers on tag push)
- opencastor-ops: `/home/craigm26/opencastor-ops` on `master` (no tag; direct commit triggers monitor on next scheduled run, or via `workflow_dispatch`)

**Spec:** `/home/craigm26/robot-md/docs/superpowers/specs/2026-04-23-release-c-opencastor-rcan-3.0-alignment-design.md` (approved 2026-04-23, HEAD at `42f0909`).

**Out of scope (reject drift during execution):**
- Rewriting `castor/conformance.py` / `castor/doctor.py` / `castor/watermark.py` spec citations like "RCAN v2.2 §7.2 — ML-DSA-65 signing key MUST exist" — these cite historical spec sections where a rule was introduced; rewriting is factually misleading.
- Adopting new rcan 3.1 APIs (`canonical_json`, `sign_body`, `build_*`) in opencastor — its rcan surface is narrow (`SPEC_VERSION`, `SDK_VERSION`, subprocess `rcan_bridge`) and doesn't need them.
- opencastor-docs / opencastor-client / opencastor-autoresearch doc refreshes.
- LiveCaptionsXR (no RCAN touchpoints).
- `rcan/signing.py` doctrine cleanup (Release B deferred item).
- Any runtime override / deprecation flag.

---

## Release sequencing

**Wave A — opencastor `2026.4.23.0`** (Tasks 1–11)
**Wave B — robot-md-mcp `0.2.2`** (Tasks 12–17) — independent of Wave A, can run in parallel
**Wave C — opencastor-ops sync** (Tasks 18–19) — MUST land AFTER both A + B registries confirm new versions
**Wave D — cross-repo acceptance** (Task 20)

---

## Wave A — opencastor `2026.4.23.0`

### Task 1: Pre-flight — opencastor working tree hygiene

**Files:**
- Read: `/home/craigm26/OpenCastor/pyproject.toml`
- Read: `/home/craigm26/OpenCastor/castor/compliance.py:1-50`
- Read: `/home/craigm26/OpenCastor/castor/loa.py:40-50`

- [ ] **Step 1: Confirm working tree is clean and on main**

Run:
```bash
cd /home/craigm26/OpenCastor
git status
git branch --show-current
git pull --ff-only origin main
```
Expected: clean tree, on `main`, fast-forward (or "Already up to date").

- [ ] **Step 2: Record current state for before/after comparison**

Run:
```bash
grep -n "rcan>=" pyproject.toml
grep -nE "ACCEPTED_RCAN_VERSIONS|is_accepted_version" castor/compliance.py
grep -n "loa_required" castor/loa.py
```
Expected:
- `pyproject.toml:69:    "rcan>=1.2.1",` and `pyproject.toml:98:    "rcan>=1.2.1",`
- `castor/compliance.py:20:ACCEPTED_RCAN_VERSIONS: tuple[str, ...] = (` (with 2.x entries following)
- `castor/loa.py:47:        "loa_required": config.get("rcan_version", "0") >= "1.6",`

No commit.

---

### Task 2: Write failing test for tightened version gate

**Files:**
- Create: `/home/craigm26/OpenCastor/tests/test_compliance_version_gate.py`

- [ ] **Step 1: Create the test file**

Write `/home/craigm26/OpenCastor/tests/test_compliance_version_gate.py`:

```python
"""Regression tests for the RCAN 3.0 hard-cut version gate.

Release C (2026.4.23.0) hard-cuts 2.x acceptance. These tests lock the
invariant that is_accepted_version() rejects 2.x and does not give a free
pass to future majors.
"""

from __future__ import annotations

from castor.compliance import ACCEPTED_RCAN_VERSIONS, is_accepted_version


def test_accepted_versions_is_3_0_only():
    assert ACCEPTED_RCAN_VERSIONS == ("3.0",)


def test_accepts_3_0():
    assert is_accepted_version("3.0") is True


def test_accepts_3_x_forward_compat():
    assert is_accepted_version("3.1") is True
    assert is_accepted_version("3.2.1") is True


def test_rejects_2_x_hard_cut():
    for v in ("2.1", "2.1.0", "2.2", "2.2.0", "2.2.1"):
        assert is_accepted_version(v) is False, f"{v!r} should be rejected"


def test_rejects_1_x():
    for v in ("1.6", "1.9.0"):
        assert is_accepted_version(v) is False, f"{v!r} should be rejected"


def test_rejects_future_major_no_free_pass():
    """4.x and above are NOT forward-compatible — explicit bump required."""
    assert is_accepted_version("4.0") is False
    assert is_accepted_version("10.0") is False


def test_rejects_malformed():
    assert is_accepted_version("") is False
    assert is_accepted_version("not-a-version") is False
    assert is_accepted_version("3") is False  # no minor
```

- [ ] **Step 2: Run the new test suite and confirm it fails**

Run:
```bash
cd /home/craigm26/OpenCastor
pytest tests/test_compliance_version_gate.py -v
```
Expected: Multiple FAILs — `test_accepted_versions_is_3_0_only` fails (current tuple has 2.x), `test_rejects_2_x_hard_cut` fails (current code accepts them), `test_rejects_future_major_no_free_pass` fails (current code returns True for major > 3).

- [ ] **Step 3: Commit the failing test**

```bash
cd /home/craigm26/OpenCastor
git add tests/test_compliance_version_gate.py
git commit -m "test(compliance): lock RCAN 3.0 hard-cut version gate invariants

Release C tests for is_accepted_version(): accepts 3.x only, rejects
all 2.x, rejects future majors (no free pass), rejects malformed.

Expected to fail until castor/compliance.py is updated in the next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Implement tightened version gate in compliance.py

**Files:**
- Modify: `/home/craigm26/OpenCastor/castor/compliance.py:1-43`

- [ ] **Step 1: Update the module docstring header**

Edit `/home/craigm26/OpenCastor/castor/compliance.py` lines 1-5. Replace:
```python
"""castor.compliance — RCAN v2.1 compliance constants, ComplianceReport, and report generation.

SPEC_VERSION: the RCAN spec version this OpenCastor build targets.
ACCEPTED_RCAN_VERSIONS: versions accepted in inbound messages (no v1.x compat).
"""
```

With:
```python
"""castor.compliance — RCAN 3.0 compliance constants, ComplianceReport, and report generation.

SPEC_VERSION: the RCAN spec version this OpenCastor build targets.
ACCEPTED_RCAN_VERSIONS: versions accepted in inbound messages (hard-cut: 3.x only — 2.x no longer accepted per ecosystem policy).
"""
```

- [ ] **Step 2: Tighten ACCEPTED_RCAN_VERSIONS**

Edit `/home/craigm26/OpenCastor/castor/compliance.py` lines 20-27. Replace:
```python
ACCEPTED_RCAN_VERSIONS: tuple[str, ...] = (
    "2.1",
    "2.1.0",
    "2.2",
    "2.2.0",
    "2.2.1",
    "3.0",
)
```

With:
```python
ACCEPTED_RCAN_VERSIONS: tuple[str, ...] = ("3.0",)
```

- [ ] **Step 3: Tighten is_accepted_version forward-compat**

Edit `/home/craigm26/OpenCastor/castor/compliance.py` lines 30-43. Replace:
```python
def is_accepted_version(version: str) -> bool:
    """Return True if *version* satisfies the minimum supported spec (≥ 2.1).

    Accepts any version in ACCEPTED_RCAN_VERSIONS, and also any future version
    whose major component is ≥ 3 (forward-compatible with RCAN 3.x).
    """
    if version in ACCEPTED_RCAN_VERSIONS:
        return True
    try:
        parts = [int(x) for x in str(version).split(".")[:2]]
        major = parts[0]
        return major > 3
    except Exception:
        return False
```

With:
```python
def is_accepted_version(version: str) -> bool:
    """Return True if *version* is RCAN 3.x (hard-cut — 2.x rejected).

    Accepts any version whose major component is exactly 3 (forward-compatible
    within RCAN 3.x). Future majors (4.x+) require an explicit opencastor bump
    and are NOT granted a free pass here.
    """
    try:
        parts = str(version).split(".")
        if len(parts) < 2:
            return False
        major = int(parts[0])
        int(parts[1])  # ensure minor is numeric
        return major == 3
    except (ValueError, AttributeError):
        return False
```

- [ ] **Step 4: Run the version-gate tests and confirm they pass**

Run:
```bash
cd /home/craigm26/OpenCastor
pytest tests/test_compliance_version_gate.py -v
```
Expected: All 8 tests PASS.

- [ ] **Step 5: Run full pytest to confirm no regression elsewhere**

Run:
```bash
cd /home/craigm26/OpenCastor
pytest tests/ -x --ignore=tests/integration 2>&1 | tail -40
```
Expected: Full suite passes. If any test fails asserting 2.x acceptance, open the failing test, update the mocked `rcan_version` to `"3.0"`, re-run, confirm pass. Include those mock fixes in this commit.

- [ ] **Step 6: Commit**

```bash
cd /home/craigm26/OpenCastor
git add castor/compliance.py
# plus any test files updated for mock fixes
git commit -m "feat(compliance)!: hard-cut RCAN 2.x at ingress (accept 3.x only)

BREAKING: ACCEPTED_RCAN_VERSIONS drops 2.1, 2.1.0, 2.2, 2.2.0, 2.2.1 —
only '3.0' listed. is_accepted_version() forward-compat tightened from
'major > 3' (accidentally accepted 4.x) to 'major == 3'.

Per feedback_rcan_3_plus_policy: 2.x frozen out across the ecosystem.
Federation peers sending rcan_version: '2.x' now rejected.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Fix castor/loa.py lexical string compare

**Files:**
- Modify: `/home/craigm26/OpenCastor/castor/loa.py:41-48`

- [ ] **Step 1: Replace the lexical compare with unconditional True**

Edit `/home/craigm26/OpenCastor/castor/loa.py` lines 41-48. Replace:
```python
def get_loa_status(config: dict[str, Any]) -> dict[str, Any]:
    """Return a status dict describing the current LoA enforcement state."""
    return {
        "loa_enforcement": bool(config.get("loa_enforcement", False)),
        "min_loa_for_control": int(config.get("min_loa_for_control", 1)),
        "rcan_version": config.get("rcan_version", "unknown"),
        "loa_required": config.get("rcan_version", "0") >= "1.6",
    }
```

With:
```python
def get_loa_status(config: dict[str, Any]) -> dict[str, Any]:
    """Return a status dict describing the current LoA enforcement state."""
    # RCAN 3.0+ mandates LoA unconditionally. The previous lexical compare
    # (rcan_version >= "1.6") was an artifact of the v1.6 era where LoA was
    # first introduced as optional — under the 3.0 hard-cut policy, LoA is
    # always required (is_accepted_version() already rejects 2.x).
    return {
        "loa_enforcement": bool(config.get("loa_enforcement", False)),
        "min_loa_for_control": int(config.get("min_loa_for_control", 1)),
        "rcan_version": config.get("rcan_version", "unknown"),
        "loa_required": True,
    }
```

- [ ] **Step 2: Run LoA tests**

Run:
```bash
cd /home/craigm26/OpenCastor
pytest tests/ -v -k "loa" 2>&1 | tail -40
```
Expected: All LoA tests pass. If any test asserted `loa_required` could be False (e.g., for a 2.x mocked config), update to assert True and include in commit.

- [ ] **Step 3: Commit**

```bash
cd /home/craigm26/OpenCastor
git add castor/loa.py
# plus any test files updated
git commit -m "fix(loa): mandate LoA unconditionally under RCAN 3.0

Drop the lexical rcan_version >= '1.6' compare — it was accidentally
correct for '3.0' (lexical 3 > 1) but would break for any '10.x'. Under
the 3.0 hard-cut (compliance.ACCEPTED_RCAN_VERSIONS = ('3.0',)), LoA is
unconditionally required.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Bump rcan dep floor in pyproject.toml

**Files:**
- Modify: `/home/craigm26/OpenCastor/pyproject.toml:69` and `:98`

- [ ] **Step 1: Replace both occurrences**

Run:
```bash
cd /home/craigm26/OpenCastor
sed -i 's/"rcan>=1\.2\.1"/"rcan>=3.1.1,<4.0"/g' pyproject.toml
grep -n "rcan" pyproject.toml
```
Expected: two lines `    "rcan>=3.1.1,<4.0",` at lines 69 and 98. No more `1.2.1` references.

- [ ] **Step 2: Verify dep resolves in a fresh venv**

Run:
```bash
cd /home/craigm26/OpenCastor
python3 -m venv /tmp/oc-resolve-check && source /tmp/oc-resolve-check/bin/activate && pip install -e . 2>&1 | tail -20 && python -c "import rcan; print('rcan:', rcan.SPEC_VERSION); import castor; print('castor OK')" && deactivate && rm -rf /tmp/oc-resolve-check
```
Expected: installs cleanly, prints `rcan: 3.0` and `castor OK`. If pip resolves to rcan < 3.1.1, fail — investigate (likely `pip cache purge` needed).

- [ ] **Step 3: Commit**

```bash
cd /home/craigm26/OpenCastor
git add pyproject.toml
git commit -m "deps: bump rcan floor to >=3.1.1,<4.0

Was pinned to >=1.2.1 (pre-RCAN-3.0 era). Opencastor's actual rcan API
surface is narrow (SPEC_VERSION, SDK_VERSION, subprocess rcan_bridge) —
all satisfied by the current 3.1.1 release. Upper bound <4.0 matches the
hard-cut on ACCEPTED_RCAN_VERSIONS.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Rewrite README "RCAN v1.6 Features" section

**Files:**
- Modify: `/home/craigm26/OpenCastor/README.md` — the `## RCAN v1.6 Features` section and the `rcan_version: "1.6"` example block.

- [ ] **Step 1: Locate the stale section**

Run:
```bash
cd /home/craigm26/OpenCastor
grep -nE "RCAN v1\.6|rcan_version: \"1\.6\"|rcan_version: '1\.6'" README.md
```
Record the line numbers. Expect a `## RCAN v1.6 Features` heading + a YAML example block with `rcan_version: "1.6"`.

- [ ] **Step 2: Read surrounding context to preserve formatting**

Open README.md and read ~20 lines around each match found in Step 1. Preserve any sub-bullet structure.

- [ ] **Step 3: Rewrite the heading and feature list**

Edit `README.md`:
- Change `## RCAN v1.6 Features` → `## RCAN 3.0 Features`
- Under that heading, replace the bullet list body with:
  ```markdown
  - **Replay prevention** — hybrid signatures (ML-DSA-65 + Ed25519) over canonical JSON bodies
  - **Level of Assurance (LoA)** — mandatory under 3.0+; gates control-plane operations behind HiTL authorization
  - **Canonical JSON wire format** — `rcan.canonical_json(body)` produces byte-identical serialization across Python and TypeScript SDKs
  - **§22-26 compliance artifacts** — emit §23 safety benchmarks, §24 IFU, §25 post-market incident reports, §26 EU register entries via `rcan.build_*` builders
  - **Federation + constrained transport** — BLE / LoRa / MQTT carriers; RRN-based identity resolution via rcan.dev
  - **Post-quantum ready** — NIST FIPS 204 ML-DSA-65 is the primary signing scheme (Q-Day 2029 is NOW)
  ```

Preserve any pre-existing formatting (blank lines, horizontal rules) immediately around the section.

- [ ] **Step 4: Update example YAML block**

In the same file, replace any `rcan_version: "1.6"` or `rcan_version: '1.6'` with `rcan_version: "3.0"`.

- [ ] **Step 5: Verify the sweep**

Run:
```bash
cd /home/craigm26/OpenCastor
grep -nE "RCAN v1\.6|rcan_version: \"1\.6\"|rcan_version: '1\.6'" README.md
```
Expected: no matches.

- [ ] **Step 6: Commit**

```bash
cd /home/craigm26/OpenCastor
git add README.md
git commit -m "docs(readme): rewrite 'RCAN v1.6 Features' as 'RCAN 3.0 Features'

Section + example YAML were stale. Feature list now reflects the 3.0
surface: hybrid signing, mandatory LoA, canonical JSON wire format,
§22-26 compliance builders, ML-DSA-65 post-quantum primary.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Sweep stale SDK version references in CLAUDE.md

**Files:**
- Modify: `/home/craigm26/OpenCastor/CLAUDE.md` — two stale "v2.0.0+" SDK references.

- [ ] **Step 1: Locate the stale references**

Run:
```bash
cd /home/craigm26/OpenCastor
grep -n "v2\.0\.0+" CLAUDE.md
```
Expected: two lines, one for `rcan-py SDK (Python, v2.0.0+)` and one for `rcan-ts SDK (TypeScript, v2.0.0+)`.

- [ ] **Step 2: Update both lines**

Edit `CLAUDE.md`. Replace:
- `rcan-py SDK (Python, v2.0.0+)` → `rcan-py SDK (Python, v3.0+)`
- `rcan-ts SDK (TypeScript, v2.0.0+)` → `rcan-ts SDK (TypeScript, v3.0+)`

- [ ] **Step 3: Verify sweep**

Run:
```bash
grep -nE "v2\.0\.0\+|rcan-py SDK.*v2|rcan-ts SDK.*v2" CLAUDE.md
```
Expected: no matches.

- [ ] **Step 4: Commit**

```bash
cd /home/craigm26/OpenCastor
git add CLAUDE.md
git commit -m "docs(claude-md): bump rcan-py/rcan-ts SDK refs to v3.0+

Both were marked 'v2.0.0+' — stale. RCAN 3.0+ is the ecosystem baseline
per feedback_rcan_3_plus_policy.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Spot-check cloud/bridge.py rcan_bridge launcher

**Files:**
- Read-only: `/home/craigm26/OpenCastor/castor/cloud/bridge.py`

This is a verification task — no code change expected unless the subprocess launcher explicitly passes a `rcan_version` argument that conflicts with the hard-cut. The memory says "RCN_IDS/RMN/RHN_IDS end-to-end works in production unchanged" for RRF; opencastor's bridge should likewise still start.

- [ ] **Step 1: Read the rcan_bridge launch path**

Run:
```bash
cd /home/craigm26/OpenCastor
grep -nE "rcan_bridge|rcan_version" castor/cloud/bridge.py
```
Record each match.

- [ ] **Step 2: Read the full surrounding block for each match**

Open `castor/cloud/bridge.py` in a reader and read ±15 lines around each matched line. Confirm:
- The bridge launches `rcan_bridge` as a subprocess (CLI binary from rcan-py package)
- If any hardcoded `rcan_version` string is passed as an argument, it is `"3.0"` (not `"1.6"` or `"2.2"`)

- [ ] **Step 3: If a stale version arg exists, fix it**

If (and only if) step 2 surfaces a hardcoded `"1.6"` / `"2.x"` arg, replace with `"3.0"` and commit:
```bash
git add castor/cloud/bridge.py
git commit -m "fix(cloud/bridge): hardcode rcan_version arg to '3.0'

Was '<stale value>' — out of sync with the 3.0 hard-cut in compliance.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Otherwise, no commit; record "bridge launcher clean" in your task log and proceed.

---

### Task 9: Full pytest sweep

**Files:**
- Run-only.

- [ ] **Step 1: Run full test suite**

Run:
```bash
cd /home/craigm26/OpenCastor
pytest tests/ 2>&1 | tail -80
```
Expected: full suite passes (opencastor has 7804+ tests per CLAUDE.md). If any test fails with a 2.x-version assertion, update the mock to `"3.0"` and re-run.

- [ ] **Step 2: If fixes needed, commit them**

```bash
cd /home/craigm26/OpenCastor
git add tests/
git commit -m "test: update 2.x rcan_version mocks to '3.0' post hard-cut

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

If no fixes needed, no commit.

---

### Task 10: Add CHANGELOG entry for 2026.4.23.0

**Files:**
- Modify: `/home/craigm26/OpenCastor/CHANGELOG.md` — insert new entry at top of versioned entries.

- [ ] **Step 1: Open CHANGELOG.md and locate the insertion point**

The file starts with `# Changelog` header, then format notes, then a `---` separator, then `## [2026.4.17.0] - 2026-04-17`. New entries go **above** the previous version heading, below the `---`.

- [ ] **Step 2: Insert the new entry**

Insert this block immediately after the `---` separator and before `## [2026.4.17.0] - 2026-04-17`:

```markdown
## [2026.4.23.0] - 2026-04-23

### BREAKING — RCAN 3.0 hard-cut at ingress
- `castor.compliance.ACCEPTED_RCAN_VERSIONS` reduced to `("3.0",)` — 2.1,
  2.1.0, 2.2, 2.2.0, 2.2.1 removed. Federation peers sending
  `rcan_version: "2.x"` in messages are now rejected at ingress. This
  matches the ecosystem-wide RCAN 3.0+ policy (see
  feedback_rcan_3_plus_policy memo).
- `castor.compliance.is_accepted_version()` forward-compat tightened from
  `major > 3` (accidentally accepted 4.x+) to `major == 3`. Future major
  bumps require an explicit opencastor release.
- Robots still running with `rcan_version: "2.x"` in their config YAML
  will now fail startup validation. Fix: edit the config to
  `rcan_version: "3.0"` (the `castor wizard` command already writes "3.0"
  by default).

### Changed
- `pyproject.toml` dep floor `rcan>=1.2.1` → `rcan>=3.1.1,<4.0` (both
  occurrences). Upper bound matches the 3.x hard-cut.
- `castor/loa.py::get_loa_status` — replaced lexical
  `config.get("rcan_version", "0") >= "1.6"` with unconditional `True`.
  Under the 3.0 hard-cut LoA is always required; the `>= "1.6"` compare
  was an artifact of the v1.6 era when LoA was first introduced.
- `castor/compliance.py` module docstring: "RCAN v2.1 compliance
  constants" → "RCAN 3.0 compliance constants".
- `README.md` "RCAN v1.6 Features" section rewritten as "RCAN 3.0
  Features" covering hybrid signing, mandatory LoA, canonical JSON,
  §22-26 builders, ML-DSA-65.
- `CLAUDE.md` SDK references bumped: `rcan-py v2.0.0+` → `v3.0+`,
  `rcan-ts v2.0.0+` → `v3.0+`.

### Added
- `tests/test_compliance_version_gate.py` — 8 regression tests locking
  the 3.0 hard-cut invariant.
```

- [ ] **Step 3: Verify the CHANGELOG parses as Markdown**

Run:
```bash
cd /home/craigm26/OpenCastor
head -60 CHANGELOG.md
```
Expected: new entry sits cleanly above the 2026.4.17.0 entry, correct heading level, no mangled bullet indentation.

- [ ] **Step 4: Commit**

```bash
cd /home/craigm26/OpenCastor
git add CHANGELOG.md
git commit -m "docs(changelog): [2026.4.23.0] Release C — RCAN 3.0 hard-cut

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Build, twine check, tag, publish

**Files:**
- Read-only (build artifacts discarded).

- [ ] **Step 1: Clean old build artifacts**

Run:
```bash
cd /home/craigm26/OpenCastor
rm -rf dist/ build/ *.egg-info
```

- [ ] **Step 2: Build the sdist + wheel**

Run:
```bash
cd /home/craigm26/OpenCastor
python -m build 2>&1 | tail -20
```
Expected: creates `dist/opencastor-2026.4.23.0.tar.gz` and `dist/opencastor-2026.4.23.0-py3-none-any.whl`.

- [ ] **Step 3: Twine validate**

Run:
```bash
cd /home/craigm26/OpenCastor
twine check dist/*
```
Expected: `PASSED` for both artifacts.

- [ ] **Step 4: Push commits**

Run:
```bash
cd /home/craigm26/OpenCastor
git push origin main
```
Expected: push succeeds.

- [ ] **Step 5: Tag the release**

Run:
```bash
cd /home/craigm26/OpenCastor
git tag v2026.4.23.0
git push origin v2026.4.23.0
```
Expected: tag push triggers `release.yml` workflow (PyPI publish).

- [ ] **Step 6: Watch the release workflow**

Run:
```bash
gh run list --workflow release.yml -R craigm26/OpenCastor --limit 3
```
Get the run id of the triggered run. Then:
```bash
gh run watch <run-id> -R craigm26/OpenCastor
```
Expected: workflow completes successfully. If it fails, read the failure log before assuming rollback — most failures are transient (PyPI upload flaky) and the workflow can be rerun via `gh run rerun <run-id>`.

---

### Task 12: Verify opencastor 2026.4.23.0 is live on PyPI

**Files:**
- Run-only.

- [ ] **Step 1: Fresh-venv install test (authoritative)**

Run:
```bash
python3 -m venv /tmp/oc-release-check
source /tmp/oc-release-check/bin/activate
pip install --no-cache-dir 'opencastor==2026.4.23.0' 2>&1 | tail -5
python -c "import castor; from castor.compliance import ACCEPTED_RCAN_VERSIONS; print('installed:', ACCEPTED_RCAN_VERSIONS)"
deactivate
rm -rf /tmp/oc-release-check
```
Expected: pip install succeeds, prints `installed: ('3.0',)`.

- [ ] **Step 2: PyPI JSON API check (may lag the fresh-install result by minutes)**

Run:
```bash
curl -s https://pypi.org/pypi/opencastor/json | python3 -c "import sys, json; d=json.load(sys.stdin); print('pypi latest:', d['info']['version']); print('2026.4.23.0 in releases:', '2026.4.23.0' in d['releases'])"
```
Expected eventually: `pypi latest: 2026.4.23.0`. Cache lag is normal — if the latest still shows 2026.4.17.0 but step 1 succeeded, step 1 is authoritative.

---

## Wave B — robot-md-mcp `0.2.2`

Independent of Wave A. Can run in parallel.

### Task 13: Pre-flight — robot-md-mcp working tree

**Files:**
- Read-only.

- [ ] **Step 1: Confirm working tree clean and on main**

Run:
```bash
cd /home/craigm26/robot-md-mcp
git status
git branch --show-current
git pull --ff-only origin main
```
Expected: clean, on `main`, fast-forward.

- [ ] **Step 2: Record current schema state**

Run:
```bash
cd /home/craigm26/robot-md-mcp
grep -A2 '"rcan_version"' src/schema/robot.schema.json
```
Expected: current bundled copy still has the "2.1+; 3.0+ recommended" description (stale).

- [ ] **Step 3: Confirm canonical upstream is already 3.0+ tightened**

Run:
```bash
grep -A2 '"rcan_version"' /home/craigm26/robot-md/schema/v1/robot.schema.json
```
Expected:
```json
"rcan_version": {
  "type": "string",
  "pattern": "^3\\.[0-9]+(\\.[0-9]+)?$",
```

---

### Task 14: Sync schema from canonical upstream

**Files:**
- Modify: `/home/craigm26/robot-md-mcp/src/schema/robot.schema.json`

- [ ] **Step 1: Run sync-schema to write from canonical**

Run:
```bash
cd /home/craigm26/robot-md-mcp
npm run sync-schema 2>&1 | tail -10
```
Expected: writes bundled copy from `/home/craigm26/robot-md/schema/v1/robot.schema.json`.

- [ ] **Step 2: Verify drift check now passes**

Run:
```bash
npm run sync-schema -- --check
echo "exit: $?"
```
Expected: exit 0 (no drift).

- [ ] **Step 3: Verify the rcan_version pattern is live in bundled copy**

Run:
```bash
grep -A2 '"rcan_version"' src/schema/robot.schema.json
```
Expected:
```json
"rcan_version": {
  "type": "string",
  "pattern": "^3\\.[0-9]+(\\.[0-9]+)?$",
```

- [ ] **Step 4: Do NOT commit yet — Task 15 adds tests that also go in this commit**

---

### Task 15: Add failing schema validation tests

**Files:**
- Read-only scan first: `/home/craigm26/robot-md-mcp/tests/` to find naming convention and existing fixture.
- Create or extend: `/home/craigm26/robot-md-mcp/tests/schema-rcan-version.test.ts` (new file — keeps test isolated).

- [ ] **Step 1: Scan existing test layout**

Run:
```bash
cd /home/craigm26/robot-md-mcp
ls tests/
head -30 tests/*.test.ts 2>/dev/null | head -80
```
Expected: at least one `.test.ts` file with a vitest pattern. Record the import style used (e.g. `import { describe, it, expect } from "vitest"`).

- [ ] **Step 2: Create new test file**

Write `/home/craigm26/robot-md-mcp/tests/schema-rcan-version.test.ts`:

```typescript
/**
 * Regression tests for Release C schema tightening: rcan_version
 * must match pattern ^3\.[0-9]+(\.[0-9]+)?$ (RCAN 3.0+ only).
 */

import { describe, it, expect } from "vitest";
import Ajv from "ajv";
import addFormats from "ajv-formats";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const schemaPath = resolve(here, "..", "src", "schema", "robot.schema.json");
const schema = JSON.parse(readFileSync(schemaPath, "utf8"));

const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);
const validate = ajv.compile(schema);

/**
 * Minimal fixture that satisfies the rest of the schema — filled with plausible
 * values for required fields. Individual tests override only rcan_version.
 */
function makeFixture(rcanVersion: string): Record<string, unknown> {
  return {
    rcan_version: rcanVersion,
    metadata: { robot_name: "test-bot" },
    physics: { type: "arm", dof: 6 },
    drivers: [{ id: "test", protocol: "simulation" }],
    safety: { enforcement: "enabled" },
  };
}

describe("rcan_version schema gate (Release C)", () => {
  it("accepts 3.0", () => {
    const ok = validate(makeFixture("3.0"));
    if (!ok) console.error(validate.errors);
    expect(ok).toBe(true);
  });

  it("accepts 3.1", () => {
    expect(validate(makeFixture("3.1"))).toBe(true);
  });

  it("accepts 3.1.1", () => {
    expect(validate(makeFixture("3.1.1"))).toBe(true);
  });

  it("rejects 2.1", () => {
    const ok = validate(makeFixture("2.1"));
    expect(ok).toBe(false);
    const patternErr = validate.errors?.find(e => e.keyword === "pattern");
    expect(patternErr).toBeDefined();
  });

  it("rejects 2.2.1", () => {
    expect(validate(makeFixture("2.2.1"))).toBe(false);
  });

  it("rejects 1.6", () => {
    expect(validate(makeFixture("1.6"))).toBe(false);
  });

  it("rejects 4.0 (no free pass for future majors)", () => {
    expect(validate(makeFixture("4.0"))).toBe(false);
  });
});
```

**Note on the minimal fixture:** if the robot.schema.json requires additional fields beyond {rcan_version, metadata, physics, drivers, safety}, inspect `grep -A2 '"required"' src/schema/robot.schema.json | head -20` and extend `makeFixture` with the missing fields. The schema-specific validity of the fixture is the developer's responsibility; this test is specifically about the `rcan_version` pattern gate.

- [ ] **Step 3: Run the test suite**

Run:
```bash
cd /home/craigm26/robot-md-mcp
npm test 2>&1 | tail -40
```
Expected: all new tests PASS (schema was already synced in Task 14). If any legacy test asserted acceptance of a 2.x `rcan_version`, it now fails — update the fixture to `"3.0"` and include in this commit.

- [ ] **Step 4: If existing tests fail, fix them**

Search tests for 2.x literals:
```bash
grep -rnE "rcan_version.*['\"]2\.[0-9]" tests/ 2>&1 | head -20
```
If any hit, edit those fixtures to `"3.0"`, re-run `npm test`, confirm green.

- [ ] **Step 5: Commit the schema sync + new tests together**

```bash
cd /home/craigm26/robot-md-mcp
git add src/schema/robot.schema.json tests/schema-rcan-version.test.ts
# plus any legacy tests updated
git commit -m "feat(schema)!: sync rcan_version to 3.0+ pattern from canonical

BREAKING: ROBOT.md files declaring rcan_version: '2.x' now fail schema
validation. Fix: update to '3.0'.

The bundled schema at src/schema/robot.schema.json was drifting behind
the canonical upstream at robot-md/schema/v1/robot.schema.json, which
already enforces pattern ^3\.[0-9]+(\.[0-9]+)?\$. This commit runs
npm run sync-schema to catch up.

Adds tests/schema-rcan-version.test.ts with 7 regression cases locking
the gate: accepts 3.0/3.1/3.1.1, rejects 2.1/2.2.1/1.6/4.0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 16: Version bump + CHANGELOG

**Files:**
- Modify: `/home/craigm26/robot-md-mcp/package.json` — `"version": "0.2.1"` → `"0.2.2"`
- Modify: `/home/craigm26/robot-md-mcp/CHANGELOG.md` — new `[0.2.2]` entry at top.

- [ ] **Step 1: Bump package.json**

Edit `/home/craigm26/robot-md-mcp/package.json`:
- Change `"version": "0.2.1"` to `"version": "0.2.2"`.

Verify:
```bash
cd /home/craigm26/robot-md-mcp
grep '"version"' package.json | head -1
```
Expected: `"version": "0.2.2",`.

- [ ] **Step 2: Read current CHANGELOG header format**

Run:
```bash
head -20 CHANGELOG.md
```
Record the heading style used for prior entries.

- [ ] **Step 3: Insert new CHANGELOG entry**

Insert the following block below the top-of-file header / "Unreleased" section (match whatever pattern the file uses — if there's no "Unreleased" section, insert immediately above the most recent versioned entry):

```markdown
## [0.2.2] - 2026-04-23

### BREAKING — RCAN 3.0+ required
- Bundled `src/schema/robot.schema.json` resynced from canonical upstream
  (`robot-md/schema/v1/robot.schema.json`). `rcan_version` now enforced
  as pattern `^3\.[0-9]+(\.[0-9]+)?$` with description "RCAN protocol
  version. Must be 3.0 or higher (ecosystem policy: RCAN 3.0+ only
  going forward; 2.x no longer accepted)." ROBOT.md files declaring
  `rcan_version: "2.x"` will fail validation.

### Added
- `tests/schema-rcan-version.test.ts` — 7 regression tests locking the
  3.0+ acceptance gate.
```

- [ ] **Step 4: Rebuild to pick up new version in dist**

Run:
```bash
cd /home/craigm26/robot-md-mcp
npm run build 2>&1 | tail -10
```
Expected: tsup builds `dist/` with no errors.

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/robot-md-mcp
git add package.json CHANGELOG.md
git commit -m "release: v0.2.2 — RCAN 3.0+ hard-cut in bundled schema

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 17: Dry-run, push, tag, publish

**Files:**
- Run-only.

- [ ] **Step 1: npm publish dry-run**

Run:
```bash
cd /home/craigm26/robot-md-mcp
npm publish --dry-run 2>&1 | tail -25
```
Expected: prints the tarball contents and target version `0.2.2`. No errors.

- [ ] **Step 2: Push commits**

Run:
```bash
cd /home/craigm26/robot-md-mcp
git push origin main
```

- [ ] **Step 3: Tag + push tag to trigger release workflow**

Run:
```bash
cd /home/craigm26/robot-md-mcp
git tag v0.2.2
git push origin v0.2.2
```

- [ ] **Step 4: Watch release workflow**

Run:
```bash
gh run list --workflow release.yml -R RobotRegistryFoundation/robot-md-mcp --limit 3
```
Identify the run id, then:
```bash
gh run watch <run-id> -R RobotRegistryFoundation/robot-md-mcp
```
Expected: workflow completes successfully (npm publish).

- [ ] **Step 5: Verify live on npm**

Run:
```bash
npm view robot-md-mcp version
```
Expected: `0.2.2`.

Smoke test the binary:
```bash
cd /tmp && npx -y robot-md-mcp@0.2.2 --help 2>&1 | head -10
```
Expected: prints help/usage text without crashing.

---

## Wave C — opencastor-ops `repos.json` sync

Lands AFTER Waves A + B both confirm registry publishes.

### Task 18: Update repos.json expected_version fields

**Files:**
- Modify: `/home/craigm26/opencastor-ops/config/repos.json`

- [ ] **Step 1: Pre-flight**

Run:
```bash
cd /home/craigm26/opencastor-ops
git status
git branch --show-current
git pull --ff-only origin master
```
Expected: clean, on `master`, fast-forward.

- [ ] **Step 2: Read current expected_version fields**

Run:
```bash
cd /home/craigm26/opencastor-ops
python3 -c "import json; d=json.load(open('config/repos.json')); [print(f\"{r['id']}: {r.get('expected_version')}\") for r in d['repos']]"
```
Expected to print:
```
opencastor: 2026.4.17.0
rcan-spec: None
rcan-py: 2.0.0
rcan-ts: 2.0.0
robot-md: 1.0.1
robot-md-mcp: 0.2.1
...
```

- [ ] **Step 3: Update the four stale fields + the _updated date**

Edit `/home/craigm26/opencastor-ops/config/repos.json`:
- Top-level `"_updated": "2026-04-22"` → `"_updated": "2026-04-23"`
- `repos[].id == "opencastor"` → `"expected_version": "2026.4.23.0"` (was `"2026.4.17.0"`)
- `repos[].id == "rcan-py"` → `"expected_version": "3.1.1"` (was `"2.0.0"`)
- `repos[].id == "rcan-ts"` → `"expected_version": "3.1.1"` (was `"2.0.0"`)
- `repos[].id == "robot-md-mcp"` → `"expected_version": "0.2.2"` (was `"0.2.1"`)

- [ ] **Step 4: Verify JSON parses and values are correct**

Run:
```bash
cd /home/craigm26/opencastor-ops
python3 -c "import json; d=json.load(open('config/repos.json')); assert d['_updated'] == '2026-04-23'; rbi = {r['id']: r for r in d['repos']}; assert rbi['opencastor']['expected_version'] == '2026.4.23.0'; assert rbi['rcan-py']['expected_version'] == '3.1.1'; assert rbi['rcan-ts']['expected_version'] == '3.1.1'; assert rbi['robot-md-mcp']['expected_version'] == '0.2.2'; print('all 4 bumps + _updated verified')"
```
Expected: `all 4 bumps + _updated verified`.

- [ ] **Step 5: Commit + push**

```bash
cd /home/craigm26/opencastor-ops
git add config/repos.json
git commit -m "config: sync expected_version for Release C ecosystem state

- opencastor 2026.4.17.0 → 2026.4.23.0 (RCAN 3.0 hard-cut release)
- rcan-py 2.0.0 → 3.1.1 (shipped in Release B, sync catches up)
- rcan-ts 2.0.0 → 3.1.1 (shipped in Release B, sync catches up)
- robot-md-mcp 0.2.1 → 0.2.2 (Release C schema tightening)
- _updated 2026-04-22 → 2026-04-23

Silences monitor drift alerts that have been firing since Release B.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push origin master
```

---

### Task 19: Trigger monitor and verify zero drift

**Files:**
- Run-only.

- [ ] **Step 1: Trigger ecosystem monitor**

Run:
```bash
gh workflow run "Ecosystem Monitor" -R craigm26/opencastor-ops
```
Expected: returns success (queued).

- [ ] **Step 2: Wait for run to complete**

Run:
```bash
gh run list --workflow "Ecosystem Monitor" -R craigm26/opencastor-ops --limit 1
```
Re-run every ~30s until `status: completed`. When complete:
```bash
gh run list --workflow "Ecosystem Monitor" -R craigm26/opencastor-ops --limit 1
```
Expected: `completed ✔ success`.

- [ ] **Step 3: Inspect the run log for drift alerts**

Get the run id from step 2, then:
```bash
gh run view <run-id> --log -R craigm26/opencastor-ops | grep -iE "drift|stale|mismatch|alert" | head -30
```
Expected: zero matches, or matches only for non-version-drift categories (e.g. Dependabot alert #15 on RRF, which is a known separate follow-up).

If version-drift alerts appear, open the run log and reconcile the observed state against `config/repos.json` — typically means the PyPI/npm cache hasn't caught up yet. Wait 5min and rerun the monitor with `gh run rerun <run-id>`.

---

## Wave D — Cross-repo acceptance

### Task 20: Confirm ecosystem state from a clean shell

**Files:**
- Run-only.

- [ ] **Step 1: Query both registries for all 5 packages**

Run:
```bash
pip index versions rcan 2>&1 | head -3
pip index versions opencastor 2>&1 | head -3
pip index versions robot-md 2>&1 | head -3
npm view rcan-ts version
npm view robot-md-mcp version
```
Expected:
- `rcan` latest `3.1.1` (unchanged since Release B)
- `opencastor` latest `2026.4.23.0`
- `robot-md` latest `1.0.1` (unchanged since Release B)
- rcan-ts `3.1.1` (unchanged since Release B)
- robot-md-mcp `0.2.2`

- [ ] **Step 2: Cross-check against opencastor-ops expected_version**

Run:
```bash
cd /home/craigm26/opencastor-ops
python3 -c "
import json, subprocess
d = json.load(open('config/repos.json'))
for r in d['repos']:
    ev = r.get('expected_version')
    if not ev:
        continue
    pkg = {'opencastor': ('pypi', 'opencastor'), 'rcan-py': ('pypi', 'rcan'), 'rcan-ts': ('npm', 'rcan-ts'), 'robot-md': ('pypi', 'robot-md'), 'robot-md-mcp': ('npm', 'robot-md-mcp')}.get(r['id'])
    if not pkg:
        continue
    registry, name = pkg
    if registry == 'pypi':
        live = subprocess.run(['pip', 'index', 'versions', name], capture_output=True, text=True).stdout.split('\n')[0].split()[-1].strip('()')
    else:
        live = subprocess.run(['npm', 'view', name, 'version'], capture_output=True, text=True).stdout.strip()
    status = 'OK' if live == ev else f'DRIFT (expected {ev}, live {live})'
    print(f'{r[\"id\"]:20} {ev:15} {live:15} {status}')
"
```
Expected: every row prints `OK`.

- [ ] **Step 3: Declare Release C shipped**

If step 2 is all OK and Task 19's monitor is green, Release C is done.

Update the auto-memory at `/home/craigm26/.claude/projects/-home-craigm26/memory/project_robot_md_v080_state.md` noting Release C shipped: opencastor `2026.4.23.0` + robot-md-mcp `0.2.2` + opencastor-ops sync. (The update is per the memory system rules — only note what's surprising or non-obvious; the commit SHAs and tag names are the durable record.)

---

## Completion criteria

Release C is DONE when **all of the following hold**:

1. `pip install opencastor==2026.4.23.0 --no-cache-dir` succeeds in a fresh venv and prints `ACCEPTED_RCAN_VERSIONS == ('3.0',)`.
2. `npm view robot-md-mcp version` returns `0.2.2`.
3. `opencastor-ops/config/repos.json` has `_updated: "2026-04-23"` + all four expected_version fields bumped.
4. Ecosystem monitor run post-sync reports zero version drift.
5. Cross-repo verification (Task 20 Step 2) prints all `OK` rows.

## Known follow-ups (non-blocking)

- opencastor-docs / opencastor-client / opencastor-autoresearch — still carry stale refs; handle in a future docs-sweep pass.
- `castor/conformance.py` / `doctor.py` / `watermark.py` spec citations kept as-is (historically accurate).
- `rcan/signing.py` v2.2 doctrine file in rcan-py — Release B deferred item, separate future release.
- Dependabot alert #15 on RRF — unrelated, check separately.

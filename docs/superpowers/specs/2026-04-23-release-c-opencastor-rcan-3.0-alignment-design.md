# Release C: opencastor RCAN 3.0 alignment + ecosystem drift sweep

**Date:** 2026-04-23
**Status:** Approved for plan-writing
**Tracking task:** #192

## Context

The 2026-04-16 ecosystem audit flagged three drift issues that Release B (the rcan 3.1 consolidation shipped 2026-04-23) deliberately left open:

1. **opencastor still pins `rcan>=1.2.1`** in `pyproject.toml` despite rcan 3.1.1 being live on PyPI. The pin predates RCAN 3.0.
2. **opencastor still accepts 2.x versions** at the ingress gate (`ACCEPTED_RCAN_VERSIONS` in `castor/compliance.py` includes `"2.1"`, `"2.2"`, `"2.2.1"`).
3. **robot-md-mcp's schema** says `rcan_version: "Must be 2.1+; 3.0+ recommended"` — inconsistent with the RCAN 3.0+ ecosystem policy.

Separately, `opencastor-ops/config/repos.json` (the ecosystem monitor's source of truth) still carries stale `expected_version` values for rcan-py (`2.0.0`) and rcan-ts (`2.0.0`) — drift that has been firing monitor alerts since Release B shipped.

The `feedback_rcan_3_plus_policy.md` memo is unambiguous: **"All new robot-md/RRF/ecosystem work must depend on RCAN 3.0+; 2.x frozen out."** Release C makes the ecosystem consistent with that policy.

## Scope

**In scope** (one combined release cycle, two package releases + one config-sync commit):

- opencastor `2026.4.23.0` — bump rcan dep; hard-cut 2.x at the ingress gate; fix `castor/loa.py` string compare; refresh README.
- robot-md-mcp `0.2.2` — tighten schema to enforce `rcan_version: "3.x"` via Ajv pattern.
- opencastor-ops — `repos.json` sync commit (no tag; direct commit on master) to clear monitor drift.

**Out of scope** (reject any task that drifts into these):

- Rewriting historically-accurate spec citations ("RCAN v2.2 §7.2 — ML-DSA-65 signing key MUST exist") in `castor/conformance.py`, `castor/doctor.py`, `castor/watermark.py`. These cite the spec section where a rule was introduced; rewriting to "v3.0 §…" would be factually misleading.
- Adopting new rcan-py 3.1 APIs (`canonical_json`, `sign_body`, `build_*`) in opencastor. Opencastor's narrow rcan surface (`SPEC_VERSION`, `SDK_VERSION`, subprocess `rcan_bridge`) doesn't need them. This release is *alignment*, not *adoption*.
- opencastor-docs, opencastor-client (Dart), opencastor-autoresearch doc refreshes. These carry stale refs but are documentation-only drift; handle ad-hoc if they become blocking.
- LiveCaptionsXR — zero RCAN touchpoints.
- `rcan/signing.py` doctrine cleanup (Release B deferred item; separate future release).
- Any runtime override / deprecation flag (`OPENCASTOR_ALLOW_LEGACY_RCAN` etc.) — the hard-cut is the explicit chosen behavior.
- Dependabot alert #15 on RRF (Release B known follow-up; unrelated).

## Architecture

Two coordinated package releases + one config-sync commit. No new subsystems, no new APIs adopted in opencastor, no wire-format changes. The release makes RCAN 3.0 the hard minimum across all ecosystem consumers.

- **opencastor `2026.4.23.0`** — bumps rcan dep to `>=3.1.1,<4.0`, hard-cuts `ACCEPTED_RCAN_VERSIONS` to `("3.0",)` with `major == 3` forward-compat, replaces `castor/loa.py`'s lexical string compare with unconditional `True`, rewrites the stale "RCAN v1.6 Features" README section.
- **robot-md-mcp `0.2.2`** — `src/schema/robot.schema.json` syncs from the canonical upstream (`/home/craigm26/robot-md/schema/v1/robot.schema.json`), which already enforces `rcan_version` as `pattern: "^3\\.[0-9]+(\\.[0-9]+)?$"` with "RCAN 3.0+ only" description. This is a drift-correction, not a schema redesign.
- **opencastor-ops sync commit** — `config/repos.json` bumps 4 `expected_version` values + `_updated` date.

**Release sequencing:** opencastor and robot-md-mcp are independent and can publish in parallel. The `repos.json` sync commit lands **last**, after both registries confirm the new versions, to avoid a race where the monitor sees "expected version not yet on registry."

**No breaking-change tag** on opencastor despite the 2.x ingress hard-cut: calver doesn't distinguish breaking releases. The CHANGELOG explicitly marks the 2.x rejection under a `BREAKING` header.

## Components

### opencastor (release `2026.4.23.0`)

Repo: `/home/craigm26/OpenCastor`, branch `main`.

Files:
- `pyproject.toml` — replace both `"rcan>=1.2.1"` occurrences with `"rcan>=3.1.1,<4.0"`
- `castor/compliance.py`:
  - Module docstring header: `"""castor.compliance — RCAN v2.1 compliance constants..."""` → `"""castor.compliance — RCAN 3.0 compliance constants..."""`
  - `ACCEPTED_RCAN_VERSIONS = ("3.0",)` (strip `"2.1"`, `"2.1.0"`, `"2.2"`, `"2.2.0"`, `"2.2.1"`)
  - `is_accepted_version()`: change forward-compat check from `major >= 3` to `major == 3`
- `castor/loa.py:47` — replace `"loa_required": config.get("rcan_version", "0") >= "1.6"` with `"loa_required": True` plus a one-line comment explaining 3.0+ mandates LoA unconditionally.
- `README.md` — rewrite the `## RCAN v1.6 Features` section as `## RCAN 3.0 Features` (LoA enforcement, ML-DSA-65 signing, canonical JSON, hybrid signing). Replace example `rcan_version: "1.6"` with `rcan_version: "3.0"`.
- `CHANGELOG.md` — new `[2026.4.23.0]` entry with `BREAKING` header calling out 2.x ingress rejection + dep floor bump.
- `tests/test_compliance_version_gate.py` — new file with 4 tests (see Testing section).

### robot-md-mcp (release `0.2.2`)

Repo: `/home/craigm26/robot-md-mcp`, branch `main`. Canonical schema source: `/home/craigm26/robot-md/schema/v1/robot.schema.json` (already enforces `"pattern": "^3\\.[0-9]+(\\.[0-9]+)?$"` on `rcan_version`, with description `"RCAN protocol version. Must be 3.0 or higher (ecosystem policy: RCAN 3.0+ only going forward; 2.x no longer accepted)."` — no change needed upstream).

Files:
- `src/schema/robot.schema.json` — run `npm run sync-schema` (writes bundled copy from canonical). This imports the already-correct 3.0+ pattern + description in one step. Post-sync, `npm run sync-schema -- --check` exits 0.
- `package.json` — version `0.2.1` → `0.2.2`
- `CHANGELOG.md` — new `[0.2.2]` entry under "Changed" noting the bundled-schema resync that now enforces RCAN 3.0+.
- `tests/` — new test cases (see Testing section).

### opencastor-ops (no tag; direct commit on master)

Repo: `/home/craigm26/opencastor-ops`, branch `master`.

File:
- `config/repos.json`:
  - `repos[].id == "rcan-py"` → `expected_version: "3.1.1"` (was `"2.0.0"`)
  - `repos[].id == "rcan-ts"` → `expected_version: "3.1.1"` (was `"2.0.0"`)
  - `repos[].id == "opencastor"` → `expected_version: "2026.4.23.0"` (was `"2026.4.17.0"`)
  - `repos[].id == "robot-md-mcp"` → `expected_version: "0.2.2"` (was `"0.2.1"`)
  - `_updated: "2026-04-23"`

## Data flow

Release sequencing (manual — no CI gate enforces ordering):

1. **Parallel publish:**
   - opencastor `2026.4.23.0` → PyPI (existing calver release workflow)
   - robot-md-mcp `0.2.2` → npm (existing Release workflow)
2. **Verify both live:**
   - `pip index versions opencastor` → shows `2026.4.23.0`
   - `npm view robot-md-mcp version` → `0.2.2`
3. **Land opencastor-ops sync commit:** Push `repos.json` update to master.
4. **Smoke check the monitor:** `gh workflow run "Ecosystem Monitor" -R craigm26/opencastor-ops` → expect 0 drift alerts.

**Dependency graph:**
- opencastor release depends on: rcan 3.1.1 on PyPI — already satisfied (shipped in Release B).
- robot-md-mcp release depends on: nothing (pure schema + version bump, no rcan SDK dep).
- repos.json sync depends on: both publishes completing.

## Error handling + risks

**Accepted behavioral consequences of the hard-cut:**
- Federation peers sending `rcan_version: "2.x"` are rejected at `is_accepted_version()` in opencastor. Per policy memo.
- Existing `robot.yaml` configs with `rcan_version: "2.x"` fail validation on opencastor startup. User fix: edit to `"3.0"` (the wizard already writes `"3.0"` by default).
- `ROBOT.md` files with `rcan_version: "2.x"` fail robot-md-mcp schema validation. Same user fix.

**Release-sequencing risk:**
- If `repos.json` sync commit lands before registry publishes complete, the monitor could false-alarm briefly. Mitigation: push repos.json only after step 2 confirms registry state.

**Test-regression risk (low):**
- opencastor `tests/test_rcan_sdk_bridge.py` + `tests/test_rcan_bridge_integration.py` import `SPEC_VERSION` only — still resolves to `"3.0"` under rcan 3.1.1.
- Any opencastor test asserting 2.x acceptance fails after the hard-cut. Mitigation: full `pytest` pre-publish; update mocks in same commit.
- robot-md-mcp has ~15 vitest cases. Schema tightening breaks any fixture/test with `rcan_version: "2.x"`. Mitigation: grep tests for `"2.1"|"2.2"` + fix inline.

**Rollback posture:**
- PyPI + npm don't allow un-publish cleanly. Fix-forward only: publish a `.1` patch reverting the gate if needed.
- opencastor-ops: revert commit on master.
- No production RRF / Cloudflare Pages touched → zero runtime outage surface.

**Spot-check during execution:**
- `castor/cloud/bridge.py` `rcan_bridge` subprocess launch — confirm the bridge's own startup path doesn't break under rcan 3.1.1. One-line grep + read of the arg-passing.

## Testing

### opencastor pre-release

1. Fresh venv install from working tree: `pip install -e .` — confirms `rcan>=3.1.1,<4.0` resolves to 3.1.1.
2. Full `pytest` — all existing tests pass. If any mock a 2.x version, fix inline in the same commit.
3. New `tests/test_compliance_version_gate.py`:
   ```python
   from castor.compliance import is_accepted_version

   def test_accepts_3_0():
       assert is_accepted_version("3.0") is True

   def test_accepts_3_1_forward_compat():
       assert is_accepted_version("3.1") is True

   def test_rejects_2_x():
       for v in ("2.1", "2.2", "2.2.1"):
           assert is_accepted_version(v) is False

   def test_rejects_future_major_no_free_pass():
       assert is_accepted_version("4.0") is False
   ```
4. Spot-check bridge launch: `grep -n "rcan_bridge" castor/cloud/bridge.py` + read the arg-passing block. Confirm version gate doesn't break the subprocess startup.
5. Build dry-run: `python -m build && twine check dist/*`

### opencastor release gate

6. Tag `v2026.4.23.0` + PyPI publish via existing GH Actions workflow.
7. Fresh venv: `pip install opencastor==2026.4.23.0 --no-cache-dir` + `opencastor --version` → prints new version.

### robot-md-mcp pre-release

1. `npm ci && npm run build && npm test` — existing suite passes.
2. New schema validation tests in `tests/`:
   ```ts
   test("rcan_version 2.1 is rejected", () => {
     const bad = { ...validFixture, rcan_version: "2.1" };
     expect(validate(bad)).toBe(false);
     expect(validate.errors?.[0].message).toMatch(/pattern/);
   });

   test("rcan_version 3.0 is accepted", () => {
     const good = { ...validFixture, rcan_version: "3.0" };
     expect(validate(good)).toBe(true);
   });
   ```
3. `npm run sync-schema -- --check` — confirms bundled schema matches canonical copy.
4. `npm publish --dry-run` — shows expected dist contents.

### robot-md-mcp release gate

5. Tag `v0.2.2`, publish to npm via existing Release workflow.
6. `npm view robot-md-mcp version` → `0.2.2`.
7. `npx -y robot-md-mcp@0.2.2 --version` in a scratch directory.

### opencastor-ops sync gate

1. Edit `config/repos.json`, commit, push to master.
2. `gh workflow run "Ecosystem Monitor" -R craigm26/opencastor-ops`
3. `gh run list --workflow "Ecosystem Monitor" -R craigm26/opencastor-ops --limit 1` → ✅
4. `gh run view <run-id> --log -R craigm26/opencastor-ops` → zero drift alerts.

### Cross-repo acceptance criterion

After all three land, from a clean shell:
```bash
pip index versions rcan opencastor robot-md
npm view rcan-ts version
npm view robot-md-mcp version
```
Expected:
- rcan `3.1.1`
- opencastor `2026.4.23.0`
- robot-md `1.0.1`
- rcan-ts `3.1.1`
- robot-md-mcp `0.2.2`

All 5 packages on 2 registries, all consistent with `repos.json`. This is the Release C done-state.

## Budget

~1 session. Work is mechanical; largest risk is test-regression in opencastor's large suite. If `pytest` surfaces unexpected 2.x-dependent tests, fix-in-place in the same PR and keep moving.

## Known follow-ups (non-blocking, explicitly deferred)

- opencastor-docs / opencastor-client / opencastor-autoresearch doc refreshes (cosmetic)
- `castor/conformance.py` / `doctor.py` / `watermark.py` spec citation rewrites — rejected in scope; keep historical accuracy
- `rcan/signing.py` v2.2 doctrine file in rcan-py — separate future release per Release B memo
- Release D candidates: RRF compliance intake endpoints; rcan-ts 3.2.0 compliance builders

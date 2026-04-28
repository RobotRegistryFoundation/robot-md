# NA Compliance + `compliance.jurisdictions[]` Refactor — Design

**Date:** 2026-04-27
**Status:** Draft (awaiting user review)
**Spec home:** robot-md (this repo) — touches rcan-spec, rcan-py, rcan-ts, RRF backend, opencastor, bob
**Related prior specs:**
- `2026-04-21-v0.9-rcan-3-compliance-design.md` — original EU AI Act compliance shape
- `2026-04-23-release-d2-rrf-compliance-intake-design.md` — RRF EU-register intake (§22-26)
- `2026-04-23-release-d1-rcan-ts-3.2.0-compliance-builders-design.md` — TS compliance builders (parallel pattern for jurisdiction builders here)
**Related memories:**
- `feedback_breaking_changes_ok_no_external_robots.md` — justifies the breaking schema refactor
- `feedback_runtime_change_protocol.md` — bob migration triggers re-emit + RRF re-submit
- `feedback_rcan_spec_authority.md` — fix upstream first (rcan-spec ships before robot-md)
- `project_rcan_py_sign_verify_asymmetry_2026_04_27.md` — RRF backend issues #71/#72 may block step (5)

---

## Overview

The current `compliance` block in `robot.schema.json` is shaped around the EU AI Act: `fria_ref`, `annex_iii_basis`, `eu_ai_act.audit_retention_days`, plus a flat `iso_42001` companion. There is no shape for North American regimes (ANSI/RIA R15.06 industrial-robot safety, ANSI/RIA R15.08 collaborative-robot safety) or for the standards underneath them (ISO 10218 alignment doc exists; ISO/TS 15066 has no doc).

This design adds NA conformance support and refactors the compliance block to a jurisdiction-pluggable shape so subsequent regimes (UK AI Bill, Canadian AIDA, etc.) plug in without further refactoring.

**Scope of first cut:**
- New schema shape: `compliance.jurisdictions[]` with discriminated union over `regime`
- Three regime entries supported: `eu_ai_act` (existing data, new home), `ansi_ria_r1506`, `ansi_ria_r1508`
- Three new alignment docs in rcan-spec: R15.06, R15.08, ISO/TS 15066
- Standard-of-conduct gates (FRIA-style: declaration must come with evidence)
- Migration script + bob re-emit + RRF re-submit
- New schema URL path `v2/robot.schema.json` (v1 frozen)

**Out of scope (listed as follow-ups):**
- Capability-layer cross-validation (does the backend actually expose a safety-rated stop?)
- Regime-agnostic `/v1/conformance-declaration` RRF endpoint
- ISO 42001 / NIST AI RMF / IEC 62443 schema fields beyond `self_assessed: bool`
- UK AI Bill, Canadian AIDA, or other non-NA regimes (the array shape supports them; entries to be added later)
- R15.08 power-and-force-limiting numerical limit cross-validation against robot mass/speed

## Design Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| Q1 | Deliverable shape | **B** — schema + alignment docs, no new RRF endpoints in first cut | NA standards are conformance-by-declaration; central NA register doesn't exist; endpoints are premature |
| Q2 | Standards covered in first cut | **C** — R15.06, R15.08, ISO/TS 15066 bundled | R15.06+R15.08 share regulator (A3/ANSI), share risk-assessment vocabulary; schema cost of doing both at once is marginal once `compliance.na` block exists; ISO/TS 15066 is the parent of R15.08 |
| Q3 | Schema shape | **B** — `compliance.jurisdictions[]` array, full breaking refactor | No third-party robots in deployment (only bob, self-owned); the right shape now beats a backward-compat shim that locks in a bad layout |
| Q4 | Conformance gate aggressiveness | **B** — standard-of-conduct gates | Declaration without evidence is the failure mode the FRIA gate already prevents for EU; we extend the same pattern to NA obligations |
| Q5 | What lives inside the array | **A** — strict legal regimes only | Voluntary frameworks (ISO 42001, NIST AI RMF, IEC 62443) have no MUST clauses; folding them in creates a kind-discriminator that does no work for those entries |
| Schema path | `v1/` in-place vs `v2/` new path | **`v2/`** — v1 frozen, v2 published alongside | RRF backend has external HTTP consumers (registry website, future plugin importers); cost of an extra path is low |
| Bob migration | EU-only re-submit vs add R15.06 too | **Add R15.06 in same migration** | Bob is industrial; R15.06 declaration costs nothing operationally and exercises the new code path end-to-end |

## Section 1 — Architecture & Repository Cascade

This work lands across 5 repos in a fixed dependency order. Each PR can ship independently once its predecessors land.

| # | Repo | Bump | Blocking | What lands |
|---|---|---|---|---|
| 1 | rcan-spec | v3.1 → v3.2 | none | New §27, three new alignment docs, cross-ref into existing iso-10218 doc |
| 2 | robot-md | v1.2.x → v2.0.0 | needs (1) | Schema refactor + validator gates + fixture tests + migration script |
| 3 | rcan-py | 3.3.1 → 3.4.0 | needs (2) | `Jurisdiction.*` builders, deprecate `eu_ai_act_compliance(...)` |
| 4 | rcan-ts | 3.3.x → 3.4.0 | needs (2) | TypeScript builder parity |
| 5 | RRF backend | minor | needs (2), **#72 fixed** | `/v1/eu-register` accepts new shape (server-side coercion) |
| 6 | opencastor | next minor | needs (3) | Bumps rcan-py dep, regenerates embedded schema |
| 7 | bob | (memory bump) | needs (5) | Run migration, re-sign, re-submit, verify 5/5 artifacts |

**Critical-path dependency on RRF #72:** the eu-register endpoint currently returns 405 (per `project_rcan_py_sign_verify_asymmetry_2026_04_27.md`). Step 5 of this spec cannot ship until #72 closes. Step 7 (bob re-submit) cannot ship until step 5.

## Section 2 — Schema Design

The new `compliance` block in `robot-md/site/schema/v2/robot.schema.json`. v1 schema is frozen at its current shape; v2 is published alongside.

```json
"compliance": {
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "jurisdictions": {
      "type": "array",
      "description": "Legal regimes the robot is declared conformant with. Each entry uses a discriminated union on `regime`. Order is not significant.",
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

Jurisdiction shapes (in `$defs`):

```json
"jurisdiction.eu_ai_act": {
  "type": "object",
  "additionalProperties": true,
  "required": ["regime", "risk_assessment_ref"],
  "properties": {
    "regime":               { "const": "eu_ai_act" },
    "risk_assessment_ref":  { "$ref": "#/$defs/uri" },
    "annex_iii_basis": {
      "type": "string",
      "enum": ["safety_component", "biometric", "critical_infrastructure",
               "education", "employment", "essential_services",
               "law_enforcement", "migration", "administration_of_justice",
               "general_purpose_ai"]
    },
    "fria_ref":              { "$ref": "#/$defs/uri" },
    "audit_retention_days":  { "type": "integer", "minimum": 0 }
  },
  "allOf": [
    { "if":   { "required": ["annex_iii_basis"] },
      "then": { "required": ["fria_ref"] } }
  ]
}

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
    { "if":   { "properties": { "collaborative_modes":
                  { "contains": { "const": "power_force_limiting" } } } },
      "then": { "required": ["force_limits_ref"] } }
  ]
}
```

Voluntary framework shapes are intentionally minimal in this cut:

```json
"voluntary.iso_42001":   { "type": "object", "properties": {
  "self_assessed": { "type": "boolean" },
  "level": { "type": "integer", "minimum": 1, "maximum": 5 },
  "audit_ref": { "$ref": "#/$defs/uri" }
}, "additionalProperties": true }

"voluntary.nist_ai_rmf": { "type": "object", "properties": {
  "self_assessed": { "type": "boolean" },
  "profile_ref":   { "$ref": "#/$defs/uri" }
}, "additionalProperties": true }

"voluntary.iec_62443":   { "type": "object", "properties": {
  "self_assessed":  { "type": "boolean" },
  "security_level": { "type": "integer", "minimum": 1, "maximum": 4 },
  "assessment_ref": { "$ref": "#/$defs/uri" }
}, "additionalProperties": true }
```

`#/$defs/uri` is the existing pattern: `^[a-zA-Z][a-zA-Z0-9+.-]*:.+` (RFC 3986 scheme + colon + non-empty path).

**Design notes:**
- `additionalProperties: false` at the top-level `compliance` object is a tightening from current. Now that the full shape is known, anything else is a typo.
- `additionalProperties: true` on each jurisdiction entry preserves room for regulator-specific extensions without spec bumps.
- The `oneOf`+`const` discriminator pattern produces clean validation errors that name the failing regime.
- Array form (vs. flat object keyed by regime) lets a robot declare R15.06 *and* R15.08 simultaneously, preserves manifest declaration order, and matches how alignment docs cross-reference.

## Section 3 — Gates & Enforcement Layers

Three layers, each catching a different class of violation. Schema gates fail at parse time; validator gates fail at `robot-md validate` time; capability gates fail at `robot-md doctor` / runtime. Putting things at the right layer matters — schema gates can't be bypassed.

**Schema-layer gates (built into the JSON Schema above):**

| When | Then | Why |
|---|---|---|
| `regime: eu_ai_act` declared | `risk_assessment_ref` required | All regimes require risk assessment |
| `regime: eu_ai_act` and `annex_iii_basis` set | `fria_ref` required | Existing FRIA gate, preserved across refactor |
| `regime: ansi_ria_r1506` declared | `edition`, `system_integrator`, `risk_assessment_ref` required | R15.06-2 mandates named integrator |
| `regime: ansi_ria_r1508` declared | `edition`, `risk_assessment_ref`, `collaborative_modes[]` (≥1) required | Declaring cobot conformance without naming the collab mode is meaningless |
| `regime: ansi_ria_r1508` and `collaborative_modes` contains `power_force_limiting` | `force_limits_ref` required | ISO/TS 15066 Annex A obligation; PFL without limits is the canonical paper-only-compliance failure |

**Validator-layer gates (`robot-md validate`):**
- Each `regime` value in `jurisdictions[]` must be unique (no double-declaring R15.06).
- `edition` must be a known edition for that regime; emit a friendly error ("R15.06:2025 not yet published; use 2012 or wait").
- Ref URIs must be RFC 3986 absolute. The schema pattern catches this; validator wraps it with a clearer message.
- If `audit_retention_days < 365` on the EU entry, warn (not block).

**Capability-layer gates (out of scope here, listed as follow-up):**
- `safety_rated_monitored_stop` declared → backend must expose safety-rated stop primitive (SO-ARM101 currently does not — would be a doctor error on bob).
- `speed_and_separation_monitoring` declared → robot must declare an SSM-capable proximity sensor in `sensors[]`.
- These belong in robot-md's first-motion-readiness scaffold, not in schema.

## Section 4 — Alignment Doc Structure

Three new files in `rcan-spec/docs/compliance/`, each following the structure already established by `iso-10218-alignment.md`:

```
rcan-spec/docs/compliance/
├── iso-10218-alignment.md         (existing — gets a 1-paragraph cross-ref to R15.06 added)
├── ansi-ria-r1506-alignment.md    (new — ~150 lines)
├── ansi-ria-r1508-alignment.md    (new — ~200 lines)
└── iso-ts-15066-alignment.md      (new — ~120 lines)
```

Each new doc has six sections matching the existing template:

1. **Header block** — Document type, RCAN spec version (3.2), Standard, Status (Informative), Last updated.
2. **Purpose** — Doc is informative, not prescriptive; conformance with the standard plus RCAN gives operators a complete coverage story.
3. **Document Scope** — Two-column table: standard-covers vs. RCAN-covers. RCAN covers the AI/network governance layer above the mechanical/integration layer the standard targets.
4. **Clause-by-Clause Alignment Table** — three columns: RCAN Provision | Standard Requirement | Relationship (`Aligned` / `RCAN Fills Gap` / `Standard Fills Gap`).
   - **R15.06**: ~12 rows. Risk assessment (RCAN audit trail satisfies traceability), system integrator declaration (RCAN's principal-RBAC tracks operator identity), software integrity (RCAN prompt-injection defense extends), AI accountability (RCAN fills entirely).
   - **R15.08**: ~15 rows. Each of the four collaborative modes maps to RCAN message types and audit fields. PFL force/pressure limits map to capability declarations + safety_envelope. Hand-guiding maps to LEASEE role + scoped JWT. SSM maps to perception telemetry message types.
   - **ISO/TS 15066**: ~10 rows. Mostly mirrors R15.08 since 15066 is its parent; this doc exists for traceability when European operators reference 15066 directly without going through R15.08.
5. **Cross-references** — Pointers to schema fields the standard maps to (e.g., R15.06 alignment doc → `compliance.jurisdictions[].regime=ansi_ria_r1506` schema entry; R15.08 → `collaborative_modes` enum + `force_limits_ref` gate).
6. **Versioning note** — When the spec version is bumped (3.2 → 3.3), alignment docs are re-reviewed for staleness.

The existing `iso-10218-alignment.md` gets one paragraph appended near the top:

> Operators in North America declaring conformance with ANSI/RIA R15.06 should refer to that standard's alignment doc; R15.06 is the US adoption of ISO 10218-1/2 with US-specific integration extensions. The schema field `compliance.jurisdictions[].regime=ansi_ria_r1506` is the declarative mechanism.

The §27 spec section in `rcan-spec/spec/sections/` describes the multi-jurisdiction declaration semantics, the regime enum, and the gate layering. It is normative; alignment docs are informative.

## Section 5 — Migration Plan

**One-shot migration script:** `robot-md/scripts/migrate-compliance-v2.py`

Pure data transform. No long-lived compatibility shim — per `feedback_breaking_changes_ok_no_external_robots.md`.

```
old: compliance.fria_ref + .annex_iii_basis + .eu_ai_act.audit_retention_days
new: compliance.jurisdictions[0] = {
       regime: "eu_ai_act",
       risk_assessment_ref: <derived from old fria_ref or prompted>,
       annex_iii_basis: <copy>,
       fria_ref: <copy>,
       audit_retention_days: <copy>
     }

old: compliance.iso_42001        →  unchanged (still flat)
new: compliance.nist_ai_rmf      →  empty (operator opts in if applicable)
new: compliance.iec_62443        →  empty (operator opts in if applicable)
```

Behavior:
1. Parse old ROBOT.md.
2. Print unified diff against new shape.
3. Prompt for `[y/N]` confirmation.
4. Write.
5. With `--add-r1506` flag: append a second `jurisdictions[]` entry for ANSI/RIA R15.06 conformance. Required fields prompted interactively (edition, system_integrator, risk_assessment_ref). Bob will use this flag.
6. After write, the script announces the runtime-change protocol applies (per `feedback_runtime_change_protocol.md`): re-emit FRIA, benchmarks, IFU, eu-register; sign + submit; update bob memory.

The script is idempotent on already-v2 manifests (detects the `jurisdictions[]` key and exits 0 with a notice).

## Section 6 — Testing

Three layers:

**1. Schema fixture tests** (`robot-md/tests/schema/`):

Positive fixtures:
- `compliance_jurisdictions_eu_only.json` (EU regime, full shape)
- `compliance_jurisdictions_na_industrial.json` (R15.06 only)
- `compliance_jurisdictions_na_cobot_pfl.json` (R15.08 with PFL, force_limits_ref present)
- `compliance_jurisdictions_na_cobot_ssm.json` (R15.08 with SSM, no force_limits required)
- `compliance_jurisdictions_eu_plus_na.json` (both — bob's new shape)

Negative fixtures (each asserts the validator returns the *specific* schema path of the violation):
- `compliance_eu_annex_iii_no_fria.json` (regression for the existing FRIA gate)
- `compliance_r1506_missing_integrator.json`
- `compliance_r1506_missing_edition.json`
- `compliance_r1508_pfl_missing_force_limits.json`
- `compliance_r1508_no_collaborative_modes.json`
- `compliance_jurisdictions_duplicate_regime.json` (validator-layer, not schema)

**2. Builder cross-language parity tests** (rcan-py + rcan-ts):

Existing parity test harness from rcan-py 3.2.0 already does this for EU. Adds R15.06 and R15.08 cases. Asserts both languages emit byte-identical JSON for the same builder inputs.

**3. End-to-end fixture:**

Bob's new ROBOT.md (EU + R15.06) gets emitted, signed via rcan-py, submitted to RRF's `/v1/eu-register` (which now accepts the new schema), and round-trip verified. Catches schema-vs-backend drift early — the kind that produced the §26 rmn gap before. Lives in `robot-md/tests/integration/test_compliance_v2_roundtrip.py`.

## Out of Scope / Follow-ups

| Item | Why deferred | When to revisit |
|---|---|---|
| Capability-layer cross-validation | Lives in `robot-md doctor` / first-motion-readiness scaffold, not schema | After bob's first R15.08 deployment (cobot use case appears) |
| `/v1/conformance-declaration` regime-agnostic RRF endpoint | Premature; no NA central register exists | When a third regime needs an endpoint (UK / Canada) |
| ISO 42001 / NIST AI RMF / IEC 62443 deeper schema | Those are voluntary; over-modeling them adds noise without enforcement value | When a customer asks for one to be auditable |
| UK AI Bill, Canadian AIDA, other regimes | Array shape supports them; entries can be added without spec changes | When a deployment lands in those jurisdictions |
| R15.08 PFL numerical force/pressure limit cross-validation | Requires robot mass/speed/geometry; complex; safer as a `doctor` check | After SO-ARM101 cobot pilot |

## Open Questions

None blocking. Listed for awareness:

- The §27 spec text in rcan-spec needs to decide whether `regime` values are case-sensitive (lean: yes, lowercase by convention).
- Whether the deprecated `eu_ai_act_compliance(...)` builder in rcan-py 3.4.0 should emit a `DeprecationWarning` or just a docstring note (lean: warning).
- Whether bob's existing `annex_iii_basis=safety_component` (DEMO classification, per memory) should be revisited as part of this re-emit — likely no, but worth confirming during step (7).

## Spec Self-Review

- ✅ No placeholders ("TBD", "TODO", incomplete sections).
- ✅ Internal consistency: gate table in Section 3 matches `allOf` blocks in Section 2; cascade order in Section 1 matches PR sequence in Section 5.
- ✅ Scope: focused enough for a single design (one schema refactor + three docs + migration script). The 7 PRs are sequencing of one logical change, not separate projects. Each gets its own writing-plans pass.
- ✅ Ambiguity: resolved — both schema-path question (B: v2/) and bob-migration question (R15.06 included) explicitly settled.

---

**Next step:** user reviews this spec; on approval, brainstorming hands off to `superpowers:writing-plans` for the per-repo implementation plans.

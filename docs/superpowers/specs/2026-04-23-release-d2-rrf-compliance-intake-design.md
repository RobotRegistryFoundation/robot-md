# Release D2 — RRF Compliance Intake Endpoints

**Status:** Spec — **SCOPE REDUCED 2026-04-23 (partial-ship):** §26 EU Register deferred to D3 pending rcan-ts 3.3.0 (needs `rmn` added to envelope upstream). D2 ships four endpoints: §22 FRIA, §23 SafetyBenchmark, §24 IFU, §25 IncidentReport. See `reference_rcan_spec_eu_register_rmn_gap.md` for the upstream bookmark.

**Binding corrections** (from reading rcan-ts 3.2.0 source, not original spec assumptions):
- §22 FRIA — check `doc.system.rrn === URL rrn` (no top-level rrn)
- §23 SafetyBenchmark — **no doc-level binding check**; URL + sig only (builder output has no rrn field)
- §24 IFU — **no doc-level binding check**; URL + sig only (builder output has no rrn field)
- §25 IncidentReport — check `doc.rrn === URL rrn` (builder emits top-level rrn)

The security model is unchanged: `verifyComplianceSubmission` looks up `pq_signing_pub` at the URL-derived `robot:{rrn}` and verifies the signature. A mismatched RRN would fail signature verification because it would look up a different robot's pubkey.

**Status:** Spec (2026-04-23)
**Target:** RobotRegistryFoundation (Astro + Cloudflare Pages Functions)
**Depends on:** rcan-ts 3.2.0 (shipped in Release D1), existing RRF `/v2/robots/register` flow
**First producer:** Bob (RRN-000000000001, RPi5 + Hailo-8, OpenCastor v2026.3.13.11)

## Purpose

Add five compliance intake endpoints to RRF so robots registered under RCAN 3.0 §21 can submit the EU AI Act compliance artifacts defined in RCAN §22-26 and produced by `rcan-ts` 3.2.0's `build*` functions. Each endpoint stores the signed document and serves it back — either publicly or behind Bearer auth — following the existing `firmware-manifest.ts` / `sbom.ts` precedent for transport, with `verifyBody`-based cryptographic auth inherited from `/v2/robots/register`.

## Scope

**In scope:**
- Five POST+GET endpoints (one per compliance type)
- Shared auth helper reusing `verifyBody` from rcan-ts
- KV retention scheme (current + history, 10-year TTL)
- Per-type GET policy (public vs Bearer-gated)
- Tests (~55-60 unit + 5 smoke)
- Documentation updates to `README.md` and `src/pages/api/index.astro`
- Optional cross-link from `src/pages/rcan-integration/`

**Out of scope:**
- Bearer token issuance / consumer auth model for authenticated GETs (reserved door only — D2 rejects missing Bearer with 401 but does not validate token contents)
- National-authority access controls for Art. 72 incident reports
- Public search/index pages for compliance submissions
- Producer SDK beyond what rcan-ts 3.2.0 already ships
- D1 deliverables (byte-parity fixture, rcan-ts builders — already shipped)

## Architecture

Five POST+GET endpoints under RRF, sharing one auth library:

```
functions/v2/robots/[rrn]/fria.ts                   (§22)  auth GET
functions/v2/robots/[rrn]/safety-benchmark.ts       (§23)  public GET
functions/v2/robots/[rrn]/ifu.ts                    (§24)  public GET
functions/v2/robots/[rrn]/incident-report.ts        (§25)  auth GET
functions/v2/models/[rmn]/eu-register.ts            (§26)  public GET  (new subroute)
functions/v2/_lib/compliance-auth.ts                 (shared helper)
functions/v2/_lib/test-helpers.ts                    (test-only signing helper)
```

EU Register lives under `/v2/models/[rmn]/` rather than `/v2/robots/[rrn]/` because Art. 49 registration is legally per-model/per-provider, not per-robot.

### KV schema

| Key | Purpose | TTL |
|---|---|---|
| `compliance:fria:{rrn}` | current FRIA | 10y |
| `compliance:fria:history:{rrn}:{ts}` | snapshots | 10y |
| `compliance:safety-benchmark:{rrn}` | current benchmark | 10y |
| `compliance:safety-benchmark:history:{rrn}:{ts}` | snapshots | 10y |
| `compliance:ifu:{rrn}` | current IFU | 10y |
| `compliance:ifu:history:{rrn}:{ts}` | snapshots | 10y |
| `compliance:incident-report:{rrn}` | current report snapshot | 10y |
| `compliance:incident-report:history:{rrn}:{ts}` | snapshots | 10y |
| `compliance:eu-register:{rmn}` | current entry | 10y |
| `compliance:eu-register:history:{rmn}:{ts}` | snapshots | 10y |

10-year TTL matches the existing `robot:{rrn}` record and the Art. 72 record-keeping obligation for high-risk AI systems.

## Components

### Shared helper: `functions/v2/_lib/compliance-auth.ts`

```ts
export interface VerifiedSubmission {
  ok: true;
  document: Record<string, unknown>;   // original body minus sig/pq_kid
}

export interface VerifyError {
  ok: false;
  status: number;                      // 400, 401, or 500
  error: string;
}

export async function verifyComplianceSubmission(
  request: Request,
  env: { RRF_KV: KVNamespace },
  entityKey: string,                   // "robot:{rrn}"
): Promise<VerifiedSubmission | VerifyError>;
```

Flow:
1. `request.json()` → 400 on parse error
2. Extract `{ sig, pq_kid, ...rest }`; 400 if `sig` or `pq_kid` missing
3. `env.RRF_KV.get(entityKey)` → 401 if not found
4. Parse stored record, extract `pq_signing_pub`
5. `verifyBody({ ...rest, sig }, pqPub)` from rcan-ts → 401 if false
6. Return `{ ok: true, document: rest }`

### Handler files (five total)

Each ~120 lines, all share shape:

```ts
export const onRequest: PagesFunction<Env> = async (ctx) => {
  // 1. validate URL param (RRN or RMN format)
  // 2. dispatch GET / POST / 405
};

async function handleGet(env, id): Promise<Response> {
  // public types: serve current doc, cache 300s, 404 if missing
  // auth types (fria, incident-report): reject missing Bearer with 401, else public path
}

async function handlePost(request, env, id): Promise<Response> {
  const result = await verifyComplianceSubmission(request, env, `robot:${submitterRrn}`);
  if (!result.ok) return errorResponse(result);
  const doc = result.document;

  if (doc.schema !== EXPECTED_SCHEMA) return err(`Expected schema ${EXPECTED_SCHEMA}`, 400);
  if (doc.rrn !== id) return err("Document rrn does not match URL rrn", 400);  // rmn for eu-register

  const stored = JSON.stringify({ ...doc, _received_at: new Date().toISOString() });
  await env.RRF_KV.put(`compliance:${type}:${id}`, stored, { expirationTtl: TEN_YEARS });
  await env.RRF_KV.put(`compliance:${type}:history:${id}:${Date.now()}`, stored, { expirationTtl: TEN_YEARS });
  return new Response(JSON.stringify({ ok: true, /*...*/ }), { status: 201 });
}
```

Schema constants imported from rcan-ts 3.2.0:
- `SAFETY_BENCHMARK_SCHEMA`, `IFU_SCHEMA`, `INCIDENT_REPORT_SCHEMA`, `EU_REGISTER_SCHEMA` — already exported
- FRIA: inline `"rcan-fria-v1"` string for D2; sweep into rcan-ts as `FRIA_SCHEMA` constant in a later minor bump

### EU Register special case (`models/[rmn]/eu-register.ts`)

URL has no RRN, so the submitting robot's identity is conveyed via header:
- Producer includes `X-Submitter-RRN: RRN-...` header
- Handler calls `verifyComplianceSubmission(req, env, "robot:{X-Submitter-RRN}")`
- `document.rmn === URL rmn` check (not `document.rrn`)
- Stored doc includes `_submitted_by_rrn: <header value>` as RRF-added metadata (outside the signed payload, for provenance)

## Data Flow

### Happy path (per-robot POST)

```
Producer (Bob, rcan-ts client)
  │
  ├─ build doc:    doc = buildSafetyBenchmark({ rrn, ... })
  │                → { schema: "rcan-safety-benchmark-v1", rrn, ..., generated_at }
  │
  ├─ sign doc:     canon = canonicalJson(doc)
  │                sig = { ml_dsa, ed25519, ed25519_pub }
  │
  └─ POST /v2/robots/RRN-000000000001/safety-benchmark
     body: { ...doc, sig, pq_kid }

RRF edge worker
  │
  ├─ validate RRN format                                    → 400 if bad
  ├─ parse JSON                                             → 400 if bad
  ├─ verifyComplianceSubmission(req, env, "robot:RRN-...")
  │     ├─ KV.get("robot:RRN-000000000001")                 → 401 if unregistered
  │     ├─ extract pq_signing_pub from record
  │     └─ verifyBody({ ...doc, sig }, pqPub)               → 401 if bad sig
  ├─ document.schema === "rcan-safety-benchmark-v1"         → 400 if mismatch
  ├─ document.rrn === URL rrn                               → 400 if mismatch
  ├─ stored = JSON.stringify({ ...document, _received_at })
  ├─ KV.put("compliance:safety-benchmark:RRN-...", stored, TTL=10y)
  └─ KV.put("compliance:safety-benchmark:history:RRN-...:{now}", stored, TTL=10y)
  
  → 201 { ok: true, rrn, submitted_at, safety_benchmark_url }
```

### GET — public types (safety-benchmark, ifu, eu-register)

`KV.get` → 404 if missing, else 200 with `Cache-Control: public, max-age=300`. Same shape as `firmware-manifest.ts`.

### GET — authenticated types (fria, incident-report)

Check `Authorization: Bearer ` prefix → 401 if missing. Otherwise identical to public path. D2 does not validate token contents — this is a reserved door for a future consumer-auth release.

### EU Register POST variation

- URL: `/v2/models/{rmn}/eu-register`
- Header: `X-Submitter-RRN: RRN-...` (identifies which robot's PQ key signed)
- `verifyComplianceSubmission(req, env, "robot:{X-Submitter-RRN}")`
- Required: `document.rmn === URL rmn`
- Stored doc carries `_submitted_by_rrn` for provenance (not part of signed payload)

## Error Handling

Uniform status codes across all five endpoints:

| Case | Status | Body |
|---|---|---|
| URL param bad format | 400 | `{ error: "Invalid RRN format" }` (or RMN) |
| Method not GET/POST | 405 | `{ error: "Method not allowed" }` |
| Body not valid JSON | 400 | `{ error: "Invalid JSON body" }` |
| Missing `sig` or `pq_kid` | 400 | `{ error: "Missing signature fields" }` |
| Robot not registered | 401 | `{ error: "Robot not registered" }` |
| Signature verification failed | 401 | `{ error: "Signature verification failed" }` |
| Schema string mismatch | 400 | `{ error: "Expected schema X, got Y" }` |
| `document.rrn` / `document.rmn` vs URL mismatch | 400 | `{ error: "Document <id> does not match URL <id>" }` |
| GET 404 (nothing submitted) | 404 | `{ error: "<type> not found", rrn }` |
| GET 401 (fria/incident, no Bearer) | 401 | `{ error: "Authorization required" }` |
| Internal error (KV, crypto) | 500 | `{ error: "Internal error", detail: msg }` |

**401 for unregistered RRN vs sig-failure**: avoid leaking "this RRN exists/doesn't exist" to unsigned callers.

**400 for schema mismatch, not 422**: matches existing RRF convention (`firmware-manifest.ts` uses 400 for all shape-related errors).

**No structured error codes** (no `error_code: "SIG_FAIL"` taxonomy). Existing endpoints use human-readable `error` strings only; do not introduce a second style in D2.

## Server-side validation strictness

**Liberal.** Verify sig, check `document.schema` string matches expected, check `document.rrn`/`document.rmn` matches URL param. Accept extra fields. Do not re-run rcan-ts builders server-side.

Rationale: the crypto signature guarantees provenance. Content validity is the producer's problem. Liberal acceptance keeps RRF forward-compatible as rcan-ts evolves; schema correctness is enforced by the rcan-spec `compliance-v1.json` fixture at the library layer, not at the intake.

## Testing

### Per-endpoint vitest files

One file per handler (`fria.test.ts`, `safety-benchmark.test.ts`, `ifu.test.ts`, `incident-report.test.ts`, `eu-register.test.ts`), each covering:

| Case | Every endpoint |
|---|---|
| GET 404 when nothing submitted | yes |
| POST valid sig succeeds (201), stores current + history | yes |
| POST tampered body rejected (401) | yes |
| POST bad pq_signing_pub (unregistered) rejected (401) | yes |
| POST missing `sig` rejected (400) | yes |
| POST wrong schema string rejected (400) | yes |
| POST `document.rrn` ≠ URL rrn rejected (400) | yes |
| GET 401 without Bearer | fria, incident-report |
| GET 200 public with cache header | safety-benchmark, ifu, eu-register |
| Invalid URL param → 400 | yes |
| Non-GET/POST method → 405 | yes |

### Shared test helper

`functions/v2/_lib/test-helpers.ts` (new): `signComplianceBody(document, keypair)` — uses rcan-ts to produce a valid `{ ...doc, sig, pq_kid }` body. Prevents every test file from reimplementing signing.

### Integration smoke test

`tests/compliance-intake.smoke.test.ts` at repo root: one end-to-end per endpoint using a KV mock — register a robot, build doc via rcan-ts, sign, POST, verify 201, GET, verify bytes round-trip. Proves the `verifyBody` wire matches rcan-ts 3.2.0 builder output.

### Cross-repo parity

The rcan-spec fixture `compliance-v1.json` (shipped in Release D1) already proves rcan-ts builds produce byte-identical output to rcan-py. D2 does not ship a new fixture; the existing one remains the canonical reference.

### Bob live validation

Out of scope for automated tests. Manual milestone after deploy: Bob (RPi5) calls `buildSafetyBenchmark` from rcan-ts 3.2.0, signs with his registered PQ key, POSTs to production RRF, confirms GET returns the submission. This is the "Bob as first producer" milestone.

**Total new tests:** ~55-60 unit + 5 smoke.

## Documentation deliverables

- **`RobotRegistryFoundation/README.md`**: add a "Compliance intake (RCAN §22-26)" section with the five endpoints, request/response shapes, and the happy-path flow diagram
- **`src/pages/api/index.astro`**: add API documentation for the five endpoints matching the existing style for firmware-manifest and sbom
- **`src/pages/rcan-integration/`** (optional cross-link): since §22-26 are part of RCAN 3.0, reference the new intake endpoints from the spec-integration page

These ship with the code in the same release, not as a follow-up.

## Non-Goals / Deferred

- **Consumer auth model for Bearer-gated GETs** — D2 only reserves the door (rejects missing Bearer). Who holds which token, how they're issued, and what the access-control graph looks like are future work.
- **Public search / listing pages** — no `/registry/:rrn/compliance` page, no aggregate dashboards. Data is stored and retrievable by direct URL only.
- **National-authority access for Art. 72 incident reports** — separate legal workflow, out of scope.
- **Producer SDK beyond rcan-ts 3.2.0** — producers sign with whatever tooling produces ML-DSA-65 + Ed25519 signatures over rcan-ts builder output; no new helper ships in D2.
- **Automated incident escalation / notifications** — incident-report is store-and-serve in D2; triggering alerts on severity="life_health" is future work.

## Open questions / future work

- **FRIA_SCHEMA constant**: add to rcan-ts 3.3.0 so RRF can drop the inline `"rcan-fria-v1"` string.
- **History pagination**: `compliance:{type}:history:{rrn}:{ts}` keys pile up over 10 years. A future endpoint could list them; not in D2.
- **Rate limiting**: none in D2. Cloudflare edge handles flood protection at the infrastructure layer.
- **Schema versioning**: when `rcan-*-v2` lands, RRF needs to decide whether endpoints accept both or reject the old. Liberal validation in D2 defers this to a per-schema-version decision.

## Success criteria

- All five endpoints deployed to production RRF
- Test suite green: ~55-60 unit + 5 smoke + existing RRF suite unchanged
- Bob submits a valid `safety-benchmark` document, RRF stores it, GET returns byte-identical on retrieval
- README and `/api/` page updated with endpoint documentation
- No regression in existing `firmware-manifest` / `sbom` / `register` flows

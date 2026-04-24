# RRF Tier-Gated Write-Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three auth gaps surfaced by the 2026-04-24 RRF audit — no key rotation/recovery, no revocation, no squatting protection for high-tier robots — while preserving the zero-friction default (`unverified` remains TOFU).

**Architecture:**
1. **Rotation** — `POST /v2/robots/:rrn/rotate-key` accepts a payload signed by the *old* key that binds a new key. Survivable against lost-laptop scenarios only when an offline recovery copy of the old key exists; no account-recovery out of band (intentional).
2. **Revocation** — `POST /v2/robots/:rrn/revoke-key` writes a revocation entry consulted by every compliance-verify path. Revoked records cannot receive further PATCH / compliance submissions and are flagged in GET responses.
3. **Tier-gated identity binding** — `RobotRecord.verification_status` ∈ `{unverified, community, manufacturer_claimed, manufacturer_verified}`. `unverified` (the default on register) is TOFU. Promoting to `manufacturer_claimed` requires a server-verified DNS TXT proof. Promoting to `manufacturer_verified` additionally requires a signed attestation and a reachable RURI. The promotion endpoint is separate from register so the default path stays zero-friction.

**Tech Stack:** Cloudflare Pages Functions (TypeScript), vitest, Cloudflare KV, rcan-ts `verifyBody`, DNS-over-HTTPS (Cloudflare 1.1.1.1 `application/dns-json`), WebCrypto `SubtleCrypto.verify` for X.509 attestation chain.

**Codebase affected:**
- `RobotRegistryFoundation/` — endpoints, verification logic, KV schema
- `robot-md/cli/src/robot_md/` — new `rotate-key`, `revoke-key`, `verify-tier` subcommands
- `rcan-spec/` — optional §27 note about the rotation/revocation envelope shape (pure docs)

---

## Pre-flight

Before starting any task, the executor should:

```bash
cd ~/RobotRegistryFoundation
git pull --rebase origin main
npm ci
npm test   # must pass 96/96 baseline from 2026-04-24
```

If baseline is not green, STOP and flag to the operator.

---

## File Structure (locked in before Task 1)

### Created files

| Path | Responsibility |
|---|---|
| `RobotRegistryFoundation/functions/v2/_lib/revocation.ts` | Revocation KV helper (`markRevoked`, `isRevoked`) |
| `RobotRegistryFoundation/functions/v2/_lib/dns-verify.ts` | DoH-based `_rcan-verify.<domain>` TXT lookup |
| `RobotRegistryFoundation/functions/v2/_lib/attestation-verify.ts` | Signed-attestation + RURI `/.well-known/rcan-manifest.json` check |
| `RobotRegistryFoundation/functions/v2/robots/[rrn]/rotate-key.ts` | `POST /v2/robots/:rrn/rotate-key` |
| `RobotRegistryFoundation/functions/v2/robots/[rrn]/revoke-key.ts` | `POST /v2/robots/:rrn/revoke-key` |
| `RobotRegistryFoundation/functions/v2/robots/[rrn]/verify-tier.ts` | `POST /v2/robots/:rrn/verify-tier` (promotion endpoint) |
| `RobotRegistryFoundation/functions/v2/robots/[rrn]/rotate-key.test.ts` | Tests for rotation |
| `RobotRegistryFoundation/functions/v2/robots/[rrn]/revoke-key.test.ts` | Tests for revocation |
| `RobotRegistryFoundation/functions/v2/robots/[rrn]/verify-tier.test.ts` | Tests for tier promotion |
| `RobotRegistryFoundation/functions/v2/_lib/revocation.test.ts` | Unit tests for revocation helper |
| `RobotRegistryFoundation/functions/v2/_lib/dns-verify.test.ts` | DoH mock tests |
| `robot-md/cli/src/robot_md/rotate_key.py` | CLI `robot-md rotate-key` |
| `robot-md/cli/src/robot_md/revoke_key.py` | CLI `robot-md revoke-key` |
| `robot-md/cli/src/robot_md/verify_tier.py` | CLI `robot-md verify-tier` |
| `robot-md/cli/tests/test_rotate_key.py` | CLI rotation tests |
| `robot-md/cli/tests/test_revoke_key.py` | CLI revocation tests |
| `robot-md/cli/tests/test_verify_tier.py` | CLI promotion tests |

### Modified files

| Path | Change |
|---|---|
| `RobotRegistryFoundation/functions/v2/_lib/compliance-auth.ts` | `verifyComplianceBody` calls `isRevoked` before accepting |
| `RobotRegistryFoundation/functions/v2/robots/[rrn]/index.ts` | PATCH checks `isRevoked`; GET surfaces `revoked` + `verification_status` |
| `RobotRegistryFoundation/functions/v2/robots/register.ts` | Defaults `verification_status: "unverified"` on mint |
| `RobotRegistryFoundation/functions/v2/_lib/types.ts` (or wherever `RobotRecord` is) | Add `verification_status`, `identity_binding`, `revoked_at`, `rotations` fields |
| `robot-md/cli/src/robot_md/cli.py` | Register subcommands |

---

## Data-Model Delta

Add these fields to `RobotRecord` (KV value at `robot:<rrn>`):

```ts
interface RobotRecord {
  // ...existing fields...
  verification_status: "unverified" | "community" | "manufacturer_claimed" | "manufacturer_verified";
  identity_binding?: {
    type: "dns-txt" | "github-org" | "manufacturer-cert";
    value: string;         // domain, org slug, or cert fingerprint
    verified_at: string;   // ISO 8601
    verifier_evidence?: string;  // raw TXT record, attestation digest, etc.
  };
  revoked_at?: string;     // ISO 8601, presence means revoked
  rotations?: Array<{
    rotated_at: string;
    old_pq_kid: string;
    new_pq_kid: string;
  }>;
}
```

Migration: no backfill. Existing records are read with the new shape; missing fields are treated as `verification_status: "unverified"` and `revoked_at: undefined`.

KV keys:
- `robot:<rrn>` — the RobotRecord (existing)
- `revocation:<rrn>` — presence means revoked; value is `{revoked_at, reason}`

---

### Task 1: Revocation helper + tests

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/_lib/revocation.ts`
- Create: `RobotRegistryFoundation/functions/v2/_lib/revocation.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// functions/v2/_lib/revocation.test.ts
import { describe, it, expect, vi } from "vitest";
import { isRevoked, markRevoked } from "./revocation.js";

const RRN = "RRN-000000000042";

function makeEnv() {
  const store: Record<string, string> = {};
  return {
    RRF_KV: {
      get: vi.fn(async (k: string) => store[k] ?? null),
      put: vi.fn(async (k: string, v: string) => { store[k] = v; }),
      delete: vi.fn(async (k: string) => { delete store[k]; }),
      list: vi.fn(),
    } as unknown as KVNamespace,
    __store: store,
  };
}

describe("revocation helper", () => {
  it("isRevoked returns false when no revocation entry", async () => {
    const env = makeEnv();
    expect(await isRevoked(env, RRN)).toBe(false);
  });

  it("markRevoked writes a revocation entry that isRevoked observes", async () => {
    const env = makeEnv();
    await markRevoked(env, RRN, "operator request");
    expect(await isRevoked(env, RRN)).toBe(true);
    const raw = JSON.parse(env.__store[`revocation:${RRN}`]);
    expect(raw.reason).toBe("operator request");
    expect(raw.revoked_at).toBeTypeOf("string");
  });

  it("isRevoked tolerates malformed revocation blobs (treat as revoked)", async () => {
    const env = makeEnv();
    env.__store[`revocation:${RRN}`] = "not-json";
    expect(await isRevoked(env, RRN)).toBe(true);
  });
});
```

- [ ] **Step 2: Verify RED**

```bash
cd ~/RobotRegistryFoundation
npm test -- functions/v2/_lib/revocation.test.ts
```

Expected: 3 failures, all `Cannot find module './revocation.js'`.

- [ ] **Step 3: Implement the helper**

```ts
// functions/v2/_lib/revocation.ts
export interface RevocationEnv { RRF_KV: KVNamespace }

export async function isRevoked(env: RevocationEnv, rrn: string): Promise<boolean> {
  const raw = await env.RRF_KV.get(`revocation:${rrn}`, "text");
  return raw !== null;  // presence = revoked, regardless of content parseability
}

export async function markRevoked(env: RevocationEnv, rrn: string, reason: string): Promise<void> {
  const entry = { revoked_at: new Date().toISOString(), reason };
  await env.RRF_KV.put(`revocation:${rrn}`, JSON.stringify(entry));
}
```

- [ ] **Step 4: Verify GREEN**

```bash
npm test -- functions/v2/_lib/revocation.test.ts
```

Expected: 3/3 pass.

- [ ] **Step 5: Commit**

```bash
git add functions/v2/_lib/revocation.ts functions/v2/_lib/revocation.test.ts
git commit -m "feat(rrf): add revocation KV helper"
```

---

### Task 2: Wire `isRevoked` into `verifyComplianceBody`

**Files:**
- Modify: `RobotRegistryFoundation/functions/v2/_lib/compliance-auth.ts`
- Modify: `RobotRegistryFoundation/functions/v2/_lib/compliance-auth.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `compliance-auth.test.ts`:

```ts
it("rejects submission when entity is revoked (403)", async () => {
  const kp = await makeTestKeypair();
  const env = makeEnv({
    [`robot:${RRN}`]: makeRobotRecord(RRN, kp),
    [`revocation:${RRN}`]: JSON.stringify({ revoked_at: "2026-04-24T00:00:00Z", reason: "test" }),
  });
  const doc = { schema: "rcan-fria-v1", rrn: RRN, generated_at: "x" };
  const signed = await signComplianceBody(doc, kp);
  const result = await verifyComplianceBody(signed, env, `robot:${RRN}`);
  expect(result.ok).toBe(false);
  if (!result.ok) expect(result.status).toBe(403);
});
```

(Use the same `makeEnv` / `makeTestKeypair` / `makeRobotRecord` / `signComplianceBody` helpers already in `_lib/test-helpers.ts`.)

- [ ] **Step 2: Verify RED**

```bash
npm test -- functions/v2/_lib/compliance-auth.test.ts
```

Expected: 1 failure — test expects 403 but gets 200 (verify passes without revocation check).

- [ ] **Step 3: Modify `compliance-auth.ts`**

Add at top:
```ts
import { isRevoked } from "./revocation.js";
```

In `verifyComplianceBody`, directly after the `stored = await env.RRF_KV.get(entityKey, ...)` lookup and the `stored ? ... : 401`, insert:
```ts
const rrnMatch = entityKey.match(/^robot:(RRN-\d{12})$/);
if (rrnMatch && await isRevoked(env, rrnMatch[1])) {
  return { ok: false, status: 403, error: "Entity key is revoked" };
}
```

- [ ] **Step 4: Verify GREEN**

```bash
npm test -- functions/v2/_lib/compliance-auth.test.ts
npm test    # full suite — make sure no regressions on fria, ifu, safety-benchmark, incident-report, eu-register
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add functions/v2/_lib/compliance-auth.ts functions/v2/_lib/compliance-auth.test.ts
git commit -m "feat(rrf): refuse compliance submissions for revoked entities"
```

---

### Task 3: `POST /v2/robots/:rrn/revoke-key`

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/revoke-key.ts`
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/revoke-key.test.ts`

**Contract:**
- Request: `POST` with body `{sig, pq_kid, reason?: string}` signed over `{rrn, action: "revoke", reason}` with the *current* key.
- Auth: signature must verify against the record's current `pq_signing_pub`. No Bearer token — proof of key possession is the authorization.
- On success: writes `revocation:<rrn>`, returns 204.
- On revoked-already: 409.

- [ ] **Step 1: Write the failing tests**

```ts
// revoke-key.test.ts
import { describe, it, expect, vi } from "vitest";
import { onRequestPost } from "./revoke-key.js";
import { makeTestKeypair, makeRobotRecord, signBody } from "../../_lib/test-helpers.js";

const RRN = "RRN-000000000042";

function makeEnv(init: Record<string, string> = {}) {
  const store: Record<string, string> = { ...init };
  return {
    RRF_KV: {
      get: vi.fn(async (k: string) => store[k] ?? null),
      put: vi.fn(async (k: string, v: string) => { store[k] = v; }),
      delete: vi.fn(async (k: string) => { delete store[k]; }),
      list: vi.fn(),
    } as unknown as KVNamespace,
    __store: store,
  };
}

function req(body: unknown): Request {
  return new Request(`https://x/v2/robots/${RRN}/revoke-key`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /v2/robots/[rrn]/revoke-key", () => {
  it("404 when record does not exist", async () => {
    const env = makeEnv();
    const res = await onRequestPost({ request: req({}), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(404);
  });

  it("revokes with valid signature (204) and writes revocation entry", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signBody({ rrn: RRN, action: "revoke", reason: "lost laptop" }, kp);
    const res = await onRequestPost({ request: req(signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(204);
    const rev = JSON.parse(env.__store[`revocation:${RRN}`]);
    expect(rev.reason).toBe("lost laptop");
  });

  it("rejects signature with wrong key (401)", async () => {
    const kp1 = await makeTestKeypair();
    const kp2 = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp1) });
    const signed = await signBody({ rrn: RRN, action: "revoke" }, kp2);
    const res = await onRequestPost({ request: req(signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("rejects tampered body (401)", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signBody({ rrn: RRN, action: "revoke" }, kp);
    const tampered = { ...signed, action: "keep" };
    const res = await onRequestPost({ request: req(tampered), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("409 when already revoked", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({
      [`robot:${RRN}`]: makeRobotRecord(RRN, kp),
      [`revocation:${RRN}`]: JSON.stringify({ revoked_at: "2026-04-24T00:00:00Z", reason: "first" }),
    });
    const signed = await signBody({ rrn: RRN, action: "revoke" }, kp);
    const res = await onRequestPost({ request: req(signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(409);
  });

  it("400 on invalid RRN format", async () => {
    const env = makeEnv();
    const res = await onRequestPost({ request: req({}), env, params: { rrn: "bad" } } as any);
    expect(res.status).toBe(400);
  });
});
```

Note: this requires a `signBody` helper in `test-helpers.ts` that wraps `signComplianceBody` without the schema-specific envelope. If `signComplianceBody` already works for arbitrary shapes, reuse it and rename the test import.

- [ ] **Step 2: Verify RED**

```bash
npm test -- functions/v2/robots/\[rrn\]/revoke-key.test.ts
```

Expected: 6 failures, all `Cannot find module './revoke-key.js'`.

- [ ] **Step 3: Implement `revoke-key.ts`**

```ts
// functions/v2/robots/[rrn]/revoke-key.ts
import { isValidId } from "../../_lib/id.js";
import { verifyBody } from "rcan-ts";
import { isRevoked, markRevoked } from "../../_lib/revocation.js";

export interface Env { RRF_KV: KVNamespace }

function err(msg: string, status: number): Response {
  return new Response(JSON.stringify({ error: msg }), {
    status, headers: { "Content-Type": "application/json" },
  });
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env, params }) => {
  const rrn = params.rrn as string;
  if (!isValidId(rrn, "RRN")) return err("Invalid RRN format", 400);

  let body: Record<string, unknown>;
  try { body = await request.json() as Record<string, unknown>; }
  catch { return err("Invalid JSON body", 400); }

  const stored = await env.RRF_KV.get(`robot:${rrn}`, "text");
  if (!stored) return err("Not found", 404);
  const record = JSON.parse(stored);

  const pqPubB64 = record.pq_signing_pub;
  if (typeof pqPubB64 !== "string") return err("Record has no registered key", 400);

  if (body.rrn !== rrn || body.action !== "revoke") {
    return err("Body must bind rrn and action:revoke", 400);
  }

  if (await isRevoked(env, rrn)) return err("Already revoked", 409);

  let verified = false;
  try {
    const pqPub = Uint8Array.from(atob(pqPubB64), c => c.charCodeAt(0));
    verified = await verifyBody(body, pqPub);
  } catch { /* verified stays false */ }
  if (!verified) return err("Signature verification failed", 401);

  const reason = typeof body.reason === "string" ? body.reason : "unspecified";
  await markRevoked(env, rrn, reason);
  return new Response(null, { status: 204 });
};
```

- [ ] **Step 4: Verify GREEN**

```bash
npm test -- functions/v2/robots/\[rrn\]/revoke-key.test.ts
```

Expected: 6/6 pass.

- [ ] **Step 5: Commit**

```bash
git add functions/v2/robots/\[rrn\]/revoke-key.ts functions/v2/robots/\[rrn\]/revoke-key.test.ts
git commit -m "feat(rrf): add POST /v2/robots/:rrn/revoke-key"
```

---

### Task 4: `POST /v2/robots/:rrn/rotate-key`

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/rotate-key.ts`
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/rotate-key.test.ts`

**Contract:**
- Request: body is a *co-signed* envelope: `{old_sig, old_pq_kid, new_pq_signing_pub, new_pq_kid, new_sig}` where `old_sig` is the current key signing `{rrn, action: "rotate", new_pq_signing_pub, new_pq_kid}` and `new_sig` is the new key signing the same payload.
- Auth: `old_sig` must verify against the record's current `pq_signing_pub`; `new_sig` must verify against `new_pq_signing_pub` (proves possession of the new private key).
- On success: updates the record's `pq_signing_pub`/`pq_kid`, appends to `rotations[]`, returns 200 with the updated record.
- Refuse if revoked (403).

Full tests + implementation follow the same structure as Task 3. Edge cases to cover:
1. Happy path (old+new both verify, record updates).
2. `old_sig` invalid → 401.
3. `new_sig` invalid → 401.
4. New key equals old key → 400 ("rotation requires a different key").
5. Revoked record → 403.
6. Missing fields → 400.
7. `rotations[]` is appended (not overwritten) across multiple rotations.

Implementation note: use the same `verifyBody` helper for both signatures. Structure the payload as `{rrn, action, new_pq_signing_pub, new_pq_kid}` for both signatures — co-signing the same bytes is cleaner than two separate payloads.

Commit message:
```
feat(rrf): add POST /v2/robots/:rrn/rotate-key (co-signed by old+new)
```

---

### Task 5: Update `PATCH /v2/robots/:rrn` and `GET` to respect revocation

**Files:**
- Modify: `RobotRegistryFoundation/functions/v2/robots/[rrn]/index.ts`
- Modify: `RobotRegistryFoundation/functions/v2/robots/[rrn]/index.test.ts`

- [ ] **Step 1: Write failing tests**

Add to `index.test.ts`:
```ts
it("PATCH returns 403 when record is revoked", async () => {
  const env = makeEnv();
  env.__store[`revocation:${RRN}`] = JSON.stringify({ revoked_at: "2026-04-24T00:00:00Z", reason: "test" });
  const res = await onRequestPatch({
    request: makePatchRequest(STUB_PATCH_BODY),
    env, params: { rrn: RRN },
  } as any);
  expect(res.status).toBe(403);
});

it("GET surfaces revoked flag", async () => {
  const env = makeEnv();
  env.__store[`revocation:${RRN}`] = JSON.stringify({ revoked_at: "2026-04-24T00:00:00Z", reason: "test" });
  const res = await onRequestGet({ env, params: { rrn: RRN } } as any);
  expect(res.status).toBe(200);
  const json = await res.json();
  expect(json.revoked).toBe(true);
  expect(json.revoked_at).toBe("2026-04-24T00:00:00Z");
});
```

- [ ] **Step 2: Verify RED**

```bash
npm test -- functions/v2/robots/\[rrn\]/index.test.ts
```

- [ ] **Step 3: Modify `index.ts`**

In `onRequestPatch`, after loading the record and before the existing logic, add:
```ts
import { isRevoked } from "../../_lib/revocation.js";
// ...
if (await isRevoked(env, rrn)) return err("Record is revoked", 403);
```

In `onRequestGet`, after loading the raw record:
```ts
const parsed = JSON.parse(stored);
const revRaw = await env.RRF_KV.get(`revocation:${rrn}`, "text");
if (revRaw) {
  try {
    const rev = JSON.parse(revRaw);
    parsed.revoked = true;
    parsed.revoked_at = rev.revoked_at;
  } catch { parsed.revoked = true; }
}
return new Response(JSON.stringify(parsed), { headers: { ... } });
```
(Drop the existing `return new Response(stored, ...)` optimization; re-serializing is fine for this small payload and lets us merge the revoked flag.)

- [ ] **Step 4: Verify GREEN**

```bash
npm test    # full suite
```

- [ ] **Step 5: Commit**

```bash
git add functions/v2/robots/\[rrn\]/index.ts functions/v2/robots/\[rrn\]/index.test.ts
git commit -m "feat(rrf): PATCH refuses revoked; GET surfaces revocation"
```

---

### Task 6: DNS-TXT verifier

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/_lib/dns-verify.ts`
- Create: `RobotRegistryFoundation/functions/v2/_lib/dns-verify.test.ts`

**Contract:** `verifyDnsTxt(domain, expectedRrn, expectedModel, fetchFn?): Promise<{ok: true, evidence: string} | {ok: false, error: string}>`.

Looks up `_rcan-verify.<domain>` via Cloudflare DoH (`https://cloudflare-dns.com/dns-query?name=_rcan-verify.<domain>&type=TXT`, `Accept: application/dns-json`). Expects a TXT record string `rrn=<rrn>;model=<model>` (format defined in `rcan-spec/docs/verification/manufacturer-verification.md`). Returns the raw record as `evidence`.

- [ ] **Step 1: Tests — mock `fetch` for DoH, assert**
  - valid TXT → ok + evidence.
  - TXT missing → error.
  - TXT wrong rrn → error.
  - TXT wrong model → error.
  - DoH 5xx / network error → error (never throw).
  - Multiple TXT records, one matches → ok.
  - Domain with subdomain injection (e.g. `evil.com.\nattacker.com`) → rejected.

- [ ] **Step 2: Verify RED.**

- [ ] **Step 3: Implement.** Use `fetch` injected via optional second arg (default: global `fetch`). Parse `application/dns-json`. Iterate `Answer[].data` stripping quotes.

- [ ] **Step 4: Verify GREEN.**

- [ ] **Step 5: Commit.** `feat(rrf): add DNS TXT verifier for manufacturer_claimed tier`

---

### Task 7: Attestation + RURI verifier

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/_lib/attestation-verify.ts`
- Create: `RobotRegistryFoundation/functions/v2/_lib/attestation-verify.test.ts`

**Contract:** `verifyAttestation({attestation, ruri, pqPubBytes, expectedRrn}): Promise<{ok: true} | {ok: false, error: string}>`.

Checks:
1. Attestation JSON schema (per `rcan-spec/docs/verification/manufacturer-verification.md`) — `rrn`, `manufacturer`, `model`, `timestamp_iso`, `signature`.
2. Signature over canonical attestation body verifies against `pqPubBytes` using `rcan-ts verifyBody`.
3. `fetch(ruri + "/.well-known/rcan-manifest.json")` returns 200 and JSON with matching `rrn`.

Tests should include: tampered attestation, expired timestamp (> 1 year), missing manifest, manifest mismatched rrn, network error. Inject `fetchFn` for testing.

Commit: `feat(rrf): add signed-attestation + RURI verifier`

---

### Task 8: `POST /v2/robots/:rrn/verify-tier`

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/verify-tier.ts`
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/verify-tier.test.ts`

**Contract:**
- Request body: `{target_tier, binding, sig, pq_kid}` where `binding` is `{type, value}` and `sig` is over `{rrn, action: "verify-tier", target_tier, binding}`.
- Server dispatches on `target_tier`:
  - `"community"` — no external verification. Requires signature and at least one `attestations[]` entry in request (future work; for now accept `attestations: []` but flag as TODO in impl).
  - `"manufacturer_claimed"` — `binding.type` MUST be `"dns-txt"`; calls `verifyDnsTxt(binding.value, rrn, record.model)`.
  - `"manufacturer_verified"` — binding must also include `attestation` + `ruri`; calls `verifyAttestation(...)`.
- On success: updates `record.verification_status` and `record.identity_binding`, returns 200.
- On revoked: 403. On verifier failure: 400 with reason.

Seven tests minimum: happy path each tier, DNS failure, attestation failure, downgrade attempt (reject), revoked record, missing fields, bad signature.

Commit: `feat(rrf): add POST /v2/robots/:rrn/verify-tier`

---

### Task 9: Default `verification_status: "unverified"` on register

**Files:**
- Modify: `RobotRegistryFoundation/functions/v2/robots/register.ts`
- Modify: `RobotRegistryFoundation/functions/v2/robots/register.test.ts`

- [ ] **Step 1: Test** — after register, `GET /v2/robots/:rrn` returns `verification_status: "unverified"`.

- [ ] **Step 2: Verify RED** (current code does not set the field).

- [ ] **Step 3: Implement** — in the register handler's record-mint block, add `verification_status: "unverified"`.

- [ ] **Step 4: Verify GREEN.**

- [ ] **Step 5: Commit.** `feat(rrf): default verification_status to unverified on register`

---

### Task 10: CLI — `robot-md revoke-key`

**Files:**
- Create: `robot-md/cli/src/robot_md/revoke_key.py`
- Create: `robot-md/cli/tests/test_revoke_key.py`
- Modify: `robot-md/cli/src/robot_md/cli.py` (wire subcommand)

**Contract:**
```
robot-md revoke-key <rrn> [--reason TEXT] [--endpoint URL]
```

Loads `~/.robot-md/keys/<rrn>.signing.json`, builds a `{rrn, action: "revoke", reason}` payload, signs it, POSTs to `<endpoint>/v2/robots/<rrn>/revoke-key`. On 204 prints `Revoked: <rrn>`. On 409 prints `Already revoked: <rrn>` (exit 0). On other errors, prints and exits non-zero.

Tests mock `urllib.request.urlopen` (same pattern used by existing CLI tests) for each status.

Commit: `feat(cli): add robot-md revoke-key`

---

### Task 11: CLI — `robot-md rotate-key`

**Files:**
- Create: `robot-md/cli/src/robot_md/rotate_key.py`
- Create: `robot-md/cli/tests/test_rotate_key.py`
- Modify: `robot-md/cli/src/robot_md/cli.py`

**Contract:**
```
robot-md rotate-key <rrn> [--endpoint URL]
```

Generates a new ML-DSA + Ed25519 keypair, builds a `{rrn, action: "rotate", new_pq_signing_pub, new_pq_kid}` payload, signs it twice (with the old key and with the new key), POSTs. On 200, atomically replaces `~/.robot-md/keys/<rrn>.signing.json` (write-to-tmp-then-rename) and updates `~/.robot-md/keys/<rrn>.apikey` if server returns a new one. On failure, does NOT touch the on-disk key.

Tests cover: happy path, network error (on-disk key untouched), server returns 401 (same).

Commit: `feat(cli): add robot-md rotate-key`

---

### Task 12: CLI — `robot-md verify-tier`

**Files:**
- Create: `robot-md/cli/src/robot_md/verify_tier.py`
- Create: `robot-md/cli/tests/test_verify_tier.py`
- Modify: `robot-md/cli/src/robot_md/cli.py`

**Contract:**
```
robot-md verify-tier <rrn> --target {community|manufacturer_claimed|manufacturer_verified} [options]
  --dns-domain DOMAIN           # for manufacturer_claimed
  --attestation-file PATH       # for manufacturer_verified
  --ruri URI                    # for manufacturer_verified
  --endpoint URL
```

Builds the signed body per Task 8, POSTs, prints resulting `verification_status`. Pre-flight: if `--target manufacturer_claimed`, print instructions for the TXT record and ask the user to press Enter to continue (zero-friction reminder: higher-tier promotion is a deliberate, user-initiated action).

Commit: `feat(cli): add robot-md verify-tier`

---

### Task 13: Integration smoke test (staging RRF)

**Files:**
- Create: `robot-md/cli/tests/integration/test_rotate_revoke_verify_roundtrip.py`

Manual / opt-in integration test (skipped in CI unless `ROBOT_MD_RRF_STAGING` env var set). Registers a throwaway robot, rotates its key, revokes it, confirms subsequent compliance POST fails with 403. Tests against `https://staging.robotregistryfoundation.org` (or the `--endpoint` supplied).

Commit: `test(cli): staging integration test for rotate/revoke/verify`

---

### Task 14: Documentation update

**Files:**
- Modify: `rcan-spec/docs/verification/manufacturer-verification.md` — add note that DNS TXT is now server-enforced (was previously "registry will perform a DNS lookup" aspirational)
- Modify: `RobotRegistryFoundation/src/pages/api/index.astro` — add the three new endpoints to the API docs
- Modify: `RobotRegistryFoundation/CLAUDE.md` — note `verification_status` default on register

Commit: `docs: document rotate/revoke/verify-tier endpoints`

---

## Self-Review Checklist

- [ ] Every spec requirement has a task (revocation, rotation, DNS, attestation, tier default, CLI parity — covered by Tasks 1–12).
- [ ] No placeholders — each code step has full code.
- [ ] Type consistency — `RobotRecord` fields used in Task 5, 8, 9 match the Data-Model Delta section.
- [ ] Function names consistent: `isRevoked`, `markRevoked`, `verifyDnsTxt`, `verifyAttestation`, `verifyComplianceBody`.
- [ ] TDD strict — every task starts with a failing test.

## Open questions for operator sign-off before execution

1. **Rotation envelope shape** — co-signed single payload (`{old_sig, new_sig}` over same bytes) vs nested envelope (new sig over `{old_sig, new_pub}`). Plan assumes co-signed. Confirm OK.
2. **CLI key backup** — on `rotate-key`, should the OLD key be archived to `~/.robot-md/keys/archive/<rrn>.<kid>.signing.json` so an operator who lost trust in the new key can still revoke using the old? Plan assumes YES (belt-and-suspenders). Confirm.
3. **DNS verifier TTL** — should successful DNS verification be re-checked after N days, or is it one-shot? Plan assumes one-shot (evidence stored at `verified_at`); re-verification is a future task. Confirm.
4. **`community` tier logic** — left as TODO in Task 8. Is per-PR attestation collection still the intended path, or is this tier going away in favor of `unverified → manufacturer_claimed`? Clarify before Task 8.

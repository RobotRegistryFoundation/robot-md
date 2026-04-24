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

**Contract:** co-signed single payload. Both `old_sig` and `new_sig` cover the same canonical body `{rrn, action: "rotate", new_pq_signing_pub, new_pq_kid}`. `old_sig` verifies against `record.pq_signing_pub`; `new_sig` verifies against `new_pq_signing_pub`. On success: replace `pq_signing_pub`/`pq_kid`, append to `rotations[]`, return 200. Refuse if revoked (403), new==old key (400), missing fields (400), either sig invalid (401).

**Known limitation:** Cloudflare Workers KV has no CAS primitive in this project's setup, so two concurrent rotate requests can both read the current key, both verify, and both write — last-write-wins. Mitigated by: rotations are rare, user-initiated events; the `rotations[]` audit log will show the collision post-facto; optimistic versioning is deferred to a later revision.

- [ ] **Step 1: Write the failing tests**

```ts
// functions/v2/robots/[rrn]/rotate-key.test.ts
import { describe, it, expect, vi } from "vitest";
import { onRequestPost } from "./rotate-key.js";
import { makeTestKeypair, makeRobotRecord, signBody, toPqPubB64 } from "../../_lib/test-helpers.js";

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
  return new Request(`https://x/v2/robots/${RRN}/rotate-key`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function buildRotateBody(currentKp: any, newKp: any) {
  const payload = {
    rrn: RRN,
    action: "rotate",
    new_pq_signing_pub: toPqPubB64(newKp),
    new_pq_kid: newKp.pq_kid,
  };
  const oldSigned = await signBody(payload, currentKp);
  const newSigned = await signBody(payload, newKp);
  return {
    ...payload,
    old_sig: oldSigned.sig,
    old_pq_kid: currentKp.pq_kid,
    new_sig: newSigned.sig,
  };
}

describe("POST /v2/robots/[rrn]/rotate-key", () => {
  it("400 on invalid RRN format", async () => {
    const env = makeEnv();
    const res = await onRequestPost({ request: req({}), env, params: { rrn: "bad" } } as any);
    expect(res.status).toBe(400);
  });

  it("404 when record does not exist", async () => {
    const oldKp = await makeTestKeypair();
    const newKp = await makeTestKeypair();
    const env = makeEnv();
    const body = await buildRotateBody(oldKp, newKp);
    const res = await onRequestPost({ request: req(body), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(404);
  });

  it("rotates with valid old+new sigs (200), appends rotations[], updates record", async () => {
    const oldKp = await makeTestKeypair();
    const newKp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, oldKp) });
    const body = await buildRotateBody(oldKp, newKp);
    const res = await onRequestPost({ request: req(body), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(200);
    const updated = await res.json();
    expect(updated.pq_signing_pub).toBe(toPqPubB64(newKp));
    expect(updated.pq_kid).toBe(newKp.pq_kid);
    expect(updated.rotations).toHaveLength(1);
    expect(updated.rotations[0].old_pq_kid).toBe(oldKp.pq_kid);
    expect(updated.rotations[0].new_pq_kid).toBe(newKp.pq_kid);
  });

  it("appends (not overwrites) rotations[] across multiple rotations", async () => {
    const k0 = await makeTestKeypair();
    const k1 = await makeTestKeypair();
    const k2 = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, k0) });
    await onRequestPost({ request: req(await buildRotateBody(k0, k1)), env, params: { rrn: RRN } } as any);
    await onRequestPost({ request: req(await buildRotateBody(k1, k2)), env, params: { rrn: RRN } } as any);
    const final = JSON.parse(env.__store[`robot:${RRN}`]);
    expect(final.rotations).toHaveLength(2);
    expect(final.pq_kid).toBe(k2.pq_kid);
  });

  it("401 when old_sig is invalid (signed by a non-current key)", async () => {
    const currentKp = await makeTestKeypair();
    const attackerKp = await makeTestKeypair();
    const newKp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, currentKp) });
    const body = await buildRotateBody(attackerKp, newKp);  // old_sig from attacker
    const res = await onRequestPost({ request: req(body), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("401 when new_sig is invalid (new key does not own the new_pq_signing_pub)", async () => {
    const oldKp = await makeTestKeypair();
    const newKp = await makeTestKeypair();
    const otherKp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, oldKp) });
    const body = await buildRotateBody(oldKp, newKp);
    // Swap new_sig for a sig from otherKp over the same payload — new_pq_signing_pub is still newKp.
    const payload = { rrn: RRN, action: "rotate", new_pq_signing_pub: body.new_pq_signing_pub, new_pq_kid: body.new_pq_kid };
    body.new_sig = (await signBody(payload, otherKp)).sig;
    const res = await onRequestPost({ request: req(body), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("400 when new key equals old key", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const body = await buildRotateBody(kp, kp);
    const res = await onRequestPost({ request: req(body), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });

  it("403 when record is revoked", async () => {
    const oldKp = await makeTestKeypair();
    const newKp = await makeTestKeypair();
    const env = makeEnv({
      [`robot:${RRN}`]: makeRobotRecord(RRN, oldKp),
      [`revocation:${RRN}`]: JSON.stringify({ revoked_at: "2026-04-24T00:00:00Z", reason: "test" }),
    });
    const body = await buildRotateBody(oldKp, newKp);
    const res = await onRequestPost({ request: req(body), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(403);
  });

  it("400 when body is missing required fields", async () => {
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, await makeTestKeypair()) });
    const res = await onRequestPost({ request: req({ rrn: RRN }), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });
});
```

- [ ] **Step 2: Verify RED**

```bash
npm test -- functions/v2/robots/\[rrn\]/rotate-key.test.ts
```

Expected: 9 failures, all `Cannot find module './rotate-key.js'`.

- [ ] **Step 3: Implement `rotate-key.ts`**

```ts
// functions/v2/robots/[rrn]/rotate-key.ts
import { isValidId } from "../../_lib/id.js";
import { verifyBody } from "rcan-ts";
import { isRevoked } from "../../_lib/revocation.js";

export interface Env { RRF_KV: KVNamespace }

function err(msg: string, status: number): Response {
  return new Response(JSON.stringify({ error: msg }), {
    status, headers: { "Content-Type": "application/json" },
  });
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env, params }) => {
  const rrn = params.rrn as string;
  if (!isValidId(rrn, "RRN")) return err("Invalid RRN format", 400);

  let body: any;
  try { body = await request.json(); }
  catch { return err("Invalid JSON body", 400); }

  const { new_pq_signing_pub, new_pq_kid, old_sig, old_pq_kid, new_sig } = body ?? {};
  if (typeof new_pq_signing_pub !== "string" || typeof new_pq_kid !== "string"
      || typeof old_pq_kid !== "string"
      || !old_sig?.ml_dsa || !old_sig?.ed25519 || !old_sig?.ed25519_pub
      || !new_sig?.ml_dsa || !new_sig?.ed25519 || !new_sig?.ed25519_pub) {
    return err("Missing required fields (new_pq_signing_pub, new_pq_kid, old_pq_kid, old_sig, new_sig)", 400);
  }
  if (body.rrn !== rrn || body.action !== "rotate") {
    return err("Body must bind rrn and action:rotate", 400);
  }

  const stored = await env.RRF_KV.get(`robot:${rrn}`, "text");
  if (!stored) return err("Not found", 404);
  const record = JSON.parse(stored);

  if (await isRevoked(env, rrn)) return err("Record is revoked", 403);

  const currentPubB64 = record.pq_signing_pub;
  if (typeof currentPubB64 !== "string") return err("Record has no registered key", 400);
  if (currentPubB64 === new_pq_signing_pub) return err("Rotation requires a different key", 400);

  const canonical = { rrn, action: "rotate", new_pq_signing_pub, new_pq_kid };

  async function verify(pubB64: string, sig: any): Promise<boolean> {
    try {
      const pub = Uint8Array.from(atob(pubB64), c => c.charCodeAt(0));
      return await verifyBody({ ...canonical, sig, pq_kid: "ignored" }, pub);
    } catch { return false; }
  }

  if (!(await verify(currentPubB64, old_sig))) return err("old_sig verification failed", 401);
  if (!(await verify(new_pq_signing_pub, new_sig))) return err("new_sig verification failed", 401);

  const now = new Date().toISOString();
  record.rotations = Array.isArray(record.rotations) ? record.rotations : [];
  record.rotations.push({ rotated_at: now, old_pq_kid: record.pq_kid, new_pq_kid });
  record.pq_signing_pub = new_pq_signing_pub;
  record.pq_kid = new_pq_kid;
  record.updated_at = now;
  await env.RRF_KV.put(`robot:${rrn}`, JSON.stringify(record));
  return new Response(JSON.stringify(record), {
    status: 200, headers: { "Content-Type": "application/json" },
  });
};
```

Note: `verifyBody` in rcan-ts expects a body that looks like `{...canonical, sig, pq_kid}`. We pass a synthetic `pq_kid: "ignored"` because verifyBody signs over everything except `sig` — `pq_kid` is present in the canonical form but does not participate in sig comparison logic beyond being part of the signed bytes. If rcan-ts's exact canonical shape requires `pq_kid` to match one specific value, adapt this to pass `old_pq_kid` / `new_pq_kid` respectively.

- [ ] **Step 4: Verify GREEN**

```bash
npm test -- functions/v2/robots/\[rrn\]/rotate-key.test.ts
npm test    # full suite, watch for regressions
```

Expected: 9/9 pass plus full suite green.

- [ ] **Step 5: Commit**

```bash
git add functions/v2/robots/\[rrn\]/rotate-key.ts functions/v2/robots/\[rrn\]/rotate-key.test.ts
git commit -m "feat(rrf): add POST /v2/robots/:rrn/rotate-key (co-signed by old+new)"
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

**Contract:**
```ts
interface VerifyAttestationInput {
  attestation: {
    rrn: string;
    manufacturer: string;
    model: string;
    timestamp_iso: string;
    sig: { ml_dsa: string; ed25519: string; ed25519_pub: string };
    pq_kid: string;
  };
  ruri: string;           // e.g. "https://robotis.com"
  pqPubB64: string;       // robot's registered pq_signing_pub (from RobotRecord)
  expectedRrn: string;    // RRN from the URL path being verified
  expectedModel: string;  // record.model, to cross-check attestation
  fetchFn?: typeof fetch;
  nowMs?: number;         // injectable for time-based tests
}

type VerifyAttestationResult =
  | { ok: true; evidence: { attestation_digest: string; ruri_matched: string } }
  | { ok: false; error: string };

export async function verifyAttestation(input: VerifyAttestationInput): Promise<VerifyAttestationResult>;
```

- [ ] **Step 1: Write the failing tests**

```ts
// attestation-verify.test.ts
import { describe, it, expect, vi } from "vitest";
import { verifyAttestation } from "./attestation-verify.js";
import { makeTestKeypair, signBody, toPqPubB64 } from "./test-helpers.js";

const RRN = "RRN-000000000042";
const MODEL = "turtlebot3_burger";

async function buildAttestation(kp: any, overrides: Record<string, unknown> = {}) {
  const body = {
    rrn: RRN,
    manufacturer: "ROBOTIS",
    model: MODEL,
    timestamp_iso: "2026-04-24T12:00:00Z",
    ...overrides,
  };
  return await signBody(body, kp);
}

function okManifestFetch(rrn: string) {
  return vi.fn(async () => new Response(JSON.stringify({ rrn }), { status: 200 }));
}

describe("verifyAttestation", () => {
  it("accepts a valid attestation + matching RURI manifest", async () => {
    const kp = await makeTestKeypair();
    const attestation = await buildAttestation(kp);
    const res = await verifyAttestation({
      attestation, ruri: "https://robotis.com", pqPubB64: toPqPubB64(kp),
      expectedRrn: RRN, expectedModel: MODEL,
      fetchFn: okManifestFetch(RRN),
      nowMs: Date.parse("2026-04-25T00:00:00Z"),
    });
    expect(res.ok).toBe(true);
  });

  it("rejects a tampered attestation (wrong sig)", async () => {
    const kp = await makeTestKeypair();
    const attestation = await buildAttestation(kp);
    attestation.manufacturer = "evil-inc";
    const res = await verifyAttestation({
      attestation, ruri: "https://robotis.com", pqPubB64: toPqPubB64(kp),
      expectedRrn: RRN, expectedModel: MODEL,
      fetchFn: okManifestFetch(RRN),
      nowMs: Date.parse("2026-04-25T00:00:00Z"),
    });
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error).toMatch(/sig/i);
  });

  it("rejects if attestation.rrn disagrees with expectedRrn", async () => {
    const kp = await makeTestKeypair();
    const attestation = await buildAttestation(kp, { rrn: "RRN-000000000999" });
    const res = await verifyAttestation({
      attestation, ruri: "https://robotis.com", pqPubB64: toPqPubB64(kp),
      expectedRrn: RRN, expectedModel: MODEL,
      fetchFn: okManifestFetch(RRN),
      nowMs: Date.parse("2026-04-25T00:00:00Z"),
    });
    expect(res.ok).toBe(false);
  });

  it("rejects if attestation.model disagrees with expectedModel", async () => {
    const kp = await makeTestKeypair();
    const attestation = await buildAttestation(kp, { model: "some-other-model" });
    const res = await verifyAttestation({
      attestation, ruri: "https://robotis.com", pqPubB64: toPqPubB64(kp),
      expectedRrn: RRN, expectedModel: MODEL,
      fetchFn: okManifestFetch(RRN),
      nowMs: Date.parse("2026-04-25T00:00:00Z"),
    });
    expect(res.ok).toBe(false);
  });

  it("rejects a timestamp > 1 year old", async () => {
    const kp = await makeTestKeypair();
    const attestation = await buildAttestation(kp, { timestamp_iso: "2024-01-01T00:00:00Z" });
    const res = await verifyAttestation({
      attestation, ruri: "https://robotis.com", pqPubB64: toPqPubB64(kp),
      expectedRrn: RRN, expectedModel: MODEL,
      fetchFn: okManifestFetch(RRN),
      nowMs: Date.parse("2026-04-25T00:00:00Z"),
    });
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error).toMatch(/expired|stale/i);
  });

  it("rejects if RURI manifest is unreachable", async () => {
    const kp = await makeTestKeypair();
    const attestation = await buildAttestation(kp);
    const res = await verifyAttestation({
      attestation, ruri: "https://robotis.com", pqPubB64: toPqPubB64(kp),
      expectedRrn: RRN, expectedModel: MODEL,
      fetchFn: vi.fn(async () => { throw new TypeError("fetch failed"); }),
      nowMs: Date.parse("2026-04-25T00:00:00Z"),
    });
    expect(res.ok).toBe(false);
  });

  it("rejects if RURI manifest's rrn does not match", async () => {
    const kp = await makeTestKeypair();
    const attestation = await buildAttestation(kp);
    const res = await verifyAttestation({
      attestation, ruri: "https://robotis.com", pqPubB64: toPqPubB64(kp),
      expectedRrn: RRN, expectedModel: MODEL,
      fetchFn: okManifestFetch("RRN-000000000999"),
      nowMs: Date.parse("2026-04-25T00:00:00Z"),
    });
    expect(res.ok).toBe(false);
  });

  it("rejects if RURI manifest returns non-200", async () => {
    const kp = await makeTestKeypair();
    const attestation = await buildAttestation(kp);
    const res = await verifyAttestation({
      attestation, ruri: "https://robotis.com", pqPubB64: toPqPubB64(kp),
      expectedRrn: RRN, expectedModel: MODEL,
      fetchFn: vi.fn(async () => new Response("", { status: 404 })),
      nowMs: Date.parse("2026-04-25T00:00:00Z"),
    });
    expect(res.ok).toBe(false);
  });
});
```

- [ ] **Step 2: Verify RED**

```bash
npm test -- functions/v2/_lib/attestation-verify.test.ts
```

Expected: 8 failures, all module-not-found.

- [ ] **Step 3: Implement `attestation-verify.ts`**

```ts
// functions/v2/_lib/attestation-verify.ts
import { verifyBody } from "rcan-ts";

const ONE_YEAR_MS = 365 * 24 * 3600 * 1000;

async function digestHex(bytes: Uint8Array): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function verifyAttestation(input: VerifyAttestationInput): Promise<VerifyAttestationResult> {
  const { attestation, ruri, pqPubB64, expectedRrn, expectedModel } = input;
  const fetchFn = input.fetchFn ?? fetch;
  const now = input.nowMs ?? Date.now();

  if (attestation.rrn !== expectedRrn) return { ok: false, error: "attestation rrn mismatch" };
  if (attestation.model !== expectedModel) return { ok: false, error: "attestation model mismatch" };

  const issued = Date.parse(attestation.timestamp_iso);
  if (!Number.isFinite(issued)) return { ok: false, error: "invalid timestamp_iso" };
  if (now - issued > ONE_YEAR_MS) return { ok: false, error: "attestation expired (> 1 year)" };
  if (issued - now > 60_000) return { ok: false, error: "attestation timestamp in the future" };

  let sigOk = false;
  try {
    const pub = Uint8Array.from(atob(pqPubB64), c => c.charCodeAt(0));
    sigOk = await verifyBody(attestation as unknown as Record<string, unknown>, pub);
  } catch { /* sigOk stays false */ }
  if (!sigOk) return { ok: false, error: "attestation sig verification failed" };

  const manifestUrl = ruri.replace(/\/+$/, "") + "/.well-known/rcan-manifest.json";
  let manifestBody: string;
  try {
    const res = await fetchFn(manifestUrl, { headers: { "Accept": "application/json" } });
    if (!res.ok) return { ok: false, error: `RURI manifest returned ${res.status}` };
    manifestBody = await res.text();
  } catch (e: any) {
    return { ok: false, error: `RURI unreachable: ${e?.message ?? "unknown"}` };
  }

  let manifest: { rrn?: unknown };
  try { manifest = JSON.parse(manifestBody); }
  catch { return { ok: false, error: "RURI manifest is not valid JSON" }; }
  if (manifest.rrn !== expectedRrn) return { ok: false, error: "RURI manifest rrn mismatch" };

  const canonicalBytes = new TextEncoder().encode(JSON.stringify({
    rrn: attestation.rrn, manufacturer: attestation.manufacturer,
    model: attestation.model, timestamp_iso: attestation.timestamp_iso,
  }));
  return {
    ok: true,
    evidence: { attestation_digest: await digestHex(canonicalBytes), ruri_matched: manifestUrl },
  };
}
```

- [ ] **Step 4: Verify GREEN**

```bash
npm test -- functions/v2/_lib/attestation-verify.test.ts
```

Expected: 8/8 pass.

- [ ] **Step 5: Commit**

```bash
git add functions/v2/_lib/attestation-verify.ts functions/v2/_lib/attestation-verify.test.ts
git commit -m "feat(rrf): add signed-attestation + RURI verifier"
```

---

### Task 8: `POST /v2/robots/:rrn/verify-tier`

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/verify-tier.ts`
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/verify-tier.test.ts`

**Scope decision:** Only `manufacturer_claimed` and `manufacturer_verified` are promotable via this endpoint. The `community` tier is maintainer-curated — it is set by a PR against `src/content/robots/<slug>.json`, not by an API call (see `rcan-spec/docs/verification/manufacturer-verification.md`). Attempts to POST `target_tier: "community"` return 400.

**Contract:**
- Request body: `{rrn, action: "verify-tier", target_tier, binding, ruri?, attestation?, sig, pq_kid}`.
  - `target_tier`: `"manufacturer_claimed" | "manufacturer_verified"`.
  - `binding`: `{type: "dns-txt", value: <domain>}` (only DNS TXT is accepted for `manufacturer_claimed`; `manufacturer_verified` requires DNS TXT AND a signed `attestation` + `ruri`).
  - `sig`: envelope signed by the robot's current `pq_signing_pub` over the canonical body (minus `sig`/`pq_kid`).
- Server checks (in order): RRN format, revocation, record exists, signature verifies, new tier > current tier (no downgrades), then dispatches on `target_tier`.
- On success: updates `record.verification_status` + `record.identity_binding`, returns 200 with updated record.

- [ ] **Step 1: Write the failing tests**

```ts
// verify-tier.test.ts
import { describe, it, expect, vi } from "vitest";
import { onRequestPost } from "./verify-tier.js";
import { makeTestKeypair, makeRobotRecord, signBody } from "../../_lib/test-helpers.js";

const RRN = "RRN-000000000042";
const DOMAIN = "robotis.com";

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
  return new Request(`https://x/v2/robots/${RRN}/verify-tier`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /v2/robots/[rrn]/verify-tier", () => {
  it("rejects target_tier=community (not promotable via API)", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signBody(
      { rrn: RRN, action: "verify-tier", target_tier: "community", binding: { type: "dns-txt", value: DOMAIN } },
      kp,
    );
    const res = await onRequestPost({
      request: req(signed), env, params: { rrn: RRN },
      // @ts-expect-error injected verifiers for test determinism
      verifiers: { dns: vi.fn(), attestation: vi.fn() },
    } as any);
    expect(res.status).toBe(400);
  });

  it("promotes to manufacturer_claimed when DNS TXT verifies", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp, { model: "turtlebot3_burger" }) });
    const signed = await signBody(
      { rrn: RRN, action: "verify-tier", target_tier: "manufacturer_claimed", binding: { type: "dns-txt", value: DOMAIN } },
      kp,
    );
    const verifiers = {
      dns: vi.fn(async () => ({ ok: true, evidence: `rrn=${RRN};model=turtlebot3_burger` })),
      attestation: vi.fn(),
    };
    const res = await onRequestPost({ request: req(signed), env, params: { rrn: RRN }, verifiers } as any);
    expect(res.status).toBe(200);
    const updated = JSON.parse(env.__store[`robot:${RRN}`]);
    expect(updated.verification_status).toBe("manufacturer_claimed");
    expect(updated.identity_binding.type).toBe("dns-txt");
    expect(updated.identity_binding.value).toBe(DOMAIN);
    expect(verifiers.dns).toHaveBeenCalledWith(DOMAIN, RRN, "turtlebot3_burger");
  });

  it("400 when DNS TXT verification fails", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signBody(
      { rrn: RRN, action: "verify-tier", target_tier: "manufacturer_claimed", binding: { type: "dns-txt", value: DOMAIN } },
      kp,
    );
    const verifiers = {
      dns: vi.fn(async () => ({ ok: false, error: "TXT record not found" })),
      attestation: vi.fn(),
    };
    const res = await onRequestPost({ request: req(signed), env, params: { rrn: RRN }, verifiers } as any);
    expect(res.status).toBe(400);
  });

  it("promotes to manufacturer_verified when DNS + attestation both verify", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp, { model: "turtlebot3_burger" }) });
    const attestation = { rrn: RRN, manufacturer: "ROBOTIS", model: "turtlebot3_burger", timestamp_iso: "2026-04-24T00:00:00Z" };
    const signed = await signBody(
      {
        rrn: RRN, action: "verify-tier", target_tier: "manufacturer_verified",
        binding: { type: "dns-txt", value: DOMAIN },
        ruri: "https://robotis.com", attestation,
      },
      kp,
    );
    const verifiers = {
      dns: vi.fn(async () => ({ ok: true, evidence: `rrn=${RRN};model=turtlebot3_burger` })),
      attestation: vi.fn(async () => ({ ok: true, evidence: { attestation_digest: "abc", ruri_matched: "https://robotis.com/.well-known/rcan-manifest.json" } })),
    };
    const res = await onRequestPost({ request: req(signed), env, params: { rrn: RRN }, verifiers } as any);
    expect(res.status).toBe(200);
    const updated = JSON.parse(env.__store[`robot:${RRN}`]);
    expect(updated.verification_status).toBe("manufacturer_verified");
  });

  it("400 on downgrade attempt (current=manufacturer_verified, target=manufacturer_claimed)", async () => {
    const kp = await makeTestKeypair();
    const record = JSON.parse(makeRobotRecord(RRN, kp));
    record.verification_status = "manufacturer_verified";
    const env = makeEnv({ [`robot:${RRN}`]: JSON.stringify(record) });
    const signed = await signBody(
      { rrn: RRN, action: "verify-tier", target_tier: "manufacturer_claimed", binding: { type: "dns-txt", value: DOMAIN } },
      kp,
    );
    const verifiers = { dns: vi.fn(), attestation: vi.fn() };
    const res = await onRequestPost({ request: req(signed), env, params: { rrn: RRN }, verifiers } as any);
    expect(res.status).toBe(400);
  });

  it("403 when record is revoked", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({
      [`robot:${RRN}`]: makeRobotRecord(RRN, kp),
      [`revocation:${RRN}`]: JSON.stringify({ revoked_at: "2026-04-24T00:00:00Z", reason: "test" }),
    });
    const signed = await signBody(
      { rrn: RRN, action: "verify-tier", target_tier: "manufacturer_claimed", binding: { type: "dns-txt", value: DOMAIN } },
      kp,
    );
    const verifiers = { dns: vi.fn(), attestation: vi.fn() };
    const res = await onRequestPost({ request: req(signed), env, params: { rrn: RRN }, verifiers } as any);
    expect(res.status).toBe(403);
  });

  it("401 when signature does not verify against record's pq_signing_pub", async () => {
    const kp = await makeTestKeypair();
    const attackerKp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signBody(
      { rrn: RRN, action: "verify-tier", target_tier: "manufacturer_claimed", binding: { type: "dns-txt", value: DOMAIN } },
      attackerKp,
    );
    const verifiers = { dns: vi.fn(), attestation: vi.fn() };
    const res = await onRequestPost({ request: req(signed), env, params: { rrn: RRN }, verifiers } as any);
    expect(res.status).toBe(401);
  });

  it("400 when target_tier is invalid", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signBody(
      { rrn: RRN, action: "verify-tier", target_tier: "wizard_tier", binding: { type: "dns-txt", value: DOMAIN } },
      kp,
    );
    const verifiers = { dns: vi.fn(), attestation: vi.fn() };
    const res = await onRequestPost({ request: req(signed), env, params: { rrn: RRN }, verifiers } as any);
    expect(res.status).toBe(400);
  });

  it("400 when manufacturer_verified request is missing ruri or attestation", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signBody(
      { rrn: RRN, action: "verify-tier", target_tier: "manufacturer_verified", binding: { type: "dns-txt", value: DOMAIN } },
      kp,
    );
    const verifiers = { dns: vi.fn(), attestation: vi.fn() };
    const res = await onRequestPost({ request: req(signed), env, params: { rrn: RRN }, verifiers } as any);
    expect(res.status).toBe(400);
  });
});
```

- [ ] **Step 2: Verify RED**

```bash
npm test -- functions/v2/robots/\[rrn\]/verify-tier.test.ts
```

Expected: 9 failures, module-not-found.

- [ ] **Step 3: Implement `verify-tier.ts`**

```ts
// functions/v2/robots/[rrn]/verify-tier.ts
import { isValidId } from "../../_lib/id.js";
import { verifyBody } from "rcan-ts";
import { isRevoked } from "../../_lib/revocation.js";
import { verifyDnsTxt } from "../../_lib/dns-verify.js";
import { verifyAttestation } from "../../_lib/attestation-verify.js";

export interface Env { RRF_KV: KVNamespace }

interface Verifiers {
  dns: typeof verifyDnsTxt;
  attestation: typeof verifyAttestation;
}

const TIER_ORDER = ["unverified", "community", "manufacturer_claimed", "manufacturer_verified"] as const;
type Tier = typeof TIER_ORDER[number];

function err(msg: string, status: number): Response {
  return new Response(JSON.stringify({ error: msg }), {
    status, headers: { "Content-Type": "application/json" },
  });
}

export const onRequestPost: PagesFunction<Env> = async (ctx) => {
  const { request, env, params } = ctx;
  const verifiers: Verifiers = (ctx as any).verifiers ?? { dns: verifyDnsTxt, attestation: verifyAttestation };
  const rrn = params.rrn as string;

  if (!isValidId(rrn, "RRN")) return err("Invalid RRN format", 400);

  let body: any;
  try { body = await request.json(); }
  catch { return err("Invalid JSON body", 400); }

  const targetTier = body?.target_tier;
  if (targetTier === "community") return err("community tier is maintainer-curated (PR, not API)", 400);
  if (targetTier !== "manufacturer_claimed" && targetTier !== "manufacturer_verified") {
    return err("target_tier must be manufacturer_claimed or manufacturer_verified", 400);
  }
  if (body?.action !== "verify-tier" || body?.rrn !== rrn) {
    return err("Body must bind rrn and action:verify-tier", 400);
  }
  const binding = body?.binding;
  if (!binding || binding.type !== "dns-txt" || typeof binding.value !== "string") {
    return err("binding must be {type:'dns-txt', value:<domain>}", 400);
  }
  if (targetTier === "manufacturer_verified") {
    if (typeof body?.ruri !== "string" || !body?.attestation) {
      return err("manufacturer_verified requires ruri + attestation", 400);
    }
  }

  if (await isRevoked(env, rrn)) return err("Record is revoked", 403);

  const stored = await env.RRF_KV.get(`robot:${rrn}`, "text");
  if (!stored) return err("Not found", 404);
  const record = JSON.parse(stored);

  const pqPubB64 = record.pq_signing_pub;
  if (typeof pqPubB64 !== "string") return err("Record has no registered key", 400);

  let sigOk = false;
  try {
    const pub = Uint8Array.from(atob(pqPubB64), c => c.charCodeAt(0));
    sigOk = await verifyBody(body, pub);
  } catch { /* sigOk stays false */ }
  if (!sigOk) return err("Signature verification failed", 401);

  const currentTier = (record.verification_status ?? "unverified") as Tier;
  const currentIdx = TIER_ORDER.indexOf(currentTier);
  const targetIdx = TIER_ORDER.indexOf(targetTier);
  if (targetIdx <= currentIdx) return err("Cannot downgrade or stay at current tier", 400);

  const dns = await verifiers.dns(binding.value, rrn, record.model);
  if (!dns.ok) return err(`DNS verification failed: ${dns.error}`, 400);

  let ruriEvidence: string | undefined;
  if (targetTier === "manufacturer_verified") {
    const att = await verifiers.attestation({
      attestation: body.attestation,
      ruri: body.ruri,
      pqPubB64,
      expectedRrn: rrn,
      expectedModel: record.model,
    });
    if (!att.ok) return err(`Attestation verification failed: ${att.error}`, 400);
    ruriEvidence = att.evidence.ruri_matched;
  }

  const now = new Date().toISOString();
  record.verification_status = targetTier;
  record.identity_binding = {
    type: "dns-txt",
    value: binding.value,
    verified_at: now,
    verifier_evidence: ruriEvidence ? `${dns.evidence}; ${ruriEvidence}` : dns.evidence,
  };
  record.updated_at = now;
  await env.RRF_KV.put(`robot:${rrn}`, JSON.stringify(record));
  return new Response(JSON.stringify(record), {
    status: 200, headers: { "Content-Type": "application/json" },
  });
};
```

- [ ] **Step 4: Verify GREEN**

```bash
npm test -- functions/v2/robots/\[rrn\]/verify-tier.test.ts
npm test    # full suite
```

Expected: 9/9 pass plus full suite green.

- [ ] **Step 5: Commit**

```bash
git add functions/v2/robots/\[rrn\]/verify-tier.ts functions/v2/robots/\[rrn\]/verify-tier.test.ts
git commit -m "feat(rrf): add POST /v2/robots/:rrn/verify-tier (manufacturer_claimed + manufacturer_verified)"
```

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

Behavior:
1. Load current signing keypair from `~/.robot-md/keys/<rrn>.signing.json`.
2. Generate a new ML-DSA + Ed25519 keypair.
3. Build canonical `{rrn, action: "rotate", new_pq_signing_pub, new_pq_kid}`; sign with old key (→ `old_sig`) and with new key (→ `new_sig`).
4. POST to `<endpoint>/v2/robots/<rrn>/rotate-key`.
5. **On 200 — order matters:**
   a. Archive the old keypair to `~/.robot-md/keys/archive/<rrn>.<old_kid>.signing.json` (mode 0600). Create the archive directory if missing. Write-to-tmp-then-rename for crash-safety.
   b. Atomically replace `~/.robot-md/keys/<rrn>.signing.json` with the new keypair (write-to-tmp-then-rename).
   c. Print: `Rotated. Old key archived at ~/.robot-md/keys/archive/<rrn>.<old_kid>.signing.json (treat as backup credential — can still revoke if new key is lost).`
6. **On any non-200 — do NOT touch the on-disk key.** The archive step only happens after the server confirms the rotation.

Tests:
- Happy path: new keystore replaces old; archive contains the old keypair; exit 0.
- Server returns 401: keystore untouched; archive dir not created; non-zero exit.
- Server returns 404: same as 401.
- Network error (urlopen raises URLError): same as 401.
- Crash between archive-write and new-keystore-write: on next invocation, archive exists but keystore still has old key — idempotent retry should notice and complete. (Test by mocking the rename step to raise partway.)
- Archive dir already has an entry with the same `<old_kid>`: overwrite without error (archive is provenance, not durable store).

Commit: `feat(cli): add robot-md rotate-key (with old-key archive)`

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

## Design decisions (locked 2026-04-24)

1. **Rotation envelope** — co-signed single payload. Both sigs cover canonical `{rrn, action: "rotate", new_pq_signing_pub, new_pq_kid}`. See Task 4.
2. **Rotate archives old key** — `~/.robot-md/keys/archive/<rrn>.<old_kid>.signing.json` mode 0600. Treated as a backup credential. See Task 11.
3. **DNS TTL** — one-shot at promotion time, `verified_at` recorded in `identity_binding`. Periodic re-verification is a follow-up.
4. **`community` tier** — dropped from the `verify-tier` API; remains maintainer-curated via PR against `src/content/robots/<slug>.json` per `rcan-spec/docs/verification/manufacturer-verification.md`. Task 8 dispatches only on `manufacturer_claimed` and `manufacturer_verified`.

## Known limitations

- **Concurrent rotate race** — KV has no CAS primitive; two simultaneous rotate requests can both verify and both write (last-write-wins). The `rotations[]` audit log will reflect the collision post-facto. Optimistic versioning is deferred.

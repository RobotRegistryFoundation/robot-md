# Release D2 — RRF Compliance Intake Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **SCOPE UPDATE 2026-04-23 (partial-ship):** Task 8 (eu-register) deferred to future D3 — rcan-ts 3.2.0's `EuRegisterEntry` envelope has no top-level `rmn` field, so the per-model `/v2/models/[rmn]/eu-register` design can't be implemented without upstream changes. See `reference_rcan_spec_eu_register_rmn_gap.md`. Tasks 4-7 also need builder-input corrections — this plan has NOT been edited in-place for those; the implementer subagent prompts carry the corrected task text verbatim.

**Goal:** Ship four RRF POST+GET endpoints that accept signed RCAN §22-25 compliance artifacts produced by rcan-ts 3.2.0 builders, store them in KV, and serve them back. §26 deferred.

**Architecture:** Five Cloudflare Pages Function handlers under `functions/v2/robots/[rrn]/` and `functions/v2/models/[rmn]/`, all sharing a `verifyComplianceSubmission` helper that reuses `verifyBody` from rcan-ts against the `pq_signing_pub` stored by the existing `/v2/robots/register` flow. Per-type GET policy (public for safety-benchmark/ifu/eu-register; Bearer-gated for fria/incident-report). 10-year KV TTL.

**Tech Stack:** Cloudflare Pages Functions (TypeScript), KV storage, vitest, rcan-ts 3.2.0, Astro (docs pages).

**Spec:** `docs/superpowers/specs/2026-04-23-release-d2-rrf-compliance-intake-design.md`

**Target repo:** `/home/craigm26/RobotRegistryFoundation` (branch: `main`)

---

## Wave 0: Dependencies

### Task 1: Bump rcan-ts to ^3.2.0 and add `@noble/curves` dev dep

**Files:**
- Modify: `RobotRegistryFoundation/package.json`
- Modify: `RobotRegistryFoundation/package-lock.json` (via npm install)

- [ ] **Step 1: Verify you're in the RRF repo on a clean main branch**

```bash
cd /home/craigm26/RobotRegistryFoundation
git status
git rev-parse --abbrev-ref HEAD   # should print "main"
```
Expected: clean working tree, on `main`.

- [ ] **Step 2: Bump rcan-ts dependency**

Edit `package.json`: change `"rcan-ts": "^3.1.1"` to `"rcan-ts": "^3.2.0"`.

- [ ] **Step 3: Install `@noble/curves` as a dev dependency**

Needed by the test-signing helper (Task 2) to derive an Ed25519 public key from a raw 32-byte seed, matching the shape that `signBody` expects. Web Crypto's Ed25519 does not expose raw seeds cleanly.

```bash
cd /home/craigm26/RobotRegistryFoundation
npm install --save-dev @noble/curves
```

- [ ] **Step 4: Install and verify build**

```bash
cd /home/craigm26/RobotRegistryFoundation
npm install
npm run build
npm test
```
Expected: build clean, all existing tests pass.

- [ ] **Step 5: Verify rcan-ts 3.2.0 exports resolved**

```bash
node -e 'const r = require("rcan-ts"); console.log(Object.keys(r).filter(k => k.includes("SCHEMA") || k.startsWith("build")).sort());'
```
Expected output contains: `buildEuRegisterEntry, buildIfu, buildIncidentReport, buildSafetyBenchmark, EU_REGISTER_SCHEMA, IFU_SCHEMA, INCIDENT_REPORT_SCHEMA, SAFETY_BENCHMARK_SCHEMA`.

- [ ] **Step 6: Commit**

```bash
cd /home/craigm26/RobotRegistryFoundation
git add package.json package-lock.json
git commit -m "chore: bump rcan-ts to ^3.2.0 and add @noble/curves dev dep for D2"
```

---

## Wave 1: Shared Helpers

### Task 2: Test helper for signing compliance bodies

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/_lib/test-helpers.ts`
- Test: `RobotRegistryFoundation/functions/v2/_lib/test-helpers.test.ts`

- [ ] **Step 1: Write the failing test**

Create `functions/v2/_lib/test-helpers.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { verifyBody } from "rcan-ts";
import { signComplianceBody, makeTestKeypair } from "./test-helpers.js";

describe("signComplianceBody", () => {
  it("produces a body that verifyBody accepts", async () => {
    const kp = await makeTestKeypair();
    const doc = { schema: "rcan-safety-benchmark-v1", rrn: "RRN-000000000001", version: "1.0" };
    const signed = await signComplianceBody(doc, kp);

    expect(signed.pq_signing_pub).toBeTypeOf("string");
    expect(signed.pq_kid).toBeTypeOf("string");
    expect((signed.sig as any).ml_dsa).toBeTypeOf("string");
    expect((signed.sig as any).ed25519).toBeTypeOf("string");
    expect((signed.sig as any).ed25519_pub).toBeTypeOf("string");

    const pqPub = Uint8Array.from(atob(signed.pq_signing_pub as string), c => c.charCodeAt(0));
    const ok = await verifyBody(signed, pqPub);
    expect(ok).toBe(true);
  });

  it("round-trip fails if body is tampered", async () => {
    const kp = await makeTestKeypair();
    const doc = { schema: "rcan-safety-benchmark-v1", rrn: "RRN-000000000001" };
    const signed = await signComplianceBody(doc, kp);
    const tampered = { ...signed, rrn: "RRN-000000000002" };

    const pqPub = Uint8Array.from(atob(tampered.pq_signing_pub as string), c => c.charCodeAt(0));
    const ok = await verifyBody(tampered, pqPub);
    expect(ok).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/_lib/test-helpers.test.ts
```
Expected: FAIL with "Cannot find module './test-helpers.js'".

- [ ] **Step 3: Write the helper**

Create `functions/v2/_lib/test-helpers.ts`:

```ts
/**
 * Test-only helpers. Do NOT import from production handler code.
 */

import { signBody, generateMlDsaKeypair } from "rcan-ts";
import { ed25519 } from "@noble/curves/ed25519";

export interface TestKeypair {
  mlDsa: { publicKey: Uint8Array; privateKey: Uint8Array };
  ed25519Secret: Uint8Array;   // 32-byte seed
  ed25519Public: Uint8Array;   // 32-byte pub
}

export async function makeTestKeypair(): Promise<TestKeypair> {
  const mlDsa = generateMlDsaKeypair();  // sync
  const ed25519Secret = crypto.getRandomValues(new Uint8Array(32));
  const ed25519Public = ed25519.getPublicKey(ed25519Secret);
  return { mlDsa, ed25519Secret, ed25519Public };
}

/**
 * Sign a compliance document for use in tests.
 * Returns a body ready to POST (flat: { ...doc, pq_signing_pub, pq_kid, sig }).
 */
export async function signComplianceBody(
  doc: Record<string, unknown>,
  kp: TestKeypair,
): Promise<Record<string, unknown>> {
  return signBody(kp.mlDsa, doc, {
    ed25519Secret: kp.ed25519Secret,
    ed25519Public: kp.ed25519Public,
  });
}

/**
 * Build a fake robot KV record containing the given PQ public key,
 * matching the shape register.ts persists under robot:{rrn}.
 */
export function makeRobotRecord(rrn: string, kp: TestKeypair): string {
  const pq_signing_pub = btoa(String.fromCharCode(...kp.mlDsa.publicKey));
  return JSON.stringify({
    rrn, name: "test", manufacturer: "test", model: "test",
    firmware_version: "1.0", rcan_version: "3.0",
    pq_signing_pub,
    pq_kid: "testkid1",
    registered_at: "2026-04-23T00:00:00Z",
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/_lib/test-helpers.test.ts
```
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/RobotRegistryFoundation
git add functions/v2/_lib/test-helpers.ts functions/v2/_lib/test-helpers.test.ts
git commit -m "test: add compliance signing helpers for D2 endpoint tests"
```

---

### Task 3: `verifyComplianceSubmission` shared helper

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/_lib/compliance-auth.ts`
- Test: `RobotRegistryFoundation/functions/v2/_lib/compliance-auth.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `functions/v2/_lib/compliance-auth.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import { verifyComplianceSubmission } from "./compliance-auth.js";
import { signComplianceBody, makeTestKeypair, makeRobotRecord } from "./test-helpers.js";

const RRN = "RRN-000000000001";

function makeEnv(stored: Record<string, string> = {}) {
  return {
    RRF_KV: {
      get: vi.fn(async (k: string) => stored[k] ?? null),
      put: vi.fn(async (k: string, v: string) => { stored[k] = v; }),
      list: vi.fn(),
      delete: vi.fn(),
    } as unknown as KVNamespace,
  };
}

function makePost(body: unknown): Request {
  return new Request("https://x/v2/robots/R/ifu", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

describe("verifyComplianceSubmission", () => {
  it("returns ok with document on valid sig", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const doc = { schema: "rcan-ifu-v1", rrn: RRN, version: "1.0" };
    const signed = await signComplianceBody(doc, kp);

    const result = await verifyComplianceSubmission(makePost(signed), env, `robot:${RRN}`);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.document.schema).toBe("rcan-ifu-v1");
      expect(result.document.rrn).toBe(RRN);
      expect("sig" in result.document).toBe(false);
      expect("pq_kid" in result.document).toBe(false);
    }
  });

  it("returns 400 on invalid JSON", async () => {
    const env = makeEnv();
    const result = await verifyComplianceSubmission(makePost("not json"), env, `robot:${RRN}`);
    expect(result).toEqual({ ok: false, status: 400, error: "Invalid JSON body" });
  });

  it("returns 400 when sig is missing", async () => {
    const env = makeEnv({ [`robot:${RRN}`]: "{}" });
    const result = await verifyComplianceSubmission(
      makePost({ schema: "x", rrn: RRN, pq_kid: "k" }),
      env, `robot:${RRN}`,
    );
    expect(result).toEqual({ ok: false, status: 400, error: "Missing signature fields" });
  });

  it("returns 400 when pq_kid is missing", async () => {
    const env = makeEnv({ [`robot:${RRN}`]: "{}" });
    const result = await verifyComplianceSubmission(
      makePost({ schema: "x", sig: { ml_dsa: "a", ed25519: "b", ed25519_pub: "c" } }),
      env, `robot:${RRN}`,
    );
    expect(result).toEqual({ ok: false, status: 400, error: "Missing signature fields" });
  });

  it("returns 401 when robot not registered", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv();
    const signed = await signComplianceBody({ schema: "rcan-ifu-v1", rrn: RRN }, kp);
    const result = await verifyComplianceSubmission(makePost(signed), env, `robot:${RRN}`);
    expect(result).toEqual({ ok: false, status: 401, error: "Robot not registered" });
  });

  it("returns 401 when sig does not verify", async () => {
    const kp1 = await makeTestKeypair();
    const kp2 = await makeTestKeypair();
    // Store kp1's record, sign with kp2 — keys mismatch.
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp1) });
    const signed = await signComplianceBody({ schema: "rcan-ifu-v1", rrn: RRN }, kp2);
    const result = await verifyComplianceSubmission(makePost(signed), env, `robot:${RRN}`);
    expect(result).toEqual({ ok: false, status: 401, error: "Signature verification failed" });
  });

  it("returns 401 when body tampered after sign", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody({ schema: "rcan-ifu-v1", rrn: RRN }, kp);
    const tampered = { ...signed, rrn: "RRN-000000000999" };
    const result = await verifyComplianceSubmission(makePost(tampered), env, `robot:${RRN}`);
    expect(result).toEqual({ ok: false, status: 401, error: "Signature verification failed" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/_lib/compliance-auth.test.ts
```
Expected: FAIL with "Cannot find module './compliance-auth.js'".

- [ ] **Step 3: Implement the helper**

Create `functions/v2/_lib/compliance-auth.ts`:

```ts
/**
 * Shared auth helper for RCAN §22-26 compliance intake endpoints.
 *
 * Loads the entity (robot or model) record from KV, extracts the registered
 * ML-DSA-65 public key (`pq_signing_pub`), and calls `verifyBody` from rcan-ts
 * against the signed compliance document.
 *
 * On success, returns the document stripped of `sig` + `pq_kid` + `pq_signing_pub`
 * (envelope fields), ready for schema and rrn/rmn validation by the caller.
 */

import { verifyBody } from "rcan-ts";

export interface VerifiedSubmission {
  ok: true;
  document: Record<string, unknown>;
}

export interface VerifyError {
  ok: false;
  status: number;
  error: string;
}

export type VerifyResult = VerifiedSubmission | VerifyError;

export async function verifyComplianceSubmission(
  request: Request,
  env: { RRF_KV: KVNamespace },
  entityKey: string,
): Promise<VerifyResult> {
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return { ok: false, status: 400, error: "Invalid JSON body" };
  }

  const sig = body["sig"] as Record<string, unknown> | undefined;
  const pq_kid = body["pq_kid"];
  if (!sig || typeof pq_kid !== "string"
      || typeof sig["ml_dsa"] !== "string"
      || typeof sig["ed25519"] !== "string"
      || typeof sig["ed25519_pub"] !== "string") {
    return { ok: false, status: 400, error: "Missing signature fields" };
  }

  const stored = await env.RRF_KV.get(entityKey, "text");
  if (!stored) return { ok: false, status: 401, error: "Robot not registered" };

  let record: Record<string, unknown>;
  try {
    record = JSON.parse(stored) as Record<string, unknown>;
  } catch {
    return { ok: false, status: 500, error: "Corrupt entity record" };
  }

  const pqPubB64 = record["pq_signing_pub"];
  if (typeof pqPubB64 !== "string") {
    return { ok: false, status: 401, error: "Entity has no registered PQ key" };
  }

  let verified = false;
  try {
    const pqPub = Uint8Array.from(atob(pqPubB64), (c) => c.charCodeAt(0));
    verified = await verifyBody(body, pqPub);
  } catch {
    verified = false;
  }
  if (!verified) {
    return { ok: false, status: 401, error: "Signature verification failed" };
  }

  // Strip envelope fields; return the compliance document itself.
  const document: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(body)) {
    if (k !== "sig" && k !== "pq_kid" && k !== "pq_signing_pub") document[k] = v;
  }
  return { ok: true, document };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/_lib/compliance-auth.test.ts
```
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/RobotRegistryFoundation
git add functions/v2/_lib/compliance-auth.ts functions/v2/_lib/compliance-auth.test.ts
git commit -m "feat(d2): add verifyComplianceSubmission shared auth helper"
```

---

## Wave 2: Endpoints

### Task 4: Safety Benchmark endpoint (§23)

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/safety-benchmark.ts`
- Test: `RobotRegistryFoundation/functions/v2/robots/[rrn]/safety-benchmark.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `functions/v2/robots/[rrn]/safety-benchmark.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import { onRequest } from "./safety-benchmark.js";
import { buildSafetyBenchmark, SAFETY_BENCHMARK_SCHEMA } from "rcan-ts";
import { signComplianceBody, makeTestKeypair, makeRobotRecord } from "../../_lib/test-helpers.js";

const RRN = "RRN-000000000001";

function makeEnv(init: Record<string, string> = {}) {
  const store: Record<string, string> = { ...init };
  return {
    RRF_KV: {
      get: vi.fn(async (k: string) => store[k] ?? null),
      put: vi.fn(async (k: string, v: string) => { store[k] = v; }),
      list: vi.fn(),
      delete: vi.fn(),
    } as unknown as KVNamespace,
    __store: store,
  };
}

function req(method: string, body?: unknown, headers: Record<string, string> = {}): Request {
  return new Request(`https://x/v2/robots/${RRN}/safety-benchmark`, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
}

describe("GET /v2/robots/[rrn]/safety-benchmark", () => {
  it("returns 404 when nothing submitted", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("GET"), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(404);
  });

  it("returns 400 on invalid RRN format", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("GET"), env, params: { rrn: "bad" } } as any);
    expect(res.status).toBe(400);
  });

  it("returns stored doc with cache header when present", async () => {
    const env = makeEnv({ [`compliance:safety-benchmark:${RRN}`]: JSON.stringify({ schema: "rcan-safety-benchmark-v1", rrn: RRN }) });
    const res = await onRequest({ request: req("GET"), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toContain("max-age=300");
  });
});

describe("POST /v2/robots/[rrn]/safety-benchmark", () => {
  it("stores and returns 201 on valid submission", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const doc = buildSafetyBenchmark({
      rrn: RRN, benchmark_version: "1.0",
      test_suite_id: "suite-a", executed_at: "2026-04-23T00:00:00Z",
      pass_count: 10, fail_count: 0, skip_count: 0,
    });
    const signed = await signComplianceBody(doc, kp);

    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(201);

    const body = await res.json() as any;
    expect(body.ok).toBe(true);
    expect(body.rrn).toBe(RRN);

    expect(env.__store[`compliance:safety-benchmark:${RRN}`]).toBeTruthy();
    const historyKeys = Object.keys(env.__store).filter(k => k.startsWith(`compliance:safety-benchmark:history:${RRN}:`));
    expect(historyKeys.length).toBe(1);
  });

  it("401 on tampered body", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const doc = buildSafetyBenchmark({
      rrn: RRN, benchmark_version: "1.0", test_suite_id: "s", executed_at: "t",
      pass_count: 1, fail_count: 0, skip_count: 0,
    });
    const signed = await signComplianceBody(doc, kp);
    const tampered = { ...signed, rrn: "RRN-000000000999" };
    const res = await onRequest({ request: req("POST", tampered), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("401 when robot not registered", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv();
    const doc = buildSafetyBenchmark({
      rrn: RRN, benchmark_version: "1.0", test_suite_id: "s", executed_at: "t",
      pass_count: 1, fail_count: 0, skip_count: 0,
    });
    const signed = await signComplianceBody(doc, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("400 on missing sig", async () => {
    const env = makeEnv({ [`robot:${RRN}`]: "{}" });
    const res = await onRequest({ request: req("POST", { schema: SAFETY_BENCHMARK_SCHEMA, rrn: RRN, pq_kid: "x" }), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });

  it("400 on wrong schema string", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody({ schema: "rcan-ifu-v1", rrn: RRN }, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
    expect(((await res.json()) as any).error).toContain(SAFETY_BENCHMARK_SCHEMA);
  });

  it("400 on document.rrn != URL rrn", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody(
      { schema: SAFETY_BENCHMARK_SCHEMA, rrn: "RRN-000000000999" },
      kp,
    );
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });
});

describe("method handling", () => {
  it("returns 405 on PUT", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("PUT"), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(405);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/robots/\[rrn\]/safety-benchmark.test.ts
```
Expected: FAIL with "Cannot find module './safety-benchmark.js'".

- [ ] **Step 3: Implement the endpoint**

Create `functions/v2/robots/[rrn]/safety-benchmark.ts`:

```ts
/**
 * /v2/robots/:rrn/safety-benchmark
 * RCAN 3.0 §23 — Safety Benchmark intake.
 *
 * POST — robot submits a signed safety-benchmark document.
 * GET  — public retrieval of the current benchmark for this robot.
 *
 * KV binding: RRF_KV
 * Key pattern: compliance:safety-benchmark:{rrn}
 *              compliance:safety-benchmark:history:{rrn}:{ts}
 */

import { SAFETY_BENCHMARK_SCHEMA } from "rcan-ts";
import { verifyComplianceSubmission } from "../../_lib/compliance-auth.js";

export interface Env {
  RRF_KV: KVNamespace;
}

const TEN_YEARS_SECS = 10 * 365 * 24 * 3600;
const RRN_RE = /^RRN-[0-9]{12}$/;

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const { request, env, params } = ctx;
  const rrn = params["rrn"] as string;

  if (!rrn || !RRN_RE.test(rrn)) {
    return json({ error: "Invalid RRN format" }, 400);
  }

  if (request.method === "GET")  return handleGet(env, rrn);
  if (request.method === "POST") return handlePost(request, env, rrn);
  return json({ error: "Method not allowed" }, 405);
};

async function handleGet(env: Env, rrn: string): Promise<Response> {
  const stored = await env.RRF_KV.get(`compliance:safety-benchmark:${rrn}`, "text");
  if (!stored) return json({ error: "Safety benchmark not found", rrn }, 404);
  return new Response(stored, {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, max-age=300",
    },
  });
}

async function handlePost(request: Request, env: Env, rrn: string): Promise<Response> {
  const result = await verifyComplianceSubmission(request, env, `robot:${rrn}`);
  if (!result.ok) return json({ error: result.error }, result.status);

  const doc = result.document;
  if (doc.schema !== SAFETY_BENCHMARK_SCHEMA) {
    return json({ error: `Expected schema ${SAFETY_BENCHMARK_SCHEMA}, got ${String(doc.schema)}` }, 400);
  }
  if (doc.rrn !== rrn) {
    return json({ error: "Document rrn does not match URL rrn" }, 400);
  }

  const now = new Date().toISOString();
  const stored = JSON.stringify({ ...doc, _received_at: now });
  await env.RRF_KV.put(`compliance:safety-benchmark:${rrn}`, stored, { expirationTtl: TEN_YEARS_SECS });
  await env.RRF_KV.put(`compliance:safety-benchmark:history:${rrn}:${Date.now()}`, stored, { expirationTtl: TEN_YEARS_SECS });

  return json({
    ok: true,
    rrn,
    submitted_at: now,
    safety_benchmark_url: `https://api.rrf.rcan.dev/v2/robots/${rrn}/safety-benchmark`,
  }, 201);
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/robots/\[rrn\]/safety-benchmark.test.ts
```
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/RobotRegistryFoundation
git add functions/v2/robots/\[rrn\]/safety-benchmark.ts functions/v2/robots/\[rrn\]/safety-benchmark.test.ts
git commit -m "feat(d2): add §23 safety-benchmark intake endpoint"
```

---

### Task 5: IFU endpoint (§24)

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/ifu.ts`
- Test: `RobotRegistryFoundation/functions/v2/robots/[rrn]/ifu.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `functions/v2/robots/[rrn]/ifu.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import { onRequest } from "./ifu.js";
import { buildIfu, IFU_SCHEMA } from "rcan-ts";
import { signComplianceBody, makeTestKeypair, makeRobotRecord } from "../../_lib/test-helpers.js";

const RRN = "RRN-000000000001";

function makeEnv(init: Record<string, string> = {}) {
  const store: Record<string, string> = { ...init };
  return {
    RRF_KV: {
      get: vi.fn(async (k: string) => store[k] ?? null),
      put: vi.fn(async (k: string, v: string) => { store[k] = v; }),
      list: vi.fn(), delete: vi.fn(),
    } as unknown as KVNamespace,
    __store: store,
  };
}

function req(method: string, body?: unknown): Request {
  return new Request(`https://x/v2/robots/${RRN}/ifu`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
}

describe("GET /v2/robots/[rrn]/ifu", () => {
  it("returns 404 when nothing submitted", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("GET"), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(404);
  });

  it("returns 400 on invalid RRN format", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("GET"), env, params: { rrn: "bad" } } as any);
    expect(res.status).toBe(400);
  });

  it("returns stored doc with cache header", async () => {
    const env = makeEnv({ [`compliance:ifu:${RRN}`]: JSON.stringify({ schema: IFU_SCHEMA, rrn: RRN }) });
    const res = await onRequest({ request: req("GET"), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toContain("max-age=300");
  });
});

describe("POST /v2/robots/[rrn]/ifu", () => {
  it("stores and returns 201 on valid submission", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const doc = buildIfu({
      rrn: RRN, ifu_version: "1.0",
      intended_use: "SO-ARM101 pick-and-place in controlled lab environment",
      operator_qualifications: ["RCAN-certified operator"],
      residual_risks: ["Pinch hazard: keep hands clear of gripper"],
      safety_instructions: ["E-stop accessible"],
      maintenance_schedule: "Monthly servo calibration",
      contact_manufacturer: "ops@example.com",
      generated_at: "2026-04-23T00:00:00Z",
    });
    const signed = await signComplianceBody(doc, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(201);
    expect(env.__store[`compliance:ifu:${RRN}`]).toBeTruthy();
    expect(Object.keys(env.__store).filter(k => k.startsWith(`compliance:ifu:history:${RRN}:`)).length).toBe(1);
  });

  it("401 on tampered body", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const doc = buildIfu({
      rrn: RRN, ifu_version: "1.0", intended_use: "x", operator_qualifications: [],
      residual_risks: [], safety_instructions: [], maintenance_schedule: "x",
      contact_manufacturer: "x", generated_at: "2026-04-23T00:00:00Z",
    });
    const signed = await signComplianceBody(doc, kp);
    const tampered = { ...signed, rrn: "RRN-000000000999" };
    const res = await onRequest({ request: req("POST", tampered), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("401 when robot not registered", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv();
    const signed = await signComplianceBody({ schema: IFU_SCHEMA, rrn: RRN }, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("400 on missing sig", async () => {
    const env = makeEnv({ [`robot:${RRN}`]: "{}" });
    const res = await onRequest({ request: req("POST", { schema: IFU_SCHEMA, rrn: RRN, pq_kid: "x" }), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });

  it("400 on wrong schema string", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody({ schema: "rcan-safety-benchmark-v1", rrn: RRN }, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });

  it("400 on document.rrn != URL rrn", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody({ schema: IFU_SCHEMA, rrn: "RRN-000000000999" }, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });

  it("returns 405 on PUT", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("PUT"), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(405);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/robots/\[rrn\]/ifu.test.ts
```
Expected: FAIL with "Cannot find module './ifu.js'".

- [ ] **Step 3: Implement the endpoint**

Create `functions/v2/robots/[rrn]/ifu.ts`:

```ts
/**
 * /v2/robots/:rrn/ifu
 * RCAN 3.0 §24 — Instructions For Use (EU AI Act Art. 13(3)) intake.
 *
 * POST — robot submits a signed IFU document.
 * GET  — public retrieval of the current IFU for this robot.
 *
 * KV key pattern: compliance:ifu:{rrn}
 *                 compliance:ifu:history:{rrn}:{ts}
 */

import { IFU_SCHEMA } from "rcan-ts";
import { verifyComplianceSubmission } from "../../_lib/compliance-auth.js";

export interface Env {
  RRF_KV: KVNamespace;
}

const TEN_YEARS_SECS = 10 * 365 * 24 * 3600;
const RRN_RE = /^RRN-[0-9]{12}$/;

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const { request, env, params } = ctx;
  const rrn = params["rrn"] as string;

  if (!rrn || !RRN_RE.test(rrn)) return json({ error: "Invalid RRN format" }, 400);

  if (request.method === "GET")  return handleGet(env, rrn);
  if (request.method === "POST") return handlePost(request, env, rrn);
  return json({ error: "Method not allowed" }, 405);
};

async function handleGet(env: Env, rrn: string): Promise<Response> {
  const stored = await env.RRF_KV.get(`compliance:ifu:${rrn}`, "text");
  if (!stored) return json({ error: "IFU not found", rrn }, 404);
  return new Response(stored, {
    headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=300" },
  });
}

async function handlePost(request: Request, env: Env, rrn: string): Promise<Response> {
  const result = await verifyComplianceSubmission(request, env, `robot:${rrn}`);
  if (!result.ok) return json({ error: result.error }, result.status);

  const doc = result.document;
  if (doc.schema !== IFU_SCHEMA) {
    return json({ error: `Expected schema ${IFU_SCHEMA}, got ${String(doc.schema)}` }, 400);
  }
  if (doc.rrn !== rrn) return json({ error: "Document rrn does not match URL rrn" }, 400);

  const now = new Date().toISOString();
  const stored = JSON.stringify({ ...doc, _received_at: now });
  await env.RRF_KV.put(`compliance:ifu:${rrn}`, stored, { expirationTtl: TEN_YEARS_SECS });
  await env.RRF_KV.put(`compliance:ifu:history:${rrn}:${Date.now()}`, stored, { expirationTtl: TEN_YEARS_SECS });

  return json({
    ok: true,
    rrn,
    submitted_at: now,
    ifu_url: `https://api.rrf.rcan.dev/v2/robots/${rrn}/ifu`,
  }, 201);
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/robots/\[rrn\]/ifu.test.ts
```
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/RobotRegistryFoundation
git add functions/v2/robots/\[rrn\]/ifu.ts functions/v2/robots/\[rrn\]/ifu.test.ts
git commit -m "feat(d2): add §24 IFU intake endpoint"
```

---

### Task 6: FRIA endpoint (§22, Bearer-gated GET)

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/fria.ts`
- Test: `RobotRegistryFoundation/functions/v2/robots/[rrn]/fria.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `functions/v2/robots/[rrn]/fria.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import { onRequest } from "./fria.js";
import { signComplianceBody, makeTestKeypair, makeRobotRecord } from "../../_lib/test-helpers.js";

const RRN = "RRN-000000000001";
const FRIA_SCHEMA = "rcan-fria-v1";

function makeEnv(init: Record<string, string> = {}) {
  const store: Record<string, string> = { ...init };
  return {
    RRF_KV: {
      get: vi.fn(async (k: string) => store[k] ?? null),
      put: vi.fn(async (k: string, v: string) => { store[k] = v; }),
      list: vi.fn(), delete: vi.fn(),
    } as unknown as KVNamespace,
    __store: store,
  };
}

function req(method: string, body?: unknown, headers: Record<string, string> = {}): Request {
  return new Request(`https://x/v2/robots/${RRN}/fria`, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
}

const FRIA_DOC = {
  schema: FRIA_SCHEMA,
  rrn: RRN,
  generated_at: "2026-04-23T00:00:00Z",
  risk_category: "high",
  affected_rights: ["privacy"],
  mitigation_measures: ["Data minimization"],
  signing_key: { alg: "ml-dsa-65", pq_kid: "abcd1234" },
};

describe("GET /v2/robots/[rrn]/fria (auth-gated)", () => {
  it("returns 401 without Bearer header", async () => {
    const env = makeEnv({ [`compliance:fria:${RRN}`]: JSON.stringify(FRIA_DOC) });
    const res = await onRequest({ request: req("GET"), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("returns stored doc with Bearer header", async () => {
    const env = makeEnv({ [`compliance:fria:${RRN}`]: JSON.stringify(FRIA_DOC) });
    const res = await onRequest({
      request: req("GET", undefined, { Authorization: "Bearer anytoken" }),
      env, params: { rrn: RRN },
    } as any);
    expect(res.status).toBe(200);
  });

  it("returns 404 when nothing submitted (with Bearer)", async () => {
    const env = makeEnv();
    const res = await onRequest({
      request: req("GET", undefined, { Authorization: "Bearer anytoken" }),
      env, params: { rrn: RRN },
    } as any);
    expect(res.status).toBe(404);
  });

  it("returns 400 on invalid RRN format", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("GET"), env, params: { rrn: "bad" } } as any);
    expect(res.status).toBe(400);
  });
});

describe("POST /v2/robots/[rrn]/fria", () => {
  it("stores and returns 201 on valid submission", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody(FRIA_DOC, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(201);
    expect(env.__store[`compliance:fria:${RRN}`]).toBeTruthy();
  });

  it("401 on tampered body", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody(FRIA_DOC, kp);
    const res = await onRequest({ request: req("POST", { ...signed, rrn: "RRN-000000000999" }), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("401 when robot not registered", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv();
    const signed = await signComplianceBody(FRIA_DOC, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("400 on missing sig", async () => {
    const env = makeEnv({ [`robot:${RRN}`]: "{}" });
    const res = await onRequest({ request: req("POST", { schema: FRIA_SCHEMA, rrn: RRN, pq_kid: "x" }), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });

  it("400 on wrong schema string", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody({ ...FRIA_DOC, schema: "rcan-ifu-v1" }, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });

  it("400 on document.rrn != URL rrn", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody({ ...FRIA_DOC, rrn: "RRN-000000000999" }, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });

  it("returns 405 on PUT", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("PUT"), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(405);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/robots/\[rrn\]/fria.test.ts
```
Expected: FAIL with "Cannot find module './fria.js'".

- [ ] **Step 3: Implement the endpoint**

Create `functions/v2/robots/[rrn]/fria.ts`:

```ts
/**
 * /v2/robots/:rrn/fria
 * RCAN 3.0 §22 — Fundamental Rights Impact Assessment intake.
 *
 * POST — robot submits a signed FRIA document.
 * GET  — Bearer-gated retrieval (FRIA may contain sensitive analysis).
 *
 * KV key pattern: compliance:fria:{rrn}
 *                 compliance:fria:history:{rrn}:{ts}
 */

import { verifyComplianceSubmission } from "../../_lib/compliance-auth.js";

export interface Env {
  RRF_KV: KVNamespace;
}

const TEN_YEARS_SECS = 10 * 365 * 24 * 3600;
const RRN_RE = /^RRN-[0-9]{12}$/;
const FRIA_SCHEMA = "rcan-fria-v1";  // sweep into rcan-ts as FRIA_SCHEMA in 3.3.0

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const { request, env, params } = ctx;
  const rrn = params["rrn"] as string;

  if (!rrn || !RRN_RE.test(rrn)) return json({ error: "Invalid RRN format" }, 400);

  if (request.method === "GET")  return handleGet(request, env, rrn);
  if (request.method === "POST") return handlePost(request, env, rrn);
  return json({ error: "Method not allowed" }, 405);
};

async function handleGet(request: Request, env: Env, rrn: string): Promise<Response> {
  const auth = request.headers.get("Authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return json({ error: "Authorization required" }, 401);

  const stored = await env.RRF_KV.get(`compliance:fria:${rrn}`, "text");
  if (!stored) return json({ error: "FRIA not found", rrn }, 404);
  return new Response(stored, {
    headers: { "Content-Type": "application/json", "Cache-Control": "private, max-age=60" },
  });
}

async function handlePost(request: Request, env: Env, rrn: string): Promise<Response> {
  const result = await verifyComplianceSubmission(request, env, `robot:${rrn}`);
  if (!result.ok) return json({ error: result.error }, result.status);

  const doc = result.document;
  if (doc.schema !== FRIA_SCHEMA) {
    return json({ error: `Expected schema ${FRIA_SCHEMA}, got ${String(doc.schema)}` }, 400);
  }
  if (doc.rrn !== rrn) return json({ error: "Document rrn does not match URL rrn" }, 400);

  const now = new Date().toISOString();
  const stored = JSON.stringify({ ...doc, _received_at: now });
  await env.RRF_KV.put(`compliance:fria:${rrn}`, stored, { expirationTtl: TEN_YEARS_SECS });
  await env.RRF_KV.put(`compliance:fria:history:${rrn}:${Date.now()}`, stored, { expirationTtl: TEN_YEARS_SECS });

  return json({
    ok: true,
    rrn,
    submitted_at: now,
    fria_url: `https://api.rrf.rcan.dev/v2/robots/${rrn}/fria`,
  }, 201);
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/robots/\[rrn\]/fria.test.ts
```
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/RobotRegistryFoundation
git add functions/v2/robots/\[rrn\]/fria.ts functions/v2/robots/\[rrn\]/fria.test.ts
git commit -m "feat(d2): add §22 FRIA intake endpoint (Bearer-gated GET)"
```

---

### Task 7: Incident Report endpoint (§25, Bearer-gated GET)

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/robots/[rrn]/incident-report.ts`
- Test: `RobotRegistryFoundation/functions/v2/robots/[rrn]/incident-report.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `functions/v2/robots/[rrn]/incident-report.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import { onRequest } from "./incident-report.js";
import { buildIncidentReport, INCIDENT_REPORT_SCHEMA } from "rcan-ts";
import { signComplianceBody, makeTestKeypair, makeRobotRecord } from "../../_lib/test-helpers.js";

const RRN = "RRN-000000000001";

function makeEnv(init: Record<string, string> = {}) {
  const store: Record<string, string> = { ...init };
  return {
    RRF_KV: {
      get: vi.fn(async (k: string) => store[k] ?? null),
      put: vi.fn(async (k: string, v: string) => { store[k] = v; }),
      list: vi.fn(), delete: vi.fn(),
    } as unknown as KVNamespace,
    __store: store,
  };
}

function req(method: string, body?: unknown, headers: Record<string, string> = {}): Request {
  return new Request(`https://x/v2/robots/${RRN}/incident-report`, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
}

const REPORT_INPUT = {
  rrn: RRN,
  reporting_period_start: "2026-04-01T00:00:00Z",
  reporting_period_end: "2026-04-23T00:00:00Z",
  incidents: [
    { timestamp: "2026-04-10T12:00:00Z", severity: "other" as const, description: "minor jam" },
  ],
  generated_at: "2026-04-23T00:00:00Z",
};

describe("GET /v2/robots/[rrn]/incident-report (auth-gated)", () => {
  it("returns 401 without Bearer header", async () => {
    const env = makeEnv({ [`compliance:incident-report:${RRN}`]: "{}" });
    const res = await onRequest({ request: req("GET"), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("returns stored doc with Bearer header", async () => {
    const env = makeEnv({ [`compliance:incident-report:${RRN}`]: JSON.stringify({ schema: INCIDENT_REPORT_SCHEMA, rrn: RRN }) });
    const res = await onRequest({
      request: req("GET", undefined, { Authorization: "Bearer anytoken" }),
      env, params: { rrn: RRN },
    } as any);
    expect(res.status).toBe(200);
  });

  it("returns 404 when nothing submitted (with Bearer)", async () => {
    const env = makeEnv();
    const res = await onRequest({
      request: req("GET", undefined, { Authorization: "Bearer anytoken" }),
      env, params: { rrn: RRN },
    } as any);
    expect(res.status).toBe(404);
  });

  it("returns 400 on invalid RRN format", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("GET"), env, params: { rrn: "bad" } } as any);
    expect(res.status).toBe(400);
  });
});

describe("POST /v2/robots/[rrn]/incident-report", () => {
  it("stores and returns 201 on valid submission", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const doc = buildIncidentReport(REPORT_INPUT);
    const signed = await signComplianceBody(doc, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(201);
    expect(env.__store[`compliance:incident-report:${RRN}`]).toBeTruthy();
  });

  it("401 on tampered body", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const doc = buildIncidentReport(REPORT_INPUT);
    const signed = await signComplianceBody(doc, kp);
    const res = await onRequest({ request: req("POST", { ...signed, rrn: "RRN-000000000999" }), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("401 when robot not registered", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv();
    const doc = buildIncidentReport(REPORT_INPUT);
    const signed = await signComplianceBody(doc, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(401);
  });

  it("400 on missing sig", async () => {
    const env = makeEnv({ [`robot:${RRN}`]: "{}" });
    const res = await onRequest({ request: req("POST", { schema: INCIDENT_REPORT_SCHEMA, rrn: RRN, pq_kid: "x" }), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });

  it("400 on wrong schema string", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody({ schema: "rcan-ifu-v1", rrn: RRN }, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });

  it("400 on document.rrn != URL rrn", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody({ schema: INCIDENT_REPORT_SCHEMA, rrn: "RRN-000000000999" }, kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(400);
  });

  it("returns 405 on PUT", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("PUT"), env, params: { rrn: RRN } } as any);
    expect(res.status).toBe(405);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/robots/\[rrn\]/incident-report.test.ts
```
Expected: FAIL with "Cannot find module './incident-report.js'".

- [ ] **Step 3: Implement the endpoint**

Create `functions/v2/robots/[rrn]/incident-report.ts`:

```ts
/**
 * /v2/robots/:rrn/incident-report
 * RCAN 3.0 §25 — EU AI Act Art. 72 post-market incident report intake.
 *
 * POST — robot submits a signed incident-report document (snapshot of the
 *        producer's local incident log; re-submitting replaces the current).
 * GET  — Bearer-gated retrieval (reports may contain sensitive incident data).
 *
 * KV key pattern: compliance:incident-report:{rrn}
 *                 compliance:incident-report:history:{rrn}:{ts}
 */

import { INCIDENT_REPORT_SCHEMA } from "rcan-ts";
import { verifyComplianceSubmission } from "../../_lib/compliance-auth.js";

export interface Env {
  RRF_KV: KVNamespace;
}

const TEN_YEARS_SECS = 10 * 365 * 24 * 3600;
const RRN_RE = /^RRN-[0-9]{12}$/;

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const { request, env, params } = ctx;
  const rrn = params["rrn"] as string;

  if (!rrn || !RRN_RE.test(rrn)) return json({ error: "Invalid RRN format" }, 400);

  if (request.method === "GET")  return handleGet(request, env, rrn);
  if (request.method === "POST") return handlePost(request, env, rrn);
  return json({ error: "Method not allowed" }, 405);
};

async function handleGet(request: Request, env: Env, rrn: string): Promise<Response> {
  const auth = request.headers.get("Authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return json({ error: "Authorization required" }, 401);

  const stored = await env.RRF_KV.get(`compliance:incident-report:${rrn}`, "text");
  if (!stored) return json({ error: "Incident report not found", rrn }, 404);
  return new Response(stored, {
    headers: { "Content-Type": "application/json", "Cache-Control": "private, max-age=60" },
  });
}

async function handlePost(request: Request, env: Env, rrn: string): Promise<Response> {
  const result = await verifyComplianceSubmission(request, env, `robot:${rrn}`);
  if (!result.ok) return json({ error: result.error }, result.status);

  const doc = result.document;
  if (doc.schema !== INCIDENT_REPORT_SCHEMA) {
    return json({ error: `Expected schema ${INCIDENT_REPORT_SCHEMA}, got ${String(doc.schema)}` }, 400);
  }
  if (doc.rrn !== rrn) return json({ error: "Document rrn does not match URL rrn" }, 400);

  const now = new Date().toISOString();
  const stored = JSON.stringify({ ...doc, _received_at: now });
  await env.RRF_KV.put(`compliance:incident-report:${rrn}`, stored, { expirationTtl: TEN_YEARS_SECS });
  await env.RRF_KV.put(`compliance:incident-report:history:${rrn}:${Date.now()}`, stored, { expirationTtl: TEN_YEARS_SECS });

  return json({
    ok: true,
    rrn,
    submitted_at: now,
    incident_report_url: `https://api.rrf.rcan.dev/v2/robots/${rrn}/incident-report`,
  }, 201);
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/robots/\[rrn\]/incident-report.test.ts
```
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/RobotRegistryFoundation
git add functions/v2/robots/\[rrn\]/incident-report.ts functions/v2/robots/\[rrn\]/incident-report.test.ts
git commit -m "feat(d2): add §25 incident-report intake endpoint (Art. 72, Bearer-gated GET)"
```

---

### Task 8: EU Register endpoint (§26, models/[rmn] path)

**Files:**
- Create: `RobotRegistryFoundation/functions/v2/models/[rmn]/eu-register.ts`
- Test: `RobotRegistryFoundation/functions/v2/models/[rmn]/eu-register.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `functions/v2/models/[rmn]/eu-register.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import { onRequest } from "./eu-register.js";
import { buildEuRegisterEntry, EU_REGISTER_SCHEMA } from "rcan-ts";
import { signComplianceBody, makeTestKeypair, makeRobotRecord } from "../../_lib/test-helpers.js";

const RRN = "RRN-000000000001";
const RMN = "RMN-000000000007";

function makeEnv(init: Record<string, string> = {}) {
  const store: Record<string, string> = { ...init };
  return {
    RRF_KV: {
      get: vi.fn(async (k: string) => store[k] ?? null),
      put: vi.fn(async (k: string, v: string) => { store[k] = v; }),
      list: vi.fn(), delete: vi.fn(),
    } as unknown as KVNamespace,
    __store: store,
  };
}

function req(method: string, body?: unknown, headers: Record<string, string> = {}): Request {
  return new Request(`https://x/v2/models/${RMN}/eu-register`, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
}

const ENTRY_INPUT = {
  rmn: RMN,
  provider_name: "Example Robotics Ltd",
  provider_address: "1 Robot Way, Dublin, IE",
  provider_contact: "compliance@example.com",
  intended_purpose: "Pick-and-place automation",
  risk_classification: "high",
  generated_at: "2026-04-23T00:00:00Z",
};

describe("GET /v2/models/[rmn]/eu-register", () => {
  it("returns 404 when nothing submitted", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("GET"), env, params: { rmn: RMN } } as any);
    expect(res.status).toBe(404);
  });

  it("returns 400 on invalid RMN format", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("GET"), env, params: { rmn: "bad" } } as any);
    expect(res.status).toBe(400);
  });

  it("returns stored entry with cache header (public)", async () => {
    const env = makeEnv({ [`compliance:eu-register:${RMN}`]: JSON.stringify({ schema: EU_REGISTER_SCHEMA, rmn: RMN }) });
    const res = await onRequest({ request: req("GET"), env, params: { rmn: RMN } } as any);
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toContain("max-age=300");
  });
});

describe("POST /v2/models/[rmn]/eu-register", () => {
  it("stores with _submitted_by_rrn and returns 201 on valid submission", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const doc = buildEuRegisterEntry(ENTRY_INPUT);
    const signed = await signComplianceBody(doc, kp);
    const res = await onRequest({
      request: req("POST", signed, { "X-Submitter-RRN": RRN }),
      env, params: { rmn: RMN },
    } as any);
    expect(res.status).toBe(201);

    const stored = JSON.parse(env.__store[`compliance:eu-register:${RMN}`]);
    expect(stored.rmn).toBe(RMN);
    expect(stored._submitted_by_rrn).toBe(RRN);
    expect(stored._received_at).toBeTypeOf("string");
  });

  it("400 on missing X-Submitter-RRN header", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody(buildEuRegisterEntry(ENTRY_INPUT), kp);
    const res = await onRequest({ request: req("POST", signed), env, params: { rmn: RMN } } as any);
    expect(res.status).toBe(400);
  });

  it("400 on malformed X-Submitter-RRN", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody(buildEuRegisterEntry(ENTRY_INPUT), kp);
    const res = await onRequest({
      request: req("POST", signed, { "X-Submitter-RRN": "bad" }),
      env, params: { rmn: RMN },
    } as any);
    expect(res.status).toBe(400);
  });

  it("401 when submitter robot not registered", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv();
    const signed = await signComplianceBody(buildEuRegisterEntry(ENTRY_INPUT), kp);
    const res = await onRequest({
      request: req("POST", signed, { "X-Submitter-RRN": RRN }),
      env, params: { rmn: RMN },
    } as any);
    expect(res.status).toBe(401);
  });

  it("401 on tampered body", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody(buildEuRegisterEntry(ENTRY_INPUT), kp);
    const res = await onRequest({
      request: req("POST", { ...signed, rmn: "RMN-000000000999" }, { "X-Submitter-RRN": RRN }),
      env, params: { rmn: RMN },
    } as any);
    expect(res.status).toBe(401);
  });

  it("400 on wrong schema string", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody({ schema: "rcan-ifu-v1", rmn: RMN }, kp);
    const res = await onRequest({
      request: req("POST", signed, { "X-Submitter-RRN": RRN }),
      env, params: { rmn: RMN },
    } as any);
    expect(res.status).toBe(400);
  });

  it("400 on document.rmn != URL rmn", async () => {
    const kp = await makeTestKeypair();
    const env = makeEnv({ [`robot:${RRN}`]: makeRobotRecord(RRN, kp) });
    const signed = await signComplianceBody({ schema: EU_REGISTER_SCHEMA, rmn: "RMN-000000000999" }, kp);
    const res = await onRequest({
      request: req("POST", signed, { "X-Submitter-RRN": RRN }),
      env, params: { rmn: RMN },
    } as any);
    expect(res.status).toBe(400);
  });

  it("returns 405 on PUT", async () => {
    const env = makeEnv();
    const res = await onRequest({ request: req("PUT"), env, params: { rmn: RMN } } as any);
    expect(res.status).toBe(405);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/models/\[rmn\]/eu-register.test.ts
```
Expected: FAIL with "Cannot find module './eu-register.js'".

- [ ] **Step 3: Implement the endpoint**

Create `functions/v2/models/[rmn]/eu-register.ts`:

```ts
/**
 * /v2/models/:rmn/eu-register
 * RCAN 3.0 §26 — EU AI Act Art. 49 EU-Register entry intake.
 *
 * Art. 49 registration is legally per-model/per-provider, not per-robot.
 * The submitting robot identifies itself via the `X-Submitter-RRN` header;
 * verifyComplianceSubmission looks up that robot's `pq_signing_pub`.
 *
 * POST — robot submits a signed EU-register entry for a model (rmn).
 * GET  — public retrieval of the current entry (Art. 49 transparency).
 *
 * KV key pattern: compliance:eu-register:{rmn}
 *                 compliance:eu-register:history:{rmn}:{ts}
 */

import { EU_REGISTER_SCHEMA } from "rcan-ts";
import { verifyComplianceSubmission } from "../../_lib/compliance-auth.js";

export interface Env {
  RRF_KV: KVNamespace;
}

const TEN_YEARS_SECS = 10 * 365 * 24 * 3600;
const RRN_RE = /^RRN-[0-9]{12}$/;
const RMN_RE = /^RMN-[0-9]{12}$/;

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const { request, env, params } = ctx;
  const rmn = params["rmn"] as string;

  if (!rmn || !RMN_RE.test(rmn)) return json({ error: "Invalid RMN format" }, 400);

  if (request.method === "GET")  return handleGet(env, rmn);
  if (request.method === "POST") return handlePost(request, env, rmn);
  return json({ error: "Method not allowed" }, 405);
};

async function handleGet(env: Env, rmn: string): Promise<Response> {
  const stored = await env.RRF_KV.get(`compliance:eu-register:${rmn}`, "text");
  if (!stored) return json({ error: "EU register entry not found", rmn }, 404);
  return new Response(stored, {
    headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=300" },
  });
}

async function handlePost(request: Request, env: Env, rmn: string): Promise<Response> {
  const submitterRrn = request.headers.get("X-Submitter-RRN") ?? "";
  if (!submitterRrn) return json({ error: "Missing X-Submitter-RRN header" }, 400);
  if (!RRN_RE.test(submitterRrn)) return json({ error: "Invalid X-Submitter-RRN format" }, 400);

  const result = await verifyComplianceSubmission(request, env, `robot:${submitterRrn}`);
  if (!result.ok) return json({ error: result.error }, result.status);

  const doc = result.document;
  if (doc.schema !== EU_REGISTER_SCHEMA) {
    return json({ error: `Expected schema ${EU_REGISTER_SCHEMA}, got ${String(doc.schema)}` }, 400);
  }
  if (doc.rmn !== rmn) return json({ error: "Document rmn does not match URL rmn" }, 400);

  const now = new Date().toISOString();
  // Provenance metadata (NOT part of signed payload).
  const stored = JSON.stringify({ ...doc, _received_at: now, _submitted_by_rrn: submitterRrn });
  await env.RRF_KV.put(`compliance:eu-register:${rmn}`, stored, { expirationTtl: TEN_YEARS_SECS });
  await env.RRF_KV.put(`compliance:eu-register:history:${rmn}:${Date.now()}`, stored, { expirationTtl: TEN_YEARS_SECS });

  return json({
    ok: true,
    rmn,
    submitted_by_rrn: submitterRrn,
    submitted_at: now,
    eu_register_url: `https://api.rrf.rcan.dev/v2/models/${rmn}/eu-register`,
  }, 201);
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run functions/v2/models/\[rmn\]/eu-register.test.ts
```
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/craigm26/RobotRegistryFoundation
git add functions/v2/models/\[rmn\]/eu-register.ts functions/v2/models/\[rmn\]/eu-register.test.ts
git commit -m "feat(d2): add §26 EU-register entry intake (/v2/models/[rmn]/eu-register)"
```

---

## Wave 3: Integration Smoke

### Task 9: End-to-end smoke test across all five endpoints

**Files:**
- Create: `RobotRegistryFoundation/tests/compliance-intake.smoke.test.ts`
- Modify: `RobotRegistryFoundation/vitest.config.ts` (only if needed to include `tests/**/*.test.ts`)

- [ ] **Step 1: Confirm vitest picks up the tests/ directory**

```bash
cd /home/craigm26/RobotRegistryFoundation
grep -A5 "include\|test:" vitest.config.ts
```
If `tests/**/*.test.ts` is not included, add it to the `test.include` array; otherwise skip.

- [ ] **Step 2: Write the smoke test**

Create `tests/compliance-intake.smoke.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import {
  buildSafetyBenchmark, buildIfu, buildIncidentReport, buildEuRegisterEntry,
  SAFETY_BENCHMARK_SCHEMA, IFU_SCHEMA, INCIDENT_REPORT_SCHEMA, EU_REGISTER_SCHEMA,
} from "rcan-ts";
import { onRequest as sbHandler } from "../functions/v2/robots/[rrn]/safety-benchmark.js";
import { onRequest as ifuHandler } from "../functions/v2/robots/[rrn]/ifu.js";
import { onRequest as friaHandler } from "../functions/v2/robots/[rrn]/fria.js";
import { onRequest as incHandler } from "../functions/v2/robots/[rrn]/incident-report.js";
import { onRequest as euHandler } from "../functions/v2/models/[rmn]/eu-register.js";
import { signComplianceBody, makeTestKeypair, makeRobotRecord } from "../functions/v2/_lib/test-helpers.js";

const RRN = "RRN-000000000001";
const RMN = "RMN-000000000007";

function makeSharedEnv() {
  const store: Record<string, string> = {};
  return {
    RRF_KV: {
      get: vi.fn(async (k: string) => store[k] ?? null),
      put: vi.fn(async (k: string, v: string) => { store[k] = v; }),
      list: vi.fn(), delete: vi.fn(),
    } as unknown as KVNamespace,
    __store: store,
  };
}

describe("compliance intake end-to-end smoke", () => {
  it("round-trips all five endpoints with a single registered robot", async () => {
    const kp = await makeTestKeypair();
    const env = makeSharedEnv();
    env.__store[`robot:${RRN}`] = makeRobotRecord(RRN, kp);

    // §23 Safety Benchmark — public GET
    {
      const doc = buildSafetyBenchmark({
        rrn: RRN, benchmark_version: "1.0", test_suite_id: "suite-a",
        executed_at: "2026-04-23T00:00:00Z", pass_count: 10, fail_count: 0, skip_count: 0,
      });
      const signed = await signComplianceBody(doc, kp);
      const postRes = await sbHandler({ request: mkReq("POST", `/v2/robots/${RRN}/safety-benchmark`, signed), env, params: { rrn: RRN } } as any);
      expect(postRes.status).toBe(201);
      const getRes = await sbHandler({ request: mkReq("GET", `/v2/robots/${RRN}/safety-benchmark`), env, params: { rrn: RRN } } as any);
      expect(getRes.status).toBe(200);
      const retrieved = await getRes.json() as any;
      expect(retrieved.schema).toBe(SAFETY_BENCHMARK_SCHEMA);
      expect(retrieved.rrn).toBe(RRN);
    }

    // §24 IFU — public GET
    {
      const doc = buildIfu({
        rrn: RRN, ifu_version: "1.0", intended_use: "smoke", operator_qualifications: [],
        residual_risks: [], safety_instructions: [], maintenance_schedule: "x",
        contact_manufacturer: "x", generated_at: "2026-04-23T00:00:00Z",
      });
      const signed = await signComplianceBody(doc, kp);
      const postRes = await ifuHandler({ request: mkReq("POST", `/v2/robots/${RRN}/ifu`, signed), env, params: { rrn: RRN } } as any);
      expect(postRes.status).toBe(201);
      const getRes = await ifuHandler({ request: mkReq("GET", `/v2/robots/${RRN}/ifu`), env, params: { rrn: RRN } } as any);
      expect(getRes.status).toBe(200);
      expect(((await getRes.json()) as any).schema).toBe(IFU_SCHEMA);
    }

    // §22 FRIA — Bearer-gated GET
    {
      const friaDoc = {
        schema: "rcan-fria-v1", rrn: RRN, generated_at: "2026-04-23T00:00:00Z",
        risk_category: "high", affected_rights: ["privacy"],
        mitigation_measures: [], signing_key: { alg: "ml-dsa-65", pq_kid: "abcd1234" },
      };
      const signed = await signComplianceBody(friaDoc, kp);
      const postRes = await friaHandler({ request: mkReq("POST", `/v2/robots/${RRN}/fria`, signed), env, params: { rrn: RRN } } as any);
      expect(postRes.status).toBe(201);
      const noAuth = await friaHandler({ request: mkReq("GET", `/v2/robots/${RRN}/fria`), env, params: { rrn: RRN } } as any);
      expect(noAuth.status).toBe(401);
      const getRes = await friaHandler({ request: mkReq("GET", `/v2/robots/${RRN}/fria`, undefined, { Authorization: "Bearer t" }), env, params: { rrn: RRN } } as any);
      expect(getRes.status).toBe(200);
    }

    // §25 Incident Report — Bearer-gated GET
    {
      const doc = buildIncidentReport({
        rrn: RRN, reporting_period_start: "2026-04-01T00:00:00Z",
        reporting_period_end: "2026-04-23T00:00:00Z",
        incidents: [{ timestamp: "2026-04-10T12:00:00Z", severity: "other", description: "jam" }],
        generated_at: "2026-04-23T00:00:00Z",
      });
      const signed = await signComplianceBody(doc, kp);
      const postRes = await incHandler({ request: mkReq("POST", `/v2/robots/${RRN}/incident-report`, signed), env, params: { rrn: RRN } } as any);
      expect(postRes.status).toBe(201);
      const getRes = await incHandler({ request: mkReq("GET", `/v2/robots/${RRN}/incident-report`, undefined, { Authorization: "Bearer t" }), env, params: { rrn: RRN } } as any);
      expect(getRes.status).toBe(200);
      expect(((await getRes.json()) as any).schema).toBe(INCIDENT_REPORT_SCHEMA);
    }

    // §26 EU Register — public GET, X-Submitter-RRN header
    {
      const doc = buildEuRegisterEntry({
        rmn: RMN, provider_name: "x", provider_address: "x", provider_contact: "x",
        intended_purpose: "x", risk_classification: "high",
        generated_at: "2026-04-23T00:00:00Z",
      });
      const signed = await signComplianceBody(doc, kp);
      const postRes = await euHandler({
        request: mkReq("POST", `/v2/models/${RMN}/eu-register`, signed, { "X-Submitter-RRN": RRN }),
        env, params: { rmn: RMN },
      } as any);
      expect(postRes.status).toBe(201);
      const getRes = await euHandler({ request: mkReq("GET", `/v2/models/${RMN}/eu-register`), env, params: { rmn: RMN } } as any);
      expect(getRes.status).toBe(200);
      const retrieved = await getRes.json() as any;
      expect(retrieved.schema).toBe(EU_REGISTER_SCHEMA);
      expect(retrieved.rmn).toBe(RMN);
      expect(retrieved._submitted_by_rrn).toBe(RRN);
    }
  });
});

function mkReq(method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Request {
  return new Request(`https://x${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
}
```

- [ ] **Step 3: Run smoke test**

```bash
cd /home/craigm26/RobotRegistryFoundation
npx vitest run tests/compliance-intake.smoke.test.ts
```
Expected: PASS (1 test, covers all five endpoints).

- [ ] **Step 4: Commit**

```bash
cd /home/craigm26/RobotRegistryFoundation
git add tests/compliance-intake.smoke.test.ts
# also add vitest.config.ts if modified in Step 1
git commit -m "test(d2): add end-to-end smoke across all five compliance endpoints"
```

---

## Wave 4: Documentation

### Task 10: Update README.md with compliance intake section

**Files:**
- Modify: `RobotRegistryFoundation/README.md`

- [ ] **Step 1: Add a new "Compliance Intake (RCAN §22-26)" section**

Add this section to `README.md` after the existing API documentation or endpoints section (pick the location that matches current README structure):

````markdown
## Compliance Intake (RCAN §22-26)

Robots registered under [`/v2/robots/register`](#registration) can submit EU AI Act compliance artifacts produced by the [`rcan-ts`](https://www.npmjs.com/package/rcan-ts) 3.2.0+ builders.

### Endpoints

| Endpoint | RCAN § | GET access |
|---|---|---|
| `POST /v2/robots/:rrn/fria` | §22 FRIA | Bearer-gated |
| `POST /v2/robots/:rrn/safety-benchmark` | §23 Safety Benchmark | public |
| `POST /v2/robots/:rrn/ifu` | §24 Instructions For Use (Art. 13(3)) | public |
| `POST /v2/robots/:rrn/incident-report` | §25 Post-Market Incident Report (Art. 72) | Bearer-gated |
| `POST /v2/models/:rmn/eu-register` | §26 EU Register Entry (Art. 49) | public |

All five have a matching `GET` at the same path.

### Happy path (POST)

```
Producer (robot)
  ├─ build doc:  doc = buildSafetyBenchmark({ rrn, ... })
  ├─ sign doc:   signed = await signBody(keypair, doc, { ed25519Secret, ed25519Public })
  └─ POST /v2/robots/{rrn}/safety-benchmark
     body: { ...doc, pq_signing_pub, pq_kid, sig: { ml_dsa, ed25519, ed25519_pub } }

RRF
  ├─ loads robot:{rrn} from KV, extracts pq_signing_pub
  ├─ verifyBody(signed, pq_signing_pub)           → 401 on sig failure
  ├─ checks doc.schema, doc.rrn                    → 400 on mismatch
  ├─ stores at compliance:safety-benchmark:{rrn}
  └─ appends snapshot at compliance:safety-benchmark:history:{rrn}:{ts}
     → 201 { ok, rrn, submitted_at, safety_benchmark_url }
```

EU Register uses `X-Submitter-RRN` header instead of URL rrn (since Art. 49 registration is per-model); stored docs carry `_submitted_by_rrn` for provenance.

### Auth

POST requires a signed body (ML-DSA-65 + Ed25519) against the robot's registered `pq_signing_pub`. No Bearer token needed for POST — the signature IS the auth. See the [registration flow](#registration) for how `pq_signing_pub` gets registered.

GET is public for transparency types (safety-benchmark, ifu, eu-register); Bearer-gated for FRIA and incident-report (may contain sensitive content).

### Retention

10-year TTL on both current and history keys, matching Art. 72 record-keeping obligations for high-risk AI systems.
````

- [ ] **Step 2: Verify the README still renders cleanly**

```bash
cd /home/craigm26/RobotRegistryFoundation
head -5 README.md                     # sanity check
```

- [ ] **Step 3: Commit**

```bash
cd /home/craigm26/RobotRegistryFoundation
git add README.md
git commit -m "docs(d2): README section for compliance intake endpoints (§22-26)"
```

---

### Task 11: Update API docs page (src/pages/api/index.astro)

**Files:**
- Modify: `RobotRegistryFoundation/src/pages/api/index.astro`

- [ ] **Step 1: Inspect current API docs layout**

```bash
cd /home/craigm26/RobotRegistryFoundation
head -80 src/pages/api/index.astro
```
Note the patterns used for endpoint headings, code fences, and example request/response bodies. Reuse the same patterns — do not introduce a new style.

- [ ] **Step 2: Add a "Compliance Intake (RCAN §22-26)" section**

Insert after the existing endpoint documentation, using the same Astro heading / code block conventions as the file's firmware-manifest / sbom sections. The section should include:

- Overview paragraph (what these endpoints are, when to use them)
- Table of endpoints with GET access policy column (same 5-row table as README Task 10)
- Request example (one example, using `/v2/robots/:rrn/safety-benchmark`):

```json
{
  "schema": "rcan-safety-benchmark-v1",
  "rrn": "RRN-000000000001",
  "benchmark_version": "1.0",
  "test_suite_id": "suite-a",
  "executed_at": "2026-04-23T00:00:00Z",
  "pass_count": 10,
  "fail_count": 0,
  "skip_count": 0,
  "generated_at": "2026-04-23T00:00:00Z",
  "pq_signing_pub": "<base64>",
  "pq_kid": "abcd1234",
  "sig": {
    "ml_dsa": "<base64>",
    "ed25519": "<base64>",
    "ed25519_pub": "<base64>"
  }
}
```

- Response example:

```json
{
  "ok": true,
  "rrn": "RRN-000000000001",
  "submitted_at": "2026-04-23T12:34:56.789Z",
  "safety_benchmark_url": "https://api.rrf.rcan.dev/v2/robots/RRN-000000000001/safety-benchmark"
}
```

- Note on EU Register's `X-Submitter-RRN` header requirement
- Link to `rcan-ts` npm package for producer tooling

- [ ] **Step 3: Verify site builds**

```bash
cd /home/craigm26/RobotRegistryFoundation
npm run build
```
Expected: clean Astro build, no errors.

- [ ] **Step 4: Commit**

```bash
cd /home/craigm26/RobotRegistryFoundation
git add src/pages/api/index.astro
git commit -m "docs(d2): API page coverage for compliance intake endpoints"
```

---

## Wave 5: Ship

### Task 12: Full test suite + typecheck

**Files:** (none to modify — verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd /home/craigm26/RobotRegistryFoundation
npm test
```
Expected: ALL tests pass, including the previously-existing ~N tests PLUS:
- 2 test-helpers
- 7 compliance-auth
- 9 safety-benchmark
- 9 ifu
- 12 fria
- 12 incident-report
- 11 eu-register
- 1 smoke

Total new: ~63 tests. Existing RRF suite must remain unchanged and green.

- [ ] **Step 2: Full build**

```bash
cd /home/craigm26/RobotRegistryFoundation
npm run build
```
Expected: Astro build clean, `dist/` created, no TypeScript errors.

- [ ] **Step 3: If anything fails, STOP and fix before proceeding**

Do not push broken code. If a test fails, diagnose root cause before the next task.

---

### Task 13: Merge to main and auto-deploy via Cloudflare Pages

**Files:** (none to modify — deploy only)

- [ ] **Step 1: Confirm on main, all D2 commits staged**

```bash
cd /home/craigm26/RobotRegistryFoundation
git log --oneline origin/main..HEAD
```
Expected: ~13 D2 commits (one per task, plus the chore/dep bump).

- [ ] **Step 2: Push to origin/main**

```bash
cd /home/craigm26/RobotRegistryFoundation
git push origin main
```
Expected: push accepted. Cloudflare Pages watches `main` and auto-deploys.

- [ ] **Step 3: Monitor Cloudflare Pages deployment**

```bash
# Wait ~2 minutes, then verify:
curl -s -o /dev/null -w "%{http_code}\n" https://robotregistryfoundation.org/v2/robots/RRN-000000000001/safety-benchmark
```
Expected: `404` (nothing submitted yet), NOT `405` (route not wired up) and NOT `500`.

Check each endpoint returns 404 (not 405/500):

```bash
for ep in safety-benchmark ifu fria incident-report; do
  echo -n "$ep: "
  curl -s -o /dev/null -w "%{http_code}\n" https://robotregistryfoundation.org/v2/robots/RRN-000000000001/$ep
done
echo -n "eu-register: "
curl -s -o /dev/null -w "%{http_code}\n" https://robotregistryfoundation.org/v2/models/RMN-000000000007/eu-register
```

Expected all endpoints → 404 (fria/incident-report may → 401 if Bearer-gating is applied before KV lookup; 404 is also fine; both are acceptable "route is live, nothing stored yet" signals).

- [ ] **Step 4: Commit deployment note to CHANGELOG**

Edit `CHANGELOG.md`, add entry (follow existing date/version convention in the file):

```markdown
## Compliance Intake (Release D2) — 2026-04-23

### Added
- `POST|GET /v2/robots/:rrn/fria` — §22 FRIA intake (Bearer-gated GET)
- `POST|GET /v2/robots/:rrn/safety-benchmark` — §23 intake
- `POST|GET /v2/robots/:rrn/ifu` — §24 IFU intake
- `POST|GET /v2/robots/:rrn/incident-report` — §25 Art. 72 report intake (Bearer-gated GET)
- `POST|GET /v2/models/:rmn/eu-register` — §26 Art. 49 entry intake
- Shared helper `verifyComplianceSubmission` reusing `verifyBody` from rcan-ts 3.2.0

### Changed
- `rcan-ts` dependency bumped to `^3.2.0` to pick up compliance builders + schema constants

### Retention
- 10-year TTL on compliance KV keys (Art. 72 record-keeping)
```

```bash
cd /home/craigm26/RobotRegistryFoundation
git add CHANGELOG.md
git commit -m "docs(d2): CHANGELOG entry for Release D2"
git push origin main
```

---

### Task 14: Bob live validation milestone (manual, not automated)

**Files:** (none to modify — live validation)

This task is manual and can be deferred. It is the "first real producer" milestone.

- [ ] **Step 1: On Bob (RPi5 with OpenCastor)**

Ensure Bob has:
- `rcan-ts@^3.2.0` installed
- Access to his registered ML-DSA-65 keypair (same keys that signed `/v2/robots/register`)
- Network path to `api.rrf.rcan.dev`

- [ ] **Step 2: Build and submit a real Safety Benchmark**

On Bob, write a small one-shot script (not production code — a validation oneshot):

```ts
import { buildSafetyBenchmark, signBody } from "rcan-ts";

const doc = buildSafetyBenchmark({
  rrn: "RRN-000000000001",
  benchmark_version: "1.0",
  test_suite_id: "opencastor-selftest",
  executed_at: new Date().toISOString(),
  pass_count: /* actual self-test results */ 0,
  fail_count: 0,
  skip_count: 0,
});

const signed = await signBody(bobKeypair, doc, { ed25519Secret, ed25519Public });

const res = await fetch("https://api.rrf.rcan.dev/v2/robots/RRN-000000000001/safety-benchmark", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(signed),
});
console.log(res.status, await res.json());
```

Expected: `201 { ok: true, rrn: "RRN-000000000001", submitted_at: "...", safety_benchmark_url: "..." }`.

- [ ] **Step 3: Verify GET round-trip**

```bash
curl -s https://api.rrf.rcan.dev/v2/robots/RRN-000000000001/safety-benchmark | jq .
```
Expected: the submitted document byte-identical to what Bob sent (minus the envelope fields, plus `_received_at`).

- [ ] **Step 4: Update auto-memory**

Once Bob has successfully submitted, update the user's memory file `project_robot_md_v080_state.md` to reflect: "Release D2 shipped; Bob is the first producer of compliance artifacts against production RRF."

This closes the D1+D2 arc: rcan-ts builds → Bob signs → RRF stores + serves.

---

## Self-Review Notes

Check against spec `docs/superpowers/specs/2026-04-23-release-d2-rrf-compliance-intake-design.md`:

- ✅ **Scope (5 endpoints)**: Tasks 4-8, one per compliance type
- ✅ **Shared auth helper**: Task 3 (`verifyComplianceSubmission`)
- ✅ **Test signing helper**: Task 2 (`signComplianceBody`, `makeTestKeypair`, `makeRobotRecord`)
- ✅ **KV schema + 10-year TTL**: specified in every handler's constants + tests assert history keys written
- ✅ **Per-type GET policy**: fria.ts + incident-report.ts have explicit Bearer check in `handleGet`; others do not
- ✅ **Liberal validation**: `doc.schema === EXPECTED_SCHEMA` + rrn/rmn match, accept extras — no builder round-trip on server
- ✅ **EU Register special case**: Task 8 — `X-Submitter-RRN` header, `_submitted_by_rrn` metadata
- ✅ **Error handling table**: status codes match spec (400/401/404/405/500)
- ✅ **Tests: ~60 unit + 1 smoke**: actual totals line up (63 unit + 1 smoke)
- ✅ **Docs deliverables**: Task 10 (README), Task 11 (API page)
- ✅ **CHANGELOG**: Task 13, Step 4
- ✅ **rcan-ts bump**: Task 1

No placeholders. All method signatures match between helper tests (Task 3) and helper implementation (Task 3), between handler tests and handlers (Tasks 4-8). `signComplianceBody` is defined once in Task 2 and referenced consistently.

One deliberate open item: FRIA_SCHEMA is inlined as `"rcan-fria-v1"` string in Task 6 rather than imported — spec explicitly calls this out as a future rcan-ts 3.3.0 sweep. Not a defect.

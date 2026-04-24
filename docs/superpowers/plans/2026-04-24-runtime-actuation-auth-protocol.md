# Runtime Actuation Auth Protocol — Design + Reference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement the opencastor reference (Tasks R1–R8) and CLI parity (Tasks C1–C4). The LeRobot / ROS2 / Reachy Mini integration sections are specification notes, not code tasks.

**Goal:** Define and implement a protocol by which "authorized users can actuate" a registered robot, where the robot's RRF identity (`pq_signing_pub`) is the root of trust and local runtimes (opencastor, LeRobot, ROS2, Reachy Mini) all enforce the same delegation check before accepting motor commands.

**Architecture (one paragraph):** The robot's RRF signing keypair delegates command authority to one or more *operator principals* via a short signed blob that declares scope + expiry. A runtime loads its delegation list from `robot.rcan.yaml` (authoritative) and/or `~/.robot-md/delegations/<rrn>.json` (operator-side cache). Every actuation command is wrapped in a lightweight Ed25519-signed envelope that names the operator pubkey; the runtime verifies (a) signature valid, (b) pubkey is in the delegation list and not revoked, (c) requested scope ⊆ delegated scope, (d) not expired. Runtime-specific adapters (opencastor `castor.auth.operator`, LeRobot `rcan_lerobot_bridge.auth`, ROS2 lifecycle node) implement a common `authorize(cmd) -> AuthResult` interface; the verifier itself lives in a shared `rcan-py` module so every runtime uses identical logic.

**Tech Stack:** rcan-py (Python), rcan-ts (TypeScript for web operators), Ed25519 (already in rcan crypto), ML-DSA (already used for the robot's signing key), YAML config.

**Codebases touched:**
- `rcan-spec/` — new §27 "Operator Delegation" (spec authority)
- `rcan-py/` — new `rcan.auth.operator` module (shared verifier)
- `opencastor/` — reference integration into the command dispatch path
- `robot-md/cli/` — `robot-md operator {enroll, list, revoke}` subcommands
- `lerobot-rcan-bridge/` (new, optional) — wrapper for LeRobot runtime
- Documentation-only entries for ROS2 and Reachy Mini

**Non-goals for this plan:**
- Replacing HiTL gates (§8) — those stay as-is; operator auth runs *before* HiTL, not instead.
- Network-level auth between runtimes (TLS, mTLS) — orthogonal; operator auth is application-layer.
- Account recovery if all keys are lost — same policy as RRF: no out-of-band recovery.

---

## Pre-flight

```bash
cd ~/rcan-spec && git status           # clean
cd ~/rcan-py && pytest                 # baseline green
cd ~/opencastor && pytest -q           # baseline green
cd ~/robot-md/cli && pytest -q         # baseline green
```

If any baseline fails, stop and flag.

---

## Part 1 — Design (spec-level decisions, locked before any code)

### 1.1 What is an "operator"?

An operator is a *device* (a laptop, a phone, a web dashboard, a field tablet) that holds an Ed25519 keypair and has been delegated by the robot's signing key to issue commands on its behalf. Operators are **per-device**, not per-human. A human with two devices enrolls each separately. This keeps key-compromise blast radius small and avoids needing a user-identity concept outside what the robot's own key asserts.

### 1.2 Delegation envelope (canonical format)

Signed with the robot's `pq_signing_pub` (ML-DSA + Ed25519 hybrid, same algorithm as RCAN §22-26):

```json
{
  "schema": "rcan-operator-delegation-v1",
  "rrn": "RRN-000000000001",
  "operator_pub": "<base64 Ed25519 public key>",
  "operator_name": "alice-laptop",
  "scopes": ["move", "grip", "tts"],
  "issued_at": "2026-04-24T12:00:00Z",
  "expires_at": "2026-07-24T12:00:00Z",
  "max_ops_per_minute": 60,
  "sig": { "ml_dsa": "...", "ed25519": "...", "ed25519_pub": "..." },
  "pq_kid": "<current robot pq_kid>"
}
```

Scope vocabulary is defined in `rcan-spec §27` (this plan ships the initial set): `move`, `grip`, `tts`, `camera-stream`, `config-read`, `config-write`, `reset`, `shutdown`, `all` (only for admin/recovery operators; emits an audit event every time it's used).

### 1.3 Command envelope (canonical format)

Signed with the *operator's* Ed25519:

```json
{
  "schema": "rcan-command-v1",
  "rrn": "RRN-000000000001",
  "operator_pub": "<base64 Ed25519 public key>",
  "nonce": "<16 random bytes, base64>",
  "issued_at": "2026-04-24T12:05:00Z",
  "scope": "move",
  "cmd": { /* runtime-specific payload */ },
  "sig": "<base64 Ed25519 signature over canonical json minus sig>"
}
```

Every command carries its own signature. Sessions are *not* introduced in v1 — every command is independently verifiable and replay-protected via `nonce` + `issued_at` window (±60 s default). This is simpler than session tokens and has no token-theft surface. If bandwidth becomes an issue in a later revision, sessions can be added.

### 1.4 Revocation of operator delegations

Two overlapping mechanisms:

1. **Local** — delete the delegation from `robot.rcan.yaml`. Immediate, no external calls. This is the 99% case (operator loses laptop; owner edits yaml and restarts runtime).
2. **RRF-published revocation list** — optional. Robot owner `POST`s a signed revocation to `POST /v2/robots/<rrn>/operator-revoke` (future RRF endpoint, out of scope for this plan) that publishes the operator pubkey as globally revoked. Runtimes that choose to consult RRF periodically can pick this up.

This plan ships mechanism #1 only. Mechanism #2 is a followup; noted here so v1 doesn't paint us into a corner (nothing in v1 prevents it).

### 1.5 Where the verifier lives

**In `rcan-py` (and `rcan-ts` for web).** Every runtime imports the same verifier. This is non-negotiable — if verification logic diverges between runtimes, the protocol is dead.

### 1.6 Binding to RRF tier-gated write-auth

This plan assumes the robot's `pq_signing_pub` is already registered on RRF (via the existing register flow). It does *not* require `verification_status` to be anything in particular — even an `unverified` robot can have operators. The tier affects *how much the RRF manifest can be trusted by outsiders*, not how the local runtime authorizes commands.

If the robot's RRF key is *rotated* (via the write-auth plan's rotate-key endpoint), all existing operator delegations become invalid at the expiry/verification layer — they are signed by the old key. A rotate triggers re-enrollment. This is acceptable friction because rotation is a rare operator-initiated event. (Alternative: allow the rotate-key payload to optionally re-sign existing delegations. Rejected for v1: adds complexity and a partial-failure mode.)

---

## Part 2 — rcan-spec §27 authoring

### Task S1: Draft `rcan-spec/spec/sections/27-operator-delegation.md`

**Files:**
- Create: `rcan-spec/spec/sections/27-operator-delegation.md`
- Modify: `rcan-spec/src/pages/spec/index.astro` (add section-27 link)
- Modify: `rcan-spec/src/pages/changelog.astro` (v3.3 entry: "§27 Operator Delegation")
- Modify: `rcan-spec/src/pages/about.astro` (version timeline)
- Modify: `rcan-spec/public/sdk-status.json` (`spec_version: "3.3"`)

- [ ] **Step 1:** Write the section markdown using the canonical format from Part 1 (§1.2, §1.3, §1.4). Include:
  - Scope vocabulary table.
  - Delegation envelope schema.
  - Command envelope schema.
  - Verifier pseudocode (language-agnostic).
  - Conformance requirements (L2+ runtimes MUST enforce).
  - Security considerations — nonce window, clock skew, scope escalation, operator-pub enumeration.
- [ ] **Step 2:** `npm run build && npx vitest run tests/functions.test.ts` — must pass clean.
- [ ] **Step 3:** Commit `spec(v3.3): add §27 Operator Delegation`.

(No TDD code in this task — it's a spec authoring task. The "tests" are the build succeeding and any existing conformance tests continuing to pass.)

---

## Part 3 — rcan-py reference verifier (single source of truth)

### Task R1: `rcan/auth/operator.py` — data types

**Files:**
- Create: `rcan-py/src/rcan/auth/__init__.py`
- Create: `rcan-py/src/rcan/auth/operator.py`
- Create: `rcan-py/tests/auth/test_operator_types.py`

- [ ] **Step 1: Write failing tests** — dataclasses for `OperatorDelegation` and `OperatorCommand`, `from_dict` / `to_canonical_bytes` helpers. Round-trip test: `OperatorDelegation.from_dict(d).to_dict() == d`.

```python
# tests/auth/test_operator_types.py
import pytest
from rcan.auth.operator import OperatorDelegation, OperatorCommand

def test_delegation_roundtrip():
    d = {
        "schema": "rcan-operator-delegation-v1",
        "rrn": "RRN-000000000001",
        "operator_pub": "AAAA",
        "operator_name": "alice-laptop",
        "scopes": ["move", "grip"],
        "issued_at": "2026-04-24T12:00:00Z",
        "expires_at": "2026-07-24T12:00:00Z",
        "max_ops_per_minute": 60,
        "pq_kid": "abcd1234",
        "sig": {"ml_dsa": "xx", "ed25519": "yy", "ed25519_pub": "zz"},
    }
    dg = OperatorDelegation.from_dict(d)
    assert dg.to_dict() == d

def test_command_canonical_bytes_excludes_sig():
    c = OperatorCommand(
        rrn="RRN-000000000001",
        operator_pub="AAAA",
        nonce="BBBB",
        issued_at="2026-04-24T12:05:00Z",
        scope="move",
        cmd={"dx": 0.1, "dy": 0.0},
        sig="CCCC",
    )
    assert b'"sig"' not in c.to_canonical_bytes()
    assert b'"operator_pub"' in c.to_canonical_bytes()
```

- [ ] **Step 2: Verify RED** — `pytest tests/auth/test_operator_types.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Implement** `rcan/auth/operator.py` with dataclasses + `canonical_json` reuse from existing `rcan.crypto`.

- [ ] **Step 4: Verify GREEN.**

- [ ] **Step 5: Commit** `feat(rcan-py): OperatorDelegation/OperatorCommand types`.

---

### Task R2: `verify_delegation(delegation, robot_pq_pub) -> bool`

- [ ] **Step 1: Tests**
  - Valid delegation signed by robot pq key → True.
  - Tampered `scopes` → False.
  - Tampered `operator_pub` → False.
  - Wrong pq key → False.
  - Expired `expires_at` → False (verifier checks time window).
  - `issued_at` in the future → False.

- [ ] **Step 2: Verify RED.**

- [ ] **Step 3: Implement** using existing `rcan.crypto.verify_hybrid`. Expiry check uses `datetime.now(UTC)`.

- [ ] **Step 4: Verify GREEN.**

- [ ] **Step 5: Commit** `feat(rcan-py): verify_delegation`.

---

### Task R3: `verify_command(command, known_operators, max_skew_sec=60) -> AuthResult`

Where `known_operators` is `list[OperatorDelegation]` already pre-verified (checked by the caller before caching).

**AuthResult:** dataclass `{ok: bool, reason: str | None, matched_delegation: OperatorDelegation | None}`.

- [ ] **Step 1: Tests**
  - Command signed by known operator, scope ⊆ delegated scopes, within time window → `ok=True`.
  - Command `operator_pub` not in any delegation → `ok=False, reason="unknown operator"`.
  - Matching operator but scope not in delegation → `ok=False, reason="scope"`.
  - Expired delegation (even if command is fresh) → `ok=False, reason="delegation expired"`.
  - `issued_at` > 60 s in future → `ok=False, reason="skew"`.
  - `issued_at` > 60 s in past → `ok=False, reason="skew"`.
  - Tampered signature → `ok=False, reason="signature"`.
  - Rate limit exceeded (pass in a counter) → `ok=False, reason="rate"`. **(Defer to follow-up; Task R3 ships the signature-correctness path and returns `rate=None`; rate enforcement is Task R7.)**

- [ ] **Step 2: Verify RED.**

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Verify GREEN.**

- [ ] **Step 5: Commit** `feat(rcan-py): verify_command with scope + skew checks`.

---

### Task R4: `sign_delegation(delegation_body, robot_keypair) -> OperatorDelegation`

Issuer-side helper — generates the `sig` field. Mirror of `verify_delegation`.

TDD pattern same as R2: round-trip test (`sign_delegation` then `verify_delegation` → True).

Commit: `feat(rcan-py): sign_delegation issuer helper`.

---

### Task R5: `sign_command(cmd_body, operator_ed25519_sec) -> OperatorCommand`

Operator-side helper. Round-trip test with `verify_command`.

Commit: `feat(rcan-py): sign_command operator helper`.

---

### Task R6: Nonce replay cache (`NonceCache`)

**Files:**
- Create: `rcan-py/src/rcan/auth/nonce_cache.py`
- Create: `rcan-py/tests/auth/test_nonce_cache.py`

In-memory deque+set with TTL == `2 * max_skew_sec` (nonces expire after the skew window closes). Used by runtime adapters, not by `verify_command` itself (keeps the verifier pure).

Tests: accepts first use, rejects second use within TTL, accepts same nonce after TTL, bounded memory (drops oldest when size cap hit).

Commit: `feat(rcan-py): NonceCache for command replay prevention`.

---

### Task R7: Rate-limit helper (`RateLimiter`)

Token-bucket per operator_pub. Per-delegation `max_ops_per_minute` is the bucket capacity. `RateLimiter.check(operator_pub, rate)` returns True if under budget.

Commit: `feat(rcan-py): RateLimiter for per-operator actuation budget`.

---

### Task R8: `AuthGuard` — glue class

**Files:**
- Create: `rcan-py/src/rcan/auth/guard.py`

```python
class AuthGuard:
    """One-stop auth for a runtime. Holds delegations, nonce cache, rate limiter.
    Runtime calls .check(command) → AuthResult."""

    def __init__(self, robot_pq_pub: bytes):
        self._delegations: list[OperatorDelegation] = []
        self._nonce_cache = NonceCache()
        self._rate = RateLimiter()
        self._robot_pq_pub = robot_pq_pub

    def load_delegations(self, delegations: list[dict]) -> None:
        verified: list[OperatorDelegation] = []
        for d in delegations:
            dg = OperatorDelegation.from_dict(d)
            if verify_delegation(dg, self._robot_pq_pub):
                verified.append(dg)
        self._delegations = verified

    def check(self, command: OperatorCommand) -> AuthResult: ...
```

Test `AuthGuard.check` end-to-end: load delegations, sign command, check → ok. Then: replay → not ok. Expired delegation → not ok. Over rate → not ok.

Commit: `feat(rcan-py): AuthGuard glue for runtimes`.

---

## Part 4 — opencastor reference integration

### Task O1: Discover opencastor's command dispatch path

Non-code task — the executor reads `opencastor/castor/` to find where an incoming RCAN command becomes a motor call. Likely `castor/bridge.py` or `castor/runtime.py`. Annotate findings in the commit as a prelude — paths + line numbers — so O2 knows exactly what to modify.

Commit (docs-only): `docs(opencastor): trace command dispatch path for auth integration`.

---

### Task O2: Load delegations from `robot.rcan.yaml`

**Files:**
- Modify: opencastor config loader (path discovered in O1)
- Modify: `opencastor/robot.rcan.yaml` (sample) — add `operators:` section

YAML shape:
```yaml
agent:
  operators:
    - name: alice-laptop
      delegation_file: ~/.robot-md/delegations/RRN-000000000001/alice-laptop.json
    # OR inline:
    - name: bob-phone
      delegation:
        schema: rcan-operator-delegation-v1
        rrn: RRN-000000000001
        # ... full delegation blob
```

TDD: config loader test reads both shapes, passes both to `AuthGuard.load_delegations`. Deny by default if `operators:` block is present but all delegations fail verification.

Commit: `feat(opencastor): load operator delegations from robot.rcan.yaml`.

---

### Task O3: Wire `AuthGuard.check` into command dispatch

- [ ] **Step 1: Failing test** — mock inbound command, assert dispatch rejects unsigned cmds when `operators:` is configured; accepts valid signed cmds; passes cmd through untouched to downstream HiTL/ConfidenceGate logic on accept.

- [ ] **Step 2: Verify RED.**

- [ ] **Step 3: Implement** — in the dispatch function, before existing HiTL gate invocation, call `self._auth_guard.check(cmd)`. On fail, emit a `COMMAND_REJECTED` audit event (§16 AuditChain) and return the failure to the caller. On success, continue to existing logic.

- [ ] **Step 4: Verify GREEN + run full opencastor test suite.**

- [ ] **Step 5: Commit** `feat(opencastor): enforce operator delegation on command dispatch`.

---

### Task O4: Back-compat mode — `operators:` absent

If `robot.rcan.yaml` has no `operators:` block, opencastor logs a WARNING once at startup and accepts commands (current behavior). This is the zero-friction default. Test: runtime with no `operators:` serves commands as today; warning emitted exactly once.

Commit: `feat(opencastor): warn-only when operators: block absent (zero-friction default)`.

---

### Task O5: `opencastor` CLI flag `--require-auth` to force-fail the absent case

For operators who want hard-fail semantics: `opencastor serve --require-auth` turns the warning into a fatal error if `operators:` is missing. Test: `--require-auth` without `operators:` → exits non-zero; with `operators:` → normal boot.

Commit: `feat(opencastor): --require-auth flag for hard-fail on missing delegations`.

---

## Part 5 — robot-md CLI (operator subcommand)

### Task C1: `robot-md operator enroll`

```
robot-md operator enroll <rrn> --name DEVICE_NAME [--scopes SCOPE,SCOPE...] [--expires DURATION]
```

Generates an Ed25519 keypair for the device, signs a delegation using the robot's on-disk signing key (`~/.robot-md/keys/<rrn>.signing.json`), writes:
- Operator secret: `~/.robot-md/operators/<rrn>/<name>.ed25519.json` (mode 0600)
- Delegation blob: `~/.robot-md/delegations/<rrn>/<name>.json`

Prints the delegation path with instructions to add to `robot.rcan.yaml`.

Tests: keys are generated, delegation round-trips through `rcan.auth.operator.verify_delegation`, file modes are 0600, idempotent behavior (re-enrolling same name with `--force` overwrites, without `--force` errors).

Commit: `feat(cli): robot-md operator enroll`.

---

### Task C2: `robot-md operator list`

Lists delegations under `~/.robot-md/delegations/<rrn>/`, showing name, scopes, expiry, and whether the delegation is still valid against the local robot key.

Commit: `feat(cli): robot-md operator list`.

---

### Task C3: `robot-md operator revoke`

Deletes the local delegation file and prints instructions for removing from `robot.rcan.yaml`. Does not touch RRF (local-only revocation; §1.4 mechanism 1).

Commit: `feat(cli): robot-md operator revoke (local)`.

---

### Task C4: `robot-md command` one-shot — for ergonomics + testing

```
robot-md command <rrn> --as DEVICE_NAME --scope SCOPE '{...cmd json...}'
```

Signs a one-off command envelope using the named operator's key and prints the signed JSON. Useful for driving runtimes manually or in tests. Not required for functional auth — it's a UX affordance.

Commit: `feat(cli): robot-md command one-shot signer`.

---

## Part 6 — Integration guides (docs-only, no code tasks)

### 6.1 LeRobot integration guide

**Location:** `robot-md/docs/integrations/lerobot-auth.md` (to be created when the first LeRobot-based robot is wired up).

Summary for future implementer:
1. LeRobot's main loop lives in `lerobot.scripts.control_robot` (or similar — path depends on LeRobot version).
2. Wrap the policy's `forward(observation) -> action` with a `rcan.auth.guard.AuthGuard.check(cmd)` call.
3. The cmd envelope can be received via: (a) ROS2 topic `/rcan/command` if running a bridge node, (b) HTTP POST to a small FastAPI sidecar, (c) gRPC if the deployment uses `lerobot.serve`.
4. Load delegations from the same `robot.rcan.yaml` path opencastor uses; set `ROBOT_MD_CONFIG=/path/to/robot.rcan.yaml` env var.
5. Ship a pip package `rcan-lerobot-bridge` with a single entry point `rcan_lerobot_bridge.wrap(policy) -> AuthPolicy`.

Reachy Mini is a LeRobot-based platform — it inherits this path verbatim once `rcan-lerobot-bridge` exists.

### 6.2 ROS2 integration guide

**Location:** `robot-md/docs/integrations/ros2-auth.md` (future).

Summary:
1. Create a lifecycle node `rcan_auth_guard_node` that subscribes to an "untrusted command" topic and republishes verified commands to a "trusted command" topic.
2. Downstream nodes (motor drivers) subscribe only to the trusted topic — enforced by a lock-file or a custom DDS permissions XML.
3. `AuthGuard` is the same `rcan-py` class; `rclpy` is just the transport.

Key risk: DDS permissions XML is the *actual* enforcement — if a rogue node can publish to the trusted topic, the auth node is bypassed. Document that `rcan_auth_guard_node` requires DDS security to be turned on in the robot's deployment.

### 6.3 Web-browser operators (rcan-ts)

The operator side can run in a browser via `rcan-ts` (which already has verify/sign primitives). Operator private key stored in `IndexedDB` (wrapped with `SubtleCrypto.wrapKey` against a WebAuthn-derived key). This is out of scope for this plan but noted so the spec envelope stays JSON-friendly (no binary-only payloads).

---

## Self-Review Checklist

- [ ] Every design decision in Part 1 is locked (§1.1 per-device, §1.2 canonical delegation, §1.3 per-cmd signatures, §1.4 local revocation, §1.5 shared verifier, §1.6 rotate-invalidates).
- [ ] Spec section (Task S1) covers conformance for L2+.
- [ ] rcan-py tasks R1–R8 leave a reusable, tested module.
- [ ] opencastor tasks O1–O5 include zero-friction default (O4) AND the hard-fail opt-in (O5) to match `feedback_zero_friction_first.md`.
- [ ] CLI tasks C1–C4 give operators the full enroll/list/revoke lifecycle.
- [ ] LeRobot, ROS2, Reachy Mini are integration guides — no false "we'll ship LeRobot support in task X" promises.
- [ ] No placeholders — every Task Rx step has full code; every Task Ox/Cx has an explicit file path and commit message (even if the body is sketched since executor reads opencastor first in O1).
- [ ] Type names consistent: `OperatorDelegation`, `OperatorCommand`, `AuthGuard`, `AuthResult`, `NonceCache`, `RateLimiter`.

## Open questions for operator sign-off before execution

1. **Scope vocabulary** — Part 1 §1.2 seeds with `move, grip, tts, camera-stream, config-read, config-write, reset, shutdown, all`. Are these the right initial scopes, or does a specific deployment (Bob's SO-ARM101) need finer granularity (e.g. per-joint locks)?
2. **`all` scope** — should it be allowed at all in v1? Plan says yes but audit-emit on use. Alternative: forbid, require enumerated scopes. Confirm.
3. **Clock skew window** — 60 s default. Plenty for LAN operators, possibly tight for flaky mobile networks. Confirm or bump to 300 s.
4. **Rotation + delegations** — §1.6 says rotate invalidates all existing delegations. Alternative: allow the rotate payload to carry re-signed delegations as a transactional step. Simpler to ship v1 the plan's way and add the transactional re-sign only if operators complain. Confirm.
5. **Reachy Mini** — is this a runtime-level ask, or is a Reachy Mini-specific demo robot manifest also expected? If the latter, plan needs a Part 7 for the specific integration bring-up.

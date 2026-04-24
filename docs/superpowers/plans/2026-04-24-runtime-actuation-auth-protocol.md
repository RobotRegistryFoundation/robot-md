# Runtime Actuation Auth Protocol — Design + Reference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement the rcan-py verifier (Tasks R1–R6), opencastor reference (Tasks O1–O5), and CLI parity (Tasks C1–C4). The LeRobot / ROS2 / Reachy Mini integration sections are specification notes, not code tasks.

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

Scope vocabulary (rcan-spec §27 initial set):

| Scope | Meaning |
|---|---|
| `move` | Any motor/joint command |
| `grip` | Gripper open/close |
| `tts` | Text-to-speech output |
| `camera-stream` | Subscribe to camera feeds |
| `config-read` | Read config / telemetry |
| `config-write` | Modify non-policy config (speed limits, offsets) |
| `policy-update` | Swap the active AI policy / model artifact |
| `audit-read` | Read-only access to AuditChain (§16) |
| `reset` | Soft reset / re-home |
| `shutdown` | Power down / safe-stop |
| `all` | Super-scope; **audit-emits on every command** (see §1.6a below) |

Per-joint granularity is a HiTL gate concern (§8), not a scope. If a deployment needs "Alice can move all joints except the wrist," that is expressed as `scopes: [move]` with a wrist-flex HiTL gate — not as a finer scope.

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

Every command carries its own signature. Sessions are *not* introduced in v1 — every command is independently verifiable and replay-protected via `nonce` + `issued_at` window (±300 s default, configurable per-robot via `auth.max_skew_sec` in `robot.rcan.yaml`). 300 s absorbs mobile-network delivery jitter, embedded NTP drift, and DST transitions; nonce-based replay rejection bounds the attack window regardless of skew. Sessions can be added later if per-command bandwidth becomes an issue.

### 1.4 Revocation of operator delegations

Two overlapping mechanisms:

1. **Local** — delete the delegation from `robot.rcan.yaml`. Immediate, no external calls. This is the 99% case (operator loses laptop; owner edits yaml and restarts runtime).
2. **RRF-published revocation list** — optional. Robot owner `POST`s a signed revocation to `POST /v2/robots/<rrn>/operator-revoke` (future RRF endpoint, out of scope for this plan) that publishes the operator pubkey as globally revoked. Runtimes that choose to consult RRF periodically can pick this up.

This plan ships mechanism #1 only. Mechanism #2 is a followup; noted here so v1 doesn't paint us into a corner (nothing in v1 prevents it).

### 1.5 Where the verifier lives

**In `rcan-py` (and `rcan-ts` for web).** Every runtime imports the same verifier. This is non-negotiable — if verification logic diverges between runtimes, the protocol is dead.

### 1.6 Binding to RRF tier-gated write-auth

This plan assumes the robot's `pq_signing_pub` is already registered on RRF (via the existing register flow). It does *not* require `verification_status` to be anything in particular — even an `unverified` robot can have operators. The tier affects *how much the RRF manifest can be trusted by outsiders*, not how the local runtime authorizes commands.

If the robot's RRF key is *rotated* (via the write-auth plan's rotate-key endpoint), all existing operator delegations become invalid at the verification layer — they are signed by the old key. Rotation triggers full re-enrollment. Transactional re-sign-on-rotate is rejected for v1: it couples rotate-key to an unbounded list of delegations and introduces a partial-failure mode. Rotations are rare and user-initiated; re-enrolling a handful of operators is acceptable friction.

### 1.6a `all` scope handling

The `all` super-scope is allowed so admin/recovery paths are expressible, but its cost must be visible:

1. **Enrollment friction** — `robot-md operator enroll --scopes all` refuses to proceed without `--force`. The CLI prints a warning naming the device and requires an explicit confirmation.
2. **Runtime audit-emit** — every command dispatched under a delegation whose scopes include `all` emits a `COMMAND_ADMIN_USE` AuditChain event (§16), regardless of what scope the command itself names. This makes `all`-scoped activity auditable after the fact even if the operator narrowed the command's declared scope.
3. **No silent upgrade** — a delegation never gets `all` implicitly. It must be signed in at enrollment time with `scopes: ["all"]` (or equivalent).

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

**Files:**
- Modify: `rcan-py/src/rcan/auth/operator.py`
- Create: `rcan-py/tests/auth/test_verify_delegation.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/auth/test_verify_delegation.py
from datetime import datetime, timedelta, timezone
import pytest
from rcan.auth.operator import OperatorDelegation, verify_delegation, sign_delegation
from rcan.crypto import generate_hybrid_keypair  # existing helper

ISO = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def _body(pub_ed25519_b64: str, **overrides) -> dict:
    now = datetime.now(timezone.utc)
    b = {
        "schema": "rcan-operator-delegation-v1",
        "rrn": "RRN-000000000001",
        "operator_pub": pub_ed25519_b64,
        "operator_name": "alice-laptop",
        "scopes": ["move", "grip"],
        "issued_at": ISO(now - timedelta(minutes=1)),
        "expires_at": ISO(now + timedelta(days=30)),
        "max_ops_per_minute": 60,
    }
    b.update(overrides)
    return b

def test_verify_delegation_accepts_valid(robot_kp, operator_pub_b64):
    dg = sign_delegation(_body(operator_pub_b64), robot_kp)
    assert verify_delegation(dg, robot_kp.pq_pub_bytes) is True

def test_verify_delegation_rejects_tampered_scopes(robot_kp, operator_pub_b64):
    dg = sign_delegation(_body(operator_pub_b64), robot_kp)
    dg.scopes = ["move", "grip", "shutdown"]  # escalated
    assert verify_delegation(dg, robot_kp.pq_pub_bytes) is False

def test_verify_delegation_rejects_tampered_operator_pub(robot_kp, operator_pub_b64):
    dg = sign_delegation(_body(operator_pub_b64), robot_kp)
    dg.operator_pub = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    assert verify_delegation(dg, robot_kp.pq_pub_bytes) is False

def test_verify_delegation_rejects_wrong_pq_key(robot_kp, operator_pub_b64):
    dg = sign_delegation(_body(operator_pub_b64), robot_kp)
    other_kp = generate_hybrid_keypair()
    assert verify_delegation(dg, other_kp.pq_pub_bytes) is False

def test_verify_delegation_rejects_expired(robot_kp, operator_pub_b64):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    dg = sign_delegation(_body(operator_pub_b64, expires_at=ISO(past)), robot_kp)
    assert verify_delegation(dg, robot_kp.pq_pub_bytes) is False

def test_verify_delegation_rejects_future_issued_at(robot_kp, operator_pub_b64):
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    dg = sign_delegation(_body(operator_pub_b64, issued_at=ISO(future)), robot_kp)
    assert verify_delegation(dg, robot_kp.pq_pub_bytes) is False
```

Shared fixtures in `tests/auth/conftest.py`:
```python
import base64, pytest
from nacl.signing import SigningKey
from rcan.crypto import generate_hybrid_keypair

@pytest.fixture
def robot_kp():
    return generate_hybrid_keypair()

@pytest.fixture
def operator_ed25519():
    return SigningKey.generate()

@pytest.fixture
def operator_pub_b64(operator_ed25519):
    return base64.b64encode(bytes(operator_ed25519.verify_key)).decode()
```

- [ ] **Step 2: Verify RED** — `pytest tests/auth/test_verify_delegation.py -v` → ImportError on `verify_delegation` / `sign_delegation`.

- [ ] **Step 3: Implement in `rcan/auth/operator.py`**

```python
from datetime import datetime, timezone
from rcan.crypto import canonical_json, verify_hybrid, sign_hybrid
from .operator import OperatorDelegation  # same module; arrange imports as suits

_NOW = lambda: datetime.now(timezone.utc)

def _canonical_body(dg: OperatorDelegation) -> bytes:
    """Canonical JSON of everything except sig + pq_kid."""
    d = dg.to_dict()
    d.pop("sig", None); d.pop("pq_kid", None)
    return canonical_json(d)

def verify_delegation(dg: OperatorDelegation, robot_pq_pub: bytes) -> bool:
    if not dg.sig:
        return False
    now = _NOW()
    try:
        issued = datetime.fromisoformat(dg.issued_at.replace("Z", "+00:00"))
        expires = datetime.fromisoformat(dg.expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if issued - now > _SKEW_TOLERANCE:  # issued too far in future
        return False
    if expires <= now:
        return False
    message = _canonical_body(dg)
    return verify_hybrid(robot_pq_pub, message, dg.sig)

def sign_delegation(body: dict, robot_keypair) -> OperatorDelegation:
    dg = OperatorDelegation.from_dict({**body, "pq_kid": robot_keypair.pq_kid, "sig": None})
    message = _canonical_body(dg)
    dg.sig = sign_hybrid(robot_keypair.ml_dsa, robot_keypair.ed25519_sec, message)
    return dg

_SKEW_TOLERANCE = timedelta(minutes=5)  # accept slight clock drift on issuance
```

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/auth/test_verify_delegation.py -v
```

Expected: 6/6 pass.

- [ ] **Step 5: Commit** `feat(rcan-py): verify_delegation + sign_delegation`.

---

### Task R3: `verify_command(command, known_operators, max_skew_sec=300) -> AuthResult`

**Files:**
- Modify: `rcan-py/src/rcan/auth/operator.py`
- Create: `rcan-py/tests/auth/test_verify_command.py`

`known_operators` is `list[OperatorDelegation]` — the caller is responsible for pre-verifying each via `verify_delegation` before caching.

- [ ] **Step 1: Write the failing tests**

```python
# tests/auth/test_verify_command.py
import base64, time
from datetime import datetime, timezone, timedelta
from rcan.auth.operator import (
    OperatorCommand, sign_command, verify_command, sign_delegation
)

ISO = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def _make_delegation(robot_kp, operator_ed25519, **overrides):
    pub_b64 = base64.b64encode(bytes(operator_ed25519.verify_key)).decode()
    now = datetime.now(timezone.utc)
    body = {
        "schema": "rcan-operator-delegation-v1",
        "rrn": "RRN-000000000001",
        "operator_pub": pub_b64,
        "operator_name": "alice-laptop",
        "scopes": ["move", "grip"],
        "issued_at": ISO(now - timedelta(minutes=1)),
        "expires_at": ISO(now + timedelta(days=30)),
        "max_ops_per_minute": 60,
    }
    body.update(overrides)
    return sign_delegation(body, robot_kp)

def _make_cmd(operator_ed25519, **overrides) -> OperatorCommand:
    pub_b64 = base64.b64encode(bytes(operator_ed25519.verify_key)).decode()
    body = {
        "schema": "rcan-command-v1",
        "rrn": "RRN-000000000001",
        "operator_pub": pub_b64,
        "nonce": base64.b64encode(b"x" * 16).decode(),
        "issued_at": ISO(datetime.now(timezone.utc)),
        "scope": "move",
        "cmd": {"dx": 0.1},
    }
    body.update(overrides)
    return sign_command(body, operator_ed25519)

def test_accepts_valid_command(robot_kp, operator_ed25519):
    dg = _make_delegation(robot_kp, operator_ed25519)
    cmd = _make_cmd(operator_ed25519)
    res = verify_command(cmd, [dg])
    assert res.ok
    assert res.matched_delegation is dg

def test_rejects_unknown_operator(robot_kp, operator_ed25519):
    from nacl.signing import SigningKey
    dg = _make_delegation(robot_kp, operator_ed25519)
    other = SigningKey.generate()
    cmd = _make_cmd(other)
    res = verify_command(cmd, [dg])
    assert not res.ok and res.reason == "unknown operator"

def test_rejects_out_of_scope(robot_kp, operator_ed25519):
    dg = _make_delegation(robot_kp, operator_ed25519, scopes=["move"])
    cmd = _make_cmd(operator_ed25519, scope="shutdown")
    res = verify_command(cmd, [dg])
    assert not res.ok and res.reason == "scope"

def test_rejects_expired_delegation(robot_kp, operator_ed25519):
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    dg = _make_delegation(robot_kp, operator_ed25519,
                          issued_at=ISO(datetime.now(timezone.utc) - timedelta(days=2)),
                          expires_at=ISO(past))
    cmd = _make_cmd(operator_ed25519)
    res = verify_command(cmd, [dg])
    assert not res.ok and res.reason == "delegation expired"

def test_rejects_future_skew_beyond_300s(robot_kp, operator_ed25519):
    dg = _make_delegation(robot_kp, operator_ed25519)
    future = datetime.now(timezone.utc) + timedelta(seconds=400)
    cmd = _make_cmd(operator_ed25519, issued_at=ISO(future))
    res = verify_command(cmd, [dg])
    assert not res.ok and res.reason == "skew"

def test_rejects_past_skew_beyond_300s(robot_kp, operator_ed25519):
    dg = _make_delegation(robot_kp, operator_ed25519)
    past = datetime.now(timezone.utc) - timedelta(seconds=400)
    cmd = _make_cmd(operator_ed25519, issued_at=ISO(past))
    res = verify_command(cmd, [dg])
    assert not res.ok and res.reason == "skew"

def test_accepts_drift_within_skew_window(robot_kp, operator_ed25519):
    dg = _make_delegation(robot_kp, operator_ed25519)
    drifted = datetime.now(timezone.utc) - timedelta(seconds=200)
    cmd = _make_cmd(operator_ed25519, issued_at=ISO(drifted))
    assert verify_command(cmd, [dg]).ok

def test_rejects_tampered_signature(robot_kp, operator_ed25519):
    dg = _make_delegation(robot_kp, operator_ed25519)
    cmd = _make_cmd(operator_ed25519)
    cmd.cmd = {"dx": 999.0}  # tamper after signing
    res = verify_command(cmd, [dg])
    assert not res.ok and res.reason == "signature"
```

- [ ] **Step 2: Verify RED** — import/attribute errors for `verify_command` / `sign_command` / `AuthResult`.

- [ ] **Step 3: Implement**

```python
# rcan/auth/operator.py (additions)
import base64
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from rcan.crypto import canonical_json

@dataclass
class AuthResult:
    ok: bool
    reason: Optional[str] = None
    matched_delegation: Optional["OperatorDelegation"] = None

def _cmd_canonical_bytes(cmd: "OperatorCommand") -> bytes:
    d = cmd.to_dict()
    d.pop("sig", None)
    return canonical_json(d)

def sign_command(body: dict, operator_ed25519) -> "OperatorCommand":
    cmd = OperatorCommand.from_dict({**body, "sig": None})
    message = _cmd_canonical_bytes(cmd)
    cmd.sig = base64.b64encode(operator_ed25519.sign(message).signature).decode()
    return cmd

def verify_command(cmd: "OperatorCommand", known: list["OperatorDelegation"],
                   max_skew_sec: int = 300) -> AuthResult:
    now = _NOW()
    try:
        issued = datetime.fromisoformat(cmd.issued_at.replace("Z", "+00:00"))
    except ValueError:
        return AuthResult(False, "skew")
    if abs((now - issued).total_seconds()) > max_skew_sec:
        return AuthResult(False, "skew")

    matched = next((d for d in known if d.operator_pub == cmd.operator_pub), None)
    if matched is None:
        return AuthResult(False, "unknown operator")

    try:
        expires = datetime.fromisoformat(matched.expires_at.replace("Z", "+00:00"))
    except ValueError:
        return AuthResult(False, "delegation expired")
    if expires <= now:
        return AuthResult(False, "delegation expired")

    allowed = set(matched.scopes)
    if "all" not in allowed and cmd.scope not in allowed:
        return AuthResult(False, "scope", matched)

    try:
        vk = VerifyKey(base64.b64decode(cmd.operator_pub))
        vk.verify(_cmd_canonical_bytes(cmd), base64.b64decode(cmd.sig))
    except (BadSignatureError, ValueError):
        return AuthResult(False, "signature", matched)

    return AuthResult(True, None, matched)
```

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/auth/test_verify_command.py -v
```

Expected: 8/8 pass.

- [ ] **Step 5: Commit** `feat(rcan-py): verify_command + sign_command with scope/skew/sig checks`.

---

### Task R4: `NonceCache` for replay prevention

**Files:**
- Create: `rcan-py/src/rcan/auth/nonce_cache.py`
- Create: `rcan-py/tests/auth/test_nonce_cache.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/auth/test_nonce_cache.py
import time, pytest
from rcan.auth.nonce_cache import NonceCache

def test_first_use_accepted():
    c = NonceCache(ttl_seconds=10)
    assert c.check_and_remember("n1") is True

def test_second_use_within_ttl_rejected():
    c = NonceCache(ttl_seconds=10)
    c.check_and_remember("n1")
    assert c.check_and_remember("n1") is False

def test_same_nonce_accepted_after_ttl(monkeypatch):
    t = [1000.0]
    c = NonceCache(ttl_seconds=10, now_fn=lambda: t[0])
    c.check_and_remember("n1")
    t[0] += 11
    assert c.check_and_remember("n1") is True

def test_bounded_size_drops_oldest():
    c = NonceCache(ttl_seconds=10, max_size=3)
    for n in ["n1", "n2", "n3", "n4"]:
        c.check_and_remember(n)
    # n1 evicted; re-using it is accepted
    assert c.check_and_remember("n1") is True
    # n4 still cached; rejected
    assert c.check_and_remember("n4") is False
```

- [ ] **Step 2: Verify RED.**

- [ ] **Step 3: Implement**

```python
# rcan/auth/nonce_cache.py
import time
from collections import OrderedDict

class NonceCache:
    def __init__(self, ttl_seconds: int = 600, max_size: int = 100_000, now_fn=time.monotonic):
        self._ttl = ttl_seconds
        self._max = max_size
        self._now = now_fn
        self._cache: "OrderedDict[str, float]" = OrderedDict()

    def _prune(self) -> None:
        now = self._now()
        while self._cache:
            nonce, ts = next(iter(self._cache.items()))
            if now - ts > self._ttl:
                self._cache.popitem(last=False)
            else:
                break

    def check_and_remember(self, nonce: str) -> bool:
        self._prune()
        if nonce in self._cache and self._now() - self._cache[nonce] <= self._ttl:
            return False
        self._cache[nonce] = self._now()
        self._cache.move_to_end(nonce)
        while len(self._cache) > self._max:
            self._cache.popitem(last=False)
        return True
```

- [ ] **Step 4: Verify GREEN.**

- [ ] **Step 5: Commit** `feat(rcan-py): NonceCache for command replay prevention`.

---

### Task R5: `RateLimiter` token bucket per operator

**Files:**
- Create: `rcan-py/src/rcan/auth/rate_limiter.py`
- Create: `rcan-py/tests/auth/test_rate_limiter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/auth/test_rate_limiter.py
from rcan.auth.rate_limiter import RateLimiter

def test_under_budget_accepted():
    t = [1000.0]
    r = RateLimiter(now_fn=lambda: t[0])
    for _ in range(30):
        assert r.check("op1", max_per_minute=60)

def test_bucket_drains_then_refills(monkeypatch):
    t = [1000.0]
    r = RateLimiter(now_fn=lambda: t[0])
    for _ in range(60):
        assert r.check("op1", max_per_minute=60)
    assert r.check("op1", max_per_minute=60) is False
    t[0] += 60  # one minute later — bucket refills
    assert r.check("op1", max_per_minute=60) is True

def test_buckets_are_per_operator():
    t = [1000.0]
    r = RateLimiter(now_fn=lambda: t[0])
    for _ in range(60):
        r.check("op1", max_per_minute=60)
    assert r.check("op1", max_per_minute=60) is False
    assert r.check("op2", max_per_minute=60) is True
```

- [ ] **Step 2: Verify RED.**

- [ ] **Step 3: Implement**

```python
# rcan/auth/rate_limiter.py
import time
from dataclasses import dataclass

@dataclass
class _Bucket:
    tokens: float
    last: float

class RateLimiter:
    def __init__(self, now_fn=time.monotonic):
        self._now = now_fn
        self._buckets: dict[str, _Bucket] = {}

    def check(self, operator_pub: str, max_per_minute: int) -> bool:
        now = self._now()
        refill_rate = max_per_minute / 60.0
        b = self._buckets.get(operator_pub)
        if b is None:
            b = _Bucket(tokens=float(max_per_minute), last=now)
            self._buckets[operator_pub] = b
        else:
            elapsed = now - b.last
            b.tokens = min(float(max_per_minute), b.tokens + elapsed * refill_rate)
            b.last = now
        if b.tokens < 1.0:
            return False
        b.tokens -= 1.0
        return True
```

- [ ] **Step 4: Verify GREEN.**

- [ ] **Step 5: Commit** `feat(rcan-py): RateLimiter token-bucket per operator`.

---

### Task R6: `AuthGuard` glue

**Files:**
- Create: `rcan-py/src/rcan/auth/guard.py`
- Create: `rcan-py/tests/auth/test_guard.py`

`AuthGuard` is the runtime-facing surface. It holds verified delegations, the nonce cache, the rate limiter, and the robot's pq pub, and exposes a single `check(command) -> AuthResult`.

- [ ] **Step 1: Write failing tests**

```python
# tests/auth/test_guard.py
from datetime import datetime, timezone, timedelta
import base64
from rcan.auth.guard import AuthGuard
from rcan.auth.operator import sign_command, sign_delegation

ISO = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def _delegation_body(operator_pub_b64, **overrides):
    now = datetime.now(timezone.utc)
    b = {
        "schema": "rcan-operator-delegation-v1",
        "rrn": "RRN-000000000001",
        "operator_pub": operator_pub_b64,
        "operator_name": "alice-laptop",
        "scopes": ["move", "grip"],
        "issued_at": ISO(now - timedelta(minutes=1)),
        "expires_at": ISO(now + timedelta(days=30)),
        "max_ops_per_minute": 2,   # tiny for test
    }
    b.update(overrides)
    return b

def _cmd_body(operator_pub_b64, nonce_bytes=b"x" * 16, **overrides):
    b = {
        "schema": "rcan-command-v1",
        "rrn": "RRN-000000000001",
        "operator_pub": operator_pub_b64,
        "nonce": base64.b64encode(nonce_bytes).decode(),
        "issued_at": ISO(datetime.now(timezone.utc)),
        "scope": "move",
        "cmd": {"dx": 0.1},
    }
    b.update(overrides)
    return b

def test_accepts_fresh_command(robot_kp, operator_ed25519, operator_pub_b64):
    dg = sign_delegation(_delegation_body(operator_pub_b64), robot_kp)
    guard = AuthGuard(robot_pq_pub=robot_kp.pq_pub_bytes)
    guard.load_delegations([dg.to_dict()])
    cmd = sign_command(_cmd_body(operator_pub_b64), operator_ed25519)
    assert guard.check(cmd).ok

def test_rejects_replay(robot_kp, operator_ed25519, operator_pub_b64):
    dg = sign_delegation(_delegation_body(operator_pub_b64), robot_kp)
    guard = AuthGuard(robot_pq_pub=robot_kp.pq_pub_bytes)
    guard.load_delegations([dg.to_dict()])
    cmd = sign_command(_cmd_body(operator_pub_b64), operator_ed25519)
    assert guard.check(cmd).ok
    res = guard.check(cmd)
    assert not res.ok and res.reason == "replay"

def test_rejects_over_rate(robot_kp, operator_ed25519, operator_pub_b64):
    dg = sign_delegation(_delegation_body(operator_pub_b64, max_ops_per_minute=2), robot_kp)
    guard = AuthGuard(robot_pq_pub=robot_kp.pq_pub_bytes)
    guard.load_delegations([dg.to_dict()])
    for i in range(2):
        cmd = sign_command(_cmd_body(operator_pub_b64, nonce_bytes=bytes([i]) * 16), operator_ed25519)
        assert guard.check(cmd).ok
    cmd3 = sign_command(_cmd_body(operator_pub_b64, nonce_bytes=b"3" * 16), operator_ed25519)
    res = guard.check(cmd3)
    assert not res.ok and res.reason == "rate"

def test_load_delegations_drops_unverifiable(robot_kp, operator_pub_b64):
    valid = sign_delegation(_delegation_body(operator_pub_b64), robot_kp).to_dict()
    bogus = {**valid, "scopes": ["move", "shutdown"]}  # tampered, sig no longer matches
    guard = AuthGuard(robot_pq_pub=robot_kp.pq_pub_bytes)
    guard.load_delegations([bogus])
    assert len(guard.delegations) == 0
```

- [ ] **Step 2: Verify RED.**

- [ ] **Step 3: Implement**

```python
# rcan/auth/guard.py
from .operator import (
    OperatorDelegation, OperatorCommand, AuthResult,
    verify_delegation, verify_command,
)
from .nonce_cache import NonceCache
from .rate_limiter import RateLimiter

class AuthGuard:
    def __init__(self, robot_pq_pub: bytes, max_skew_sec: int = 300,
                 admin_audit_emit=None):
        self._robot_pq_pub = robot_pq_pub
        self._max_skew_sec = max_skew_sec
        self._delegations: list[OperatorDelegation] = []
        self._nonces = NonceCache(ttl_seconds=2 * max_skew_sec)
        self._rate = RateLimiter()
        # admin_audit_emit(command, delegation) fires whenever a command dispatches
        # under an `all`-scoped delegation. Wire to §16 AuditChain in the runtime.
        self._admin_audit_emit = admin_audit_emit

    @property
    def delegations(self) -> list[OperatorDelegation]:
        return list(self._delegations)

    def load_delegations(self, raw: list[dict]) -> None:
        verified: list[OperatorDelegation] = []
        for d in raw:
            dg = OperatorDelegation.from_dict(d)
            if verify_delegation(dg, self._robot_pq_pub):
                verified.append(dg)
        self._delegations = verified

    def check(self, cmd: OperatorCommand) -> AuthResult:
        res = verify_command(cmd, self._delegations, max_skew_sec=self._max_skew_sec)
        if not res.ok:
            return res
        # Replay check — only after signature is known valid (avoid poisoning cache with forgeries).
        if not self._nonces.check_and_remember(cmd.nonce):
            return AuthResult(False, "replay", res.matched_delegation)
        # Rate limit per operator.
        cap = res.matched_delegation.max_ops_per_minute
        if not self._rate.check(cmd.operator_pub, cap):
            return AuthResult(False, "rate", res.matched_delegation)
        # Admin audit: any command under `all` scope delegation emits COMMAND_ADMIN_USE.
        if "all" in res.matched_delegation.scopes and self._admin_audit_emit:
            self._admin_audit_emit(cmd, res.matched_delegation)
        return res
```

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/auth/ -v
```

Expected: all auth tests pass.

- [ ] **Step 5: Commit** `feat(rcan-py): AuthGuard glue (nonce + rate + admin-audit)`.

Note: Tasks R4–R8 from the original draft are consolidated into R2–R6 above (verifier, nonce cache, rate limiter, guard). The `sign_delegation` / `sign_command` helpers that were previously separate tasks ride along with R2/R3 since they are trivial round-trip mirrors.

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
robot-md operator enroll <rrn> --name DEVICE_NAME [--scopes SCOPE,SCOPE...] [--expires DURATION] [--force]
```

Generates an Ed25519 keypair for the device, signs a delegation using the robot's on-disk signing key (`~/.robot-md/keys/<rrn>.signing.json`), writes:
- Operator secret: `~/.robot-md/operators/<rrn>/<name>.ed25519.json` (mode 0600)
- Delegation blob: `~/.robot-md/delegations/<rrn>/<name>.json`

Prints the delegation path with instructions to add to `robot.rcan.yaml`.

**`--force` requirements:**
- Re-enrolling an existing `<name>` (prevents accidental overwrite).
- `--scopes all` or any scope list containing `all` — the CLI prints the §1.6a warning explicitly naming the device, listing scopes, and showing that every subsequent command will emit a `COMMAND_ADMIN_USE` audit event. Refuses to proceed without `--force` even on first enrollment.

Tests:
- Keys are generated and delegation round-trips through `rcan.auth.operator.verify_delegation`.
- File modes are 0600.
- Re-enrolling same name without `--force` errors (non-zero exit, no files touched).
- Re-enrolling same name with `--force` overwrites.
- `--scopes all` without `--force` errors and prints the admin-use warning.
- `--scopes all --force` succeeds and writes a delegation whose `scopes` is `["all"]`.
- `--scopes move,all` (mixed) is rejected with "'all' must be used alone"; no files touched.

Commit: `feat(cli): robot-md operator enroll (with --force guard on 'all' scope)`.

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

- [ ] Every design decision in Part 1 is locked (§1.1 per-device, §1.2 canonical delegation with full scope table, §1.3 per-cmd signatures at 300s skew, §1.4 local revocation, §1.5 shared verifier, §1.6 rotate-invalidates, §1.6a `all`-scope audit).
- [ ] Spec section (Task S1) covers conformance for L2+.
- [ ] rcan-py tasks R1–R6 leave a reusable, tested module with full code in every step.
- [ ] opencastor tasks O1–O5 include zero-friction default (O4) AND the hard-fail opt-in (O5) to match `feedback_zero_friction_first.md`.
- [ ] CLI tasks C1–C4 give operators the full enroll/list/revoke lifecycle; C1 enforces `--force` for `all` scope.
- [ ] LeRobot, ROS2, Reachy Mini are integration guides — no false "we'll ship LeRobot support in task X" promises.
- [ ] Type names consistent: `OperatorDelegation`, `OperatorCommand`, `AuthGuard`, `AuthResult`, `NonceCache`, `RateLimiter`.

## Design decisions (locked 2026-04-24)

1. **Scope vocabulary** — §1.2 table: `move, grip, tts, camera-stream, config-read, config-write, policy-update, audit-read, reset, shutdown, all`. Coarse by design — per-joint granularity is a HiTL concern, not a scope.
2. **`all` scope** — allowed; every command emits `COMMAND_ADMIN_USE` audit event; CLI requires `--force` at enrollment (§1.6a, Task C1).
3. **Clock-skew window** — 300 s default, per-robot configurable via `auth.max_skew_sec` in `robot.rcan.yaml`. Nonce cache bounds replay window at `2 * max_skew_sec`.
4. **Rotate invalidates all delegations** — re-enrollment required after RRF key rotation. Transactional re-sign is rejected for v1 (couples rotate-key to an unbounded list; partial-failure mode).
5. **Reachy Mini** — runtime-level only; inherits `rcan-lerobot-bridge` path (§6.1). A Reachy-Mini-specific bring-up is a separate plan when hardware arrives.

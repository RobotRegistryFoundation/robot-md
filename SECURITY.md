# Security Policy

## Supported Versions

| Version | Status | Notes |
|---------|--------|-------|
| v0.1.x (current) | ✅ Active | Shipping now; spec + CLI + Claude Code hook |
| pre-v0.1 | ❌ N/A | No releases before v0.1 |

The format spec is versioned separately from the CLI: schema URL `https://robotmd.dev/schema/v1/...` will be served indefinitely even after v2 ships, so robots pinning `rcan_version: "3.0"` in existing ROBOT.md files won't break.

<!-- BEGIN: ecosystem authority disclaimer (canonical, derived from spec §10) -->
> **Where safety is actually enforced.**
>
> Physical safety is enforced at Layer 3 (`robot-md-gateway`) or Layer 4 (a runtime that embeds it, e.g., OpenCastor). Declaration alone (Layer 1) does not enforce safety. Agent host alone (Layer 2) is not the safety boundary. If a deployment lacks Layer 3, no safety claim attaches to it.
<!-- END: ecosystem authority disclaimer -->

## Reporting a Vulnerability

**Do not file a public GitHub issue for security vulnerabilities.**

Report privately via one of the following:

- **GitHub Security Advisories** (preferred): [github.com/RobotRegistryFoundation/robot-md/security/advisories/new](https://github.com/RobotRegistryFoundation/robot-md/security/advisories/new)
- **Email**: security@continuon.ai — encrypt with PGP if the report contains sensitive detail (public key at rcan.dev/security.asc)

Include in your report:
- Affected component (spec section, schema rule, CLI subcommand, or integration hook)
- A clear description of the vulnerability
- Steps to reproduce or a proof-of-concept
- Your assessment of impact and exploitability
- Whether you have a proposed fix

## Response Timeline

- **Acknowledgment**: within 72 hours
- **Triage + initial severity call**: within 7 days
- **Fix + coordinated disclosure**: typically within 30 days for high/critical severity; longer for lower severity or if upstream coordination is needed

## In Scope

- Schema bypass — a ROBOT.md that passes `robot-md validate` but violates the documented format invariants
- CLI vulnerabilities — code execution, path traversal, privilege escalation via malformed input
- Integration hook vulnerabilities — the Claude Code `session-start.sh` hook, the documented MCP server pattern, the documented URL-bridge pattern
- Supply-chain risks — dependency compromise affecting the published `robot-md` PyPI package

## Out of Scope

- Vulnerabilities in OpenCastor runtime — report to [`craigm26/OpenCastor`](https://github.com/craigm26/OpenCastor/security/advisories)
- Vulnerabilities in the RCAN wire protocol — report to [`continuonai/rcan-spec`](https://github.com/continuonai/rcan-spec/security/advisories)
- Registry vulnerabilities — report to the Robot Registry Foundation via the channels listed at [robotregistryfoundation.org](https://robotregistryfoundation.org)
- Denial-of-service from a user supplying arbitrarily large ROBOT.md files — the CLI is not intended to be run on untrusted network input; run it on files you trust

## Known v0.1 Limitations (planned fixes tracked for v0.2/v1.0)

ROBOT.md is deliberately small in v0.1. That means several safety and security primitives are **documented gaps**, not oversights. If a deployment depends on any of them, wait for the flagged release or layer your own guard above the manifest.

### Physical-safety gaps

- **The manifest's `safety` block is declarative, not enforcing.** A planner that reads ROBOT.md (including Claude Code at Tier 0) is trusted to self-enforce the declared bounds. The schema rejects obviously-absurd values (v0.1.1 hardened max velocity / payload / workspace bounds), but it does *not* physically constrain a misbehaving planner — only the robot runtime does that. **Production use-cases that need enforceable limits belong on Tier 2 (OpenCastor's SafetyLayer + P66 manifest), not Tier 0.**
- **`failsafe_behavior`** is declared but v0.1 does not define what the planner must do to honor it at comms loss. v0.2 will add a conformance test.
- **No attestation of the safety block's authorship.** Anyone can write any values (see digital-security gaps below). Combine with the point above: in v0.1, believe your own manifest, not someone else's.

### Digital-security gaps

- **No manifest signing in v0.1.** A ROBOT.md carries no signature. A third party can write a manifest claiming `rrn: RRN-000000000001` and impersonate a real robot's declared capabilities. Planned v0.2: `metadata.signature` (Ed25519 or `pqc-hybrid-v1`) over the canonical frontmatter, with the public key resolvable via `https://robotregistryfoundation.org/api/v1/robots/<rrn>` — so any receiver can verify the manifest was written by the registered owner of the RRN.
- **No RRF authentication on `robot-md register` (v0.2).** The first implementation will require proof-of-possession of the private key corresponding to the RRN being claimed. Until then, registration is trust-on-first-use. Do not register a manifest whose fidelity you depend on through an untrusted network.
- **No tamper log.** A ROBOT.md doesn't record when it was last modified or by whom. Downstream consumers should hash the served manifest and detect changes themselves. Planned v0.2: optional `metadata.authored_at` + `metadata.authored_by` + signature.
- **Tier 0 threat model is "trusted operator + trusted planner."** Claude Code with shell access to a robot is a very capable attacker if either the operator's credentials are compromised or the planner's context is poisoned with an adversarial system prompt. Do not expose a Tier 0 robot to untrusted prompts (public chatbot front-end, arbitrary user chat) without a gateway layer that enforces a ROBOT.md-derived allowlist.

### Registry gaps

- The Robot Registry Foundation currently accepts robot registrations but does not ingest a ROBOT.md as a first-class record. v0.2 will add a `/api/v1/robots/:rrn/manifest` endpoint that stores the signed manifest alongside the registration record and serves it back with verifiable provenance.

### What's hardened in v0.1.1

- JSON Schema rejects physically absurd safety values: `max_joint_velocity_dps ≤ 36000`, `max_linear_velocity_ms ≤ 100`, `payload_kg ≤ 10000`, `estop.response_ms ≤ 5000` (was 10000).
- `failsafe_behavior` and `workspace_bounds_m` are declarable (not enforced).
- CORS headers on the served schema allow cross-origin validators.

## Credit

Reporters who provide a clear, reproducible report and follow coordinated disclosure will be credited in the advisory, the CHANGELOG entry, and the release notes for the fix — unless anonymity is explicitly requested.

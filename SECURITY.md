# Security Policy

## Supported Versions

| Version | Status | Notes |
|---------|--------|-------|
| v0.1.x (current) | ✅ Active | Shipping now; spec + CLI + Claude Code hook |
| pre-v0.1 | ❌ N/A | No releases before v0.1 |

The format spec is versioned separately from the CLI: schema URL `https://robotmd.dev/schema/v1/...` will be served indefinitely even after v2 ships, so robots pinning `rcan_version: "3.0"` in existing ROBOT.md files won't break.

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

## In-Scope

- Schema bypass — a ROBOT.md that passes `robot-md validate` but violates the documented format invariants
- CLI vulnerabilities — code execution, path traversal, privilege escalation via malformed input
- Integration hook vulnerabilities — the Claude Code `session-start.sh` hook, the documented MCP server pattern, the documented URL-bridge pattern
- Supply-chain risks — dependency compromise affecting the published `robot-md` PyPI package

## Out of Scope

- Vulnerabilities in OpenCastor runtime — report to [`craigm26/OpenCastor`](https://github.com/craigm26/OpenCastor/security/advisories)
- Vulnerabilities in the RCAN wire protocol — report to [`continuonai/rcan-spec`](https://github.com/continuonai/rcan-spec/security/advisories)
- Registry vulnerabilities — report to the Robot Registry Foundation via the channels listed at [robotregistryfoundation.org](https://robotregistryfoundation.org)
- Denial-of-service from a user supplying arbitrarily large ROBOT.md files — the CLI is not intended to be run on untrusted network input; run it on files you trust

## Credit

Reporters who provide a clear, reproducible report and follow coordinated disclosure will be credited in the advisory, the CHANGELOG entry, and the release notes for the fix — unless anonymity is explicitly requested.

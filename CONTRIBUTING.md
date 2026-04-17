# Contributing to robot-md

Thanks for your interest. This guide covers how to land a PR.

## Before you start

- Open an issue first if your change is substantive (new field in the schema, breaking change, new integration surface).
- Small fixes (typos, small bugs, test additions) — PR directly.
- Breaking changes to the ROBOT.md format or schema require a design doc PR before any code PR.

## Setup

```bash
git clone https://github.com/continuonai/robot-md.git
cd robot-md/cli
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Test

```bash
cd cli
python -m pytest -v
ruff check src tests
ruff format --check src tests
```

Every `examples/*.ROBOT.md` must also validate. CI enforces this.

## Commit style

Conventional commits:

- `feat(scope): ...` — new feature
- `fix(scope): ...` — bug fix
- `docs(scope): ...` — docs only
- `test(scope): ...` — test only
- `chore(scope): ...` — tooling, release, lint

Scopes in use: `spec`, `schema`, `cli`, `parser`, `validate`, `render`, `context`, `examples`, `integrations`, `proposal`, `ci`.

Example:

```
feat(schema): add kinematics.twist_limit_nm field

For arms where torque (not just angle) matters — vendors can declare
per-joint twist limits in the kinematics block.
```

## Versioning

- Schema: URL-versioned (`/v1/`, `/v2/`). Breaking changes create `/v2/` and keep `/v1/` available indefinitely.
- CLI: semver. v1.0.0 locks the spec; v0.x is fluid.

## Out of scope

This repo is spec + tooling. Not accepted:

- Robot runtime code (goes to OpenCastor or your own runtime)
- Registry code (goes to Robot Registry Foundation)
- Wire protocol changes (propose at rcan.dev/spec)
- Skill implementation frameworks

If your change touches these, we'll close the PR and point you at the right repo.

## License

All contributions are licensed under Apache 2.0.

## Summary

<!-- 1-3 bullets describing what this PR does -->

## Motivation

<!-- What problem does this solve? Link issues: Closes #123 -->

## Changes

<!-- What's in the diff? -->

## Test plan

- [ ] `python -m pytest -v` passes (cli/)
- [ ] `ruff check cli/src cli/tests` clean
- [ ] `ruff format --check cli/src cli/tests` clean
- [ ] If schema/examples changed: every `examples/*.ROBOT.md` still validates
- [ ] If CLI changed: smoke-tested `robot-md validate | render | context` on `examples/bob.ROBOT.md`

## Breaking changes

<!-- Does this change the ROBOT.md format or the CLI output shape? If yes, describe the migration path. -->

## Docs

<!-- README, spec, or integration README updates included? -->

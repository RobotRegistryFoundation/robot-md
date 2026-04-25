"""Tests for schema + RCAN + body-section validation."""

from __future__ import annotations

from robot_md.parser import parse_file
from robot_md.validate import (
    MISSING_BODY_SECTION,
    RCAN_CONFORMANCE_VIOLATION,
    SCHEMA_VIOLATION,
    VALID,
    ValidationResult,
    validate,
)


def test_valid_minimal_returns_valid(fixtures_dir):
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    result = validate(parsed)
    assert result.code == VALID, f"expected VALID, got {result!r}"
    assert not result.errors


def test_schema_violation_missing_safety(fixtures_dir):
    parsed = parse_file(fixtures_dir / "invalid" / "missing-safety.ROBOT.md")
    result = validate(parsed)
    assert result.code == SCHEMA_VIOLATION
    assert any("safety" in e.lower() for e in result.errors)


def test_rcan_violation_old_version(fixtures_dir):
    parsed = parse_file(fixtures_dir / "invalid" / "bad-rcan-version.ROBOT.md")
    result = validate(parsed)
    # Schema pattern rejects 1.x, so this surfaces as SCHEMA_VIOLATION not RCAN_CONFORMANCE
    assert result.code in (SCHEMA_VIOLATION, RCAN_CONFORMANCE_VIOLATION)
    assert any("rcan_version" in e.lower() or "1.6" in e for e in result.errors)


def test_missing_identity_section(fixtures_dir):
    parsed = parse_file(fixtures_dir / "invalid" / "missing-identity-section.ROBOT.md")
    result = validate(parsed)
    assert result.code == MISSING_BODY_SECTION
    assert any("identity" in e.lower() for e in result.errors)


def test_h1_must_match_robot_name(fixtures_dir, tmp_path):
    # Build a file where H1 disagrees with metadata.robot_name
    bad = tmp_path / "bad-h1.ROBOT.md"
    bad.write_text(
        "---\n"
        'rcan_version: "3.0"\n'
        "metadata:\n  robot_name: alice\n"
        "physics:\n  type: wheeled\n  dof: 2\n"
        "drivers:\n  - id: wheels\n    protocol: pca9685\n"
        "safety:\n  estop:\n    software: true\n    response_ms: 200\n"
        "---\n\n"
        "# bob\n\n"
        "## Identity\nMismatched name.\n\n"
        "## What bob Can Do\nNothing.\n\n"
        "## Safety Gates\nPresent.\n"
    )
    parsed = parse_file(bad)
    result = validate(parsed)
    assert result.code == MISSING_BODY_SECTION
    assert any("h1" in e.lower() or "robot_name" in e.lower() for e in result.errors)


def test_validation_result_is_dataclass():
    r = ValidationResult(code=VALID, errors=[])
    assert r.code == 0
    assert r.errors == []


def test_valid_minimal_has_summary(fixtures_dir):
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    result = validate(parsed)
    assert result.summary
    assert "test-bot" in result.summary


# ---- capability namespace alignment warning (PR D, 2026-04-25) ----------


def test_namespace_mismatch_warning_on_manipulate_with_feetech(tmp_path):
    """Bob's actual hand-rolled gap: capabilities declare manipulate.* but
    feetech_scs driver implements arm.*. Validation should warn — not fail
    the schema (it's a runtime-time issue, not a schema violation)."""
    p = tmp_path / "ROBOT.md"
    p.write_text("""\
---
rcan_version: "3.2"
metadata:
  robot_name: bob
  manufacturer: Acme
  model: SO-ARM101
  firmware_version: 1.0.0
physics: { type: arm, dof: 6 }
drivers:
  - { id: arm, protocol: feetech_scs, port: /dev/null }
capabilities: [manipulate.pick]
safety:
  estop: { software: true, response_ms: 50 }
  max_joint_velocity_dps: 30
  hitl_gates: [{ scope: manipulate, require_auth: true }]
---
# bob

## Identity

bob.

## What bob Can Do

stuff.

## Safety Gates

manipulate.
""")
    result = validate(parse_file(p))
    assert result.code == VALID, (
        f"expected VALID + warning; got code={result.code} errors={result.errors}"
    )
    assert any("namespace mismatch" in w.lower() for w in result.warnings), (
        f"expected namespace-mismatch warning; got {result.warnings}"
    )


def test_no_namespace_mismatch_warning_when_aligned(tmp_path):
    """capabilities = arm.* with feetech_scs driver → no warning."""
    p = tmp_path / "ROBOT.md"
    p.write_text("""\
---
rcan_version: "3.2"
metadata:
  robot_name: bob
  manufacturer: Acme
  model: SO-ARM101
  firmware_version: 1.0.0
physics: { type: arm, dof: 6 }
drivers:
  - { id: arm, protocol: feetech_scs, port: /dev/null }
capabilities: [arm.pick, arm.home]
safety:
  estop: { software: true, response_ms: 50 }
  max_joint_velocity_dps: 30
  hitl_gates: [{ scope: arm, require_auth: true }]
---
# bob

## Identity

bob.

## What bob Can Do

pick + home.

## Safety Gates

arm.
""")
    result = validate(parse_file(p))
    assert result.code == VALID
    assert not any("namespace mismatch" in w.lower() for w in result.warnings)

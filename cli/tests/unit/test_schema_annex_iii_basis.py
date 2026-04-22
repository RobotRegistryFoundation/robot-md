"""v0.9.0 — compliance.annex_iii_basis slot.
v0.9.2 — FRIA gate: fria_ref required (non-null URI) when annex_iii_basis set.

Per rcan-spec §22, a robot declares which Annex III use case basis it falls
under (if any). Enum of 10 values; optional. Setting it commits the operator
to a Fundamental Rights Impact Assessment, so v0.9.2 enforces the gate.
"""

from __future__ import annotations

import json
from importlib.resources import files as _files

import jsonschema

ANNEX_III_BASES = (
    "safety_component",
    "biometric",
    "critical_infrastructure",
    "education",
    "employment",
    "essential_services",
    "law_enforcement",
    "migration",
    "administration_of_justice",
    "general_purpose_ai",
)


def _load_schema() -> dict:
    """Load the bundled schema."""
    with (_files("robot_md").joinpath("schemas/v1/robot.schema.json")).open("r") as f:
        return json.load(f)


def _validate_manifest_dict(manifest: dict) -> list[str]:
    """Validate a manifest dict directly against schema. Return list of error strings."""
    schema = _load_schema()
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )
    errors = []
    for err in sorted(validator.iter_errors(manifest), key=lambda e: e.path):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"schema: {path}: {err.message}")
    return errors


def _base() -> dict:
    """Minimal manifest shell that passes v1 schema."""
    return {
        "rcan_version": "3.0",
        "metadata": {
            "robot_name": "test_robot",
            "manufacturer": "acme",
            "model": "t1",
            "version": "1.0",
        },
        "physics": {
            "type": "arm",
            "dof": 1,
            "kinematics": [
                {
                    "id": "joint1",
                    "axis": "z",
                    "limits_deg": [-90, 90],
                    "servo_id": 1,
                    "encoder_sign": 1,
                    "zero_pose_steps": 2048,
                }
            ],
        },
        "drivers": [
            {
                "id": "driver1",
                "protocol": "feetech",
                "port": "/dev/ttyACM0",
            }
        ],
        "safety": {
            "estop": {
                "type": "gpio",
                "pin": 17,
                "software": True,
                "response_ms": 100,
            }
        },
        "compliance": {},
    }


def test_annex_iii_basis_is_optional():
    m = _base()
    errors = _validate_manifest_dict(m)
    assert errors == [], errors


def test_annex_iii_basis_accepts_each_spec_value():
    for v in ANNEX_III_BASES:
        m = _base()
        m["compliance"]["annex_iii_basis"] = v
        m["compliance"]["fria_ref"] = "https://example.org/fria/report.pdf"
        errors = _validate_manifest_dict(m)
        assert errors == [], f"{v}: {errors}"


def test_annex_iii_basis_rejects_unknown_value():
    m = _base()
    m["compliance"]["annex_iii_basis"] = "bogus_category"
    m["compliance"]["fria_ref"] = "https://example.org/fria/report.pdf"
    errors = _validate_manifest_dict(m)
    assert any("annex_iii_basis" in e or "enum" in e.lower() for e in errors), errors


# ---- v0.9.2 FRIA gate ----------------------------------------------------


def test_fria_gate_neither_set_is_ok():
    """Not declaring annex_iii_basis skips the gate entirely."""
    m = _base()
    # Neither annex_iii_basis nor fria_ref set
    errors = _validate_manifest_dict(m)
    assert errors == [], errors


def test_fria_gate_fria_alone_is_ok():
    """fria_ref without annex_iii_basis is fine — operator may record a FRIA even
    if they don't claim Annex III applicability."""
    m = _base()
    m["compliance"]["fria_ref"] = "https://example.org/fria/report.pdf"
    errors = _validate_manifest_dict(m)
    assert errors == [], errors


def test_fria_gate_annex_without_fria_fails():
    """Setting annex_iii_basis WITHOUT fria_ref must fail the gate."""
    m = _base()
    m["compliance"]["annex_iii_basis"] = "safety_component"
    errors = _validate_manifest_dict(m)
    assert any("fria_ref" in e for e in errors), f"expected fria_ref-required error, got: {errors}"


def test_fria_gate_annex_with_null_fria_fails():
    """fria_ref=null does NOT satisfy the gate — v0.9.2 requires a real URI."""
    m = _base()
    m["compliance"]["annex_iii_basis"] = "biometric"
    m["compliance"]["fria_ref"] = None
    errors = _validate_manifest_dict(m)
    assert any("fria_ref" in e for e in errors), f"expected fria_ref null to fail, got: {errors}"


def test_fria_gate_annex_with_non_uri_fria_fails():
    """fria_ref must be a URI, not an arbitrary string."""
    m = _base()
    m["compliance"]["annex_iii_basis"] = "employment"
    m["compliance"]["fria_ref"] = "not a uri"
    errors = _validate_manifest_dict(m)
    assert any("fria_ref" in e for e in errors), f"expected non-URI fria_ref to fail, got: {errors}"


def test_fria_gate_annex_with_empty_fria_fails():
    """Empty string fria_ref is not a URI and must fail."""
    m = _base()
    m["compliance"]["annex_iii_basis"] = "critical_infrastructure"
    m["compliance"]["fria_ref"] = ""
    errors = _validate_manifest_dict(m)
    assert any("fria_ref" in e for e in errors), f"expected empty fria_ref to fail, got: {errors}"

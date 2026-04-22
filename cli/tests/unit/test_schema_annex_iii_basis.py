"""v0.9.0 — compliance.annex_iii_basis slot.

Per rcan-spec §22, a robot declares which Annex III use case basis it falls
under (if any). Enum of 10 values; optional in v0.9.0. FRIA gating (requiring
fria_ref when annex_iii_basis is set) arrives in v0.9.2.
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
    validator = jsonschema.Draft202012Validator(schema)
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
        errors = _validate_manifest_dict(m)
        assert errors == [], f"{v}: {errors}"


def test_annex_iii_basis_rejects_unknown_value():
    m = _base()
    m["compliance"]["annex_iii_basis"] = "bogus_category"
    errors = _validate_manifest_dict(m)
    assert any("annex_iii_basis" in e or "enum" in e.lower() for e in errors), errors

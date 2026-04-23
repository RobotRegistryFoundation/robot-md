"""v0.9.6 — metadata.rcn_ids / rmn / rhn_ids schema slots.

RCAN spec §21 registry enumerates four entity types keyed by prefix:
RRN (robots), RCN (components), RMN (models), RHN (harnesses). robot-md
already ships RRN; v0.9.6 accepts + emits the other three in the
manifest metadata block so they flow into IFU + EU-register artifacts.
"""

from __future__ import annotations

import json
from importlib.resources import files as _files

import jsonschema


def _load_schema() -> dict:
    with (_files("robot_md").joinpath("schemas/v1/robot.schema.json")).open("r") as f:
        return json.load(f)


def _validate(manifest: dict) -> list[str]:
    schema = _load_schema()
    v = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )
    errors = []
    for err in sorted(v.iter_errors(manifest), key=lambda e: e.path):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"schema: {path}: {err.message}")
    return errors


def _base() -> dict:
    return {
        "rcan_version": "3.0",
        "metadata": {
            "robot_name": "test",
            "manufacturer": "acme",
            "model": "t1",
            "version": "1.0",
        },
        "physics": {
            "type": "arm",
            "dof": 1,
            "kinematics": [
                {
                    "id": "j1",
                    "axis": "z",
                    "limits_deg": [-90, 90],
                    "servo_id": 1,
                    "encoder_sign": 1,
                    "zero_pose_steps": 2048,
                }
            ],
        },
        "drivers": [{"id": "d", "protocol": "feetech", "port": "/dev/ttyACM0"}],
        "safety": {"estop": {"software": True, "response_ms": 100}},
        "compliance": {},
    }


# ---- absence is allowed ---------------------------------------------


def test_new_id_slots_all_optional():
    assert _validate(_base()) == []


# ---- rcn_ids --------------------------------------------------------


def test_rcn_ids_accepts_valid_array():
    m = _base()
    m["metadata"]["rcn_ids"] = ["RCN-000000000001", "RCN-000000000042"]
    assert _validate(m) == []


def test_rcn_ids_rejects_wrong_prefix():
    m = _base()
    m["metadata"]["rcn_ids"] = ["RRN-000000000001"]
    errs = _validate(m)
    assert any("rcn_ids" in e for e in errs), errs


def test_rcn_ids_rejects_bad_digit_count():
    m = _base()
    m["metadata"]["rcn_ids"] = ["RCN-001"]
    errs = _validate(m)
    assert any("rcn_ids" in e for e in errs), errs


def test_rcn_ids_rejects_duplicates():
    m = _base()
    m["metadata"]["rcn_ids"] = ["RCN-000000000001", "RCN-000000000001"]
    errs = _validate(m)
    assert any("rcn_ids" in e for e in errs), errs


# ---- rmn ------------------------------------------------------------


def test_rmn_accepts_valid():
    m = _base()
    m["metadata"]["rmn"] = "RMN-000000000007"
    assert _validate(m) == []


def test_rmn_rejects_rrn_prefix():
    m = _base()
    m["metadata"]["rmn"] = "RRN-000000000007"
    errs = _validate(m)
    assert any("rmn" in e for e in errs), errs


# ---- rhn_ids --------------------------------------------------------


def test_rhn_ids_accepts_valid_array():
    m = _base()
    m["metadata"]["rhn_ids"] = ["RHN-000000000099"]
    assert _validate(m) == []


def test_rhn_ids_rejects_lowercase_prefix():
    m = _base()
    m["metadata"]["rhn_ids"] = ["rhn-000000000099"]
    errs = _validate(m)
    assert any("rhn_ids" in e for e in errs), errs


# ---- all three together --------------------------------------------


def test_all_three_id_types_coexist():
    m = _base()
    m["metadata"]["rcn_ids"] = ["RCN-000000000001"]
    m["metadata"]["rmn"] = "RMN-000000000007"
    m["metadata"]["rhn_ids"] = ["RHN-000000000099"]
    assert _validate(m) == []

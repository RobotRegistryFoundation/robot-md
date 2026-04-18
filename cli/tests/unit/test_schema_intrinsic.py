"""Schema: camera intrinsic block + cameras[] cross-reference."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from robot_md.parser import parse_file


def _schema() -> dict:
    # Load schema directly from the file system without caching
    schema_path = Path(__file__).parent.parent.parent / "src" / "robot_md" / "schemas" / "v1" / "robot.schema.json"
    with open(schema_path) as f:
        return json.load(f)


def test_intrinsic_required_fields_accepted(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    jsonschema.Draft202012Validator(_schema()).validate(parsed.frontmatter)


def test_intrinsic_missing_fx_rejected(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["drivers"][1]["streams"]["rgb"]["intrinsic"].pop("fx")
    with pytest.raises(jsonschema.ValidationError, match="fx"):
        jsonschema.Draft202012Validator(_schema()).validate(parsed.frontmatter)


def test_distortion_model_enum(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["drivers"][1]["streams"]["rgb"]["intrinsic"]["distortion_model"] = "bogus"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(parsed.frontmatter)


def test_plumb_bob_requires_5_coeffs(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["drivers"][1]["streams"]["rgb"]["intrinsic"]["distortion_coeffs"] = [0.0]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(parsed.frontmatter)


def test_depth_stream_derived_from_allowed(fixtures_dir):
    """A `depth` stream with `derived_from` and no intrinsic validates."""
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    jsonschema.Draft202012Validator(_schema()).validate(parsed.frontmatter)


def test_stream_key_unknown_rejected(fixtures_dir):
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["drivers"][1]["streams"]["BOGUS"] = {"intrinsic": None}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(parsed.frontmatter)

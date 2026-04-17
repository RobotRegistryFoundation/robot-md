"""Verify the JSON Schema itself is a valid draft-2020-12 schema."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "v1" / "robot.schema.json"


def test_schema_file_exists():
    assert SCHEMA_PATH.exists(), f"schema missing at {SCHEMA_PATH}"


def test_schema_is_valid_json():
    with SCHEMA_PATH.open() as f:
        schema = json.load(f)
    assert isinstance(schema, dict)


def test_schema_is_valid_against_metaschema():
    with SCHEMA_PATH.open() as f:
        schema = json.load(f)
    # This raises if the schema itself is not a valid draft-2020-12 schema
    jsonschema.Draft202012Validator.check_schema(schema)


def test_schema_declares_draft_2020_12():
    with SCHEMA_PATH.open() as f:
        schema = json.load(f)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"


def test_schema_declares_its_own_id():
    with SCHEMA_PATH.open() as f:
        schema = json.load(f)
    assert schema.get("$id") == "https://robotmd.dev/schema/v1/robot.schema.json"


def test_schema_requires_core_blocks():
    with SCHEMA_PATH.open() as f:
        schema = json.load(f)
    required = set(schema["required"])
    assert {"rcan_version", "metadata", "physics", "drivers", "safety"} == required

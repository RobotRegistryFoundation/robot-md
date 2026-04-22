"""Validate a parsed ROBOT.md against schema, RCAN rules, and body requirements."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib.resources import files as _files
from typing import Any

import jsonschema

from robot_md.parser import ParsedRobotMd

# Exit codes (matches spec §8)
VALID = 0
FILE_ERROR = 1
SCHEMA_VIOLATION = 2
RCAN_CONFORMANCE_VIOLATION = 3
MISSING_BODY_SECTION = 4


REQUIRED_BODY_SECTIONS = ["## Identity", "## Safety Gates"]
# Also required: H1 matching robot_name; "## What <name> Can Do" header


@dataclass
class ValidationResult:
    code: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: str = ""


def _load_schema() -> dict[str, Any]:
    # Schema is bundled as a package resource — works in wheel, sdist, and editable installs.
    # Canonical source: robot-md repo schema/v1/robot.schema.json; CI keeps this copy in sync.
    with (_files("robot_md").joinpath("schemas/v1/robot.schema.json")).open("r") as f:
        return json.load(f)


def validate(parsed: ParsedRobotMd) -> ValidationResult:
    """Validate a parsed ROBOT.md. Return a ValidationResult.

    Order: schema first, then body-section checks. RCAN conformance is folded
    into the schema via regex patterns on rcan_version and signing_alg.
    """
    fm = parsed.frontmatter
    body = parsed.body or ""
    errors: list[str] = []

    # Internal parser markers — strip before schema validation, re-attach after
    _deprecations = fm.pop("_deprecations", None)

    # 1. Schema validation. format_checker enforces JSON Schema `format`
    # annotations (e.g., `format: uri`) — in Draft 2020-12 these are
    # annotation-only by default, so without this the FRIA gate (v0.9.2)
    # can't reject `compliance.fria_ref: "not-a-uri"`.
    schema = _load_schema()
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )
    schema_errors = sorted(validator.iter_errors(fm), key=lambda e: e.path)
    if schema_errors:
        for err in schema_errors:
            path = ".".join(str(p) for p in err.absolute_path) or "<root>"
            errors.append(f"schema: {path}: {err.message}")
        if _deprecations is not None:
            fm["_deprecations"] = _deprecations
        return ValidationResult(code=SCHEMA_VIOLATION, errors=errors)

    # 1b. Cross-reference: physics.solver.cameras[].driver_id must resolve
    cameras = (fm.get("physics", {}) or {}).get("solver", {}).get("cameras") or []
    drivers_by_id = {d.get("id"): d for d in (fm.get("drivers") or []) if d.get("id")}
    for idx, cam in enumerate(cameras):
        did = cam.get("driver_id")
        if did and did not in drivers_by_id:
            errors.append(
                f"cross-ref: physics.solver.cameras[{idx}].driver_id='{did}' "
                f"does not match any drivers[].id"
            )

    if errors:
        if _deprecations is not None:
            fm["_deprecations"] = _deprecations
        return ValidationResult(code=SCHEMA_VIOLATION, errors=errors)

    # 1c. Build warnings list for null intrinsics
    warnings: list[str] = []
    for idx, cam in enumerate(cameras):
        did = cam.get("driver_id")
        primary = cam.get("primary_stream")
        drv = drivers_by_id.get(did, {})
        streams = drv.get("streams", {}) or {}
        stream = streams.get(primary, {}) or {}
        if stream.get("intrinsic") is None and stream.get("derived_from") is None:
            warnings.append(
                f"cameras[{idx}].primary_stream='{primary}' has null intrinsic — "
                f"run `robot-md calibrate-intrinsic --driver {did} --stream {primary}`"
            )

    # 2. Body-section checks
    robot_name = fm.get("metadata", {}).get("robot_name", "")
    if not _has_matching_h1(body, robot_name):
        errors.append(
            f"body: missing H1 matching robot_name '{robot_name}' "
            f"(first line after blank should be '# {robot_name}')"
        )
    for section in REQUIRED_BODY_SECTIONS:
        if section not in body:
            errors.append(f"body: missing required section '{section}'")
    # "## What <name> Can Do" check
    what_pattern = rf"^## What {re.escape(robot_name)} Can Do\s*$"
    if not re.search(what_pattern, body, re.MULTILINE | re.IGNORECASE):
        errors.append(
            f"body: missing required section '## What {robot_name} Can Do' (case-insensitive)"
        )

    if errors:
        if _deprecations is not None:
            fm["_deprecations"] = _deprecations
        return ValidationResult(code=MISSING_BODY_SECTION, errors=errors, warnings=warnings)

    # 3. Valid — append deprecation warnings and re-attach marker
    if _deprecations:
        for msg in _deprecations:
            warnings.append(f"deprecated: {msg}")
        fm["_deprecations"] = _deprecations

    # 3. Valid — build summary
    summary = _build_summary(fm)
    return ValidationResult(code=VALID, errors=[], warnings=warnings, summary=summary)


def _has_matching_h1(body: str, robot_name: str) -> bool:
    """Check if the body has an H1 matching robot_name (case-insensitive)."""
    if not robot_name:
        return False
    pattern = rf"^# {re.escape(robot_name)}\s*$"
    return bool(re.search(pattern, body, re.MULTILINE | re.IGNORECASE))


def _build_summary(fm: dict[str, Any]) -> str:
    """Build a one-line summary of a valid ROBOT.md."""
    name = fm.get("metadata", {}).get("robot_name", "?")
    ptype = fm.get("physics", {}).get("type", "?")
    dof = fm.get("physics", {}).get("dof", "?")
    caps = fm.get("capabilities", [])
    cap_count = len(caps) if isinstance(caps, list) else 0
    return f"{name} ({ptype}, {dof} DoF, {cap_count} capabilities)"

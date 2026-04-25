"""§22 FRIA (rcan-fria-v1) emission for robot-md.

Builds the EU AI Act Art. 27 Fundamental Rights Impact Assessment from a
ROBOT.md manifest. Uses rcan-py 3.3.0's FriaDocument/FriaConformance/
FriaSigningKey dataclasses as the canonical wire format. Signing reuses
v0.9.1 signing.sign_body — same hybrid (ML-DSA-65 + Ed25519) signature
used by register POSTs and §23/§24/§25 emit-* artifacts.

Field sources:
- system               ← manifest metadata + capabilities
- deployment           ← compliance.{annex_iii_basis, deployment_context,
                                     affected_groups, known_risks} +
                         safety.{estop, hitl_gates} + brain.confidence_gate
- conformance          ← optional; populated when --conformance flag points
                         at a §23 benchmark whose results imply pass/warn/fail.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from pathlib import Path

from rcan.compliance import FriaConformance, FriaDocument

from robot_md.parser import parse_file

FRIA_SCHEMA_NAME = "rcan-fria-v1"

DEFAULT_KNOWN_RISKS = (
    "Unauthorized motion outside declared workspace bounds.",
    "LLM planner producing an invalid motion plan.",
    "Hardware actuator fault causing unintended motion.",
)


def _system(fm: dict, rcan_version: str) -> dict:
    meta = fm.get("metadata", {}) or {}
    capabilities = sorted(set(fm.get("capabilities") or ()))
    return {
        "rrn": meta.get("rrn") or "",
        "rrn_uri": meta.get("rrn_uri") or "",
        "robot_name": meta.get("robot_name") or "",
        "manufacturer": meta.get("manufacturer") or "",
        "model": meta.get("model") or "",
        "firmware_version": meta.get("firmware_version") or meta.get("version") or "",
        "rcan_version": rcan_version,
        "capabilities": capabilities,
    }


def _human_oversight(fm: dict) -> dict:
    safety = fm.get("safety", {}) or {}
    brain = fm.get("brain", {}) or {}
    estop = safety.get("estop") or {}
    return {
        "estop": {
            "software": bool(estop.get("software")),
            "hardware": bool(estop.get("hardware")),
            "response_ms": estop.get("response_ms"),
        },
        "hitl_gates": list(safety.get("hitl_gates") or ()),
        "confidence_gate": brain.get("confidence_gate"),
    }


def _deployment(
    fm: dict,
    deployment_context: str | None,
    affected_groups: list[str] | None,
    known_risks_override: list[str] | None,
) -> dict:
    comp = fm.get("compliance", {}) or {}
    risks = (
        known_risks_override
        if known_risks_override is not None
        else (comp.get("known_risks") or list(DEFAULT_KNOWN_RISKS))
    )
    return {
        "annex_iii_basis": comp.get("annex_iii_basis") or "",
        "deployment_context": (
            deployment_context if deployment_context is not None
            else comp.get("deployment_context") or ""
        ),
        "affected_groups": list(
            affected_groups if affected_groups is not None
            else comp.get("affected_groups") or ()
        ),
        "known_risks": list(risks),
        "human_oversight": _human_oversight(fm),
    }


def build_artifact(
    manifest_path: Path,
    *,
    deployment_context: str | None = None,
    affected_groups: list[str] | None = None,
    known_risks: list[str] | None = None,
    conformance: FriaConformance | None = None,
) -> dict:
    """Assemble an rcan-fria-v1 dict from the manifest + optional inputs.

    Returned dict mirrors the rcan.compliance.FriaDocument shape. `sig` and
    `signing_key` are placeholders until sign_artifact is called.
    """
    parsed = parse_file(manifest_path)
    fm = parsed.frontmatter
    rcan_version = str(fm.get("rcan_version") or "3.0")

    doc = FriaDocument(
        schema=FRIA_SCHEMA_NAME,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        system=_system(fm, rcan_version),
        deployment=_deployment(fm, deployment_context, affected_groups, known_risks),
        signing_key={},  # populated by sign_artifact
        sig={},  # populated by sign_artifact
        conformance=conformance,
    )
    return dataclasses.asdict(doc)


def sign_artifact(artifact: dict, rrn: str) -> dict:
    """Route the artifact through v0.9.1 signing.sign_body. Returns a new
    dict with `sig` and `signing_key` populated. Raises RuntimeError if the
    keystore has no signing key for `rrn`.
    """
    from robot_md.signing import load_keypair, sign_body

    kp = load_keypair(rrn)
    if kp is None:
        raise RuntimeError(
            f"no signing keypair for {rrn} at ~/.robot-md/keys/. "
            f"Run `robot-md register <manifest>` to mint one."
        )
    return sign_body(kp, artifact)

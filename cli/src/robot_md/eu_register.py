"""§26 EU Register Submission (rcan-eu-register-v1) for robot-md.

Builds the EU AI Act Art. 49 submission package from a ROBOT.md manifest
and a pre-existing signed FRIA document. Pure (apart from manifest read
+ FRIA existence check); --sign routes through v0.9.1 signing.sign_body
like every other v0.9.x external artifact.

Per rcan-spec §26, all fields are MUST. Emission errors if:
- metadata.rrn missing (can't register an unregistered robot)
- compliance.annex_iii_basis missing (Art. 49 applies to high-risk AI
  systems only — if it's not Annex III, §26 is the wrong artifact)
- metadata.manufacturer or metadata.author missing (provider identity)
- --fria path doesn't exist (package references the signed FRIA by
  filename; the file must be shipped alongside)

The FRIA is referenced BY BASENAME (not full path) because the spec
says "Filename of the signed rcan-fria-v1 document included with this
submission" — the EU database expects the FRIA as a sibling file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from robot_md.parser import parse_file

EU_REGISTER_SCHEMA_NAME = "rcan-eu-register-v1"
CONFORMITY_STATUS_DECLARED = "declared"
SUBMISSION_INSTRUCTIONS = (
    "Submit this package to the EU AI Act database at "
    "https://ec.europa.eu/digital-strategy/en/policies/european-ai-act. "
    "Include the referenced rcan-fria-v1 JSON as an attachment."
)


class EuRegisterError(ValueError):
    """Raised when the manifest or inputs don't satisfy §26 requirements."""


def _provider(fm: dict) -> dict:
    meta = fm.get("metadata", {}) or {}
    name = (meta.get("manufacturer") or "").strip()
    contact = (meta.get("author") or "").strip()
    if not name:
        raise EuRegisterError("metadata.manufacturer required — §26 MUSTs the provider name.")
    if not contact:
        raise EuRegisterError("metadata.author required — §26 MUSTs a provider contact email.")
    return {"name": name, "contact": contact}


def _system(fm: dict, opencastor_version: str | None) -> dict:
    meta = fm.get("metadata", {}) or {}
    rrn = (meta.get("rrn") or "").strip()
    if not rrn:
        raise EuRegisterError(
            "metadata.rrn required — register the robot first "
            "(`robot-md register`) before emitting §26."
        )
    return {
        "rrn": rrn,
        "rrn_uri": meta.get("rrn_uri") or "",
        "robot_name": meta.get("robot_name") or "",
        "rcan_version": str(fm.get("rcan_version") or "3.0"),
        "opencastor_version": opencastor_version or "",
    }


def build_artifact(
    manifest_path: Path,
    *,
    fria_path: Path,
    opencastor_version: str | None = None,
) -> dict:
    """Assemble an rcan-eu-register-v1 dict. Raises EuRegisterError on
    missing prerequisites. The FRIA file must exist at `fria_path` (it
    is referenced by basename in the emitted package).
    """
    if not fria_path.exists():
        raise EuRegisterError(f"FRIA file not found: {fria_path}")

    parsed = parse_file(manifest_path)
    fm = parsed.frontmatter
    comp = fm.get("compliance", {}) or {}
    basis = (comp.get("annex_iii_basis") or "").strip()
    if not basis:
        raise EuRegisterError(
            "compliance.annex_iii_basis required — §26 Art. 49 applies only "
            "to high-risk AI systems. If not Annex III, §26 is not the right artifact."
        )

    provider = _provider(fm)
    system = _system(fm, opencastor_version)

    return {
        "schema": EU_REGISTER_SCHEMA_NAME,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "fria_ref": fria_path.name,
        "provider": provider,
        "system": system,
        "annex_iii_basis": basis,
        "conformity_status": CONFORMITY_STATUS_DECLARED,
        "submission_instructions": SUBMISSION_INSTRUCTIONS,
    }


def sign_artifact(artifact: dict, rrn: str) -> dict:
    """Route through v0.9.1 signing.sign_body. Same wire format as
    register, emit-benchmarks, emit-ifu, incidents report.
    """
    from robot_md.signing import load_keypair, sign_body

    kp = load_keypair(rrn)
    if kp is None:
        raise RuntimeError(
            f"no signing keypair for {rrn} at ~/.robot-md/keys/. "
            f"Run `robot-md register <manifest>` to mint one."
        )
    return sign_body(kp, artifact)

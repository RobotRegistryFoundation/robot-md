"""Article 11 technical-documentation summary aggregator.

`robot-md-art11-summary-v0` — a single artifact that consolidates the eight
EU AI Act Art. 11 categories from a ROBOT.md manifest, the on-disk signed
artifacts inventory, and the per-robot post-market incident log.

This is intentionally an aggregator with a non-spec schema name. rcan-spec
hasn't defined an Art. 11 wire format upstream; this artifact stitches
authoritative pieces (manifest + signed §22-26 artifacts + §25 log) into
a notified-body-readable dossier without overclaiming.

Coverage of Art. 11 categories follows the structure produced by
`castor audit --art11` so robot-md and opencastor outputs are comparable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from robot_md.parser import parse_file

ART11_SCHEMA_NAME = "robot-md-art11-summary-v0"

ART11_CATEGORIES = (
    "system_identity",          # Art. 11 §1a
    "hardware_provenance",      # Art. 11 §1b
    "model_provenance",         # Art. 11 §1c
    "safety_controls",          # Art. 9
    "post_market_monitoring",   # Art. 72
    "sbom",                     # Art. 11 §1b
    "notified_body_submission", # status + artifact inventory
    "data_governance",          # Art. 10 (placeholder; manifest-derived where present)
)


def _system_identity(fm: dict, rcan_version: str) -> dict:
    meta = fm.get("metadata", {}) or {}
    return {
        "rrn": meta.get("rrn") or "",
        "rrn_uri": meta.get("rrn_uri") or "",
        "robot_name": meta.get("robot_name") or "",
        "manufacturer": meta.get("manufacturer") or "",
        "model": meta.get("model") or "",
        "firmware_version": meta.get("firmware_version") or meta.get("version") or "",
        "rcan_version": rcan_version,
    }


def _hardware_provenance(fm: dict) -> dict:
    physics = fm.get("physics", {}) or {}
    drivers = fm.get("drivers", []) or []
    components = fm.get("components", []) or []  # rcan-spec §21 component RRNs
    return {
        "physics_type": physics.get("type") or "",
        "dof": physics.get("dof"),
        "drivers": [
            {"id": d.get("id"), "protocol": d.get("protocol")} for d in drivers
        ],
        "components_count": len(components),
        "components": components,
    }


def _model_provenance(fm: dict) -> dict:
    """Pull declared LLM/model providers from agent.runtimes[].models or brain block."""
    models: list[dict] = []
    agent = fm.get("agent", {}) or {}
    for runtime in agent.get("runtimes", []) or []:
        for model in runtime.get("models", []) or []:
            models.append(
                {
                    "runtime_id": runtime.get("id"),
                    "provider": model.get("provider"),
                    "model": model.get("model"),
                    "role": model.get("role"),
                }
            )
    # Legacy single-brain shape (RCAN <3.0)
    brain = fm.get("brain", {}) or {}
    if brain.get("planning_provider"):
        models.append(
            {
                "runtime_id": "brain",
                "provider": brain.get("planning_provider"),
                "model": brain.get("planning_model"),
                "role": "planner",
            }
        )
    return {"models": models, "count": len(models)}


def _safety_controls(fm: dict) -> dict:
    safety = fm.get("safety", {}) or {}
    return {
        "estop": safety.get("estop") or {},
        "hitl_gates": list(safety.get("hitl_gates") or ()),
        "duty_cycle_limits": dict(safety.get("duty_cycle_limits") or {}),
        "bounds": safety.get("bounds") or {},
    }


def _post_market_monitoring(rrn: str) -> dict:
    """Read §25 incident log + summarize. Path resolution mirrors incidents.py."""
    log_dir = Path.home() / ".robot-md" / "incidents"
    log_path = log_dir / f"{rrn}.jsonl"
    incidents: list[dict] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    incidents.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    by_severity = {
        "life_health": sum(1 for i in incidents if i.get("severity") == "life_health"),
        "other": sum(1 for i in incidents if i.get("severity") == "other"),
    }
    return {
        "incident_log": str(log_path),
        "total_incidents": len(incidents),
        "by_severity": by_severity,
    }


def _sbom(sbom_path: Path | None) -> dict:
    if sbom_path is None:
        return {"present": False, "path": None, "format": None}
    if not sbom_path.exists():
        return {"present": False, "path": str(sbom_path), "format": None}
    try:
        data = json.loads(sbom_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"present": True, "path": str(sbom_path), "format": "unparseable"}
    fmt = data.get("bomFormat") or "unknown"
    return {"present": True, "path": str(sbom_path), "format": fmt}


def _notified_body_submission(rrn: str, artifacts_dir: Path | None) -> dict:
    """Inventory signed artifacts on disk that would be submitted to a notified body."""
    inventory: list[dict] = []
    if artifacts_dir is not None and artifacts_dir.is_dir():
        for path in sorted(artifacts_dir.glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            schema = doc.get("schema") or "unknown"
            inventory.append(
                {
                    "schema": schema,
                    "path": str(path),
                    "signed": bool(doc.get("sig")) and bool(doc.get("signing_key")),
                }
            )
    expected_schemas = {
        "rcan-fria-v1",
        "rcan-ifu-v1",
        "rcan-safety-benchmark-v1",
        "rcan-eu-register-v1",
        "rcan-incidents-v1",
    }
    present_schemas = {a["schema"] for a in inventory}
    missing = sorted(expected_schemas - present_schemas)
    return {
        "rrn": rrn,
        "artifacts": inventory,
        "missing_artifacts": missing,
        "complete": not missing,
    }


def _data_governance(fm: dict) -> dict:
    comp = fm.get("compliance", {}) or {}
    return {
        "training_data": comp.get("training_data") or {},
        "data_retention": comp.get("data_retention") or {},
        "annex_iii_basis": comp.get("annex_iii_basis") or "",
    }


def build_artifact(
    manifest_path: Path,
    *,
    sbom_path: Path | None = None,
    signed_artifacts_dir: Path | None = None,
) -> dict:
    """Assemble the Art. 11 summary dict from the manifest + on-disk evidence."""
    parsed = parse_file(manifest_path)
    fm = parsed.frontmatter
    rcan_version = str(fm.get("rcan_version") or "3.0")
    rrn = ((fm.get("metadata") or {}).get("rrn") or "").strip()

    return {
        "schema": ART11_SCHEMA_NAME,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "rrn": rrn,
        "system_identity": _system_identity(fm, rcan_version),
        "hardware_provenance": _hardware_provenance(fm),
        "model_provenance": _model_provenance(fm),
        "safety_controls": _safety_controls(fm),
        "post_market_monitoring": _post_market_monitoring(rrn),
        "sbom": _sbom(sbom_path),
        "notified_body_submission": _notified_body_submission(rrn, signed_artifacts_dir),
        "data_governance": _data_governance(fm),
        "sig": {},
        "signing_key": {},
    }


def sign_artifact(artifact: dict, rrn: str) -> dict:
    """Route through v0.9.1 signing.sign_body. Same wire format as register/IFU/FRIA."""
    from robot_md.signing import load_keypair, sign_body

    kp = load_keypair(rrn)
    if kp is None:
        raise RuntimeError(
            f"no signing keypair for {rrn} at ~/.robot-md/keys/. "
            f"Run `robot-md register <manifest>` to mint one."
        )
    return sign_body(kp, artifact)

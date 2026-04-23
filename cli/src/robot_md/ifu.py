"""§24 Instructions-for-Use (rcan-ifu-v1) emission for robot-md.

Builds the EU AI Act Art. 13(3) structured IFU from a ROBOT.md manifest
and an optional v0.9.3 §23 safety benchmark artifact. Pure (aside from
the manifest read); --sign integration reuses v0.9.1 signing.sign_body.

Field sources — all 8 Art. 13(3) categories:
- provider_identity           ← manifest metadata + brain.planning_*
- intended_purpose            ← compliance.annex_iii_basis + --description
- capabilities_and_limitations ← manifest capabilities + known_limitations
                                 (manifest override → built-in default)
- accuracy_and_performance    ← --benchmark points at a §23 artifact;
                                 embeds schema, timestamp, overall_pass,
                                 per-path p95 (no full results copy).
- human_oversight_measures    ← safety.hitl_gates + safety.estop +
                                 brain.confidence_gate
- known_risks_and_misuse      ← compliance.known_risks or built-in
- expected_lifetime           ← compliance.expected_lifetime or --lifetime
                                 or built-in
- maintenance_requirements    ← built-in, incident_log path resolves to
                                 §25 per-robot JSONL location
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from robot_md.parser import parse_file

IFU_SCHEMA_NAME = "rcan-ifu-v1"
ART13_COVERAGE = (
    "provider_identity",
    "intended_purpose",
    "capabilities_and_limitations",
    "accuracy_and_performance",
    "human_oversight_measures",
    "known_risks_and_misuse",
    "expected_lifetime",
    "maintenance_requirements",
)

DEFAULT_LIFETIME = (
    "Software support: rolling release with semver-minor updates. "
    "Hardware dependency: see manifest metadata.model."
)
DEFAULT_MAINTENANCE = {
    "update_cadence": "rolling",
    "conformance_checks": "robot-md validate on every change",
    "incident_log": "~/.robot-md/incidents/<rrn>.jsonl (rcan-spec §25)",
}
DEFAULT_KNOWN_LIMITATIONS = (
    "AI provider responses subject to model confidence thresholds.",
    "Physical limits enforced by manifest safety block.",
    "HiTL authorization required for high-risk actions.",
)
DEFAULT_KNOWN_RISKS = (
    "Unauthorized operation outside the declared workspace bounds.",
    "LLM planner producing an invalid motion plan.",
    "Hardware actuator fault causing unintended motion.",
)


def _provider_identity(fm: dict, rcan_version: str) -> dict:
    meta = fm.get("metadata", {}) or {}
    brain = fm.get("brain", {}) or {}
    return {
        "rrn": meta.get("rrn") or "",
        "rrn_uri": meta.get("rrn_uri") or "",
        "robot_name": meta.get("robot_name") or "",
        "provider_name": meta.get("manufacturer") or "",
        "provider_contact": meta.get("author") or "",
        "rcan_version": rcan_version,
        "agent_provider": brain.get("planning_provider") or "",
        "agent_model": brain.get("planning_model") or "",
    }


def _intended_purpose(fm: dict, description: str | None) -> dict:
    meta = fm.get("metadata", {}) or {}
    comp = fm.get("compliance", {}) or {}
    return {
        "description": description or meta.get("description") or "",
        "annex_iii_basis": comp.get("annex_iii_basis") or "",
        "deployment_context": comp.get("deployment_context") or "",
    }


def _capabilities(fm: dict) -> dict:
    meta = fm.get("metadata", {}) or {}
    capabilities_list = sorted(set(fm.get("capabilities") or ()))
    summary = meta.get("description") or (
        f"Robot with {len(capabilities_list)} declared capabilities."
        if capabilities_list
        else "See manifest."
    )
    limitations = (fm.get("compliance", {}) or {}).get("known_limitations") or list(
        DEFAULT_KNOWN_LIMITATIONS
    )
    return {
        "summary": summary,
        "capabilities": capabilities_list,
        "known_limitations": list(limitations),
    }


def _performance(benchmark: Path | None) -> dict:
    if benchmark is None:
        return {
            "note": (
                "No §23 benchmark artifact attached. Run "
                "`robot-md emit-benchmarks` and rerun `emit-ifu --benchmark`."
            ),
            "benchmark_ref": None,
        }
    data = json.loads(benchmark.read_text(encoding="utf-8"))
    results = data.get("results") or {}
    per_path_p95 = {path: (results.get(path) or {}).get("p95_ms") for path in results}
    return {
        "benchmark_ref": str(benchmark),
        "benchmark_schema": data.get("schema"),
        "benchmark_generated_at": data.get("generated_at"),
        "overall_pass": data.get("overall_pass"),
        "per_path_p95_ms": per_path_p95,
    }


def _oversight(fm: dict) -> dict:
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


def _risks(fm: dict) -> dict:
    comp = fm.get("compliance", {}) or {}
    risks = comp.get("known_risks") or list(DEFAULT_KNOWN_RISKS)
    return {"known_risks": list(risks)}


def _lifetime(fm: dict, override: str | None) -> dict:
    comp = fm.get("compliance", {}) or {}
    return {"description": override or comp.get("expected_lifetime") or DEFAULT_LIFETIME}


def _maintenance(fm: dict) -> dict:
    rrn = (fm.get("metadata") or {}).get("rrn") or "<rrn>"
    m = dict(DEFAULT_MAINTENANCE)
    m["incident_log"] = m["incident_log"].replace("<rrn>", rrn)
    return m


def build_artifact(
    manifest_path: Path,
    *,
    description: str | None = None,
    benchmark: Path | None = None,
    lifetime: str | None = None,
) -> dict:
    """Assemble an rcan-ifu-v1 dict from the manifest + optional inputs."""
    parsed = parse_file(manifest_path)
    fm = parsed.frontmatter
    rcan_version = str(fm.get("rcan_version") or "3.0")
    return {
        "schema": IFU_SCHEMA_NAME,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "art13_coverage": list(ART13_COVERAGE),
        "provider_identity": _provider_identity(fm, rcan_version),
        "intended_purpose": _intended_purpose(fm, description),
        "capabilities_and_limitations": _capabilities(fm),
        "accuracy_and_performance": _performance(benchmark),
        "human_oversight_measures": _oversight(fm),
        "known_risks_and_misuse": _risks(fm),
        "expected_lifetime": _lifetime(fm, lifetime),
        "maintenance_requirements": _maintenance(fm),
    }


def sign_artifact(artifact: dict, rrn: str) -> dict:
    """Route the artifact through v0.9.1 signing.sign_body (same wire format
    as register POSTs and §23 benchmark artifacts). Returns a new dict.
    Raises RuntimeError if the keystore has no signing key for `rrn`.
    """
    from robot_md.signing import load_keypair, sign_body

    kp = load_keypair(rrn)
    if kp is None:
        raise RuntimeError(
            f"no signing keypair for {rrn} at ~/.robot-md/keys/. "
            f"Run `robot-md register <manifest>` to mint one."
        )
    return sign_body(kp, artifact)

"""`robot-md compliance status` — single-shot pre-flight readiness report.

Pulls together all the local + remote signals an operator needs before
attempting an EU AI Act submission:

- Manifest validity + rcan_version + rrn
- Keystore: signing keypair + apikey presence
- Hash-chained audit log: chain integrity + entry count
- Per-robot incidents log summary
- On-disk signed artifacts inventory under <project>/compliance/
- RRF: registry reachability + RRN record presence + rcan_version drift
- Per-emit-* submission readiness (ready / blocked-on-X)
- Aggregated blocker list

Output is structured (returned as dict from gather_status) for
JSON-mode CLI and machine consumption; format_status_text() renders
the human-readable view.

Network probe is opt-in via `network_probe=True` so unit tests stay
deterministic and offline.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from robot_md import __version__
from robot_md.audit import AuditChainError, load_entries as audit_load_entries
from robot_md.audit import verify_chain as audit_verify_chain
from robot_md.parser import parse_file
from robot_md.register import load_apikey
from robot_md.signing import load_keypair

DEFAULT_RRF_ENDPOINT = "https://robotregistryfoundation.org"

# Schemas the operator should expect to find under <project>/compliance/
# when the demo or emit-* pipeline has been run.
EXPECTED_ARTIFACT_SCHEMAS: tuple[str, ...] = (
    "rcan-fria-v1",
    "rcan-ifu-v1",
    "rcan-safety-benchmark-v1",
    "rcan-incidents-v1",
    "rcan-eu-register-v1",
)

# Maps emit-* command kinds → the apikey-gated submit endpoints they POST to.
# Order matches user-facing flow (pre-market → post-market).
SUBMISSION_KINDS: tuple[str, ...] = (
    "fria",
    "ifu",
    "safety-benchmark",
    "incident-report",
    "eu-register",
)


def _load_fm(manifest_path: Path) -> dict:
    parsed = parse_file(manifest_path)
    return parsed.frontmatter


def _check_keystore(rrn: str) -> dict[str, Any]:
    keys_dir = Path.home() / ".robot-md" / "keys"
    signing_path = keys_dir / f"{rrn}.signing.json"
    apikey_path = keys_dir / f"{rrn}.apikey"
    return {
        "signing_keypair": {
            "present": load_keypair(rrn) is not None,
            "path": str(signing_path),
        },
        "apikey": {
            "present": bool(load_apikey(rrn)),
            "path": str(apikey_path),
        },
    }


def _check_audit(rrn: str) -> dict[str, Any]:
    try:
        result = audit_verify_chain(rrn)
        return {
            "valid": True,
            "entries": result["entries"],
            "note": (
                "truncation of trailing entries is undetectable without an "
                "external witness (e.g., RRF-countersigned checkpoint)"
            ),
        }
    except AuditChainError as e:
        return {"valid": False, "error": str(e)}


def _check_incidents(rrn: str) -> dict[str, Any]:
    log = Path.home() / ".robot-md" / "incidents" / f"{rrn}.jsonl"
    if not log.exists():
        return {"path": str(log), "total": 0, "by_severity": {}}
    by_sev: dict[str, int] = {}
    total = 0
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        sev = entry.get("severity", "unknown")
        by_sev[sev] = by_sev.get(sev, 0) + 1
        total += 1
    return {"path": str(log), "total": total, "by_severity": by_sev}


def _check_artifacts(artifacts_dir: Path | None) -> dict[str, Any]:
    if artifacts_dir is None or not artifacts_dir.is_dir():
        return {
            "dir": str(artifacts_dir) if artifacts_dir else None,
            "present": [],
            "missing": list(EXPECTED_ARTIFACT_SCHEMAS),
        }
    present: list[dict[str, Any]] = []
    seen_schemas: set[str] = set()
    for path in sorted(artifacts_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        schema = doc.get("schema") or "unknown"
        # Two signed-envelope shapes in the ecosystem:
        #   1. sign_body output: top-level pq_signing_pub + pq_kid + sig
        #      (used by register, IFU, benchmarks, incidents, eu-register, art-11, apikey-request)
        #   2. FriaDocument shape: nested signing_key dataclass + sig
        #      (used by fria.py — rcan-py 3.3.0 wire format)
        has_top_level_sig = bool(doc.get("sig")) and bool(doc.get("pq_signing_pub"))
        has_nested_sig = bool(doc.get("sig")) and bool(doc.get("signing_key"))
        signed = has_top_level_sig or has_nested_sig
        present.append(
            {
                "schema": schema,
                "path": str(path),
                "signed": signed,
                "size_bytes": path.stat().st_size,
            }
        )
        seen_schemas.add(schema)
    missing = sorted(set(EXPECTED_ARTIFACT_SCHEMAS) - seen_schemas)
    return {"dir": str(artifacts_dir), "present": present, "missing": missing}


def _check_registry(
    rrn: str,
    fm: dict,
    *,
    endpoint: str,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Probe RRF for reachability and record presence. Returns a structured
    result; never raises. ``manifest_rcan_version`` is always set so the
    drift comparison is well-defined even when offline.
    """
    base = endpoint.rstrip("/")
    list_url = f"{base}/v2/robots"
    record_url = f"{list_url}/{rrn}"
    manifest_v = str(fm.get("rcan_version") or "")

    out: dict[str, Any] = {
        "endpoint": base,
        "reachable": False,
        "record_present": False,
        "manifest_rcan_version": manifest_v,
        "record_rcan_version": None,
        "version_drift": False,
        "errors": [],
    }

    ua = {"User-Agent": f"robot-md/{__version__}"}

    # 1. Reachability
    req = urllib.request.Request(list_url, method="GET", headers=ua)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out["reachable"] = resp.status == 200
    except Exception as e:
        out["errors"].append(f"reachability: {type(e).__name__}: {e}")
        return out

    # 2. Record lookup
    req = urllib.request.Request(record_url, method="GET", headers=ua)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                rec = json.loads(body)
            except json.JSONDecodeError:
                rec = {}
            out["record_present"] = True
            out["record_rcan_version"] = rec.get("rcan_version")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            out["record_present"] = False
        else:
            out["errors"].append(f"record_lookup: HTTP {e.code}")
        return out
    except Exception as e:
        out["errors"].append(f"record_lookup: {type(e).__name__}: {e}")
        return out

    # 3. Drift detection (only meaningful when both versions are known)
    if manifest_v and out["record_rcan_version"] and manifest_v != out["record_rcan_version"]:
        out["version_drift"] = True
    return out


def _check_submission_readiness(apikey_present: bool) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for kind in SUBMISSION_KINDS:
        if apikey_present:
            out[kind] = {"ready": True, "reason": ""}
        else:
            out[kind] = {
                "ready": False,
                "reason": (
                    f"apikey missing — run "
                    f"`robot-md request-apikey ROBOT.md -o request.json` "
                    f"and submit it to RRF support"
                ),
            }
    return out


def _aggregate_blockers(status: dict[str, Any]) -> list[str]:
    blockers: list[str] = []

    if not status["keystore"]["signing_keypair"]["present"]:
        blockers.append(
            "no signing keypair in keystore — register the manifest first "
            "with `robot-md register`"
        )
    if not status["keystore"]["apikey"]["present"]:
        blockers.append(
            "apikey missing — 5 submission paths blocked. "
            "Run `robot-md request-apikey ROBOT.md -o request.json` and "
            "hand the signed JSON to RRF support out-of-band"
        )

    audit = status["audit"]
    if not audit.get("valid", False):
        blockers.append(
            f"audit chain INVALID: {audit.get('error', 'unknown')}"
        )

    missing = status["artifacts"]["missing"]
    if missing:
        blockers.append(
            f"{len(missing)} expected artifact(s) missing from compliance dir: "
            f"{', '.join(missing)} — rerun ./scripts/demo-eu-ai-act.sh"
        )

    reg = status.get("registry") or {}
    if reg.get("version_drift"):
        blockers.append(
            f"rcan_version DRIFT: manifest declares "
            f"{reg.get('manifest_rcan_version')!r} but RRF record has "
            f"{reg.get('record_rcan_version')!r} — PATCH the record once "
            f"apikey is recovered"
        )

    return blockers


def gather_status(
    manifest_path: Path,
    *,
    artifacts_dir: Path | None = None,
    network_probe: bool = True,
    endpoint: str = DEFAULT_RRF_ENDPOINT,
) -> dict[str, Any]:
    """Assemble the full compliance status dict for `manifest_path`.

    `artifacts_dir` defaults to ``<manifest_dir>/compliance/`` if not
    supplied. `network_probe=False` skips RRF calls — useful in CI.
    """
    fm = _load_fm(manifest_path)
    rrn = ((fm.get("metadata") or {}).get("rrn") or "").strip()
    if artifacts_dir is None:
        artifacts_dir = manifest_path.parent / "compliance"

    status: dict[str, Any] = {
        "rrn": rrn,
        "manifest": {
            "path": str(manifest_path),
            "rcan_version": str(fm.get("rcan_version") or ""),
            "robot_name": (fm.get("metadata") or {}).get("robot_name") or "",
        },
        "keystore": _check_keystore(rrn) if rrn else {
            "signing_keypair": {"present": False, "path": None},
            "apikey": {"present": False, "path": None},
        },
        "audit": _check_audit(rrn) if rrn else {"valid": True, "entries": 0},
        "incidents": _check_incidents(rrn) if rrn else {"path": None, "total": 0, "by_severity": {}},
        "artifacts": _check_artifacts(artifacts_dir),
        "registry": (
            _check_registry(rrn, fm, endpoint=endpoint)
            if (network_probe and rrn)
            else {"reachable": None, "record_present": None, "skipped": True}
        ),
    }
    apikey_present = status["keystore"]["apikey"]["present"]
    status["submission_readiness"] = _check_submission_readiness(apikey_present)
    status["blockers"] = _aggregate_blockers(status)
    return status


# ---------------------------------------------------------------- formatting


def _icon(ok: bool, neutral: bool = False) -> str:
    if neutral:
        return "—"
    return "✓" if ok else "✗"


def format_status_text(status: dict[str, Any]) -> str:
    """Render gather_status() output as human-readable text."""
    lines: list[str] = []
    lines.append("")
    lines.append(
        f"=== Compliance status for {status['rrn'] or '(unregistered)'} "
        f"({status['manifest']['robot_name']}) ==="
    )
    lines.append("")

    # Local state
    lines.append("Local state")
    ks = status["keystore"]
    lines.append(
        f"  manifest:           {status['manifest']['path']} "
        f"(rcan_version {status['manifest']['rcan_version']})"
    )
    lines.append(
        f"  signing keypair:    {_icon(ks['signing_keypair']['present'])} "
        f"{ks['signing_keypair']['path']}"
    )
    lines.append(
        f"  apikey:             {_icon(ks['apikey']['present'])} "
        f"{ks['apikey']['path']}"
    )
    audit = status["audit"]
    if audit.get("valid"):
        lines.append(
            f"  audit chain:        ✓ {audit['entries']} entries (valid)"
        )
    else:
        lines.append(f"  audit chain:        ✗ INVALID — {audit.get('error', '?')}")
    inc = status["incidents"]
    if inc["total"] == 0:
        lines.append("  incidents log:      empty")
    else:
        sev_summary = ", ".join(f"{n} {s}" for s, n in sorted(inc["by_severity"].items()))
        lines.append(f"  incidents log:      {inc['total']} entries ({sev_summary})")
    lines.append("")

    # Artifacts
    lines.append(f"Compliance artifacts ({status['artifacts']['dir'] or '(no dir)'})")
    expected_set = set(EXPECTED_ARTIFACT_SCHEMAS)
    present_by_schema = {a["schema"]: a for a in status["artifacts"]["present"]}
    for schema in EXPECTED_ARTIFACT_SCHEMAS:
        if schema in present_by_schema:
            a = present_by_schema[schema]
            sig = "signed" if a["signed"] else "unsigned"
            lines.append(
                f"  ✓ {schema:<28}  {a['size_bytes']:>5} bytes  ({sig})"
            )
        else:
            lines.append(f"  ✗ {schema:<28}  missing")
    extras = [a for a in status["artifacts"]["present"] if a["schema"] not in expected_set]
    for a in extras:
        sig = "signed" if a["signed"] else "unsigned"
        lines.append(
            f"  • {a['schema']:<28}  {a['size_bytes']:>5} bytes  ({sig}) [extra]"
        )
    lines.append("")

    # Registry
    reg = status["registry"]
    lines.append("RRF registry")
    if reg.get("skipped"):
        lines.append("  (skipped — pass --probe to enable network checks)")
    else:
        lines.append(f"  endpoint reachable: {_icon(bool(reg['reachable']))} {reg['endpoint']}")
        if reg["reachable"]:
            lines.append(f"  RRN resolvable:     {_icon(bool(reg['record_present']))}")
            if reg["record_present"]:
                manifest_v = reg.get("manifest_rcan_version") or "?"
                record_v = reg.get("record_rcan_version") or "?"
                if reg.get("version_drift"):
                    lines.append(
                        f"  rcan_version:       ✗ DRIFT — manifest={manifest_v} "
                        f"record={record_v}"
                    )
                else:
                    lines.append(f"  rcan_version:       ✓ matches ({manifest_v})")
        if reg.get("errors"):
            for err in reg["errors"]:
                lines.append(f"  error: {err}")
    lines.append("")

    # Submission readiness
    lines.append("Submission readiness")
    for kind in SUBMISSION_KINDS:
        r = status["submission_readiness"][kind]
        if r["ready"]:
            lines.append(f"  ✓ emit-{kind:<18}  ready")
        else:
            lines.append(f"  ✗ emit-{kind:<18}  blocked — {r['reason']}")
    lines.append("")

    # Blockers summary
    if status["blockers"]:
        lines.append(f"Blockers ({len(status['blockers'])})")
        for b in status["blockers"]:
            lines.append(f"  - {b}")
    else:
        lines.append("✓ no blockers — ready for submission")
    lines.append("")

    return "\n".join(lines)

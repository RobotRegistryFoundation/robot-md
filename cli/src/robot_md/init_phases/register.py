"""Phase: mint an RRN for the manifest via cli_register."""

from __future__ import annotations

from pathlib import Path

from robot_md.init_phases import PhaseResult
from robot_md.parser import parse_file
from robot_md.register import cli_register


def phase_register(
    manifest_path: Path,
    *,
    contact_email: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    version: str | None = None,
    device_id: str | None = None,
) -> PhaseResult:
    """Mint an RRN for this manifest. Returns PhaseResult; never raises.

    After a successful mint, `cli_register` has written the RRN back into
    the manifest — we read it and include it in `detail`.
    """
    rc = cli_register(
        str(manifest_path),
        manufacturer=manufacturer,
        model=model,
        version=version,
        device_id=device_id,
        contact_email=contact_email,
    )
    if rc != 0:
        return PhaseResult(
            phase="register",
            status="failed",
            message=f"cli_register exit code {rc}",
            detail={"exit_code": rc},
        )

    rrn = ""
    try:
        parsed = parse_file(manifest_path)
        rrn = str((parsed.frontmatter.get("metadata") or {}).get("rrn") or "").strip()
    except Exception:
        pass

    return PhaseResult(
        phase="register",
        status="ok",
        message=f"minted {rrn}" if rrn else "registered (RRN not yet written)",
        detail={"rrn": rrn, "exit_code": 0},
    )

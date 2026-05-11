"""Phase: write ROBOT.md from preset + hardware scan."""

from __future__ import annotations

from pathlib import Path

from robot_md.init import (
    load_presets,
    merge_preset_into_draft,
    pick_best,
    render_draft,
)
from robot_md.init_phases import PhaseResult


def _carry_forward_registration_fields(out_path: Path) -> dict[str, str]:
    """Read an existing manifest's frontmatter and extract identity fields
    that the regenerator would otherwise drop.

    `merge_preset_into_draft` builds a fresh frontmatter from preset + scan;
    it has no knowledge of an RRN that the operator already minted against
    the Robot Registry Foundation. If `init --force` is being used to
    re-run hardware discovery (e.g., after fixing /dev/ttyACM permissions),
    we must carry forward:

      - metadata.rrn      — the assigned RRN; the keypair under
                            ~/.robot-md/keys/<rrn>.signing.json is keyed
                            to this and is orphaned the moment it drops.
      - metadata.record_url — the human-resolvable URL paired with the RRN.

    Returns the carry-forward dict (possibly empty). Silently returns
    empty on any parse failure — re-init with --force on a corrupted
    manifest still works, the operator just loses the RRN reference,
    same as before this fix.
    """
    if not out_path.exists():
        return {}
    try:
        from robot_md.parser import parse_file

        parsed = parse_file(out_path)
    except Exception:
        return {}
    md = parsed.frontmatter.get("metadata") or {}
    carry: dict[str, str] = {}
    rrn = md.get("rrn")
    if rrn:
        carry["rrn"] = rrn
    record_url = md.get("record_url")
    if record_url:
        carry["record_url"] = record_url
    return carry


def phase_write_manifest(
    *,
    out_path: Path,
    robot_name: str | None,
    preset_name: str | None,
    scan,
    force: bool = False,
) -> PhaseResult:
    """Write a validated ROBOT.md draft. Returns PhaseResult; never raises
    for recoverable errors. Fatal I/O errors (disk full) may still raise.

    When `force=True` and `out_path` exists, this preserves
    `metadata.rrn` + `metadata.record_url` from the existing manifest so
    that `init --force` does not orphan an already-minted RRN. A
    subsequent `robot-md register` run will overwrite these anyway; the
    preservation only kicks in when --register is not being re-run.
    """
    if out_path.exists() and not force:
        return PhaseResult(
            phase="write_manifest",
            status="failed",
            message=f"{out_path} already exists (pass --force to overwrite)",
            detail={"reason": "exists", "path": str(out_path)},
        )

    carry_forward = _carry_forward_registration_fields(out_path) if force else {}

    presets = load_presets()
    if not presets:
        return PhaseResult(
            phase="write_manifest",
            status="failed",
            message="no presets found in preset directory",
            detail={"reason": "no_presets"},
        )

    if preset_name:
        sel = next(
            (p for p in presets if p.name == preset_name or p.display_name == preset_name),
            None,
        )
        if sel is None:
            names = [p.display_name for p in presets]
            return PhaseResult(
                phase="write_manifest",
                status="failed",
                message=f"preset {preset_name!r} not found. Available: {names}",
                detail={"reason": "unknown_preset", "requested": preset_name},
            )
        from robot_md.init import MatchResult

        chosen = MatchResult(preset=sel, score=100, reasons=["explicit --preset"])
    else:
        chosen = pick_best(presets, scan)
        if chosen is None:
            return PhaseResult(
                phase="write_manifest",
                status="failed",
                message="preset list empty after pick_best",
                detail={"reason": "pick_best_empty"},
            )

    from robot_md.init import _default_robot_name

    name = robot_name or _default_robot_name()
    fm = merge_preset_into_draft(chosen.preset, name, scan)
    if carry_forward:
        fm.setdefault("metadata", {})
        for k, v in carry_forward.items():
            fm["metadata"][k] = v
    body_hints = chosen.preset.data.get("body_hints", {}) or {}
    text = render_draft(fm, body_hints)
    out_path.write_text(text)

    return PhaseResult(
        phase="write_manifest",
        status="ok",
        message=f"wrote {out_path.name} (preset {chosen.preset.display_name})",
        detail={
            "path": str(out_path),
            "preset": chosen.preset.display_name,
            "score": chosen.score,
            "reasons": chosen.reasons,
            "robot_name": name,
            "carried_forward": sorted(carry_forward.keys()),
        },
    )

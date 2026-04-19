"""Phase: mint an RRN for the manifest via cli_register."""

from __future__ import annotations

from pathlib import Path

from robot_md.init_phases import PhaseResult
from robot_md.parser import parse_file
from robot_md.register import cli_register
from robot_md.validate import VALID
from robot_md.validate import validate as validate_parsed


def _persist_metadata_overrides(
    manifest_path: Path,
    *,
    manufacturer: str | None,
    model: str | None,
    version: str | None,
    device_id: str | None,
) -> None:
    """Rewrite metadata.{manufacturer,model,version,device_id} before the mint.

    cli_register POSTs these overrides to rcan.dev but does not rewrite the
    manifest itself — so without this step the registry and the on-disk
    manifest drift. Preserves YAML comments via ruamel.yaml.
    """
    if all(v is None for v in (manufacturer, model, version, device_id)):
        return
    try:
        from ruamel.yaml import YAML
    except ImportError:
        return

    import io

    text = manifest_path.read_text()
    end = text.find("\n---", 3)
    if end < 0:
        return
    fm_text = text[3:end].lstrip("\n")
    body_text = text[end + 4 :]
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    data = y.load(fm_text)
    meta = data.setdefault("metadata", {})
    for k, v in (
        ("manufacturer", manufacturer),
        ("model", model),
        ("version", version),
        ("device_id", device_id),
    ):
        if v is not None:
            meta[k] = v
    buf = io.StringIO()
    y.dump(data, buf)
    manifest_path.write_text("---\n" + buf.getvalue().rstrip("\n") + "\n---" + body_text)


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

    Before the mint:
      1. Validate the manifest so invalid drafts don't reach rcan.dev.
      2. Persist `--manufacturer/--model/--version-/--device-id` overrides
         into the manifest so the registry and the file stay in sync.
    After a successful mint, `cli_register` has written the RRN back into
    the manifest — we read it and include it in `detail`.
    """
    try:
        parsed = parse_file(manifest_path)
    except Exception as e:
        return PhaseResult(
            phase="register",
            status="failed",
            message=f"could not parse manifest: {e}",
            detail={"reason": "parse_error", "error": str(e)},
        )

    vresult = validate_parsed(parsed)
    if vresult.code != VALID:
        return PhaseResult(
            phase="register",
            status="failed",
            message=f"manifest failed validation before register — {vresult.summary}",
            detail={"reason": "validation_failed", "errors": list(vresult.errors)},
        )

    try:
        _persist_metadata_overrides(
            manifest_path,
            manufacturer=manufacturer,
            model=model,
            version=version,
            device_id=device_id,
        )
    except Exception as e:
        return PhaseResult(
            phase="register",
            status="failed",
            message=f"could not persist metadata overrides: {e}",
            detail={"reason": "overrides_write_failed", "error": str(e)},
        )

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

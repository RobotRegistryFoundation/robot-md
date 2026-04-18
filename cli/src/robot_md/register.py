"""`robot-md register` — mint an RRN against the Robot Registry Foundation.

Talks to the live v0.1.x RRF mint endpoint at
``https://robotregistryfoundation.org/api/v1/robots``. On success, writes the
assigned RRN back into the manifest's ``metadata.rrn``, stores the issued
API key at ``~/.robot-md/keys/<rrn>.apikey`` (mode 600), and prints the
public resolver URL for the new record.

v0.2 will add signed registration with key-binding at mint time (see
``spec/v0.2-design.md`` §9.1). When that server-side endpoint lands, this
module will gain a ``--signed`` path that generates an Ed25519 keypair,
signs the manifest, and sends the key material as part of the request —
*without* changing the v0.1 code path, so existing operators keep working.

Usage via CLI:

    robot-md register ROBOT.md                                   # use manifest fields
    robot-md register ROBOT.md --contact-email me@example.com    # override/add
    robot-md register ROBOT.md --source opencastor-community     # set provenance
    robot-md register ROBOT.md --dry-run                         # print request, don't POST
    robot-md register ROBOT.md --endpoint https://staging.rrf... # point elsewhere

Exit codes: 0 success, 2 operator error, 3 network/server error.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from robot_md.parser import parse_file


DEFAULT_ENDPOINT = "https://robotregistryfoundation.org/api/v1/robots"
KEYSTORE_DIR = Path.home() / ".robot-md" / "keys"


# --------------------------------------------------------------- request shape

@dataclass
class MintRequest:
    """Fields POSTed to RRF. Matches the current v0.1.x live schema."""
    manufacturer: str
    model: str
    version: str
    device_id: str
    description: str = ""
    contact_email: str = ""
    source: str = "robot-md-cli"
    # Metadata attached to the manifest update on successful mint
    robot_name: str = ""

    def as_body(self) -> dict[str, Any]:
        # Strip empty optional fields so the server gets a clean payload
        body: dict[str, Any] = {
            "manufacturer": self.manufacturer,
            "model": self.model,
            "version": self.version,
            "device_id": self.device_id,
            "source": self.source,
        }
        if self.description:
            body["description"] = self.description
        if self.contact_email:
            body["contact_email"] = self.contact_email
        return body


@dataclass
class MintResult:
    rrn: str
    rcan_uri: str
    api_key: str | None
    already_existed: bool
    raw: dict[str, Any]


# --------------------------------------------------------- manifest extraction

def _extract_mint_fields(
    manifest_path: Path,
    *,
    manufacturer: str | None,
    model: str | None,
    version: str | None,
    device_id: str | None,
    description: str | None,
    contact_email: str | None,
    source: str | None,
) -> MintRequest:
    """Build a MintRequest from a parsed ROBOT.md + optional CLI overrides.

    Resolution order (first non-empty wins):
      1. CLI flag
      2. manifest.metadata.<field>
      3. sensible default (e.g. device_id defaults to robot_name)
      4. raise if still empty

    RRF slugifies incoming identifiers — we don't need to pre-slugify, but we
    do need non-empty values.
    """
    parsed = parse_file(manifest_path)
    meta = parsed.frontmatter.get("metadata") or {}

    def pick(flag: str | None, key: str, default: str = "") -> str:
        v = flag or meta.get(key) or default
        return str(v).strip() if v else ""

    robot_name = pick(None, "robot_name")
    if not robot_name:
        raise ValueError("manifest has no metadata.robot_name; add one before registering")

    req = MintRequest(
        manufacturer=pick(manufacturer, "manufacturer"),
        model=pick(model, "model"),
        version=pick(version, "version", default="1.0"),
        device_id=pick(device_id, "device_id", default=robot_name),
        description=pick(description, "description"),
        contact_email=pick(contact_email, "contact_email") or pick(None, "author"),
        source=pick(source, "source", default="robot-md-cli"),
        robot_name=robot_name,
    )

    missing: list[str] = []
    for fld in ("manufacturer", "model", "version", "device_id"):
        if not getattr(req, fld):
            missing.append(fld)
    if missing:
        raise ValueError(
            f"manifest missing required mint fields: {missing}. "
            "Add them to metadata: or pass --"
            + ", --".join(m.replace("_", "-") for m in missing)
        )
    return req


# -------------------------------------------------------------- network + side

def post_to_rrf(endpoint: str, body: dict[str, Any], *, timeout: float = 15.0) -> MintResult:
    """POST the mint body. Raises :class:`RuntimeError` on network or 5xx
    failures; returns :class:`MintResult` on both first-time (201) and
    already-registered (200) responses.
    """
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "robot-md-cli/0.1 (+https://robotmd.dev)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_text = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        raise RuntimeError(
            f"RRF returned {e.code}: {err_text.strip()[:500]}"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not reach {endpoint}: {e.reason}") from e

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"RRF returned non-JSON: {text[:200]}") from e

    rrn = obj.get("rrn")
    if not rrn:
        raise RuntimeError(f"RRF response missing 'rrn': {text[:200]}")

    return MintResult(
        rrn=rrn,
        rcan_uri=obj.get("rcan_uri", ""),
        api_key=obj.get("api_key"),
        already_existed=bool(obj.get("already_existed")),
        raw=obj,
    )


def write_apikey(rrn: str, api_key: str) -> Path:
    """Store the issued API key at ~/.robot-md/keys/<rrn>.apikey, mode 600.

    The RRF returns the raw key exactly once — we don't want to print it to
    stdout where it might leak into scrollback or CI logs. Saving to a
    per-RRN file with restrictive permissions is the safe default. Operator
    can always ``cat`` it when they need it.
    """
    KEYSTORE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(KEYSTORE_DIR, 0o700)
    path = KEYSTORE_DIR / f"{rrn}.apikey"
    # Write with restrictive perms before content to avoid a race window
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(api_key + "\n")
    return path


def write_rrn_to_manifest(manifest_path: Path, rrn: str, rcan_uri: str) -> None:
    """Rewrite metadata.rrn and metadata.rcan_uri in the manifest.

    Preserves comments + formatting via ruamel.yaml.
    """
    try:
        from ruamel.yaml import YAML  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "robot-md register needs ruamel.yaml for comment-preserving rewrites. "
            "Install with: pip install ruamel.yaml"
        ) from e

    text = manifest_path.read_text()
    if not text.startswith("---"):
        raise RuntimeError(f"{manifest_path}: missing leading '---' frontmatter marker")
    end = text.find("\n---", 3)
    if end < 0:
        raise RuntimeError(f"{manifest_path}: missing closing '---' frontmatter marker")
    fm_text = text[3:end].lstrip("\n")
    body_text = text[end + 4:]

    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    data = y.load(fm_text)

    meta = data.setdefault("metadata", {})
    meta["rrn"] = rrn
    if rcan_uri:
        meta["rcan_uri"] = rcan_uri

    import io
    buf = io.StringIO()
    y.dump(data, buf)
    manifest_path.write_text("---\n" + buf.getvalue().rstrip("\n") + "\n---" + body_text)


# ------------------------------------------------------------------ cli entry

def cli_register(
    manifest_path: str,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    manufacturer: str | None = None,
    model: str | None = None,
    version: str | None = None,
    device_id: str | None = None,
    description: str | None = None,
    contact_email: str | None = None,
    source: str | None = None,
    dry_run: bool = False,
) -> int:
    path = Path(manifest_path)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2

    parsed = parse_file(path)
    existing_rrn = str((parsed.frontmatter.get("metadata") or {}).get("rrn") or "").strip()
    if existing_rrn and existing_rrn != "":
        print(
            f"note: manifest already has metadata.rrn = {existing_rrn!r}.\n"
            f"      This registration will look up (not replace) that RRN.\n",
            file=sys.stderr,
        )

    try:
        req = _extract_mint_fields(
            path,
            manufacturer=manufacturer, model=model, version=version, device_id=device_id,
            description=description, contact_email=contact_email, source=source,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    body = req.as_body()
    print("--- mint request ---", file=sys.stderr)
    print(json.dumps(body, indent=2), file=sys.stderr)
    print(f"--- endpoint: {endpoint} ---", file=sys.stderr)

    if dry_run:
        print("\n--dry-run: not POSTed to RRF.", file=sys.stderr)
        return 0

    try:
        result = post_to_rrf(endpoint, body)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    if result.already_existed:
        print(
            f"\n(already registered)\n"
            f"  RRN: {result.rrn}\n"
            f"  RCAN URI: {result.rcan_uri or '—'}",
            file=sys.stderr,
        )
    else:
        print(
            f"\n✓ registered on RRF\n"
            f"  RRN: {result.rrn}\n"
            f"  RCAN URI: {result.rcan_uri or '—'}",
            file=sys.stderr,
        )

    # Persist API key (only issued on first mint)
    if result.api_key:
        key_path = write_apikey(result.rrn, result.api_key)
        print(
            f"  API key saved to {key_path} (mode 600). Show it with: cat {key_path}",
            file=sys.stderr,
        )

    # Update manifest
    try:
        write_rrn_to_manifest(path, result.rrn, result.rcan_uri)
        print(f"  manifest {path} updated with metadata.rrn", file=sys.stderr)
    except RuntimeError as e:
        print(f"  warning: could not update manifest: {e}", file=sys.stderr)

    public_url = f"https://robotregistryfoundation.org/r/{result.rrn}"
    print(f"\nPublic resolver: {public_url}", file=sys.stderr)
    return 0

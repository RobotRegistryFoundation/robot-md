"""`robot-md register` — mint an RRN against the Robot Registry Foundation.

Talks to the live RRF mint endpoint at ``https://rcan.dev/api/v1/robots``
(the foundation's governance site is at `robotregistryfoundation.org`, but
the registry service itself is served from `rcan.dev`). On success, writes the
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

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from robot_md.parser import parse_file
from robot_md.ruri import construct_ruri
from robot_md.signing import generate_keypair, save_keypair, sign_body

DEFAULT_ENDPOINT = "https://rcan.dev/api/v2/robots/register"


def _keystore_dir() -> Path:
    return Path.home() / ".robot-md" / "keys"


def load_apikey(rrn: str) -> str | None:
    """Return the stored API key for `rrn`, or None if no keystore file."""
    p = _keystore_dir() / f"{rrn}.apikey"
    if not p.exists():
        return None
    return p.read_text().strip() or None


def delete_from_rrf(endpoint: str, rrn: str, api_key: str, *, timeout: float = 15.0) -> None:
    """DELETE `endpoint/rrn` with `Authorization: Bearer <api_key>`.

    Raises :class:`RuntimeError` with a human-readable message on any non-2xx.
    """
    url = f"{endpoint.rstrip('/')}/{rrn}"
    req = urllib.request.Request(
        url,
        method="DELETE",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "robot-md-cli/0.2 (+https://robotmd.dev)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_text = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        raise RuntimeError(f"RRF returned {e.code}: {err_text.strip()[:500]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not reach {url}: {e.reason}") from e
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Accept empty-body 204s
        return
    if "error" in obj:
        raise RuntimeError(f"RRF refused delete: {obj['error']}")


def cli_unregister(
    rrn: str, *, endpoint: str = DEFAULT_ENDPOINT, api_key: str | None = None
) -> int:
    """Operator-facing: `robot-md unregister <RRN>`.

    Reads the API key from `~/.robot-md/keys/<rrn>.apikey` unless `--api-key`
    is supplied. DELETEs the RRF entry. Does NOT touch local ROBOT.md files.
    """
    key = api_key or load_apikey(rrn)
    if not key:
        print(
            f"error: no API key for {rrn}. "
            f"Pass --api-key (or ensure ~/.robot-md/keys/{rrn}.apikey exists).",
            file=sys.stderr,
        )
        return 2
    try:
        delete_from_rrf(endpoint, rrn, key)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    # Clean up local key file (no longer valid)
    key_path = _keystore_dir() / f"{rrn}.apikey"
    if key_path.exists() and api_key is None:
        # Only delete the file if we used the stored one
        key_path.unlink()
        print(f"  removed local key {key_path}", file=sys.stderr)
    print(f"✓ deleted {rrn} from RRF ({endpoint})", file=sys.stderr)
    return 0


# --------------------------------------------------------------- request shape


@dataclass
class MintRequest:
    """Fields POSTed to RRF. Matches the current v2 live schema."""

    name: str
    manufacturer: str
    model: str
    firmware_version: str
    rcan_version: str
    pq_signing_pub: str = ""
    pq_kid: str = ""
    ruri: str = ""
    owner_uid: str = ""

    def as_body(self) -> dict[str, Any]:
        # Strip empty optional fields so the server gets a clean payload
        body: dict[str, Any] = {
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "rcan_version": self.rcan_version,
        }
        if self.pq_signing_pub:
            body["pq_signing_pub"] = self.pq_signing_pub
        if self.pq_kid:
            body["pq_kid"] = self.pq_kid
        if self.ruri:
            body["ruri"] = self.ruri
        if self.owner_uid:
            body["owner_uid"] = self.owner_uid
        return body


@dataclass
class MintResult:
    rrn: str
    registered_at: str
    record_url: str
    raw: dict[str, Any]


# --------------------------------------------------------- manifest extraction


def _extract_mint_fields(
    manifest_path: Path,
    *,
    name: str | None,
    manufacturer: str | None,
    model: str | None,
    firmware_version: str | None,
    rcan_version: str | None,
    pq_signing_pub: str | None,
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

    robot_name = pick(name, "robot_name")
    if not robot_name:
        raise ValueError("manifest has no metadata.robot_name; add one before registering")

    req = MintRequest(
        name=robot_name,
        manufacturer=pick(manufacturer, "manufacturer"),
        model=pick(model, "model"),
        firmware_version=pick(firmware_version, "firmware_version", default="1.0"),
        rcan_version=pick(rcan_version, "rcan_version", default="3.0"),
        pq_signing_pub=pick(pq_signing_pub, "pq_signing_pub"),
    )

    missing: list[str] = []
    for fld in ("name", "manufacturer", "model", "firmware_version", "rcan_version"):
        if not getattr(req, fld):
            missing.append(fld)
    if missing:
        raise ValueError(
            f"manifest missing required mint fields: {missing}. "
            "Add them to metadata: or pass --" + ", --".join(m.replace("_", "-") for m in missing)
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
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_text = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        raise RuntimeError(f"RRF returned {e.code}: {err_text.strip()[:500]}") from e
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
        registered_at=obj.get("registered_at", ""),
        record_url=obj.get("record_url", ""),
        raw=obj,
    )


def write_rrn_to_manifest(manifest_path: Path, rrn: str, record_url: str) -> None:
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
    body_text = text[end + 4 :]

    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    data = y.load(fm_text)

    meta = data.setdefault("metadata", {})
    meta["rrn"] = rrn
    if record_url:
        meta["record_url"] = record_url

    import io

    buf = io.StringIO()
    y.dump(data, buf)
    manifest_path.write_text("---\n" + buf.getvalue().rstrip("\n") + "\n---" + body_text)


# ------------------------------------------------------------------ cli entry


def _write_apikey(rrn: str, api_key: str) -> Path:
    """Persist RRF-issued API key at ~/.robot-md/keys/<rrn>.apikey (mode 600).

    Atomic via tmp-then-rename + mode-set-before-rename: a SIGTERM mid-write
    leaves either no file or a fully-mode-600 file, never a world-readable
    half-written one.
    """
    keystore = _keystore_dir()
    keystore.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        os.chmod(keystore, 0o700)
    path = keystore / f"{rrn}.apikey"
    tmp = path.with_suffix(".apikey.tmp")
    tmp.write_text(api_key)
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path


def cli_register(
    manifest_path: Path | str,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    name: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    firmware_version: str | None = None,
    rcan_version: str | None = None,
    dry_run: bool = False,
) -> int:
    """Register a ROBOT.md with RRF, signing the POST body (v0.9.1)."""
    path = Path(manifest_path)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2

    parsed = parse_file(path)
    meta = parsed.frontmatter.get("metadata") or {}
    existing_rrn = str(meta.get("rrn") or "").strip()
    if existing_rrn:
        print(
            f"error: manifest already registered as {existing_rrn}. "
            f"Key rotation is not supported in v0.9.1.",
            file=sys.stderr,
        )
        return 2

    # 1. Build MintRequest (validates required fields).
    try:
        kp = generate_keypair()
        req = _extract_mint_fields(
            path,
            name=name, manufacturer=manufacturer, model=model,
            firmware_version=firmware_version, rcan_version=rcan_version,
            pq_signing_pub=base64.b64encode(kp.ml_dsa.public_key_bytes).decode(),
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    req.pq_kid = kp.pq_kid
    req.ruri = construct_ruri(parsed.frontmatter)

    # 2. Sign canonical body.
    body = req.as_body()
    signed = sign_body(kp, body)

    if dry_run:
        print("--- signed mint request ---", file=sys.stderr)
        print(json.dumps(signed, indent=2), file=sys.stderr)
        print(f"--- endpoint: {endpoint} ---", file=sys.stderr)
        print("\n--dry-run: not POSTed to RRF.", file=sys.stderr)
        return 0

    # 3. POST.
    try:
        result = post_to_rrf(endpoint, signed)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    # 4. Persist keypair + apikey.
    save_keypair(result.rrn, kp)
    api_key = result.raw.get("api_key")
    if api_key:
        _write_apikey(result.rrn, api_key)

    # 5. Write RRN back into manifest.
    try:
        write_rrn_to_manifest(path, result.rrn, result.record_url)
    except RuntimeError as e:
        print(f"  warning: could not update manifest: {e}", file=sys.stderr)

    # 6. Friendly output.
    print(
        f"\n✓ registered on RRF\n  RRN: {result.rrn}\n  Record URL: {result.record_url or '—'}",
        file=sys.stderr,
    )
    public_url = f"https://rcan.dev/r/{result.rrn}"
    print(f"Public resolver: {public_url}", file=sys.stderr)
    return 0

"""`robot-md register` — mint an RRN against the Robot Registry Foundation.

Talks to the live RRF mint endpoint at
``https://robotregistryfoundation.org/v2/robots/register`` (see
``DEFAULT_ENDPOINT`` below). On success, writes the assigned RRN back into
the manifest's ``metadata.rrn``, stores the issued API key at
``~/.robot-md/keys/<rrn>.apikey`` (mode 600), and prints the public resolver
URL for the new record.

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

DEFAULT_ENDPOINT = "https://robotregistryfoundation.org/v2/robots/register"
DEFAULT_AUTHORITIES_ENDPOINT = "https://robotregistryfoundation.org/v2/authorities/register"


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


def patch_rrf(
    url: str,
    body: dict[str, Any],
    api_key: str,
    *,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """PATCH `url` with `body` (JSON). Bearer-authed via api_key.

    Returns the parsed JSON response. Raises urllib.error.HTTPError on 4xx/5xx.
    """
    req = urllib.request.Request(
        url,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "robot-md-cli/0.9 (+https://robotmd.dev)",
        },
        data=json.dumps(body).encode("utf-8"),
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def auto_mint_if_needed(rrn: str, *, endpoint: str = DEFAULT_ENDPOINT) -> None:
    """If the keystore has an apikey for this RRN but no signing keypair,
    generate one and PATCH it onto the RRF record. Idempotent no-op when
    either (a) a signing keypair already exists, or (b) no apikey exists.

    Used by RRF-touching commands (cli_unregister so far) to transparently
    upgrade pre-v0.9.1 records to RCAN 3.0 signed shape on first contact.
    """
    from rcan.crypto import sign_hybrid

    from robot_md.signing import (
        canonical_json,
        generate_keypair,
        load_keypair,
        save_keypair,
    )

    if load_keypair(rrn) is not None:
        return
    api_key = load_apikey(rrn)
    if not api_key:
        return

    kp = generate_keypair()
    ml_pub_b64 = base64.b64encode(kp.ml_dsa.public_key_bytes).decode()

    # RRF PATCH /v2/robots/<rrn> verifies over canonical {rrn, pq_signing_pub, pq_kid}.
    signed_payload = {"rrn": rrn, "pq_signing_pub": ml_pub_b64, "pq_kid": kp.pq_kid}
    message = canonical_json(signed_payload)
    hs = sign_hybrid(kp.ml_dsa, kp.ed25519_sec, message)

    patch_body = {
        "pq_signing_pub": ml_pub_b64,
        "pq_kid": kp.pq_kid,
        "sig": {
            "ml_dsa": base64.b64encode(hs.ml_dsa_sig).decode(),
            "ed25519": base64.b64encode(hs.ed25519_sig).decode(),
            "ed25519_pub": base64.b64encode(kp.ed25519_pub).decode(),
        },
    }

    # DEFAULT_ENDPOINT is .../v2/robots/register; PATCH endpoint is .../v2/robots/<rrn>.
    patch_url = endpoint.replace("/register", f"/{rrn}")
    try:
        patch_rrf(patch_url, patch_body, api_key)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"auto-mint PATCH failed for {rrn}: {e.code} {body_text.strip()[:300]}"
        ) from e

    save_keypair(rrn, kp)


def cli_unregister(
    rrn: str, *, endpoint: str = DEFAULT_ENDPOINT, api_key: str | None = None
) -> int:
    """Operator-facing: `robot-md unregister <RRN>`.

    v0.9.1: Transparently upgrades unsigned RRF records (legacy) before any
    RRF call by minting a hybrid keypair and PATCHing it on. If the upgrade
    fails the unregister attempt continues — the user clearly wants the
    record gone, not a half-signed record.

    Reads the API key from `~/.robot-md/keys/<rrn>.apikey` unless `--api-key`
    is supplied. DELETEs the RRF entry. Does NOT touch local ROBOT.md files.
    """
    try:
        auto_mint_if_needed(rrn, endpoint=endpoint)
    except RuntimeError as e:
        print(f"warning: {e}", file=sys.stderr)

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
    # v0.9.7 — operator-declared §21 sibling registry IDs. RRF 1.10.0+ stores
    # them on the RobotRecord when present; pre-1.10.0 RRFs ignore them. All
    # optional; empty values strip from the POST body.
    rcn_ids: tuple[str, ...] = ()
    rmn: str = ""
    rhn_ids: tuple[str, ...] = ()

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
        if self.rcn_ids:
            body["rcn_ids"] = list(self.rcn_ids)
        if self.rmn:
            body["rmn"] = self.rmn
        if self.rhn_ids:
            body["rhn_ids"] = list(self.rhn_ids)
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

    # v0.9.7 — pull sibling §21 IDs from manifest metadata if set.
    rcn_ids = tuple(str(x).strip() for x in (meta.get("rcn_ids") or ()) if str(x).strip())
    rhn_ids = tuple(str(x).strip() for x in (meta.get("rhn_ids") or ()) if str(x).strip())

    req = MintRequest(
        name=robot_name,
        manufacturer=pick(manufacturer, "manufacturer"),
        model=pick(model, "model"),
        firmware_version=pick(firmware_version, "firmware_version", default="1.0"),
        rcan_version=pick(rcan_version, "rcan_version", default="3.0"),
        pq_signing_pub=pick(pq_signing_pub, "pq_signing_pub"),
        rcn_ids=rcn_ids,
        rmn=pick(None, "rmn"),
        rhn_ids=rhn_ids,
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


def peek_next_rrn(endpoint: str, *, timeout: float = 5.0) -> dict[str, Any] | None:
    """GET <endpoint-base>/_next to preview the RRN the next mint will allocate.

    `endpoint` is the mint endpoint (`.../v2/robots/register`); the peek lives
    at `.../v2/robots/_next` (added 2026-05-11 — see RRF PR #101).

    Returns the parsed JSON body on success or None on any failure (404 from
    older RRF deployments, network error, malformed JSON). Preflight is
    best-effort UX, never a mint gate — the caller must continue regardless.
    """
    if not endpoint.endswith("/register"):
        return None
    peek_url = endpoint.rsplit("/", 1)[0] + "/_next"
    req = urllib.request.Request(
        peek_url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "robot-md-cli/0.1 (+https://robotmd.dev)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
    except Exception:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or "next_rrn" not in obj:
        return None
    return obj


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


def post_envelope_authority(
    endpoint: str, body: dict[str, Any], *, timeout: float = 15.0
) -> dict[str, Any]:
    """POST a signed authority body to /v2/authorities/register and return the
    parsed response. Raises :class:`RuntimeError` on network or non-2xx.
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
        raise RuntimeError(
            f"authorities/register returned {e.code}: {err_text.strip()[:500]}"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not reach {endpoint}: {e.reason}") from e
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"authorities/register returned non-JSON: {text[:200]}") from e


def _register_envelope_authority(
    rrn: str,
    kp: Any,
    meta: dict[str, Any],
    *,
    authorities_endpoint: str = DEFAULT_AUTHORITIES_ENDPOINT,
) -> dict[str, Any]:
    """Bind the robot's pq_kid to an ``operator-envelope`` authority so the
    gateway's ``/v2/keys/{pq_kid}`` resolver can find an Ed25519 PEM for it.

    Without this step ``robot-md-gateway`` returns 403 on every
    envelope-signed invoke after a fresh mint (closes #84). Mirrors the
    manual ``scripts/register-operator-kid.ts`` flow, but signed by the
    robot's own keypair via the public ``POST /v2/authorities/register``
    endpoint — no admin auth or bulk-put needed.
    """
    ed_pub_b64 = base64.b64encode(kp.ed25519_pub).decode()
    base_body: dict[str, Any] = {
        "organization": str(meta.get("manufacturer") or meta.get("robot_name") or rrn),
        "display_name": f"{meta.get('robot_name') or rrn} — envelope signer",
        "purpose": "operator-envelope",
        "signing_pub": ed_pub_b64,
        "signing_alg": ["Ed25519", "ML-DSA-65"],
    }
    signed = sign_body(kp, base_body)
    return post_envelope_authority(authorities_endpoint, signed)


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
            name=name,
            manufacturer=manufacturer,
            model=model,
            firmware_version=firmware_version,
            rcan_version=rcan_version,
            pq_signing_pub=base64.b64encode(kp.ml_dsa.public_key_bytes).decode(),
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    req.pq_kid = kp.pq_kid
    req.ruri = construct_ruri(parsed.frontmatter)

    # 1.5. Preflight: surface the RRN the next mint will allocate so the
    # operator can see it before signing. Best-effort — older RRF deployments
    # without /_next return None and we proceed silently.
    preview = peek_next_rrn(endpoint)
    if preview is not None:
        next_rrn = preview.get("next_rrn", "?")
        reserved = preview.get("reserved_floor")
        msg = f"  Next RRN: {next_rrn}"
        if reserved:
            msg += f" (RRNs below {reserved:012d} reserved for canonical robots)"
        print(msg, file=sys.stderr)

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

    # 4.5. Bind pq_kid → operator-envelope authority so the gateway's
    # /v2/keys/<pq_kid> resolver can verify envelope signatures from this
    # robot. Non-fatal: if the authorities POST fails, the manifest is
    # still valid and the operator can re-publish later (closes #84).
    authorities_endpoint = endpoint.replace("/robots/register", "/authorities/register")
    org = str(meta.get("manufacturer") or meta.get("robot_name") or result.rrn)
    display_name = f"{meta.get('robot_name') or result.rrn} — envelope signer"
    try:
        post_envelope_authority(
            authorities_endpoint, sign_body(kp, {
                "organization": org,
                "display_name": display_name,
                "purpose": "operator-envelope",
                "signing_pub": base64.b64encode(kp.ed25519_pub).decode(),
                "signing_alg": ["Ed25519", "ML-DSA-65"],
            }),
        )
    except RuntimeError as e:
        print(
            f"  warning: could not register envelope-authority kid for {result.rrn}: {e}\n"
            f"  gateway envelope verification will 404 until this is retried "
            f"(re-run `robot-md register` won't help — manifest already has an RRN).",
            file=sys.stderr,
        )

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

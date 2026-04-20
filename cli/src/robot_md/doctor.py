"""robot-md doctor — diagnose the local environment + manifest.

Designed to be the first thing an operator runs when something is broken. No
side-effects: doctor never writes files, never modifies servo state, never
hits the registry's mutating endpoints.

Checks fall into five buckets:

  1. Install     — CLI installed, Python version, required deps importable.
  2. Manifest    — ROBOT.md in cwd (or --path) parses + validates against schema.
  3. Network     — registry (rcan.dev) reachable; if --path has `rrn`, entry exists.
  4. Drivers     — each declared driver probed (serial port readable, host reachable).
  5. Keystore    — ~/.robot-md/keys/ permissions + counts.

Output: a rich Table. Exit code 0 if all checks pass or only warn, 1 on any fail
(unless --strict, which also exits 1 on warn).
"""

from __future__ import annotations

import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import request
from urllib.error import URLError

from robot_md import __version__

# ---------------------------------------------------------------------- types


@dataclass
class CheckResult:
    name: str
    bucket: str
    status: str  # "pass" | "warn" | "fail" | "skip"
    detail: str


def _pass(name: str, bucket: str, detail: str) -> CheckResult:
    return CheckResult(name, bucket, "pass", detail)


def _warn(name: str, bucket: str, detail: str) -> CheckResult:
    return CheckResult(name, bucket, "warn", detail)


def _fail(name: str, bucket: str, detail: str) -> CheckResult:
    return CheckResult(name, bucket, "fail", detail)


def _skip(name: str, bucket: str, detail: str) -> CheckResult:
    return CheckResult(name, bucket, "skip", detail)


def _info(name: str, bucket: str, detail: str) -> CheckResult:
    return CheckResult(name, bucket, "info", detail)


# ----------------------------------------------------------------- 1. install


def check_install() -> list[CheckResult]:
    out: list[CheckResult] = []
    out.append(_pass("robot-md CLI", "install", f"v{__version__}"))

    py = sys.version_info
    py_str = f"{py.major}.{py.minor}.{py.micro}"
    if py >= (3, 10):
        out.append(_pass("python", "install", py_str))
    else:
        out.append(_fail("python", "install", f"{py_str} — requires >=3.10"))

    for mod_name, hint in (
        ("yaml", "pyyaml"),
        ("jsonschema", "jsonschema"),
        ("frontmatter", "python-frontmatter"),
        ("ruamel.yaml", "ruamel.yaml"),
        ("rich", "rich"),
        ("typer", "typer"),
    ):
        try:
            __import__(mod_name)
            out.append(_pass(f"dep: {hint}", "install", "importable"))
        except ImportError as e:
            out.append(_fail(f"dep: {hint}", "install", f"import failed — {e}"))

    # Optional: claude CLI
    claude_path = _which("claude")
    if claude_path:
        out.append(_pass("claude CLI", "install", claude_path))
    else:
        out.append(_skip("claude CLI", "install", "not on PATH (optional)"))

    # Optional: npx (for robot-md-mcp)
    npx_path = _which("npx")
    if npx_path:
        out.append(_pass("npx (for MCP)", "install", npx_path))
    else:
        out.append(_warn("npx (for MCP)", "install", "not on PATH — `claude mcp add` will fail"))

    return out


def _which(cmd: str) -> str | None:
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = Path(d) / cmd
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


# ---------------------------------------------------------------- 2. manifest


def check_manifest(path: Path | None) -> tuple[list[CheckResult], dict[str, Any] | None]:
    """Return (results, parsed_frontmatter_or_None)."""
    out: list[CheckResult] = []

    if path is None:
        candidate = Path.cwd() / "ROBOT.md"
        if candidate.exists():
            path = candidate
        else:
            out.append(
                _skip("manifest", "manifest", "no ROBOT.md in cwd (pass --path to target one)")
            )
            return out, None

    if not path.exists():
        out.append(_fail("manifest", "manifest", f"{path} does not exist"))
        return out, None

    try:
        from robot_md.parser import parse_file
    except ImportError as e:
        out.append(_fail("manifest parse", "manifest", f"parser import failed: {e}"))
        return out, None

    try:
        parsed = parse_file(path)
    except Exception as e:
        out.append(_fail("manifest parse", "manifest", f"{type(e).__name__}: {e}"))
        return out, None

    fm = parsed.frontmatter
    out.append(_pass("manifest parse", "manifest", f"{path.name} — YAML + prose loaded"))

    try:
        from robot_md.validate import VALID
        from robot_md.validate import validate as validate_parsed

        result = validate_parsed(parsed)
        if result.code == VALID:
            out.append(_pass("manifest schema", "manifest", result.summary or "valid against v1.1"))
        else:
            err_head = result.errors[0] if result.errors else f"code={result.code}"
            out.append(_fail("manifest schema", "manifest", str(err_head)))
    except Exception as e:
        out.append(_warn("manifest schema", "manifest", f"could not run: {e}"))

    name = (fm.get("metadata") or {}).get("robot_name", "?")
    dof = (fm.get("physics") or {}).get("dof", "?")
    rrn = (fm.get("metadata") or {}).get("rrn")
    out.append(
        _pass(
            "manifest summary",
            "manifest",
            f"robot_name={name} dof={dof} rrn={rrn or '(unregistered)'}",
        )
    )

    return out, fm


# ----------------------------------------------------------------- 3. network


def check_network(fm: dict[str, Any] | None) -> list[CheckResult]:
    out: list[CheckResult] = []

    endpoint = "https://rcan.dev/api/v1/robots"
    if fm:
        configured = (fm.get("network") or {}).get("rrf_endpoint")
        if configured:
            endpoint = str(configured).rstrip("/")
            if not endpoint.endswith("/api/v1/robots"):
                endpoint = endpoint + "/api/v1/robots"

    # HEAD-style GET with a small timeout; any HTTP response proves reachability.
    req = request.Request(endpoint, method="GET", headers={"User-Agent": f"robot-md/{__version__}"})
    try:
        with request.urlopen(req, timeout=5) as resp:
            out.append(_pass("registry reachable", "network", f"{endpoint} → HTTP {resp.status}"))
    except URLError as e:
        out.append(_fail("registry reachable", "network", f"{endpoint} — {e.reason}"))
        return out
    except Exception as e:
        out.append(_fail("registry reachable", "network", f"{endpoint} — {type(e).__name__}: {e}"))
        return out

    if fm:
        rrn = (fm.get("metadata") or {}).get("rrn")
        if rrn:
            lookup = f"{endpoint}/{rrn}"
            try:
                with request.urlopen(lookup, timeout=5) as resp:
                    if resp.status == 200:
                        out.append(
                            _pass("RRN lookup", "network", f"{rrn} resolvable at {endpoint}/{rrn}")
                        )
                    else:
                        out.append(_warn("RRN lookup", "network", f"{rrn} → HTTP {resp.status}"))
            except Exception as e:
                out.append(_warn("RRN lookup", "network", f"{rrn} — {type(e).__name__}: {e}"))
        else:
            out.append(
                _skip("RRN lookup", "network", "manifest has no RRN yet (run `robot-md register`)")
            )

    return out


# ----------------------------------------------------------------- 4. drivers


def check_drivers(fm: dict[str, Any] | None) -> list[CheckResult]:
    out: list[CheckResult] = []
    if not fm:
        return out
    drivers = fm.get("drivers") or []
    if not drivers:
        out.append(_skip("drivers", "drivers", "no drivers declared"))
        return out

    for drv in drivers:
        drv_id = drv.get("id", "?")
        proto = drv.get("protocol", "?")
        port = drv.get("port")
        host = drv.get("host")
        label = f"{drv_id} ({proto})"

        if port and isinstance(port, str) and port.startswith("/dev/"):
            p = Path(port)
            if not p.exists():
                out.append(_fail(label, "drivers", f"{port} — does not exist (unplugged?)"))
            elif not os.access(p, os.R_OK | os.W_OK):
                out.append(_warn(label, "drivers", f"{port} — exists but not RW (dialout group?)"))
            else:
                out.append(_pass(label, "drivers", f"{port} — RW"))
        elif host:
            probe_port = 80
            if isinstance(port, str) and port.isdigit():
                probe_port = int(port)
            elif proto == "urscript":
                probe_port = 30002
            elif proto == "franka-fci":
                probe_port = 1337
            elif proto == "unitree-sdk2":
                probe_port = 8080
            try:
                with socket.create_connection((host, probe_port), timeout=2):
                    out.append(_pass(label, "drivers", f"{host}:{probe_port} — TCP open"))
            except Exception as e:
                out.append(
                    _fail(label, "drivers", f"{host}:{probe_port} — {type(e).__name__}: {e}")
                )
        else:
            # Non-network, non-serial drivers (e.g. local compute, depthai-over-USB):
            # we can't cheaply probe them here. Flag as skip.
            out.append(_skip(label, "drivers", "no probeable port/host (protocol-specific check)"))

    return out


# ------------------------------------------------------------- 5. calibration


def check_calibration(fm: dict | None) -> list[CheckResult]:
    """§ 6: Calibration provenance — warn on preset-default extrinsics."""
    out: list[CheckResult] = []
    if fm is None:
        return out
    cams = ((fm.get("physics") or {}).get("solver") or {}).get("cameras") or []
    if not cams:
        return out  # silent — camera-free robots skip this bucket
    offenders = [i for i, c in enumerate(cams) if c.get("extrinsic_source") == "preset_default"]
    if offenders:
        out.append(_warn(
            "extrinsic source",
            "calibration",
            "preset default — run `robot-md calibrate --hand-eye ROBOT.md` for precision",
        ))
    else:
        out.append(_pass("extrinsic source", "calibration", "calibrated or user-declared"))

    # Surface extrinsic_residual_mm from the first camera entry when present.
    cam0 = cams[0] if cams else {}
    residual = cam0.get("extrinsic_residual_mm")
    if residual is not None:
        out.append(_info(
            "extrinsic residual",
            "calibration",
            f"{residual} mm",
        ))

    return out


# ----------------------------------------------------------------- 6. keystore


def check_keystore() -> list[CheckResult]:
    out: list[CheckResult] = []
    keys_dir = Path.home() / ".robot-md" / "keys"
    if not keys_dir.exists():
        out.append(_skip("keystore", "keystore", f"{keys_dir} — absent (no robots registered yet)"))
        return out

    try:
        mode = keys_dir.stat().st_mode & 0o777
    except OSError as e:
        out.append(_fail("keystore dir", "keystore", f"{keys_dir} — stat failed: {e}"))
        return out

    if mode & 0o077:
        out.append(
            _warn(
                "keystore dir", "keystore", f"{keys_dir} — mode {oct(mode)} (group/world readable)"
            )
        )
    else:
        out.append(_pass("keystore dir", "keystore", f"{keys_dir} — mode {oct(mode)}"))

    key_files = sorted(keys_dir.glob("*.apikey"))
    if not key_files:
        out.append(_skip("keystore keys", "keystore", "no .apikey files present"))
        return out

    leaky = []
    for kf in key_files:
        kmode = kf.stat().st_mode & 0o777
        if kmode & 0o077:
            leaky.append(f"{kf.name}(mode={oct(kmode)})")
    if leaky:
        out.append(
            _warn("keystore keys", "keystore", f"{len(key_files)} keys — leaky: {', '.join(leaky)}")
        )
    else:
        out.append(_pass("keystore keys", "keystore", f"{len(key_files)} keys, all mode 0600"))

    return out


# ---------------------------------------------------------------------- runner


def run_all(path: Path | None = None) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.extend(check_install())
    m_results, fm = check_manifest(path)
    results.extend(m_results)
    results.extend(check_network(fm))
    results.extend(check_drivers(fm))
    results.extend(check_calibration(fm))
    results.extend(check_keystore())
    return results


def counts(results: list[CheckResult]) -> dict[str, int]:
    c = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for r in results:
        c[r.status] = c.get(r.status, 0) + 1
    return c


def exit_code(results: list[CheckResult], strict: bool) -> int:
    c = counts(results)
    if c["fail"] > 0:
        return 1
    if strict and c["warn"] > 0:
        return 1
    return 0

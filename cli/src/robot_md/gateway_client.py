"""Client for robot-md-gateway, the bounded layer the MCP motion tools go through.

robot-md's MCP server does not write to the servo bus. ``execute_capability``,
``execute_task``, ``estop`` and ``estop_clear`` are clients of
robot-md-gateway: each sends an RCAN INVOKE envelope to the gateway's
``POST /v1/invoke`` and reports what the gateway decided. The gateway checks
the bearer's tier, the tool allowlist, the envelope's scope, the manifest and
its own safety state; the actuator behind it bounds and paces the motion; the
gateway records each decision in its audit trail.

When no gateway is configured, or the configured one does not answer, the
motion tools refuse. Nothing in this module, or in the MCP server, falls back
to opening the serial port.

Configuration is the one ``robot-md install-gateway`` writes, plus the
environment variables ``robot-md trial`` already reads. For each value the
first source that is set wins:

    gateway URL  $ROBOT_MD_GATEWAY_URL, else http://127.0.0.1:8080 (the
                 address install-gateway's systemd unit binds)
    bearer       $ROBOT_MD_GATEWAY_BEARER, else the first ``actuate``-tier
                 entry of the bearers file. The bearers file is
                 $ROBOT_MD_BEARERS_FILE, else the ROBOT_MD_BEARERS_FILE line of
                 /etc/robot-md-gateway/gateway.env, else
                 /etc/robot-md-gateway/bearers.yaml. A ``commission`` entry is
                 never picked from the file: clearing a stop needs that tier,
                 and it belongs to the person at the machine.
    manifest     $ROBOT_MD_MANIFEST_PATH, else the ROBOT_MD_PATH line of
                 gateway.env when it is an absolute path (the manifest the
                 gateway pins), else the served ROBOT.md
    ruri         $ROBOT_MD_RURI, else ``metadata.ruri`` in the served ROBOT.md
    actuator     $ROBOT_MD_GATEWAY_ACTUATOR, optional; unset lets the gateway
                 route by tool name
    stop tools   $ROBOT_MD_GATEWAY_STOP_TOOL (default ``arm.estop``) and
                 $ROBOT_MD_GATEWAY_STOP_CLEAR_TOOL (default
                 ``arm.estop.clear``), the names so-arm101-actuator declares

The bearer never appears in a tool result: results say where it came from,
not what it is. Requests ignore any HTTP proxy in the environment, so the
bearer only ever goes to the configured gateway address.
"""

from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_GATEWAY_URL = "http://127.0.0.1:8080"
INSTALL_GATEWAY_ENV_FILE = Path("/etc/robot-md-gateway/gateway.env")
INSTALL_GATEWAY_BEARERS_FILE = Path("/etc/robot-md-gateway/bearers.yaml")

#: The tier read from a bearers file. The same tier `robot-md invoke
#: --bearer-from-bearers` reads. Never `commission`.
BEARER_TIER = "actuate"

#: Seconds to wait for the gateway's answer. A paced move can take several
#: seconds, and the gateway answers after the actuator returns.
DEFAULT_TIMEOUT_S = 30.0

#: Envelope scopes. The gateway refuses a motion tool under a scope that is not
#: an actuation scope (`tool_scope`), so a wrong label here cannot move
#: anything; it can only be refused.
MOTION_SCOPE = "ACTUATE"
OBSERVE_SCOPE = "OBSERVE"
#: The scope the gateway itself uses when it sends a stop.
STOP_SCOPE = "SAFETY"
#: Clearing a stop makes the robot movable again. COMMISSION makes the gateway
#: require the `commission` tier for it (check_tier), on top of the actuator's
#: own tier table.
CLEAR_SCOPE = "COMMISSION"

DEFAULT_STOP_TOOL = "arm.estop"
DEFAULT_STOP_CLEAR_TOOL = "arm.estop.clear"

ENV_URL = "ROBOT_MD_GATEWAY_URL"
ENV_BEARER = "ROBOT_MD_GATEWAY_BEARER"
ENV_BEARERS_FILE = "ROBOT_MD_BEARERS_FILE"
ENV_MANIFEST_PATH = "ROBOT_MD_MANIFEST_PATH"
ENV_RURI = "ROBOT_MD_RURI"
ENV_ACTUATOR = "ROBOT_MD_GATEWAY_ACTUATOR"
ENV_STOP_TOOL = "ROBOT_MD_GATEWAY_STOP_TOOL"
ENV_STOP_CLEAR_TOOL = "ROBOT_MD_GATEWAY_STOP_CLEAR_TOOL"
ENV_TIMEOUT = "ROBOT_MD_GATEWAY_TIMEOUT_S"

#: Every environment variable this module reads. Tests clear these.
ENV_VARS = (
    ENV_URL,
    ENV_BEARER,
    ENV_BEARERS_FILE,
    ENV_MANIFEST_PATH,
    ENV_RURI,
    ENV_ACTUATOR,
    ENV_STOP_TOOL,
    ENV_STOP_CLEAR_TOOL,
    ENV_TIMEOUT,
)


@dataclass(frozen=True)
class GatewayConfig:
    """Where the gateway is and how to talk to it.

    `problems` lists what is missing. A config with problems is not used for
    motion: the motion tools refuse. A stop is still attempted with whatever
    is there, because a stop that might land is better than one never sent.
    """

    url: str
    bearer: str | None = field(repr=False)
    bearer_source: str
    manifest_path: str
    manifest_source: str
    ruri: str | None
    rrn: str | None
    actuator_name: str | None
    stop_tool: str
    stop_clear_tool: str
    timeout_s: float
    problems: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.problems

    def describe(self) -> dict[str, Any]:
        """What a tool result may say about this config. Never the bearer."""
        return {
            "url": self.url,
            "bearer_source": self.bearer_source,
            "manifest_path": self.manifest_path,
            "manifest_source": self.manifest_source,
            "ruri": self.ruri,
            "actuator_name": self.actuator_name,
            "problems": list(self.problems),
        }


def _read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines of a systemd EnvironmentFile. Unreadable → {}."""
    try:
        text = path.read_text()
    except OSError:
        return {}
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key] = value
    return out


def _bearer_from_file(path: Path) -> tuple[str | None, str | None]:
    """(bearer, problem). Reads the first `actuate` entry, nothing else.

    A parse error is reported by exception type only: a YAML error message
    can quote the offending line, and that line can hold a token.
    """
    from robot_md.invoke import load_bearer_for_tier

    try:
        return load_bearer_for_tier(path, BEARER_TIER), None
    except FileNotFoundError:
        return None, f"no bearers file at {path}"
    except LookupError:
        return None, f"{path} has no {BEARER_TIER!r}-tier entry"
    except PermissionError:
        return None, f"{path} is not readable by this user"
    except Exception as e:
        # Type only, never str(e): see the docstring.
        return None, f"could not read a bearer from {path} ({type(e).__name__})"


def _timeout_from(environ: Mapping[str, str]) -> float:
    raw = (environ.get(ENV_TIMEOUT) or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_S
    return value if value > 0 else DEFAULT_TIMEOUT_S


def resolve_config(
    *,
    served_manifest_path: Path | str,
    frontmatter: Mapping[str, Any] | None,
    environ: Mapping[str, str] | None = None,
    env_file: Path | None = None,
    default_bearers_file: Path | None = None,
) -> GatewayConfig:
    """Resolve the gateway configuration. Never raises; see `problems`."""
    env = os.environ if environ is None else environ
    gw_env = _read_env_file(env_file if env_file is not None else INSTALL_GATEWAY_ENV_FILE)
    fm = dict(frontmatter or {})
    metadata = fm.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    problems: list[str] = []

    url = (env.get(ENV_URL) or "").strip() or DEFAULT_GATEWAY_URL

    bearer = (env.get(ENV_BEARER) or "").strip() or None
    if bearer is not None:
        bearer_source = f"${ENV_BEARER}"
    else:
        if (env.get(ENV_BEARERS_FILE) or "").strip():
            path = Path(env[ENV_BEARERS_FILE].strip())
        elif gw_env.get("ROBOT_MD_BEARERS_FILE"):
            path = Path(gw_env["ROBOT_MD_BEARERS_FILE"])
        else:
            path = (
                default_bearers_file
                if default_bearers_file is not None
                else INSTALL_GATEWAY_BEARERS_FILE
            )
        bearer, problem = _bearer_from_file(path)
        if bearer is not None:
            bearer_source = f"{path} ({BEARER_TIER} tier)"
        else:
            bearer_source = "none"
            problems.append(
                f"no gateway bearer: ${ENV_BEARER} is not set and {problem}. "
                "Run `robot-md install-gateway` on the robot, or set "
                f"${ENV_BEARER} in the MCP server's environment."
            )

    env_manifest = (env.get(ENV_MANIFEST_PATH) or "").strip()
    gw_manifest = (gw_env.get("ROBOT_MD_PATH") or "").strip()
    if env_manifest:
        manifest_path, manifest_source = env_manifest, f"${ENV_MANIFEST_PATH}"
    elif gw_manifest and os.path.isabs(gw_manifest):
        manifest_path, manifest_source = gw_manifest, "ROBOT_MD_PATH in gateway.env"
    else:
        manifest_path = str(Path(served_manifest_path).resolve())
        manifest_source = "served ROBOT.md"

    ruri = (env.get(ENV_RURI) or "").strip() or None
    if ruri is None:
        candidate = metadata.get("ruri")
        ruri = candidate.strip() if isinstance(candidate, str) and candidate.strip() else None
    if ruri is None:
        problems.append(
            f"no robot URI: ${ENV_RURI} is not set and ROBOT.md has no metadata.ruri "
            "(run `robot-md register`)."
        )

    rrn = metadata.get("rrn") if isinstance(metadata.get("rrn"), str) else None

    return GatewayConfig(
        url=url,
        bearer=bearer,
        bearer_source=bearer_source,
        manifest_path=manifest_path,
        manifest_source=manifest_source,
        ruri=ruri,
        rrn=rrn or None,
        actuator_name=(env.get(ENV_ACTUATOR) or "").strip() or None,
        stop_tool=(env.get(ENV_STOP_TOOL) or "").strip() or DEFAULT_STOP_TOOL,
        stop_clear_tool=(env.get(ENV_STOP_CLEAR_TOOL) or "").strip() or DEFAULT_STOP_CLEAR_TOOL,
        timeout_s=_timeout_from(env),
        problems=tuple(problems),
    )


def config_for_context(ctx: Any) -> GatewayConfig:
    """`resolve_config` for an MCP server context."""
    parsed = getattr(ctx, "parsed", None)
    fm = getattr(parsed, "frontmatter", None)
    if not isinstance(fm, Mapping):
        fm = parsed if isinstance(parsed, Mapping) else {}
    return resolve_config(served_manifest_path=ctx.manifest_path, frontmatter=fm)


def prepare_envelope(
    config: GatewayConfig,
    *,
    tool_name: str,
    tool_args: Mapping[str, Any],
    scope: str,
    sign: bool = True,
) -> tuple[dict[str, Any], str]:
    """Build the envelope (and sign it when a keypair exists). Returns
    (envelope, signing note).

    The envelope carries what `robot-md invoke` sends and nothing that claims
    a human decision: no `delegation_chain`, no `human_subject`, no
    `inference_confidence`, no confirmation token. The gateway's HiTL gate
    reads `delegation_chain`, and one written in the model's process would be
    the model approving itself.
    """
    from robot_md.invoke import build_envelope, sign_envelope

    envelope = build_envelope(
        ruri=config.ruri or "",
        tool_name=tool_name,
        tool_args=dict(tool_args),
        manifest_path=config.manifest_path,
        scope=scope,
    )
    if config.actuator_name:
        # Before signing, so the signature covers the routing choice.
        envelope["actuator_name"] = config.actuator_name
    if not sign:
        return envelope, "unsigned (not sent)"
    if not config.rrn:
        return envelope, "unsigned: ROBOT.md has no metadata.rrn"
    try:
        from robot_md.signing import load_keypair

        keypair = load_keypair(config.rrn)
    except Exception as e:
        # Type only: a message from a broken keyfile could carry key bytes.
        return envelope, f"unsigned: could not load the signing keypair ({type(e).__name__})"
    if keypair is None:
        return envelope, f"unsigned: no signing keypair for {config.rrn}"
    signed = sign_envelope(envelope, keypair, kid=keypair.pq_kid)
    return signed, f"signed (kid {keypair.pq_kid})"


class _Unreachable(Exception):
    """The request could not be delivered (connect or send failed)."""


class _NoAnswer(Exception):
    """The request was sent and no complete answer came back."""


def _post(url: str, body: dict, bearer: str | None, timeout: float) -> tuple[int, Any]:
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(url, data=data, method="POST", headers=headers)
    # No proxies: the bearer goes to the configured address and nowhere else.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as resp:
            return resp.status, _parse(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, _parse(e.read())
    except urllib.error.URLError as e:
        # urllib wraps failures while connecting or sending in URLError.
        raise _Unreachable(f"{type(e.reason).__name__}: {e.reason}") from e
    except (TimeoutError, OSError, http.client.HTTPException) as e:
        # Raised after the request went out: the gateway may have acted on it.
        raise _NoAnswer(f"{type(e).__name__}: {e}") from e


def _parse(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return {"raw": text[:2000]}


def _summary(envelope: dict, note: str) -> dict[str, Any]:
    return {
        "msg_id": envelope.get("msg_id"),
        "tool_name": envelope.get("tool_name"),
        "scope": envelope.get("scope"),
        "actuator_name": envelope.get("actuator_name"),
        "manifest_path": envelope.get("manifest_path"),
        "signing": note,
    }


def interpret(status_code: int, body: Any) -> dict[str, Any]:
    """Map a /v1/invoke answer to {status, error, gateway}.

    The gateway answers 200 (allowed and executed), 403 (denied, by a gate or
    by the actuator's own policy) or 500 (the actuator raised); 401, 404 and
    422 are request problems.
    """
    detail = body.get("detail") if isinstance(body, dict) else None
    if status_code == 200 and isinstance(body, dict) and body.get("ok") is True:
        return {"status": "ok", "error": None, "gateway": body}
    if status_code == 403:
        if isinstance(detail, dict):
            error: dict[str, Any] = {
                "reason": "gateway_denied",
                "deny": detail.get("deny"),
                "message": detail.get("reason"),
            }
            if detail.get("telemetry"):
                error["telemetry"] = detail["telemetry"]
            return {"status": "denied", "error": error, "gateway": detail}
        return {
            "status": "denied",
            "error": {"reason": "gateway_denied", "message": str(detail or body)},
            "gateway": body if isinstance(body, dict) else None,
        }
    if status_code == 401:
        return {
            "status": "error",
            "error": {
                "reason": "gateway_auth",
                "message": f"the gateway did not accept this server's bearer: {detail}",
            },
            "gateway": body if isinstance(body, dict) else None,
        }
    if status_code == 500 and isinstance(detail, dict) and "actuator_error" in detail:
        return {
            "status": "error",
            "error": {
                "reason": "actuator_error",
                "message": detail.get("actuator_error"),
                "kind": detail.get("actuator_error_kind"),
            },
            "gateway": detail,
        }
    return {
        "status": "error",
        "error": {
            "reason": "gateway_rejected",
            "http_status": status_code,
            "message": detail if detail is not None else body,
        },
        "gateway": body if isinstance(body, dict) else None,
    }


def invoke(
    config: GatewayConfig,
    *,
    tool_name: str,
    tool_args: Mapping[str, Any],
    scope: str,
    withhold: Callable[[], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Send one envelope to the gateway and report its decision.

    Returns {status, error, gateway, envelope}. `status` is "ok" (the gateway
    ran it), "denied" (the gateway or the actuator refused it), "blocked"
    (`withhold` stopped it here) or "error". Never raises and never retries: a
    request the gateway may already have acted on is not sent twice.

    `withhold`, when given, is called after the envelope is built and signed,
    immediately before it is sent. If it returns an error dict, nothing is
    sent. The motion tools use it to re-check the stop latch, which a stop in
    another thread may have set while this envelope was being prepared.
    """
    envelope, note = prepare_envelope(config, tool_name=tool_name, tool_args=tool_args, scope=scope)
    summary = _summary(envelope, note)
    if withhold is not None:
        withheld = withhold()
        if withheld is not None:
            return {"status": "blocked", "error": withheld, "gateway": None, "envelope": summary}
    url = config.url.rstrip("/") + "/v1/invoke"
    try:
        status_code, body = _post(url, envelope, config.bearer, config.timeout_s)
    except _Unreachable as e:
        return {
            "status": "error",
            "error": {
                "reason": "gateway_unreachable",
                "message": (
                    f"could not deliver the request to the gateway at {config.url} ({e}). "
                    "Nothing in this MCP server can reach the actuators any other way."
                ),
            },
            "gateway": None,
            "envelope": summary,
        }
    except _NoAnswer as e:
        return {
            "status": "error",
            "error": {
                "reason": "gateway_no_answer",
                "message": (
                    f"sent {tool_name} to the gateway at {config.url} and got no complete "
                    f"answer ({e}). It may have run, or may still be running. Check the "
                    "gateway's audit record (GET /v1/audit/last) before anything else, "
                    "and do not resend it."
                ),
            },
            "gateway": None,
            "envelope": summary,
        }
    out = interpret(status_code, body)
    out["envelope"] = summary
    return out


def envelope_preview(config: GatewayConfig, envelope: dict) -> dict[str, Any]:
    """A dry run's answer: what would be sent, to where. Sends nothing."""
    return {
        "sent": False,
        "gateway_url": config.url.rstrip("/") + "/v1/invoke",
        "bearer_source": config.bearer_source,
        "envelope": envelope,
    }


__all__ = [
    "BEARER_TIER",
    "CLEAR_SCOPE",
    "DEFAULT_GATEWAY_URL",
    "DEFAULT_STOP_CLEAR_TOOL",
    "DEFAULT_STOP_TOOL",
    "ENV_VARS",
    "INSTALL_GATEWAY_BEARERS_FILE",
    "INSTALL_GATEWAY_ENV_FILE",
    "MOTION_SCOPE",
    "OBSERVE_SCOPE",
    "STOP_SCOPE",
    "GatewayConfig",
    "config_for_context",
    "envelope_preview",
    "interpret",
    "invoke",
    "prepare_envelope",
    "resolve_config",
]

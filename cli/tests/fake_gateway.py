"""A stand-in for robot-md-gateway's HTTP API, for tests.

It listens on 127.0.0.1 (the suite refuses any other host), records every
request it receives, and answers from a queue of scripted responses. With an
empty queue it answers the way a gateway that allowed and ran the call does:
200 with `ok: true`. It never touches hardware; there is nothing behind it.

It can also misbehave the way a real gateway or network can: answer only
after a delay (`hang`), or send a status line and headers and then stall
before the body (`stall_after_headers`).

GET /openapi.json lists `routes`, the way FastAPI does: by default the routes
of a gateway with robot-md-gateway#35 (the safety routes included). Set
`routes` to OLD_GATEWAY_ROUTES for one that predates it.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

#: What robot-md-gateway 0.5.0a9 serves.
OLD_GATEWAY_ROUTES = ("/v1/invoke", "/v1/audit/last")
#: What a gateway with robot-md-gateway#35 serves.
PR35_GATEWAY_ROUTES = (*OLD_GATEWAY_ROUTES, "/v1/safety/heartbeat", "/v1/safety/clear")


class FakeGateway:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.get_requests: list[dict[str, Any]] = []
        self.routes: tuple[str, ...] = PR35_GATEWAY_ROUTES
        # (status, body, delay before answering, stall after the headers,
        # extra headers)
        self._queue: list[tuple[int, dict, float, float, dict[str, str]]] = []
        self._release = threading.Event()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ scripting

    def respond(self, status: int, body: dict, headers: dict[str, str] | None = None) -> None:
        """Queue one answer. Answers are used in order, one per request."""
        self._queue.append((status, body, 0.0, 0.0, dict(headers or {})))

    def redirect(self, location: str, status: int = 302) -> None:
        """Queue a redirect to `location`, as a proxy or a wrong address might
        send one. robot-md-gateway itself never redirects /v1/invoke."""
        self.respond(status, {"detail": "moved"}, headers={"Location": location})

    def hang(self, seconds: float, status: int = 200, body: dict | None = None) -> None:
        """Queue an answer sent only after `seconds` (released early by stop())."""
        self._queue.append((status, body if body is not None else {}, seconds, 0.0, {}))

    def stall_after_headers(self, status: int, seconds: float) -> None:
        """Queue an answer whose status line and headers are sent, and whose body
        is not, for `seconds`."""
        self._queue.append((status, {"detail": "stalled"}, 0.0, seconds, {}))

    def deny(self, deny: str, reason: str, **extra: Any) -> None:
        """Queue a signed-deny shaped 403, as the gateway sends one."""
        self.respond(403, {"detail": {"deny": deny, "reason": reason, **extra}})

    @staticmethod
    def allowed(body: dict) -> dict:
        return {
            "ok": True,
            "manifest_kid": "test-manifest-kid",
            "scope": body.get("scope"),
            "tool_name": body.get("tool_name"),
            "actuator_name": body.get("actuator_name") or "so-arm101",
            "outcome_kind": "executed",
            "telemetry": {"fake": True},
            "attestation": "unattested",
            "envelope_signature": None,
        }

    # ------------------------------------------------------------ lifecycle

    @property
    def url(self) -> str:
        assert self._server is not None, "FakeGateway not started"
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> None:
        gateway = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw)
                except ValueError:
                    body = {"_unparseable": raw.decode("utf-8", "replace")}
                gateway.requests.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": body,
                    }
                )
                delay = stall = 0.0
                extra: dict[str, str] = {}
                if gateway._queue:
                    status, answer, delay, stall, extra = gateway._queue.pop(0)
                    if status == 200 and not answer:
                        answer = gateway.allowed(body if isinstance(body, dict) else {})
                else:
                    status, answer = 200, gateway.allowed(body if isinstance(body, dict) else {})
                if delay:
                    gateway._release.wait(delay)
                data = json.dumps(answer).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data) + (64 if stall else 0)))
                for name, value in extra.items():
                    self.send_header(name, value)
                self.end_headers()
                if stall:
                    self.wfile.flush()
                    gateway._release.wait(stall)
                    return
                self.wfile.write(data)

            def do_GET(self) -> None:
                gateway.get_requests.append(
                    {
                        "method": "GET",
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                    }
                )
                if self.path == "/openapi.json":
                    status = 200
                    answer: Any = {
                        "openapi": "3.1.0",
                        "info": {"title": "robot-md-gateway", "version": "0.4.0a1"},
                        "paths": {route: {} for route in gateway.routes},
                    }
                else:
                    status, answer = 404, {"detail": "Not Found"}
                data = json.dumps(answer).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._release.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    # -------------------------------------------------------------- reading

    @property
    def bodies(self) -> list[dict]:
        return [r["body"] for r in self.requests]

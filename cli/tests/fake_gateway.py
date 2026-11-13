"""A stand-in for robot-md-gateway's HTTP API, for tests.

It listens on 127.0.0.1 (the suite refuses any other host), records every
request it receives, and answers from a queue of scripted responses. With an
empty queue it answers the way a gateway that allowed and ran the call does:
200 with `ok: true`. It never touches hardware; there is nothing behind it.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeGateway:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._queue: list[tuple[int, dict]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ scripting

    def respond(self, status: int, body: dict) -> None:
        """Queue one answer. Answers are used in order, one per request."""
        self._queue.append((status, body))

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
                if gateway._queue:
                    status, answer = gateway._queue.pop(0)
                else:
                    status, answer = 200, gateway.allowed(body if isinstance(body, dict) else {})
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

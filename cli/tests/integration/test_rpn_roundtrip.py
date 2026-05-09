"""End-to-end: scaffold an actuator → publish (first time) → publish (version
update) → verify cache state. Mocks RRF as an in-process HTTP server.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import threading
from contextlib import contextmanager
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from robot_md.__main__ import app

runner = CliRunner()


class _MockRRF(http.server.BaseHTTPRequestHandler):
    seq: ClassVar[int] = 0
    records: ClassVar[dict] = {}

    def do_POST(self):
        ln = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(ln) or b"{}")
        if self.path == "/v2/packages/register":
            self.__class__.seq += 1
            rpn = f"RPN-{self.__class__.seq:012d}"
            self.__class__.records[rpn] = {
                **body,
                "rpn": rpn,
                "versions": [{"version": body["version"]}],
            }
            self._json(201, {"rpn": rpn, "registered_at": "x", "record_url": f"http://x/{rpn}"})
            return
        if self.path.startswith("/v2/packages/") and self.path.endswith("/versions"):
            rpn = self.path.split("/")[3]
            rec = self.__class__.records.get(rpn)
            if not rec:
                self._json(404, {"error": "not found"})
                return
            rec["versions"].append({"version": body["version"]})
            self._json(200, rec)
            return
        self._json(404, {"error": "no route"})

    def log_message(self, *a, **kw):
        pass

    def _json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@contextmanager
def _running_mock():
    _MockRRF.seq = 0
    _MockRRF.records = {}
    with socketserver.TCPServer(("127.0.0.1", 0), _MockRRF) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            httpd.shutdown()


@pytest.mark.slow
def test_rpn_roundtrip_first_publish_then_update(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    with _running_mock() as base:
        monkeypatch.setattr("robot_md.rrf_packages.RRF_PACKAGES_BASE", f"{base}/v2/packages")

        # 1. Scaffold an actuator.
        scaffold = runner.invoke(
            app,
            [
                "actuator",
                "init",
                "smoke-act",
                "--parent",
                str(tmp_path),
                "--author",
                "smoke@local",
                "--description",
                "smoke",
            ],
            env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
        )
        assert scaffold.exit_code == 0, scaffold.output
        pkg = tmp_path / "smoke-act"
        assert (pkg / "pyproject.toml").is_file()

        # 2. First publish.
        first = runner.invoke(
            app,
            ["actuator", "publish", "--package-dir", str(pkg), "--github-user", "alice"],
            env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
        )
        assert first.exit_code == 0, first.output
        assert "RPN-000000000001" in first.stdout

        # 3. Bump version in pyproject and publish again.
        py = pkg / "pyproject.toml"
        py.write_text(py.read_text().replace('version = "0.1.0"', 'version = "0.2.0"'))
        second = runner.invoke(
            app,
            ["actuator", "publish", "--package-dir", str(pkg), "--github-user", "alice"],
            env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
        )
        assert second.exit_code == 0, second.output
        assert "RPN-000000000001" in second.stdout
        assert "0.2.0" in second.stdout

        # 4. Check the mock saw both versions.
        rec = _MockRRF.records["RPN-000000000001"]
        versions = [v["version"] for v in rec["versions"]]
        assert versions == ["0.1.0", "0.2.0"]

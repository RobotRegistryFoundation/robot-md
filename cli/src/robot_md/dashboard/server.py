"""Dev dashboard FastAPI app. Reads ~/.robot-md/events.jsonl + writes commands.jsonl."""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


def _events_dir() -> Path:
    return Path(os.environ.get("HOME", Path.home())) / ".robot-md"


def _write_command(cmd: str) -> None:
    d = _events_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "commands.jsonl"
    with path.open("a") as f:
        f.write(json.dumps({"cmd": cmd, "ts": time.time(), "from": "dashboard"}) + "\n")


def build_app(*, manifest: Path | None = None) -> FastAPI:
    app = FastAPI(title="robot-md dev dashboard")
    pkg_dir = Path(__file__).parent
    templates = Jinja2Templates(directory=str(pkg_dir / "templates"))
    app.mount("/static", StaticFiles(directory=str(pkg_dir / "static")), name="static")

    warnings: list[str] = []
    robot_name = "robot-md"
    if manifest is not None:
        try:
            from robot_md.parser import parse_file
            from robot_md.validate import validate as _validate
            parsed = parse_file(manifest)
            result = _validate(parsed)
            warnings = list(result.warnings)
            robot_name = parsed.frontmatter.get("metadata", {}).get("robot_name", "robot-md")
        except Exception as e:
            warnings = [f"manifest parse error: {e}"]

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        from robot_md.dashboard.events import EventLog
        log = EventLog(jsonl_path=_events_dir() / "events.jsonl", ws_url=None)
        snap = await log.snapshot(n=50)
        last_hb = next((e for e in reversed(snap) if e.kind == "heartbeat"), None)
        joints = (last_hb.data.get("joints") if last_hb else {}) or {}
        estop_set = bool(last_hb.data.get("estop")) if last_hb else False
        tool_calls = [e for e in snap if e.kind in ("tool.call", "tool.result")][-20:]
        return templates.TemplateResponse(request, "index.html", {
            "robot_name": robot_name,
            "warnings": warnings,
            "joints": joints,
            "estop_set": estop_set,
            "tool_calls": tool_calls,
        })

    @app.post("/api/estop")
    async def api_estop():
        _write_command("estop.set")
        return {"ok": True}

    @app.post("/api/estop/clear")
    async def api_estop_clear():
        _write_command("estop.clear")
        return {"ok": True}

    @app.post("/api/snapshot")
    async def api_snapshot():
        _write_command("snapshot")
        return {"ok": True}

    @app.get("/api/frame/latest.png")
    async def api_frame():
        from robot_md.dashboard.events import EventLog
        log = EventLog(jsonl_path=_events_dir() / "events.jsonl", ws_url=None)
        snap = await log.snapshot(n=500)
        frame = next((e for e in reversed(snap) if e.kind == "frame"), None)
        if frame is None or not frame.data.get("png_b64"):
            return Response(status_code=404)
        png = base64.b64decode(frame.data["png_b64"])
        return Response(content=png, media_type="image/png")

    @app.get("/api/tunnel")
    async def api_tunnel():
        tf = _events_dir() / "tunnel.json"
        if tf.exists():
            try:
                return json.loads(tf.read_text())
            except Exception:
                return {}
        return {}

    return app


def main() -> int:
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(prog="robot-md dashboard serve")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()

    app = build_app(manifest=args.manifest)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

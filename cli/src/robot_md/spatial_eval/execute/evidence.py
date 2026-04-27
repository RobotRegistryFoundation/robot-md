from __future__ import annotations

import hashlib
import json
from pathlib import Path

from robot_md.spatial_eval.score import ScoreJSON


def write_evidence_packet(
    *,
    run_dir: Path,
    trials: list[dict],
    score: ScoreJSON,
    videos: dict[str, bytes],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps({"trials": trials}, sort_keys=True, indent=2))
    (run_dir / "Score.json").write_text(score.to_json())
    vdir = run_dir / "videos"
    vdir.mkdir(exist_ok=True)
    for trial_id, blob in videos.items():
        (vdir / f"{trial_id}.mp4").write_bytes(blob)


def packet_root_sha256(run_dir: Path) -> str:
    """Deterministic hash over (relative path, file bytes) for all files in run_dir."""
    h = hashlib.sha256()
    files = sorted(run_dir.rglob("*"))
    for f in files:
        if not f.is_file():
            continue
        rel = f.relative_to(run_dir).as_posix().encode("utf-8")
        h.update(len(rel).to_bytes(4, "big"))
        h.update(rel)
        b = f.read_bytes()
        h.update(len(b).to_bytes(8, "big"))
        h.update(b)
    return h.hexdigest()


def sign_packet(run_dir: Path, *, signer) -> str:
    """Compute root hash + sign with the supplied apikey signer.

    `signer` is an injected callable `(bytes) -> str` (base64 signature). The MCP
    tool layer wires the production signer; tests pass a fake.
    """
    root = packet_root_sha256(run_dir)
    return signer(root.encode("utf-8"))

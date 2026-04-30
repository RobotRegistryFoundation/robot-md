"""Typer subcommands for spatial-eval CLI surface.

Registered as `robot-md spatial-eval ...`. Phase 1.5 ships
`submit-to-rrf`; future Phase work will add `verify`, `dry-run`, etc.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(help="Spatial intelligence eval (SP6) commands")


@app.command("submit-to-rrf")
def submit_to_rrf(
    score_path: Path = typer.Argument(
        ...,
        help="Path to a self-attested Score.json produced by spatial-eval-run-*.",
        exists=True,
        readable=True,
    ),
    endpoint: str | None = typer.Option(
        None,
        "--endpoint",
        help="RRF base URL. Defaults to https://robotregistryfoundation.org.",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="Override apikey from ~/.robot-md/keys/<rrn>.apikey.",
    ),
) -> None:
    """Submit a self-attested Score JSON to RRF §27 for counter-signature.

    Score must already be signed (rcan_signature populated). On success,
    prints the submission_id (async path) or the counter-signed score
    (sync path) to stdout. Audit-records every attempt under the
    submitting robot's RRN.
    """
    from robot_md.spatial_eval.rrf import (
        DEFAULT_RRF_ENDPOINT,
        RrfSubmitError,
        submit_score,
    )
    from robot_md.spatial_eval.score import ScoreJSON

    score = ScoreJSON.from_json(score_path.read_text())
    if score.rcan_signature is None:
        typer.secho(
            f"error: {score_path} has no rcan_signature — sign the run first.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    try:
        result = submit_score(
            score,
            endpoint=endpoint or DEFAULT_RRF_ENDPOINT,
            api_key=api_key,
        )
    except RrfSubmitError as e:
        typer.secho(f"submit failed: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=3) from e

    typer.echo(json.dumps(result, indent=2))

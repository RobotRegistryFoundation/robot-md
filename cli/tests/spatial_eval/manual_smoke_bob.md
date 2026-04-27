# Manual smoke test: spatial-eval on bob

Run BEFORE declaring SP6 Phase 0 done. Estimated time: ~40 min.

**Status: ready to run.** T30 (server registration) shipped in PR #14 (merge commit `f238c72`); all 9 SP6 MCP tools are registered on the `robot-md mcp` server.

## Prerequisites

- bob plugged in: SO-ARM101 on `/dev/ttyACM0`, OAK-D connected, idle.
- Phone tripod aimed at the play surface; 30×30 cm play area in frame at the resolution declared in `ROBOT.md`.
- `pip install 'robot-md[hardware]'` in bob's venv (covers SP6 deps — see `cli/pyproject.toml` `[hardware]` extra note).
- ROBOT.md updated: `spatial_eval_init(units=["O1","O2","O3","A1","A2"])` ran successfully (the tool inserts the `spatial-eval:` block into the manifest).
- Fixture kit assembled per `cli/src/robot_md/spatial_eval/execute/fixtures/kit_v1.md`.
- `ANTHROPIC_API_KEY` exported in bob's shell.
- Bob's RCAN apikey is on file (per `project_bob_apikey_state.md`); production signer wiring may be partial — `spatial_eval_verify` will refuse to verify unsigned scores in v1.0.0.

## Procedure

1. **Dry-run preflight.** Run `spatial_eval_dry_run` (no args). Expect `{"ok": true, "checks": {"spatial_eval_section": "present", "anthropic_api_key": "set", "judge_camera_device": "phone:tripod"}}`. If any check is `"missing"`, fix it and re-run.

2. **Probe-only baseline.** Run `spatial_eval_run_probe(units=["O1"], baseline_only=true)` against the public split (3 stub probes). Expect:
   - <60 s wall-clock (3 probes × 1 stack × ~5 s/probe).
   - Score JSON returned with `tracks.probe.baseline_claude.O1.passed >= 1` and `tracks.probe.robot_declared == {}`, `delta_per_unit == {}` (baseline-only contract).
   - Anthropic API cost <$1 (check console.anthropic.com usage page).

3. **Probe full side-by-side.** Run `spatial_eval_run_probe(units=["O1"])` (no `baseline_only`). Expect:
   - 6 model calls (3 probes × 2 stacks).
   - Score JSON has both `baseline_claude` and `robot_declared` populated.
   - `delta_per_unit.O1` is a number (typically 0.0 since baseline + declared resolve to the same Claude model in v1).

4. **Execute small.** Run `spatial_eval_run_execute(units=["O1"], trials_per_unit=3)`.
   - Manually slide the green cup over the red cube before each trial (the standard kit O1 procedure).
   - Expect Score JSON with `tracks.execute.O1.n == 3` and `evidence_root == "sha256:<64-hex>"`.
   - Evidence packet on disk at the returned `run_dir` containing `manifest.json`, `Score.json`, and (for now) an empty `videos/` dir.
   - Inspect `pending_review/` — any low-confidence trials are flagged for human review.

5. **Replay determinism.** Run `spatial_eval_replay(run_dir=<path from step 4>)`.
   - Expect Score JSON with `tracks.execute.O1.passed == n_passed_in_step_4`.
   - The replay's `evidence_sha256` must match step 4's `evidence_root` byte-for-byte (deterministic root hash).

6. **Verify (gated on signed Score.json).** If bob's apikey is wired and step 4's Score.json carries an `rcan_signature`:
   - Run `spatial_eval_verify(score_json=<contents of Score.json>)`.
   - Expect `{"ok": true, "attestation": "self-attested"}`.
   - Tamper one byte in the signature, re-run, expect `{"ok": false, "error": "invalid signature"}`.
   - If apikey is not yet wired, this step returns `{"ok": false, "error": "production verifier not wired"}` — that is the documented Phase-0 state, not a failure.

7. **Submit-to-RRF stub.** Run `spatial_eval_submit_to_rrf(run_dir=<path>)`. Expect `{"ok": true, "status": "pending_phase_1", "message": "...RRF §27..."}`. This is the documented Phase-0 stub.

8. **Full sweep.** Run `spatial_eval_run_full(units=["O1","O2","O3","A1","A2"], trials_per_unit=10)` for a complete pass.
   - Expect <40 min total wall-clock (5 units × 30 probes × 2 stacks ≈ 25 min for probe phase + 5 units × 10 trials × ~30 s each ≈ 25 min for execute, with overlap).
   - Inspect any flagged manual-review trials; resolve via `manual_gate.resolve_review` (or whatever T28+ shape ships).

## Pass criteria (Phase 0)

All seven success criteria from the spec hold:

1. `spatial_eval_dry_run` passes with all checks present/set.
2. `spatial_eval_run_probe --units O1 --baseline_only` yields Score JSON in <60 s with the empty-declared-track contract honored.
3. `spatial_eval_run_execute --units O1 --trials 3` yields Score JSON + evidence packet with deterministic root hash.
4. `spatial_eval_replay` reproduces Score byte-for-byte (modulo the new `timestamp` and `rrn=RRN-replayed`).
5. `spatial_eval_verify` accepts a signed Score and rejects a tampered signature (gated on apikey wiring).
6. `spatial_eval_run_full` completes in <40 min with all 5 units enabled.
7. ROBOT.md schema validation rejects malformed `spatial-eval:` sections (covered by automated test `test_schema.py`; spot-check by editing the manifest to inject a non-claude `reasoning_stack.declared` and re-running `validate`).

If any criterion fails: capture the failure (logs, Score JSON, video frames) and open an issue tagged `sp6-bob-smoke`. Do not declare Phase 0 done until all 7 pass.

## Known gaps (Phase 0 → Phase 1)

- **No video bundling yet:** `videos/` in the evidence packet is empty in Phase 0. Phase 1 will populate it from the judge camera capture (T19's `_score_unit` reads frames but does not currently retain them).
- **No reset_scorer_registry consumer:** the test fixture exists but no Phase-0 test uses it; T15+ scorer dispatcher tests in v1.1 may.
- **Production signer not wired:** `spatial_eval_verify` accepts an injected verifier in tests but has no production counterpart yet. Apikey integration is the Phase-1 item.
- **`grid_mat.pdf` is a placeholder path:** the file does not exist on disk in v1.0.0; the BOM doc has manual print instructions instead.

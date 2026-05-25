# Changelog

All notable changes to `robot-md` are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [1.10.5] - 2026-05-25

### Added

- **`register --export-to <path>`.** Writes copies of the minted
  `<rrn>.signing.json` and `<rrn>.apikey` to a caller-supplied directory
  in addition to `~/.robot-md/keys/`. Lets a subagent harness with an
  isolated `HOME` persist credentials to the caller's filesystem before
  teardown — the structural fix for the silent operator/RRF drift caught
  during Spec B Phase E orientation (closes #79).

  Files preserve their canonical names (`<rrn>.signing.json`,
  `<rrn>.apikey`) so the natural restore path is `cp <export-dir>/* ~/.robot-md/keys/`.
  Atomic write + mode 0o600, matching the in-place writers.

  Fails loud (exit 4) if the export write fails after the RRF mint
  succeeded: prints a recovery message naming the minted RRN and the
  HOME path. Silently swallowing the failure would re-introduce the
  drift bug. With `--dry-run`, surfaces a warning and skips the export
  (nothing was minted).

---

## [1.10.4] - 2026-05-11

### Fixed

- **`register` auto-binds the robot's `pq_kid` as an `operator-envelope`
  authority.** After a successful mint, `robot-md register` (and `init
  --register`) now POSTs to `/v2/authorities/register` with `purpose:
  operator-envelope`, signed by the robot's own keypair. Without this step,
  `robot-md-gateway`'s envelope verifier returned 403 `kid not registered`
  on every signed invoke — e.g., from `robot-md trial iteration
  --capture-pre`, blocking PICK-PLACE-10 cert minting end-to-end. The
  gateway resolves kids via `GET /v2/keys/<kid>`, which scans authority
  records only; robot mints persisted `pq_signing_pub` to `robot:<rrn>`
  but never wrote a `kid:<pq_kid>:<ts>` → `authority:<ran>` mapping. The
  `/v2/authorities/register` endpoint already supported `purpose:
  operator-envelope` for this case (mirrors the manual
  `scripts/register-operator-kid.ts` flow used to seed `bob-operator-2026`).
  Non-fatal on failure — register still returns 0 with a warning. Closes #84.
- **`install-gateway` default `ROBOT_MD_TOOL_ALLOWLIST` includes `perceive`.**
  Without `perceive` on the allowlist, the Spec B trial flow's first
  hardware call — `_gateway_invoke("oak-d", "perceive", {"query":
  "red_blob"})` for pre-state capture — 403'd on tool-allowlist even after
  passing envelope auth. Closes #85.

### Changed

- `robot-md-gateway` dependency tightened from `>=0.5.0a1` to `>=0.5.0a3`
  so fresh `pip install robot-md` pulls the version that actually reads
  `bearers.yaml`'s `actuators:` list. Gateway 0.5.0a1 / 0.5.0a2 silently
  fall back to the legacy singleton `actuator:` entry, breaking multi-
  actuator dispatch (e.g., oak-d for perceive alongside so-arm101 for arm).

---

## [1.10.3] - 2026-05-11

### Fixed
- **Cold-install UX: serial-bus probe failures are no longer silent.**
  Previously, when `/dev/ttyACM*` was hardened to gateway-only ownership
  (the default udev rule on cert-bearing rigs), `robot-md init`'s
  auto-discovery would catch the `PermissionError`, swallow it, and fall
  back to `preset: minimal` — operator only noticed when the rendered
  manifest had no `arm.pick` / `arm.place` capabilities. `_probe_servo_buses`
  now catches `PermissionError` specifically, surfaces a stderr warning
  with the exact remediation command, and appends to `scan.warnings`.
  `scan_feetech` re-raises `PermissionError` unchanged instead of wrapping
  it in a generic `RuntimeError`.
- **`robot-md init --force` preserves `metadata.rrn` + `metadata.record_url`.**
  Previously, `--force` regenerated the manifest from scratch via
  `merge_preset_into_draft`, dropping the operator's already-minted RRN
  and orphaning the signing keypair under `~/.robot-md/keys/<rrn>.signing.json`.
  `phase_write_manifest` now reads the existing manifest's frontmatter
  before regenerating and carries forward the two registration-identity
  fields. A subsequent `robot-md register` run still overwrites them
  (correct), but a `--force` re-init without re-register no longer
  silently orphans the keypair.

### Added
- **`robot-md install-gateway` adds `$SUDO_USER` to the `robot-md-gateway` group.**
  After the systemd unit is installed and the gateway is verified active,
  the invoking user (`$SUDO_USER`) is added to the `robot-md-gateway` group
  so that a subsequent `robot-md init` can read `/dev/ttyACM*` for serial-bus
  auto-discovery. The operator must log out + back in (or run `newgrp
  robot-md-gateway`) before the new group takes effect — `install-gateway`
  prints this remediation. New `--no-add-user` flag opts out on locked-down
  service hosts that intentionally keep operator accounts out of the
  gateway group.

### Notes
- Closes #82. All three remediations from the issue ship together. Tested
  end-to-end on Bob during Spec B Phase E T22 cold-install prep.
- No code changes to the CLI surface that would affect existing manifests
  or signing flows. The carry-forward only kicks in when `--force` is
  passed and an existing manifest is present.

---

## [1.10.2] - 2026-05-11

### Fixed
- Release workflow's `pypi-publish` job now fires on tag push, not only on
  manual `workflow_dispatch`. The previous gate (added Apr 17 when
  Trusted Publisher was unconfigured) was made vestigial by the later
  switch to `PYPI_TOKEN`, but the gate stayed and silently skipped PyPI
  upload for v1.10.1 — the GitHub release shipped while PyPI still
  served 1.10.0. Manual dispatch with `publish_pypi=true` is preserved
  as an explicit re-publish escape hatch.

### Notes
- This release is a no-code republish of 1.10.1's CLI payload to make
  `pip install robot-md` actually deliver the `_gateway_invoke`
  full-envelope fix (closes #69, originally shipped in 1.10.1).

---

## [1.10.1] - 2026-05-11

### Fixed
- `robot-md trial`'s `_gateway_invoke` now builds the full `InvokeEnvelope`
  the gateway requires — `msg_id`, `type`, `ruri`, `scope`, `tool_name`,
  `tool_args`, `manifest_path`, `actuator_name`. Prior 1.10.0 omitted
  `ruri` / `scope` / `manifest_path`, which caused a 422 from any gateway
  with `extra='forbid'` and silently dropped the `actuator_name` on
  multi-actuator gateways (robot-md-gateway >= 0.5.0a3). Closes #69.

### Changed
- `trial start` warns when `ROBOT_MD_RURI` / `ROBOT_MD_MANIFEST_PATH` are
  unset — these are required by `_gateway_invoke` and the trial would
  otherwise fail at the first `--capture-pre`.

### Notes
- Requires `robot-md-gateway >= 0.5.0a3` if the rig hosts multiple
  actuators behind one gateway (typical for pick-place rigs with both
  perception and motion drivers).

---

## [1.10.0] - 2026-05-11

### Added
- `robot-md trial` subcommand family for capturing pick-and-place trial evidence:
  - `trial start --property <name>` writes `~/.robot-md/trials/<id>/start.json` with cold-install wall-clock anchor.
  - `trial iteration --trial <id> --capture-pre` records perceive + joint state via the gateway.
  - `trial iteration --trial <id> --capture-post-and-verdict` computes the verdict (centroid ∈ bowl bbox AND |depth_delta| ≤ 80mm).
  - `trial iteration --trial <id> --reset-confirmed` stamps operator reset confirmation.
  - `trial abort --trial <id>` aborts a trial; further iterations are refused.
  - `trial finalize --trial <id>` rolls 10 iterations into `evidence.json` with the 10-min cold-install wall-clock verdict block.
- Skill `using-robot-md` gains a "Pick-place trial protocol" section guiding the agent through `oak-d perceive` + `so-arm101 move` sequencing.

### Notes
- Trial commands assume the gateway is reachable at `ROBOT_MD_GATEWAY_URL` (default `http://127.0.0.1:8080`) with `ROBOT_MD_GATEWAY_BEARER`. Phase E (#69) tracks the envelope-shape gap before Bob runs the physical trial.

---

## [1.5.1] - 2026-05-01

### Notes
- No code changes. This release validates Plan 1 Phase 1 of the OpenCastor
  Ecosystem Direction (2026-05-04) — the new release CI now emits a
  hybrid-signed version-tuple envelope via the
  `continuonai/rcan-spec/.github/actions/emit-version-tuple@v3.2.0`
  composite action. Signing identity: `RAN-000000000002`.

---

## [1.5.0] — 2026-05-01

**SP-AN v2 + SP6 Phase 1.5 (RRF counter-sign) + SP3 Phase D + a complete robotmd.dev redesign.** Versioned MINOR not PATCH because four feature tracks landed on top of v1.4.0 — only the parser fix was originally framed as v1.4.1. Strict-semver upgrade is safe; no breaking changes.

### Added
- **SP-AN v2 — multi-session subscribe + capability advertisement.** Drops down to `mcp.server.lowlevel.Server` for proper per-session `subscribe_resource` / `unsubscribe_resource` handlers, removing v1's single-session-per-process limitation. Capability advertisement so subscribed clients can announce voice-mode, terminal-mode, etc. ([#28](https://github.com/RobotRegistryFoundation/robot-md/pull/28))
- **SP6 Phase 1.5 — RRF §27 counter-sign client.** New `spatial_eval_submit_to_rrf` MCP tool packages a self-attested Score.json and posts to `/v2/robots/<rrn>/spatial-eval`. RRF independently re-runs the held-out probe split and returns a counter-signed score; `spatial_eval_verify` returns `{"ok": true, "attestation": "registry-attested"}` against it. First successful end-to-end submission: `sub_8c686d6e-6e87-49ef-8bb5-0b51e5982de7`. ([#29](https://github.com/RobotRegistryFoundation/robot-md/pull/29), [#30](https://github.com/RobotRegistryFoundation/robot-md/pull/30), [#31](https://github.com/RobotRegistryFoundation/robot-md/pull/31))
- **SP3 Phase D — backend extras + entry-points + preset preference.** Wires `[project.entry-points."robot_md.backends"]` so installed backends are runtime-discoverable; preset preference logic for tie-breaking among multiple matching backends. ([#27](https://github.com/RobotRegistryFoundation/robot-md/pull/27))
- **robotmd.dev complete redesign.** Four-PR information-architecture rebuild of the site under `site/`, ~+8,750 net new lines.
  - IA review + landing page + managed-agents stub + Cloudflare Workers KV-backed waitlist endpoint. ([#33](https://github.com/RobotRegistryFoundation/robot-md/pull/33))
  - Eight MVP secondary pages: `/spec/`, `/mcp/`, `/registry/`, `/compliance/`, `/agents/{claude-code,gemini,codex,chatgpt}/`. ([#34](https://github.com/RobotRegistryFoundation/robot-md/pull/34))
  - `render-spec.py` (RCAN spec Markdown → HTML), `/agents/` hub, `/agents/q/` (Amazon Q aarch64-block surface). ([#35](https://github.com/RobotRegistryFoundation/robot-md/pull/35))
  - 14 routes total, build-time stats injection (npm-weekly downloads, RRF endpoint count), strict CSP.

### Fixed
- **`parse_file` now accepts directories** — `robot-md compliance status .`, `robot-md validate ./bob`, and every other CLI command that takes a manifest path now resolve a directory argument to `<dir>/ROBOT.md`. Previously raised `ParseError: Is a directory`. ([#32](https://github.com/RobotRegistryFoundation/robot-md/issues/32) / [#36](https://github.com/RobotRegistryFoundation/robot-md/pull/36))

### Notes
- All robotmd.dev pages above are live and CSP-validated.
- SP6 Phase 1.5 unlocks the public spatial-eval leaderboard distinction: only registry-attested scores show up there. Self-attested scores remain valid for development, CI gating, and private benchmarking.
- The `RRF_SPATIAL_EVAL_PQ_PRIV` secret-encoding mishap discovered along the way was fixed via RRF #75 / #76 (keypair rotation, clean encoding); no `robot-md` change needed.

---

## [1.4.0] — 2026-04-30

**SP-HP hot-plug daemon + SP-AN announce/confirm + SP6 Phase 1 self-attestation.** Three independent feature tracks land together; together they change what registering a new piece of hardware feels like — OS-level event, conversational confirm in Claude, cryptographically self-attested eval scores.

### Added
- **SP-HP — `robot-md hotplug-daemon`** per-user daemon watching `pyudev` (Linux), `ioreg + pyserial` (macOS), or polling (Windows). Hash-chained append-only event log at `~/.robot-md/hotplug-events.jsonl`. Three tiers (HIGH / MEDIUM / LOW) based on VID:PID-to-preset uniqueness and matching backend availability. HIGH-tier auto-binds via `fcntl`-locked `ROBOT.md` merge; MEDIUM and LOW queue for operator confirmation. Operator CLI: `robot-md hotplug review|confirm`. MCP tools: `hotplug_review`, `hotplug_confirm`. Service installer: `robot-md hotplug install-service` (systemd / launchd; Windows stub). 50 unit tests + 1 e2e.
- **SP-AN — MCP resource `robot-md://hotplug/pending`** plus `notifications/resources/updated` plumbing. Linux uses an AF_UNIX socket fanout from the daemon; macOS / Windows fall back to a 2-second mtime poll. Both paths share an opportunistic active-session capture inside the FastMCP `lifespan`. Three new sections in `using-robot-md.SKILL.md` describe the announce-by-voice-then-mirror-to-chat UX, the 30-second undo window, the resolved-elsewhere acknowledgement path, and the MEDIUM-tier alternative-options surface. 24 unit tests (incl. canonical/mirror skill-text harness with char-exact substring contracts).
- **SP6 Phase 1 — self-attested spatial scores.** `spatial_eval_verify` is now a real verifier: loads the keystore keypair at `~/.robot-md/keys/<rrn>.signing.json` and checks the signature via `rcan.crypto.verify_ml_dsa`. `spatial_eval_run_execute` and `spatial_eval_run_full` produce signed Score.json on disk. Robots without a keypair produce unsigned scores cleanly. New module `robot_md.spatial_eval.sign` is the single source of truth for canonical signing bytes; `payload_bytes` clears `rcan_signature` before serialization (closing the sign-over-own-signature bug Phase 0 stub had embedded). 87 spatial_eval tests.
- `watchdog>=3.0` added to core dependencies (`hotplug.manifest_watcher` uses `FileSystemEventHandler`).

### Fixed
- `socket_listener.py`: `cleanup_socket` kwarg to `asyncio.start_unix_server` is Python 3.13+ only — pass it conditionally so SP-HP socket tests pass on the 3.10/3.11/3.12 CI legs.
- `spatial_eval.run_full_tool`: re-sign merged Score.json after merging probe + execute tracks. The execute-track signature was stamped before the merge and would otherwise show as `invalid signature` — looks like tampering, isn't.

### Changed
- 59 ruff lint findings across SP-HP / SP-AN files cleaned up (B017/B904/E402/E501/E702/F401/I001/RUF059/SIM105 + `ruff format` on 46 files).

### Notes
- 163 cross-area tests green on Python 3.13. Manual smoke on bob is the next gate (SP-AN: `cli/tests/manual/span_smoke.md`; SP6: `cli/tests/spatial_eval/manual_smoke_bob.md`).
- SP-AN runs single-session-per-process via opportunistic active-session capture. Multi-session generalization needs the lowlevel `mcp.server.lowlevel.Server` API and is a v2 deliverable; trade-off is documented in `cli/docs/hotplug-roadmap.md` and the public spike memo at `docs/superpowers/specs/2026-04-30-span-fastmcp-subscribe-spike.md`.
- SP6 Phase 1 lands the self-attested half. The registry-attested half (RRF §27 endpoints, RRF independently re-running the held-out probe split, RRF counter-signing for leaderboard eligibility) is RRF-side work in a separate plan.

---

## [1.3.0] — 2026-04-29

**SP3: capability metadata foundation + RealSense + LeRobot adapter backends.** Three SP3 phases shipped on top of v1.2.5:

- **Phase A — Capability metadata API.** New `Capability` dataclass (`name`, `namespace: Literal["core","vendor"]`, `arg_schema`, `description`) plus a backward-compatible `describe_capabilities() -> list[Capability]` default on `CapabilityBackend`. Backends still implement `capabilities() -> frozenset[str]`; the default walker reads each capability's metadata from `cli/src/robot_md/schemas/capabilities.json`. Vendor capabilities use `<backend>.<verb>` namespacing, validated at backend registration via a single regex (`^[a-z][a-z0-9_]*\.[a-z]([a-z0-9_.]*[a-z0-9_])?$`). New `robot-md describe-capabilities [--json]` CLI subcommand enumerates declared backends.
- **Phase B — RealSense camera backend.** `RealsenseBackend` (`name="realsense"`, `read_only_capabilities={perceive.rgb, perceive.depth}`) declares `perceive.rgb`, `perceive.depth`, and the vendor `realsense.aligned_depth`. Lazy-imports `pyrealsense2`; `open()` starts a pipeline with color BGR8 + depth Z16 @640x480/30fps; `scene_describe()` snapshots latest frames. Camera-only adapter — no motion handlers.
- **Phase C — LeRobot motion + camera backend.** `LerobotBackend` (`name="lerobot"`, `protocols={feetech, dynamixel}`, `read_only_capabilities={perceive.rgb, perceive.depth}`) declares all 7 core caps (arm.pick/place/home, gripper.open/close, perceive.rgb/depth) plus the vendor `lerobot.teleop`. Wraps `lerobot.common.robot_devices.robots.factory.make_robot`; merges `DriverEntry` (port, baud_rate, model) with `physics.kinematics` (per-joint servo_id) into the per-motor config dict.

**Note on runtime discovery.** Both backends are importable but not yet entry-point registered — `discover_backends()` won't find them until SP3 Phase D wires the `robot_md.backends` group in `pyproject.toml`. Direct import works today: `from robot_md.backends.realsense import RealsenseBackend` and `from robot_md.backends.lerobot import LerobotBackend`.

Also includes the v1.2.5 fix that never reached PyPI (eu-register URL routing — see [1.2.5] below).

### Added
- `robot_md.backends.capability.Capability` dataclass + `derive_namespace(name)` helper.
- `CapabilityBackend.describe_capabilities()` ABC default; `_capability_default.describe_default()` schema-driven walker.
- `cli/src/robot_md/schemas/capabilities.json` — JSON-Schema for the 7 core capabilities + nav.go_to + safety.estop, all with `additionalProperties: false`.
- `_validate_capability_namespace(name, caps)` at backend registration; rejects malformed names (trailing dot, missing verb, non-lowercase) with `BackendRegistrationError`.
- `robot_md.backends.enumerate_capabilities(registry)` walker re-exported from `robot_md.backends`.
- `RealsenseBackend` (`backends/realsense/{__init__, perception, capabilities}.py`).
- `LerobotBackend` (`backends/lerobot/{__init__, config, motion, perception, capabilities}.py`).
- 87 backends tests across Phases A+B+C.

### CI
- Phase A merge sequence (`9f9ae29`/`70e797e`/`3244460`/`0b33874`/`b1c5564` + PR #22 squash).
- Phase B (PR #25, `cb1e61a`).
- Phase C (PR #26, `535a6a0`).
- `SKIP_FLAKY_DISCOVER=1` flag added to `.github/workflows/ci.yml` Test step (PR #23, `5747939`); deeper root cause for `test_discover_emits_per_step_progress` tracked in issue #24.

### Notes
- This release bundles the v1.2.5 eu-register URL routing fix (RRF #72) — that tag was created and a GitHub release published, but `workflow_dispatch publish_pypi=true` was never run. PyPI users upgrading from 1.2.4 receive both the v1.2.5 fix and the SP3 backend infrastructure in a single hop.

---

## [1.2.5] — 2026-04-28

**`emit-eu-register --submit` now POSTs to the correct RRF endpoint.** The §26 / Art. 49 submission lives at `/v2/models/<rmn>/eu-register` (per-AI-system, not per-robot); robot-md was POSTing to `/v2/robots/<rrn>/eu-register` and getting a 405 from Cloudflare's default-no-handler response. Builder also now enforces `metadata.rmn` per rcan-spec §26 MUST. Closes RRF #72.

### Fixed
- `submit.py`: introduced `KIND_REGISTRY` mapping `kind → {id, path, bearer}`. eu-register routes to `/v2/models/<rmn>/eu-register` and skips the Bearer header (RRF derives submitter from the signed payload, not Authorization). Other kinds unchanged. `submit_artifact()` now accepts `rmn=...` kwarg in addition to `rrn`. The audit log is still keyed by rrn for all kinds.
- `eu_register.py`: builder now raises `EuRegisterError` when `metadata.rmn` is empty, mirroring the existing `metadata.rrn` check. Per rcan-spec §26 the top-level rmn is MUST.
- `__main__.py:_maybe_submit`: extracts `rmn` from the artifact (top-level or `system.rmn`) when kind=eu-register and passes it to `submit_artifact`. Help text on `emit-eu-register --submit` updated to point at the correct URL.

### Added
- New regression tests: `test_submit_eu_register_uses_models_url_and_no_bearer`, `test_submit_eu_register_requires_rmn`, `test_errors_when_rmn_missing`. Existing tests kept for `metadata.rrn` parity.

### Notes

- Wire-format unchanged. Existing eu-register artifacts on disk that were emitted with empty rmn under 1.2.4 are no longer valid §26 submissions — re-emit under 1.2.5 against a manifest that has `metadata.rmn: RMN-...`. Mint an RMN via `POST /v2/models/register` (signed body required per RCAN 3.0 §2.2).
- Closes RRF #72.

## [1.2.4] — 2026-04-27

**`compliance status` now cryptographically verifies signatures.** Previously checked only that a `sig` field was present, leaving structurally-signed-but-cryptographically-invalid artifacts (e.g. those produced by 1.2.2 emitters against rcan-py 3.3.0's sign↔verify asymmetry) reported as `(signed)` with green submission readiness. Now reports a tri-state per artifact and gates submission readiness on cryptographic validity.

### Fixed
- `robot-md compliance status` now calls `rcan.hybrid.verify_body` per artifact instead of just checking for the presence of a `sig` field. Artifacts with invalid signatures report as `(signed, INVALID)` and fail submission readiness with reason `signature invalid for <schema> — re-emit with a recent rcan-py (>=3.3.1) and check rcan.hybrid.verify_body`.

### Added
- `robot_md.signing._verify_with_pq_pub(signed, pq_pub_b64)` — verify helper for the FriaDocument nested-key shape (where `pq_signing_pub` is at `signing_key.public_key` rather than top-level). Re-injects `pq_signing_pub` into the dict before delegating to `rcan.hybrid.verify_body` so the canonical pre-image matches `sign_body` output.
- `robot_md.compliance_status._render_sig_state(state)` — renders `(✓, "(signed, verified)")` / `(✗, "(signed, INVALID)")` / `(•, "(unsigned)")` for the three artifact states.
- `_KIND_TO_SCHEMA` mapping in `compliance_status.py` — links each `SUBMISSION_KIND` (`fria`, `ifu`, `safety-benchmark`, `incident-report`, `eu-register`) to its corresponding artifact schema, so per-kind readiness can read the right artifact's `sig_state`.

### Changed
- `compliance status` per-artifact output: `(signed)` → `(signed, verified)` or `(signed, INVALID)`.
- `_check_submission_readiness` signature now also takes the artifacts inventory: `_check_submission_readiness(apikey_present, artifacts_present)`. Per-kind readiness now requires `sig_state == "verified"` on the corresponding artifact (when one exists on disk).

### Tests
- `tests/test_compliance_status.py::test_status_marks_artifact_invalid_when_signature_does_not_verify`
- `tests/test_compliance_status.py::test_status_marks_artifact_verified_when_signature_is_valid`
- `tests/test_compliance_status.py::test_status_marks_artifact_unsigned_when_no_sig_field`
- `tests/test_compliance_status.py::test_render_sig_state_returns_correct_marker_and_suffix`
- `tests/test_signing.py::test_verify_with_pq_pub_*` (3 tests)

### Related
- Pairs with `rcan-py 3.3.1` ([continuonai/rcan-py#49](https://github.com/continuonai/rcan-py/pull/49), released 2026-04-27) which fixed the upstream `sign_body` / `verify_body` asymmetry that surfaced this gap.
- RRF backend issues opened separately: [#71](https://github.com/craigm26/RobotRegistryFoundation/issues/71) `/safety-benchmark` returns 401 on bodies that locally verify; [#72](https://github.com/craigm26/RobotRegistryFoundation/issues/72) `/eu-register` returns 405 for POST/PUT/PATCH.

---

## [1.2.3] — 2026-04-27

**`request-apikey --submit` now usable end-to-end.** Closes the apikey gap
for any operator who lost (or never received) the original apikey for a
registered RRN. The RRF `/v2/robots/<rrn>/apikey-requests` endpoint
shipped 2026-04-27 (RRF commit `cdf5198`); this release wires the CLI
side so the issued apikey lands on stdout AND is auto-saved to
`~/.robot-md/keys/<rrn>.apikey` (mode 600) — no manual curl.

### Added

- `robot_md.apikey_request.persist_response()` helper: parses the submit
  result, atomically writes a string `api_key` to the keystore via the
  same `_write_apikey` used at initial registration, returns the JSON
  body for the caller to surface.
- `request-apikey --submit` now:
  - prints the response body to stdout (or `--output` file)
  - prints `saved apikey to <path> (mode 600)` to stderr on success
  - 5 new unit tests + 1 CliRunner integration test covering the helper.

### Changed

- `request-apikey --submit` help text now reflects that the endpoint is
  live, not "may not be implemented yet."
- `submit_request` docstring updated to point at the live endpoint.

### Docs

- `cli/tests/spatial_eval/manual_smoke_bob.md` no longer claims SP1 gates
  T30 — that gate cleared when PR #14 merged at `f238c72`.

---

## [1.2.2] — 2026-04-27

**Servo SDK rewrite to `scservo_sdk.sms_sts`.** Unblocks Phase 8 hardware
verification on real Feetech buses. The PyPI `feetech-servo-sdk` package
ships a `scservo_sdk` Python module whose top-level `PacketHandler()`
factory is broken (calls undefined `SCS_SETEND` and passes the wrong
arg count to `protocol_packet_handler`). Robot-md previously imported
`from feetech_servo_sdk import PacketHandler, PortHandler` — that name
isn't exported by the published wheel, so SO-ARM101 owners hit
`ImportError` on every motion call and `context.py` silently degraded
to "no backend".

### Fixed

- All servo call sites now use `scservo_sdk.sms_sts.sms_sts(portHandler)`,
  the working SMS/STS protocol class. SO-ARM101 + every Feetech-bus
  arm uses this protocol. Touched files:
  - `cli/src/robot_md/calibrate.py` (read-pose, sign-test paths)
  - `cli/src/robot_md/init_phases/_feetech_probe.py` (autodetect probe)
  - `cli/src/robot_md/backends/feetech_depthai/servo.py` (live ServoBus)
  - `cli/src/robot_md/bus_scan.py` (Tier B autodetect)
- API signature now drops the leading `portHandler` argument from
  `read2ByteTxRx` / `write1ByteTxRx` / `write2ByteTxRx` (the port is
  bound at `sms_sts(ph)` construction time). Test stubs and arg-index
  assertions updated to match.
- `__version__` in `cli/src/robot_md/__init__.py` was stale at `0.7.3`;
  now tracks `pyproject.toml` (1.2.2).
- `load_context` now degrades to a backend-less context on port-open
  failures (`OSError` / `pyserial.SerialException`) and backend
  open-time validation failures (`RuntimeError`), not only missing
  imports. A misconfigured `drivers[].port` no longer crashes MCP
  startup; the server boots in read-only mode and `execute_capability`
  returns `no_backend` until the operator fixes the config.

### Notes

- PyPI distribution name is unchanged (`feetech-servo-sdk` in extras);
  only the Python module name (`scservo_sdk`) and the call API have
  changed.
- Operators on v1.2.0 / v1.2.1 must upgrade for any motion to work
  on hardware — manifest reads / validate / render were never affected.

---

## [1.2.1] — 2026-04-27

**Lint cleanup of v1.2.0.** No behavior change. Wheel built from a
green-CI commit so future maintainers can rely on the published artifact
matching `ruff check`/`format` clean.

### Fixed

- `ruff check src tests` now passes (66 → 0 errors). Combined manual
  fixes (broke prompt content strings in `mcp/server.py` for E501,
  combined nested `async with` in `tests/hardware/test_sp1_demo_path.py`
  for SIM117) with auto-fix + `ruff format`. v1.2.0's published wheel
  was functional but failed lint.

---

## [1.2.0] — 2026-04-27

**SP1: One MCP server.** The `robot-md` plugin now ships the Python
`robot-md mcp` server directly via its `.mcp.json` (drops the npm
`robot-md-mcp@^0.3` fallback). Operators get manifest reads AND motion
(`execute_task`, `execute_capability`, `vision_find`, `estop`, …) in one
MCP server. Plugin requires `pip install 'robot-md[hardware]'`.

See `docs/superpowers/specs/2026-04-26-sp1-wire-python-mcp-server-design.md`
and `docs/superpowers/specs/2026-04-27-sp1-5-simplification-revisions.md`.

### Added

- `robot-md mcp` (no positional argument) walks up from cwd to find
  `ROBOT.md`. Enables the plugin's no-arg invocation. Pass
  `robot-md mcp /path/to/ROBOT.md` to override.
- `[hardware]` meta-extra in `pyproject.toml` — pulls common backends in
  one install: `pip install 'robot-md[hardware]'`. Equivalent to
  `[feetech-depthai]` today; SP3 will extend with lerobot + realsense.
- `_emit_motion_extras_hint` in `init.py` — when manifest declares
  `arm.*`/`nav.*`/`gripper.*`/`perceive.*` capabilities, prints the
  `pip install 'robot-md[hardware]'` reminder + `/mcp → Reconnect`
  guidance. Fires from both `default_flow` and `non_interactive`.
- `doctor_summary` MCP tool — wraps `validate` with a structured
  human-readable health summary (matches the npm v0.3 server's contract).
- 4 new MCP prompts: `brief-me`, `check-safety`, `explain-capability`,
  `manifest-status`. Activated via `/<name>` in Claude Code (matches the
  npm v0.3 server's prompt set).
- `using-robot-md` skill: `## Motion intent without motion tools` stanza.
  When operator requests motion AND `execute_task` tool is missing,
  skill halts and emits verbatim upgrade instructions
  (lazy-discovery path).
- `scripts/sync-skill.sh` + CI `skill-sync-check` job — keeps the
  bundled `using-robot-md` SKILL.md in sync with the canonical at
  `robot-md-mcp/skills/using-robot-md/SKILL.md`.
- Six new `robot-md init --preset` targets in
  `cli/src/robot_md/presets/`. Brings the bundled count from 11 to 17:
  - `reachy2` — Pollen Robotics open-source humanoid (bimanual 7-DoF
    arms + 3-DoF Orbita neck + Zuuu holonomic mobile base + 4-camera
    head/wrist stack). `physics.type: humanoid`. First preset to drive
    the `reachy2_sdk` gRPC interface (port `50051`); same surface for
    real robot and the `pollenrobotics/reachy2` Docker simulator.
  - `stretch3` — Hello Robot Stretch 3 mobile manipulator (vertical
    lift + telescoping arm + 3-DoF wrist + pan/tilt head + diff-drive
    base + tri-RealSense vision). `physics.type: arm_manipulator`.
  - `lekiwi` — HuggingFace LeRobot LeKiwi mobile manipulator (6-DoF
    Feetech arm on a 3-omni-wheel holonomic base, single shared
    Feetech bus). `physics.type: arm_manipulator`.
  - `lego-spike-prime` — ported from `opencastor`'s
    `config/presets/lego_spike_prime.rcan.yaml`. Differential-drive
    classroom build over the SPIKE hub serial protocol.
  - `lego-ev3` — ported from `opencastor`'s
    `config/presets/lego_mindstorms_ev3.rcan.yaml`. Differential-drive
    via `ev3dev` over SSH/RNDIS; common in second-hand classroom kits.
  - `turtlebot3-burger` — ported from `opencastor`'s
    `config/presets/turtlebot3_burger.rcan.yaml`. ROS 2 + LDS-01 lidar;
    complements the existing `turtlebot4` preset.

  All six pass the standard round-trip
  (`robot-md init … --non-interactive | robot-md validate`).

### Changed

- Plugin `.mcp.json` (in `RobotRegistryFoundation/robot-md-mcp` repo):
  spawns `robot-md mcp` (Python) instead of `npx -y robot-md-mcp@^0.3`.
- Plugin description tells operators upfront that the Python CLI is
  required.
- `using-robot-md` skill drift between the two repos resolved:
  `robot-md-mcp/skills/using-robot-md/SKILL.md` is canonical; the
  bundled CLI copy syncs from it.
- `init` no longer calls `phase_install_mcp` from `default_flow`. Plugin
  handles MCP wiring; init's job is just the manifest + skill + cal.
- `non_interactive()` no longer prints stale
  `claude mcp add ... robot-md-mcp` Next: line; emits motion-extras hint
  in parity with `default_flow`.

### Deprecated

- `phase_install_mcp` is now a no-op returning
  `PhaseResult(status="skipped", ...)`. Function signature preserved
  for backward compat. `install_mcp_claude_code.add()` still exported
  for non-plugin operators who explicitly call it.
- `--no-install-mcp` CLI flag is a no-op; help text marks the
  deprecation.

### Migration

- Existing manifests continue to work unchanged.
- Existing operators upgrade with: `pip install --upgrade robot-md` then
  `/plugin update robot-md` in Claude Code. No re-init required.

---

## [1.1.1] — 2026-04-24

**R6 demo-day fixes.** Patch release surfacing two interop gaps caught
while recording the Bob peer-runtime hot-swap demo.

### Fixed

- `robot_md.register.DEFAULT_ENDPOINT` changed from
  `https://rcan.dev/api/v2/robots/register` (returns 405) to
  `https://robotregistryfoundation.org/v2/robots/register` (the
  canonical RRF v2 ingress). Users previously had to pass
  `--endpoint https://robotregistryfoundation.org/v2/robots/register`
  explicitly; `robot-md register <ROBOT.md>` now works out of the box.

### Changed

- `schemas/v1/robot.schema.json` — `physics.type` enum extended to
  accept `arm_manipulator` in addition to `arm`, `arm+camera`, and
  friends. Aligns the robot-md body schema with the rcan-spec R6 draft
  terminology (SO-ARM101 and similar 6-DoF arms declare themselves as
  `arm_manipulator` in the spec). `arm+camera` still works unchanged.
- `autodetect.py` TODO comment updated to include `arm_manipulator` in
  the allowed-types hint.

### Tests

- `tests/unit/test_schema_intrinsic.py` — new tests assert
  `arm_manipulator` validates and unknown types still reject.

---

## [1.1.0] — 2026-04-24

**RCAN 3.2 peer-runtime alignment.** robot-md now declares itself in
its own dogfood `ROBOT.md` using the new multi-runtime primitive from
rcan-spec 3.2 (§8.6 `agent.runtimes[]`). R5 of the peer-runtimes
cascade — ships alongside opencastor 3.0.0 (R4) as the two first peer
RCAN 3.x runtimes against a single ROBOT.md.

### Changed

- `ROBOT.md` frontmatter
  - `rcan_version: "3.0"` → `"3.2"`
  - added `agent.runtimes[]` with a single `robot-md` entry
    (`harness: robot-md-cli`, `default: true`, `models: []`). The
    empty `models` reflects that this tooling node doesn't run an
    LLM-backed agent loop — it's a schema/lint/validate surface.
- `cli/pyproject.toml`
  - `version = "1.0.1"` → `"1.1.0"`
  - `rcan[pq,crypto]>=3.1.1,<4.0` → `>=3.3,<4`. Dogfoods rcan-py
    3.3.0's `agent_runtimes` field so the self-ROBOT.md parses
    through a shared validator.

### Unchanged

- No behavior change to `robot-md validate`, `robot-md init`, or any
  of the CLI surfaces. No test surface change.

---

## [1.0.1] — 2026-04-23

**rcan 3.1.1 consolidation.** Deletes duplicated primitives and spec-domain
constants that now live upstream in rcan 3.1.1. No behavior change, no
wire-format change, no test changes. All signing envelopes and compliance
artifacts are byte-identical to 1.0.0's output.

### Changed

- `cli/pyproject.toml`: `rcan[pq,crypto]>=3.1,<4.0` → `rcan[pq,crypto]>=3.1.1,<4.0`.
- `signing.py`: local `canonical_json` / `sign_body` / `verify_body` replaced
  by thin adapters calling `rcan.canonical_json` / `rcan.sign_body` /
  `rcan.verify_body` (Task 14, commit `bcb79e8`).
- `benchmarks.py`, `ifu.py`, `incidents.py`, `eu_register.py`: the four
  `build_artifact` emitters now call `rcan.build_safety_benchmark`,
  `rcan.build_ifu`, `rcan.build_incident_report`,
  `rcan.build_eu_register_entry` respectively. Domain logic (manifest
  parsing, measurement, threshold resolution, FRIA validation) stays local.
- Spec-domain constants `ART13_COVERAGE`, `VALID_SEVERITIES`,
  `REPORTING_DEADLINES`, `ART72_NOTE`, `CONFORMITY_STATUS_DECLARED`,
  `SUBMISSION_INSTRUCTIONS` now imported from `rcan` (previously duplicated).

### Unchanged

- Wire format for register POSTs and all compliance artifacts.
- All 32 tests in `test_register.py` + `test_signing.py` pass UNCHANGED.
- Full `cli/tests/` suite: 274 passed, 0 failed.

---

## [1.0.0] — 2026-04-23

**RCAN 3.0 compliance declaration.** No new code. This release tags the
end of the v0.9 compliance theme: seven successive sub-releases (0.9.1
through 0.9.7) each closed one slice of the v0.9 umbrella spec, and
this tag marks the point at which all seven criteria ship together
under a stable major version.

### What was in the v0.9 arc

| Release | Theme |
|---|---|
| 0.9.0 | `rcan>=3.0,<4.0` dep bump + RCAN 3.0 version declaration |
| 0.9.1 | Hybrid signing on `register` (ML-DSA-65 + Ed25519); RURI construction; `test_register.py` rewrite |
| 0.9.2 | Schema gate — `compliance.annex_iii_basis` present ⇒ `compliance.fria_ref` required and URI-shaped |
| 0.9.3 | `emit-benchmarks` — §23 safety benchmark emitter over robot-md's own safety paths |
| 0.9.4 | `emit-ifu` (§24 IFU, Art. 13(3)) + `incidents record`/`report` (§25 PMM, Art. 72) |
| 0.9.5 | `emit-eu-register` (§26 EU Register submission, Art. 49) |
| 0.9.6 | Schema slots for `metadata.rcn_ids[]` / `metadata.rmn` / `metadata.rhn_ids[]`; surfaced in IFU + EU register |
| 0.9.7 | Signed register POST emits the operator-declared sibling IDs — closes ecosystem loop |

### Ecosystem state at 1.0.0

- **robot-md**: 1.0.0 — RCAN 3.0 compliant client.
- **rcan-py**: 3.0.1 on PyPI — ML-DSA-65 + Ed25519 hybrid signing primitives.
- **RRF**: 1.10.0 live at robotregistryfoundation.org — strict hybrid
  signing on all `/v2/*/register` endpoints; `RobotRecord` persists
  operator-declared `rcn_ids`/`rmn`/`rhn_ids`.

### Not in 1.0.0 (carried forward)

- Key rotation (§2.3), at-rest keystore encryption, FRIA content
  enforcement (vs. just reference-gate), and the RCN/RMN/RHN client-side
  register commands — all deferred to v1.1+.
- Opencastor still accepts only RCAN 2.2 configs and reads `.rcan.yaml`
  rather than ROBOT.md; the end-to-end round-trip through opencastor
  remains broken pending a separate alignment release.

### No migration

Drop-in from 0.9.7. `pip install -U robot-md` — no schema change, no
config change, no API change.

---

## [0.9.7] — 2026-04-23

Closes the ecosystem loop on RCN/RMN/RHN sibling registry IDs: robot-md
now emits them in the **signed** register POST body. Pairs with RRF
1.9.0 (sibling endpoints signed) + 1.10.0 (robot record persists
declared sibling IDs).

### Added

- `MintRequest` carries optional `rcn_ids: tuple[str, ...]`, `rmn: str`,
  `rhn_ids: tuple[str, ...]`.
- `as_body()` emits them (or strips them when empty).
- `_extract_mint_fields()` pulls them from `metadata.rcn_ids`,
  `metadata.rmn`, `metadata.rhn_ids`.
- 4 new tests in `test_register.py` covering body shape, empty-strip,
  manifest extraction, and end-to-end signed-POST carry.

### Ecosystem alignment

- robot-md @ 0.9.5 shipped the schema slots. 0.9.6 emitted them in IFU
  and EU-register artifacts. 0.9.7 closes the last emission path: the
  signed register POST. All three paths now carry the operator-declared
  sibling IDs.
- RRF 1.9.0 tightened `/v2/{components,models,harnesses}/register` to
  require hybrid signing (matching `/v2/robots/register`).
- RRF 1.10.0 accepts + persists `rcn_ids`/`rmn`/`rhn_ids` on the
  `RobotRecord`.

All seven v0.9 compliance criteria remain satisfied; v1.0.0
(declaration tag) remains the next release.

---

## [0.9.6] — 2026-04-23

Seventh release in the v0.9 RCAN 3.0 compliance theme. Adds schema
slots for the three sibling RCAN §21 registry ID types (RCN, RMN, RHN)
alongside the existing RRN, and surfaces them in the IFU and EU
register artifacts. Completes success criterion #5 from the v0.9
umbrella spec.

### Added

- **`metadata.rcn_ids[]`** — array of Robot Component Numbers
  (`RCN-[0-9]{12}`, unique). Identifies this robot's constituent
  components (sensors, actuators, SBC, etc.) as registered on RRF
  `/v2/components/`.
- **`metadata.rmn`** — single Robot Model Number (`RMN-[0-9]{12}`).
  Identifies the underlying platform model (reference SKU) from which
  this instance was built.
- **`metadata.rhn_ids[]`** — array of Robot Harness Numbers
  (`RHN-[0-9]{12}`, unique). Identifies tested harness/cabling
  configurations this robot conforms to.
- 10 new tests at `cli/tests/unit/test_schema_rcn_rmn_rhn.py` covering
  optional presence, pattern validation, prefix rejection, digit-count
  rejection, uniqueness, and co-existence of all three ID types.

### Emitted in

- **§24 IFU `provider_identity`**: adds `rcn_ids`, `rmn`, `rhn_ids`
  (empty when absent from manifest).
- **§26 EU register `system`**: adds the same three fields.

Registration POST body intentionally unchanged — RCN/RMN/RHN identify
entities registered via the separate RRF `/v2/{components,models,
harnesses}/` endpoints, not re-minted per robot.

### v0.9 compliance ✅ matrix

| Criterion | Status |
|---|---|
| Signed register (v0.9.1) | ✅ |
| FRIA gate (v0.9.2) | ✅ |
| `annex_iii_basis` enum (v0.9.0) | ✅ |
| §23–§26 CLI emitters (v0.9.3–v0.9.5) | ✅ |
| **RCN/RMN/RHN registry IDs** (v0.9.6) | ✅ |
| `rcan[pq,crypto]>=3.0` runtime dep (v0.9.1) | ✅ |
| `rcan_version` schema pin (v0.9.0) | ✅ |

All seven success criteria met. **v1.0.0** (the RCAN 3.0 compliance
declaration tag) is the next release — no new functionality, just the
declaration + CHANGELOG wrap.

---

## [0.9.5] — 2026-04-23

Sixth release in the v0.9 RCAN 3.0 compliance theme. Completes the §23–§26
external-artifact emission matrix with §26 EU Register submission
package emission per EU AI Act Art. 49.

### Added

- **`robot-md emit-eu-register MANIFEST --fria PATH [--opencastor-version VER] [--output OUT] [--sign]`**
  — build the Art. 49 submission package. Pulls provider identity
  (manufacturer, author), system identity (rrn, rrn_uri, robot_name,
  rcan_version), and the Annex III basis from the manifest. References
  the signed FRIA by basename (submit both files together to the EU AI
  database). `conformity_status` is hardcoded `"declared"` — the
  Art. 43 self-declared conformity path.
- **`robot_md.eu_register` module** — reusable `build_artifact` +
  `sign_artifact` + `EuRegisterError` sentinel. 11 TDD tests in
  `cli/tests/test_eu_register.py` covering every MUST field, every
  missing-prerequisite error, and the signed roundtrip.

### Validation gates (all raise `EuRegisterError`)

- `--fria PATH` must point at an existing file.
- `metadata.rrn` must be set (register the robot first).
- `compliance.annex_iii_basis` must be set (§26 applies to high-risk
  AI only — if not Annex III, this is the wrong artifact).
- `metadata.manufacturer` and `metadata.author` must both be set
  (provider identity is MUST per §26).

### Reused (no new primitives)

- `--sign` routes through v0.9.1 `signing.sign_body` like emit-benchmarks,
  emit-ifu, incidents report. Single signing scheme, five artifact types.

### Completes v0.9.x external-artifact matrix

| Artifact | Command | Shipped |
|---|---|---|
| §23 safety benchmark | `emit-benchmarks` | v0.9.3 |
| §24 IFU (Art. 13(3))  | `emit-ifu` | v0.9.4 |
| §25 incident record  | `incidents record` | v0.9.4 |
| §25 Art. 72 report   | `incidents report` | v0.9.4 |
| §26 EU register pkg  | `emit-eu-register` | v0.9.5 |

All signed via the same hybrid wire format introduced in v0.9.1.

### Out of scope

- `emit-fria` / FRIA document generation inside robot-md — the spec
  treats FRIA as external (operator-generated), and `--fria` takes an
  existing file by path. Out of v0.9.x entirely.
- Automated submission to the EU AI database — Art. 49 requires
  operator action, not CLI automation.

### Compliance status (delta from 0.9.4)

- §26 EU Register submission CLI: ✅ shipped (was ❌)

---

## [0.9.4] — 2026-04-22

Fifth release in the v0.9 RCAN 3.0 compliance theme. Adds emission of
two EU AI Act external artifacts: §24 Instructions for Use
(`rcan-ifu-v1`, Art. 13(3)) and §25 Post-Market Monitoring
(`rcan-incidents-v1`, Art. 72). Both can sign via the v0.9.1 hybrid
keypair — same wire format as register, emit-benchmarks, and future
§26 submissions.

### Added

- **`robot-md emit-ifu MANIFEST [--description TEXT] [--benchmark PATH] [--lifetime TEXT] [--output OUT] [--sign]`**
  — build the Art. 13(3) IFU artifact from a manifest. Fills all 8
  mandatory sections (provider_identity, intended_purpose,
  capabilities_and_limitations, accuracy_and_performance,
  human_oversight_measures, known_risks_and_misuse, expected_lifetime,
  maintenance_requirements). `--benchmark` embeds a v0.9.3 §23
  artifact's overall_pass + per-path p95 without copying full results.
- **`robot-md incidents record MANIFEST --severity {life_health|other} --category STR --description STR [--system-state JSON]`**
  — append an entry to the per-robot JSONL at
  `~/.robot-md/incidents/<rrn>.jsonl` (append-only, UUID v4 + ISO-8601
  timestamp stamped on write).
- **`robot-md incidents report MANIFEST [--output OUT] [--sign]`** —
  emit an `rcan-incidents-v1` Art. 72 report summarizing all logged
  incidents (total, by severity, reporting deadlines, art72_note, full
  list).
- **`robot_md.ifu` and `robot_md.incidents` modules** — reusable
  `build_artifact` / `build_report` + `sign_artifact`. 14 + 10 TDD
  tests respectively.

### Reused (no new primitives)

- `--sign` on IFU and incident-report artifacts routes through
  v0.9.1 `signing.sign_body`. Any verifier that accepts a v0.9.1
  register body accepts a v0.9.4 IFU or incident report. Single
  signing scheme ecosystem-wide.

### Out of scope this release

- Classification gate (refusing to emit IFU when `annex_iii_basis`
  unset) — v0.9.4.1 if operators want it.
- Submitting reports to a national authority — operator action per
  Art. 72, not CLI-automated.
- Incident retention/pruning policies.
- §26 EU Register submission pipeline (→ v0.9.5).

### Compliance status (delta from 0.9.3)

- §24 IFU emit CLI: ✅ shipped (was ❌)
- §25 PMM incident log + report: ✅ shipped (was ❌)

---

## [0.9.3] — 2026-04-22

Fourth release in the v0.9 RCAN 3.0 compliance theme. Adds the
`rcan-spec §23` Safety Benchmark Protocol emitter — robot-md's own
synthetic benchmark of its safety-critical paths, no hardware, no
castor dependency, optionally signed with the v0.9.1 hybrid keypair.

### Added

- **`robot-md emit-benchmarks MANIFEST [--iterations N] [--output OUT] [--sign]`**
  — run 4 synthetic benchmarks against robot-md's own safety code,
  emit a spec-conformant `rcan-safety-benchmark-v1` artifact.
  Path mapping: `estop` ← `EstopFlag.set/is_set/clear`;
  `bounds_check` ← `preconditions._check_one(workspace_declared)`;
  `confidence_gate` ← `preconditions._check_one(learned_skill_ok)`;
  `full_pipeline` ← `parse_file → validate → RobotSpec.from_parsed →
  preconditions.evaluate` end-to-end.
- **`robot_md.benchmarks` module** — reusable `build_artifact`,
  `run_estop`, `run_bounds_check`, `run_confidence_gate`,
  `run_full_pipeline`, `resolve_thresholds`, `sign_artifact`. 14 TDD
  tests in `cli/tests/test_benchmarks.py`.
- **Threshold resolution.** `estop` threshold is pulled from the
  manifest's `safety.estop.response_ms`; other three paths default to
  the §23 example values (5/2/50 ms).
- **`--sign` uses v0.9.1 signing.** After building the artifact, the
  canonical JSON is routed through `signing.sign_body` with the
  keypair at `~/.robot-md/keys/<rrn>.signing.json`. Output is
  wire-compatible with `signing.verify_body` — any verifier that
  accepts a v0.9.1-signed register body accepts a v0.9.3-signed
  benchmark artifact.

### Out of scope this release

- Live mode (connecting to a running robot / MCP subprocess).
- Uploading the artifact to RRF. `§26` EU Register submission (v0.9.5)
  will carry signed §23 artifacts as part of the conformity package.
- New schema slots inside `compliance` for benchmark references — the
  §23 artifact is an external object, not a ROBOT.md field, per the
  v0.9 umbrella spec's spec-authority principle.

### Compliance status (delta from 0.9.2)

- §23 Safety Benchmarks emit CLI: ✅ shipped (was ❌)
- Signed external artifact production: ✅ first (register/patch wire
  format reused verbatim — one signing scheme ecosystem-wide).

---

## [0.9.2] — 2026-04-22

Third release in the v0.9 RCAN 3.0 compliance theme. **FRIA enforcement**
per rcan-spec §22: declaring `compliance.annex_iii_basis` now commits the
operator to a Fundamental Rights Impact Assessment, so
`compliance.fria_ref` MUST be a non-null URI. Enforced via JSON Schema
conditional in `robot-md validate`.

### Added

- **Schema `if/then` FRIA gate** in `compliance.allOf`: when
  `annex_iii_basis` is present, `fria_ref` is required AND must match
  `{ type: string, pattern: "^[a-zA-Z][a-zA-Z0-9+.-]*:.+" }` — an RFC 3986
  absolute-URI scheme prefix. Rejects missing, null, empty-string, and
  scheme-less values. A regex pattern is used instead of `format: uri`
  so the gate works on jsonschema installs without the optional
  `rfc3987` extra (the default CI environment).

### Changed (BREAKING)

- **`robot-md validate` now enforces `format` annotations** via
  `jsonschema.Draft202012Validator.FORMAT_CHECKER`. Draft 2020-12 treats
  `format` as annotation-only by default, so this was a no-op before
  v0.9.2; now any schema field declared `format: uri` is actually
  validated (affects `rrf_endpoint`, `compliance.fria_ref`, and the
  `$id` URI self-reference). Existing shipped manifests were already
  URI-valid, so no migration is expected.
- Any manifest that declared `annex_iii_basis` without a matching
  non-null URI `fria_ref` will now fail validation. v0.9.0-v0.9.1
  accepted this combination (spec-strict slot without gating).

### Compliance status (delta from 0.9.1)

- `compliance.annex_iii_basis` + `fria_ref` gate: ✅ enforced (was ❌)
- Everything else unchanged from 0.9.1.

---

## [0.9.1] — 2026-04-22

Second release in the v0.9 RCAN 3.0 compliance theme. **Mandatory hybrid
signing** — every `robot-md register` POST is now signed with ML-DSA-65
+ Ed25519. Pairs with `RobotRegistryFoundation@1.8.0` (deployed
2026-04-22), which rejects unsigned registrations per RCAN 3.0 §2.2. See
`docs/superpowers/specs/2026-04-22-v0.9.1-hybrid-signing-design.md`.

### Added

- **`robot_md.signing` module.** `generate_keypair`, `save_keypair`,
  `load_keypair`, `sign_body`, `verify_body`, `canonical_json`. Wraps
  `rcan.crypto` (ML-DSA-65 via `dilithium-py`) + `cryptography` (Ed25519).
  Keystore at `~/.robot-md/keys/<rrn>.signing.json` (mode 600, dir 700,
  atomic tmp-then-rename writes).
- **`robot_md.ruri` module.** `construct_ruri(manifest)` builds the
  spec-mandated `rcan://<host>/<manufacturer>/<model>/<robot_name>` URI
  (defaulting host to `robotregistryfoundation.org`) when
  `metadata.ruri` is absent.
- **`auto_mint_if_needed` + `patch_rrf` in `robot_md.register`.** RRF
  records that exist with an apikey but no signing key (legacy /
  pre-v0.9.1) are transparently upgraded via signed PATCH on first
  contact. Wired into `cli_unregister`.

### Changed (BREAKING)

- **`robot-md register` always signs.** No `--skip-sign` opt-out; per
  RCAN 3.0 §2.2 unsigned registration is no longer permitted by the
  reference RRF. Each register: generates a per-RRN hybrid keypair,
  constructs the RURI if absent, signs the canonical MintRequest body
  (`{...fields, pq_signing_pub, pq_kid}`), POSTs to RRF, persists
  keypair + apikey on success.
- **Already-registered manifests now error (rc=2).** Running register
  on a manifest with `metadata.rrn` already set is rejected — key
  rotation is out of scope for v0.9.1 (a later release).
- **`cli_register` signature.** Drops dead kwargs `version`,
  `device_id`, `description`, `contact_email`, `source` (none did
  anything in 0.9.0); adds `--firmware-version`, `--rcan-version`,
  `--name`. The `__main__.py register` typer command updated to match.
- **`rcan` extras bumped to `rcan[pq,crypto]>=3.0,<4.0`.** Pulls
  `dilithium-py>=1.0` and `cryptography>=42.0` as runtime deps so users
  don't need an extras install.

### Fixed

- `cli/tests/test_register.py` rewritten — was module-skipped in
  `c07e8b4` (v0.9.0) pending the API update. Now 13 tests covering
  `_extract_mint_fields`, `MintRequest.as_body()`, signed POST flow,
  keypair/apikey persistence, already-registered guard, `post_to_rrf`,
  and the auto-mint PATCH path.
- `examples/bob.ROBOT.md` cleared stale `RRN-000000000003` (never in
  prod KV) so fresh clones can register without the new error path.

### Compliance status (delta from 0.9.0)

- Signing: ✅ mandatory (was ❌)
- Everything else unchanged from 0.9.0.

---

## [0.9.0] — 2026-04-21

First release in the v0.9 RCAN 3.0 compliance theme. See
`docs/superpowers/specs/2026-04-21-v0.9-rcan-3-compliance-design.md`.
Spec-strict and additive — no enforcement, no signing yet.

### Added

- **`rcan>=3.0,<4.0` runtime dependency.** Unlocks SDK primitives
  (`rcan.crypto` hybrid signing, `rcan.manifest.from_manifest`, version
  constants) for v0.9.1+ work. Not used at runtime in v0.9.0; import-only.
  rcan-py 3.0.0 published to PyPI 2026-04-21 from
  `continuonai/rcan-py@v3.0.0`.
- **`compliance.annex_iii_basis` enum** per rcan-spec §22 — EU AI Act
  Annex III use-case basis (10 values: `safety_component`, `biometric`,
  `critical_infrastructure`, `education`, `employment`, `essential_services`,
  `law_enforcement`, `migration`, `administration_of_justice`,
  `general_purpose_ai`). Optional in v0.9.0; FRIA gating (require
  `fria_ref` when set) lands in v0.9.2.

### Compliance status

- `compliance.annex_iii_basis` slot: ✅ present (optional)
- `compliance.fria_ref`: ✅ present (optional; gated on `annex_iii_basis` in v0.9.2)
- Signing: ❌ not yet (v0.9.1)
- §23 Safety Benchmarks emit CLI: ❌ not yet (v0.9.3)
- §24 IFU / §25 PMM emit CLI: ❌ not yet (v0.9.4)
- §26 EU Register submission: ❌ not yet (v0.9.5)
- RCN/RMN/RHN registry IDs: ❌ not yet (v0.9.6)

---

## [0.8.0] — 2026-04-20

### Added — MCP observability

- **`recent_invocations` MCP resource** — `robot-md://<robot>/recent_invocations` returns the last ≤100 completed tool invocations (newest-first) for this manifest. Each entry: `{timestamp, tool, capability, args, status, reason, request_id, manifest_path, preconditions}`. Backed by an in-memory ring on `McpContext` that's backfilled at boot from `~/.robot-md/events.jsonl`.
- **`recent_errors` MCP resource** — `robot-md://<robot>/recent_errors` returns the same shape filtered to `status != "ok"`. Answers "why did my last pick fail?" without shelling out.
- **Structured precondition failures.** Every `_check_one` branch in `preconditions.evaluate` now returns a `PreconditionFailure(kind, name, message, suggested_fix)`. `suggested_fix` carries an actionable verb hint where one exists (e.g., `robot-md calibrate --extrinsic`) or `null` where remediation requires judgement. MCP clients append the ROBOT.md path when running the hint.
- **`discover` streaming.** The tool now accepts a FastMCP `Context` and emits one MCP progress notification per step via `await ctx.report_progress(i, total, step_name)`. Dashboard substrate also receives `discover.step.begin` / `discover.step.end` events so long `discover` sweeps (multi-second arm motion) report per-step instead of blocking silently.

### Changed (breaking)

- **`execute_capability` error payload for `reason: "precondition"` changes shape.** Old: `{reason, failed: list[str]}`. New: `{reason, preconditions: list[dict]}` where each entry is `{kind, name, message, suggested_fix}`. MCP clients parsing the old `failed` field must read `error.preconditions` instead and render `preconditions[*].message` + `preconditions[*].suggested_fix`.
- **`robot_md.preconditions.evaluate(...)` return type** changes from `(bool, list[str])` to `(bool, list[PreconditionFailure])`. Direct callers must adapt; the MCP error payload surface is the more common consumer.
- **`robot_md.mcp.tools.discover.discover_tool` is now an async function.** FastMCP handles async tool functions natively; external MCP clients see no wire-format change. Direct callers of `discover_tool` outside the FastMCP binding must `await` it.

### Fixed

- **`execute_capability` observability.** Previously, `no_backend` failures returned early before publishing `tool.call`/`tool.result`, leaving no record in the InvocationLog or `events.jsonl`. Now every invocation (including `no_backend`) flows through the publisher so the ring and backfill path capture it.
- **`_publish_result` forwards the `error` field.** Previously stripped the `error` key from the `tool.result` event payload, so both the live fan-out path and the JSONL backfill path landed records with `reason=null` regardless of actual failure. Fixed so `InvocationRecord.from_event_pair` can populate `reason` and `preconditions`.

### Added (experimental — not wired)

- **`calibrate_extrinsic.capture_via_wrist_wiggle(bus, camera, kin, pose)`** — attempted gripper-isolation primitive. At each target pose, captures `depth_A`, shifts *only* `wrist_flex` by ±0.15 rad, captures `depth_B`, returns the motion-delta centroid. Unit-tested; kept in the module for future use. **Not wired into `phase_calibrate_extrinsic`** — on-rig validation showed the OAK-D depth noise floor exceeds the wiggle signal: zero-commanded-motion `find_via_motion_delta` returned confidence 1.0 with 7,655 "arrived" pixels (>60mm frame-to-frame variation). The ~18mm tip motion from a 0.15-rad wiggle cannot rise above that floor. The v0.7.3 pose-to-pose motion-delta remains the primary detector because its whole-arm transit motion is large enough to out-vote the noise.

### Known limitation (from v0.7.3)

- **v0.7.3 residual ceiling unchanged at ~128mm on physical SO-ARM101+OAK-D.** The real fix requires either temporal denoising of depth frames before the delta, or a non-motion-based primitive (3D shape match against known gripper geometry, or colored-fiducial HSV detection). Tracked for a future milestone.

### Internal

- `robot_md.mcp.invocation_record.InvocationRecord` — immutable record coalesced from paired `tool.call` / `tool.result` events (request_id keyed).
- `robot_md.mcp.invocation_log.InvocationLog` — per-`McpContext` ring buffer (maxlen=100, thread-safe, backfilled from JSONL at boot).
- `McpContext.publisher` is wrapped by `_PublisherFanoutWrapper` at `load_context` time — stamps `manifest_path` into every event and appends paired invocations to the ring. All existing `ctx.publisher.publish(...)` call sites are unchanged.

---

## [0.7.3] — 2026-04-20

### Added — extrinsic-free bootstrap for calibration

- **`gripper_silhouette.find_via_motion_delta(depth_prev, depth_curr, K)`.** Primary detector for `phase_calibrate_extrinsic`; locates the arm in `depth_curr` by comparing to `depth_prev` using a signed-delta filter — pixels where depth got meaningfully closer are the "arm arrived here" cluster. No projection through any extrinsic, so the 570-pixel bootstrap gap that killed v0.7.0–.2 on non-canonical camera mounts is gone. Solver absorbs any consistent bias from the centroid not being exactly the gripper tip.

### Changed

- **`phase_calibrate_extrinsic` uses motion-delta first, projection as fallback.** First pose is captured only as a baseline for the delta comparison; remaining poses produce samples via motion-delta. When motion-delta confidence is below 0.2 (e.g., arm didn't actually move between poses because IK happened to produce nearly-equal configs), the phase falls back to the v0.7.x projection-based `find_in_depth` search. Confidence threshold loosened from 0.3 to 0.2 to accommodate the slightly noisier motion-delta observations.

### Known issues (resolved from v0.7.0–.2)

- **Bootstrap cliff — CLOSED.** The issue that blocked real-hardware calibration (see CHANGELOG [0.7.1] known issues) is fixed by this release.

### Compatibility

- v0.7.2 manifests validate and load unchanged. No schema changes.

---

## [0.7.2] — 2026-04-20

### Fixed — stereo-hole survival in HSV + vision.find

- **`_depth_mask` now accepts unknown-depth pixels (value 0).** Stereo depth sensors produce holes on textureless or highly reflective surfaces; painted LEGOs and matte tabletops are common offenders. Previously `detect_hsv(..., depth_frame=depth)` with workspace-derived bounds rejected every hole pixel, turning a clean color match into `no_match` because the joint (color ∧ depth) mask was empty. The mask now includes both in-range AND unknown-depth pixels, leaving real depth rejection to the resolve step.
- **`vision_find` patch-median filters to the workspace depth band.** When the centroid pixel has zero depth and a 30m ceiling is visible through the stereo hole, the raw patch median locked onto the ceiling (30 000 mm), producing camera-frame XYZ that was geometrically nonsense. The patch is now filtered to pixels inside the declared workspace depth band before median, so the reported depth is the target's tabletop neighbors (~400 mm) rather than the far background.

Together these two fixes unblock `vision.find("red_lego")` on physical OAK-D + tabletop LEGO setups where the LEGO surface itself produces no depth measurement.

### Known issues (carried from v0.7.0)

- Bootstrap-extrinsic cliff in `phase_calibrate_extrinsic` is unchanged — still tracked for v0.8 (motion-delta or fiducial-assisted bootstrap). Workaround documented in v0.7.1 changelog entry still applies.

### Compatibility

- v0.7.1 manifests validate and load unchanged. No schema changes. Both fixes are backward-compatible behavior improvements.

---

## [0.7.1] — 2026-04-20

### Fixed

- **`Perception.open()` missing from production calibration flows.** `Perception.from_spec()` constructs a lazy object whose DepthAI pipeline is only started by `open()`. The `calibrate --extrinsic` CLI path and the `default_flow` init hardware-open block both forgot to call it, so `grab_frame()` returned `None` on every sweep pose and `find_in_depth` had no data to match against. Unit + integration tests used `MagicMock` cameras so the gap didn't surface until the first real hardware run. Fix adds `cam.open()` after `from_spec()` and `cam.close()` on cleanup in both production paths and the two opt-in hardware tests.

### Known issues (carried from v0.7.0)

- **Bootstrap-extrinsic cliff.** `phase_calibrate_extrinsic` projects `tip_base` through the current (preset-default) extrinsic to seed `find_in_depth`'s pixel-space search window. On physical camera mounts that differ significantly from the canonical `(400, 0, 300) → (200, 0, 0)` tripod assumed by the preset, the seed pixel is hundreds of pixels away from the actual gripper and no `search_radius_mm` closes the gap. For rigs in this state the calibration sweep returns `failed: only 0/n poses produced usable observations`. Workaround: write the extrinsic manually into `physics.solver.cameras[0].extrinsic` and set `extrinsic_source: user_declared`. A proper bootstrap (motion-delta or fiducial-assisted) is scoped for v0.8 — see `docs/superpowers/specs/2026-04-20-v0.8-v0.9-roadmap.md`.

### Compatibility

- v0.7.0 manifests validate and load unchanged. No schema changes.

---

## [0.7.0] — 2026-04-20

### Added

- **Gripper-silhouette extrinsic calibration.** `robot-md calibrate --extrinsic ROBOT.md` runs a 6-pose sweep that uses the gripper itself as the fiducial — no printed ArUco marker, no hand-measured `--marker-pos`. Residual (mm) is reported and persisted to `physics.solver.cameras[0].extrinsic_residual_mm`. New `extrinsic_source: gripper_silhouette_calibrated` enum value.
- **`init` runs extrinsic calibration as an opt-in phase.** Interactive TTY runs of `robot-md init` open the bus + camera and prompt `"Calibrate camera-to-arm alignment now?"` after the auto-calibrate-ready phase. Non-interactive runs skip cleanly; doctor warns on uncalibrated extrinsics.
- **Depth-aware HSV detectors.** HSV descriptors now accept optional `min_depth_mm` / `max_depth_mm`; when unset, bounds are auto-derived from `physics.workspace.bounds_mm` projected (Z-depth) into camera frame via the current extrinsic. Fixes `white_bowl` matching walls at 8m. Opt out per descriptor with `ignore_workspace_bounds: true`.
- **`detectors/depth.py`.** Depth-first bowl detector — color-free. Registered as `kind: depth_shape`. Params: `shape`, `min_diameter_mm`, `max_diameter_mm`, `z_range_mm`.
- **Three-layer servo-latch defense.**
  - **Pre-flight.** `Kinematics.analyze_envelope()` rejects trajectories that would hold a joint above 85% of its envelope for more than ~500ms — the exact failure mode observed on the SO-ARM101 wrist_flex during v0.6.3 hardware bring-up. `plan_pick` / `plan_place` take a `hold_ms` kwarg and invoke the analyzer.
  - **Runtime.** `motion.verify_alive()` reads bus enumeration after every motion; a dropped servo id triggers immediate torque-off of the remaining servos and a structured `{status: error, reason: servo_latched}` response. Wired into `_do_replay`, `_arm_home`, `_arm_pick`, `_arm_place`.
  - **Post-hoc.** `robot-md doctor --hardware` enumerates servos + probes RGB/depth streams; flags missing ids and missing streams. Auto-enabled when `/dev/ttyACM*` is present; `on`/`off` override available.
- **Preset-scoring tie-break.** `match.drivers.count` (already-declared schema field, previously unused) now contributes +5 when the scan's servo count matches. New `match.negative_hints` field subtracts 5 when any listed word appears in a device label. `pick_best` breaks remaining ties alphabetically by preset name. Resolves the `so_arm101` vs `so_arm101_leader` ambiguity.
- **Schema additions.** `physics.solver.cameras[].extrinsic_source` now accepts `gripper_silhouette_calibrated`. New optional `physics.solver.cameras[].extrinsic_residual_mm` field.

### Changed

- `robot-md calibrate --hand-eye` → `--extrinsic`. The old flag still works this cycle but emits a deprecation warning and routes to the new code path. Removed in v0.8.
- **Behavior:** HSV detectors now apply workspace-bounds depth filter by default. Descriptors whose valid targets sit outside the workspace must opt out via `ignore_workspace_bounds: true` or widen `physics.workspace.bounds_mm`. Doctor warns when the new filter plausibly broke a descriptor.
- `trajectory.plan_pick` / `plan_place` now take `hold_ms: int = 1000` and call `analyze_envelope` at the grasp/place pose. Out-of-envelope trajectories raise `KinematicsError`; the backend dispatcher classifies the error as `envelope_risk` (latch warning), `joint_limit` (hard limit), or `ik_failed`.

### Removed

- `cli/src/robot_md/hand_eye.py` and its ArUco / `cv2.calibrateHandEye` path.
- `opencv-contrib-python` from `[project.optional-dependencies].vision` (base `opencv-python` stays; `depthai` may still transitively install contrib).

### Compatibility

- v0.6.3 manifests validate and load unchanged. All new schema fields are additive and optional.
- Extrinsic calibrated via v0.6.x (`extrinsic_source: hand_eye_calibrated`) is still accepted by all consumers; only new calibrations produce `gripper_silhouette_calibrated`.
- **Migration for existing descriptors with out-of-workspace valid matches:** add `ignore_workspace_bounds: true` to the descriptor, or widen `physics.workspace.bounds_mm`. Doctor warns when the new filter plausibly broke a descriptor.

### Known issues

- `default_flow` opens the bus + camera synchronously when `stdin.isatty()` is true; there is no settle-delay between `bus.interpolate(...)` and `camera.grab_frame(...)` during the sweep, which may produce motion-blurred captures on rigs with slow servos. Track for v0.7.1. Mitigation: the sweep tolerates per-pose failures and aborts cleanly if more than 2 of 6 poses fail to locate the gripper.
- `mcp/resources.py::calibration_status` still exports the legacy `hand_eye` key name for backward compatibility with existing MCP clients. Will be renamed to `extrinsic` in v0.8 (with a back-compat alias for one release).

---

## [0.6.3] — 2026-04-20

### Fixed — hardware bring-up lessons

First hardware bring-up of the v0.6.2 pipeline on a real SO-ARM101 + OAK-D exposed five bugs. All shipped here; `arm.home` now actually moves the arm and holds it.

- **`Perception._spec` stash.** `Perception.from_spec` plucked only `driver_id` from the spec and dropped the reference, so direct callers of `Perception.vision_find(descriptor=...)` got `{'status': 'error', 'reason': 'no_spec'}`. Arm.pick worked through a different code path; debugging calls and non-backend callers broke. `from_spec` now keeps the full spec; `_vision_xyz_cam` also passes it explicitly.
- **Single-waypoint motion.** `motion.replay` for a single-waypoint trajectory was firing a one-shot goal write and returning immediately. Callers (`_do_replay`, `_execute_pick_or_place`) then dropped torque in a `finally` block before STS3215 servos crossed their deltas — net: arm.home reported ok but the arm barely moved. Single-waypoint path now interpolates from the current read-back position, and the existing multi-waypoint path guards `estop=None` so direct Python callers don't crash.
- **Torque-hold after successful motion.** Capability dispatch previously dropped torque unconditionally in a `finally` block, so the arm went limp after every `arm.home` / `arm.pick`. Torque now stays on after a successful motion — the arm holds the final pose. Callers that want limp (teach-mode, shutdown) drop torque explicitly.
- **IK joint-limit enforcement.** `Kinematics.ik_reach` solved for gripper-pointing-down but didn't check the solved angles against each joint's declared `limits_rad`. On SO-ARM101, the tabletop target `(200, 0, 50)` produced `wrist_flex = 94.7°` — beyond the ±90° envelope. The servo stalled, tripped into overload protection, and stopped responding on the bus. `ik_reach` now raises `KinematicsError` with a specific reason when any solved angle is out of envelope.
- **SO-ARM101 preset ships a safe `ready` pose.** Even within the ±90° limit, ik_reach puts wrist_flex near 80° for most tabletop targets — sustained gravity load at that angle trips the STS3215. The preset now ships `physics.poses.ready` with all joints near center (gripper forward, wrist neutral); `phase_auto_calibrate_ready` sees it and skips IK. Arm.pick still solves gripper-down geometry at motion time, transiently — the problem was only holding that pose indefinitely.

### Changed

- `auto_calibrate.compute_ready_pose` default target moved from `(200, 0, 50)` to `(200, 0, 20)` so fallback IK on presets without a declared `ready` stays within ±90° envelopes.
- Schema reminder: `physics.poses.<name>.source` accepts `declared | taught | solved_from_dh` — the preset's ready pose now uses `declared`.

### Compatibility

- v0.6.2 manifests validate and load unchanged. Re-init against the so-arm101 preset to pick up the safe `ready` pose, or copy the `physics.poses.ready` block from `presets/so_arm101.yaml` into an existing manifest by hand.

---

## [0.6.2] — 2026-04-20

### Fixed

- **Preset default extrinsic rotation.** The `so-arm101` preset shipped in v0.6.1 with a 6-vec whose rotation pointed the camera +z axis up-and-back (into the ceiling) instead of at the workspace. Replaced with the result of `from_mount(position=(400, 0, 300), look_at=(200, 0, 0))` — camera +z now points at the workspace center, so typical tabletop detections map to reachable grasp targets in the base frame.
- **Dependency pin for `typer<0.17`.** typer 0.17+ defines `TyperChoice(click.Choice[ParamTypeValue])`, which requires `click.Choice` to be subscriptable. click 8.x (shipped on Python 3.13) does not support that; the subscription raises `TypeError` at import time, tripping pytest collection for anything that imports typer. Pinned to the last 0.16.x line until click 9 is widespread.
- **`CliRunner.stderr` access.** `test_init_non_interactive` used `hasattr(result, "stderr")` which is True on click 8.x Result, but accessing the property raises when stderr wasn't separately captured. Switched to `result.stderr_bytes` directly.

### Changed

- Site hero + §05 demo updated to reflect the v0.6.1 auto-calibrate + `arm.pick` story; the hero's phase [5/5] no longer prompts "teach `ready` pose" (it's auto-solved), and §05 shows the full `arm.pick` → `arm.place` phase decomposition.

### Compatibility

- v0.6.1 manifests validate and load unchanged. If you want the corrected extrinsic for an existing manifest, re-init against the preset or overwrite `physics.solver.cameras[0].extrinsic` by hand with `[400, 0, 300, -2.5536, 0, 1.5708]`.

---

## [0.6.1] — 2026-04-20

### Added

- **Auto-calibrate ready pose.** `robot-md init` on SO-ARM101 now solves a canonical `ready` pose from DH params via the in-house IK solver and writes it to `physics.poses.ready` automatically — no `pose teach` step required. Opt out with the internal `do_auto_calibrate=False` flag.
- **Default camera extrinsic.** `so-arm101` preset ships a default 6-vec extrinsic for the canonical OAK-D-on-tripod mount. Tracked via the new `physics.solver.cameras[].extrinsic_source: preset_default` field.
- **`arm.pick(target)` end-to-end.** The stub is replaced with a real pipeline: `target` (descriptor ID) → `vision.find` → `camera_to_base` → workspace bounds check → `ik_reach` → hybrid trajectory (joint-space approach, cartesian descent, grasp, lift) → `motion.replay`. Same shape for `arm.place(target)`.
- **Hand-eye calibration (opt-in).** `robot-md calibrate --hand-eye ROBOT.md --marker-pos x,y,z` drives an 8-pose ArUco sweep and writes a refined extrinsic, flipping `extrinsic_source` to `hand_eye_calibrated`. Uses `cv2.calibrateHandEye` (Tsai).
- **Doctor warning for preset-default extrinsic.** `robot-md doctor` now warns (not errors) when extrinsic is still a preset guess, pointing users at the hand-eye verb.
- **Capability contracts for arm.pick / arm.place / arm.home.** so-arm101 preset declares preconditions (`pose_taught:ready`, `extrinsic_present`, `ik_provider_set`, `workspace_declared`, `backend_resolved`) that the v0.6.0 evaluator enforces.
- **Workspace bounds on the so-arm101 preset.** `physics.workspace.bounds_mm` declares the reachable envelope so arm.pick can refuse targets outside it before motion.
- **Pure extrinsic math module (`robot_md.extrinsic`).** `six_vec_to_matrix`, `matrix_to_six_vec`, `camera_to_base`, `from_mount`. XYZ extrinsic Euler convention.
- **Trajectory planner (`robot_md.trajectory`).** `plan_pick` / `plan_place` return ordered `Waypoint(phase, joints, settle_ms)` lists with cartesian linear descent.
- **OAK-D driver declared on the so-arm101 preset** (`drivers[].id=oakd, protocol=depthai`) so the camera driver_id cross-reference validates.

### Changed

- `physics.solver.ik_provider` set to `inhouse-so-arm101` on the so-arm101 preset (activates the in-house 3-link planar IK solver already present since v0.5.0).
- Feetech backend's `_arm_pick` / `_arm_place` no longer replay hardcoded waypoints; both are target-driven through the new trajectory planner.
- `hand_eye.py` replaces the v0.5.0 single-shot PnP path with the AX=XB sweep; `write_extrinsic` now writes to `physics.solver.cameras[0].extrinsic` (plural) with provenance tracking.

### Compatibility

- v0.6.0 manifests validate and load unchanged.
- Manually-taught `physics.poses.ready` from v0.6.0 is preserved during re-init (auto-calibrate is idempotent when `ready` already exists).

### Known issues

- The preset-default extrinsic's rotation is a geometric placeholder — it validates and passes all unit tests but does not match a realistic "camera looking down at tabletop" orientation. Users who need accuracy beyond the LEGO-scale tolerance should run `robot-md calibrate --hand-eye`. The doctor warning points at this.

---

## [0.6.0] — 2026-04-19

### Added — closes the Claude-triad gap spec §1–§10

- **`physics.poses`** in manifest + `robot-md pose teach <name> <path>` CLI verb. `arm.home` backend capability now targets `physics.poses.ready` when present (gap §1).
- **`capability_contracts`** with six precondition kinds (`pose_taught`, `extrinsic_present`, `ik_provider_set`, `workspace_declared`, `learned_skill_ok`, `backend_resolved`). `execute_capability` gates on them; read-only caps bypass (§3 / §10).
- **`vision.object_descriptors`** (`hsv` + `hsv_roi` detectors) and the `vision.find` MCP tool — descriptor id → camera-frame XYZ (§6).
- **`learned_skills`** top-level array + MCP `record_skill` tool + three new MCP resources (`robot-md://<name>/{learned_skills, calibration_status, poses}`, all `application/json`) (§7).
- **`discover`** MCP tool — declarative `capture` + `detect` + `probe_direction` pipeline (§8).
- **`physics.workspace`** bounds with per-axis mm ranges (§2).
- **`physics.solver.ik_provider`** + **`ik_frame`** schema fields (§5).
- **`publish-discovery`** now emits `calibration_status` + `learned_skills_summary` — Mobile operators see real status without MCP (§9).
- Generated **`CLAUDE.md`** renders new "Named poses" and "Known skills & blockers" sections.
- **so-arm101 preset** ships `red_lego` + `white_bowl` object descriptors out of the box.
- Init phase `teach_poses` offers to record `ready` on TTY.

### Changed

- `calibration_status` resource now actually inspects `physics.kinematics[].zero_pose_steps` instead of unconditionally reporting `"ok"`.
- Backend `detect_objects(descriptors=…)` routes through `robot_md.detectors.hsv` instead of returning `[]`.
- `execute_capability` precondition gate runs AFTER estop (estop always wins); read-only capabilities bypass both gates.

### Compatibility

All new fields are optional. v0.5.0 manifests validate and run unchanged. v0.6.0 deprecates the stowaway `extensions.x-learned-skills` pattern in favor of the top-level `learned_skills:` block.

---

## v0.5.0 — 2026-04-19

### Added
- `robot-md init` default flow now folds MCP install, skill install, and
  zero/sign calibration into the single command. TTY + hardware detection
  gates the interactive phases; headless / CI callers auto-skip cleanly.
- New flags: `--non-interactive` (scripted callers — manifest-only),
  `--no-install-mcp`, `--no-install-skill`, `--no-sign`, `--no-calibrate`.
- New module `robot_md.install_mcp_claude_code` — subprocess wrapper around
  `claude mcp add` that returns a `PhaseResult` rather than raising.
- New package `robot_md.init_phases` — each phase of init is an independently
  callable library function returning a uniform `PhaseResult`.

### Changed
- `robot_md.init.quick` renamed to `non_interactive`; `quick` kept as a
  deprecated alias that prints a one-time note to stderr.
- `robot-md init --wizard` now an alias for the default flow (the two paths
  are identical). Emits a one-time deprecation note.
- Generated `CLAUDE.md` template now advertises all six MCP tools
  (`validate`, `render`, `estop`, `estop_clear`, `execute_capability`,
  `execute_task`) and points the motion row at `execute_capability`.

### Migration
- Scripted callers relying on `robot-md init` being non-interactive must
  add `--non-interactive`. On CI machines this is the recommended invocation.
- External code importing `robot_md.init.quick` should switch to
  `non_interactive`. The old name still works but warns on each call.

---

## [0.4.1] - 2026-04-18

Dev ergonomics release. Live local dashboard + two safety patches from the v0.4.0 E2E smoke findings.

### Added

- **Dev dashboard** (`robot-md dashboard serve`): local FastAPI+HTMX page on
  `http://127.0.0.1:8091` showing live servo positions, last OAK-D frame,
  tool-call log, estop state, and validator warnings. Localhost-only, no auth.
- **JSONL event log** at `~/.robot-md/events.jsonl` — durable record of every
  MCP tool call + state change, written non-blockingly by an in-server
  `EventPublisher`. Rotates at 10 MB. Backs future `robot-md replay` and the
  v0.8 memory-sync feature.
- **Command channel** at `~/.robot-md/commands.jsonl` — dashboard writes,
  MCP server reads, mutates state. Commands supported: `estop.set`,
  `estop.clear`, `snapshot`.
- **`estop_clear` MCP tool** (fixes #2). HITL-gated on the `system` scope by
  default; pass a `confirm_token` to clear when the gate is declared.

### Fixed

- **#1 — read-only capabilities no longer blocked by estop.** `status.report`
  and `vision.describe` execute even when the estop flag is set. New
  `CapabilityBackend.read_only_capabilities: frozenset[str]` declares which
  capabilities skip the gate; the `feetech_depthai` backend declares those
  two. Motion-producing capabilities are unaffected.

### Added dependencies

- `fastapi>=0.110`, `jinja2>=3.1`, `websockets>=12` (base deps)
- `pytest-asyncio>=0.23` (dev extra)

### Opt-out

- Set `ROBOT_MD_DASHBOARD_DISABLED=1` to disable the publisher + command
  watcher if the MCP server runs in a constrained environment (e.g., a
  container without a writable home).

---

## [0.4.0] - 2026-04-18

Phase 1 of the adaptive backend plan (spec:
`docs/superpowers/specs/2026-04-18-feetech-depthai-real-backend-design.md`).
The `feetech_depthai` backend goes from stubs to real hardware drivers.

### Added

- **Real STS3215 wire protocol** in `backends/feetech_depthai/servo.py` —
  ports the proven code from `examples/tier0/01..04`. ServoBus supports
  `open/close`, `read_positions` (skips non-responders), `write_positions`,
  `torque(on/off)`, and `interpolate(start, target, hz, max_steps_per_tick,
  estop)` with per-tick E-stop checks.
- **Real OAK-D pipeline** in `backends/feetech_depthai/perception.py` —
  ports `examples/tier0/05_scene_snapshot.py`. Reads factory intrinsics,
  builds an RGB + stereo-depth pipeline aligned to RGB, exposes
  `grab_frame() → (rgb, depth, K)`. 3D back-projection helper `_pixel_to_3d`.
- **Trajectory replay** in `backends/feetech_depthai/motion.py` — iterates
  consecutive waypoint pairs, calling `ServoBus.interpolate` between them.
  Single-waypoint trajectories dispatch as one-shot position commands.
- **Real capability handlers** for `arm.pick`, `arm.place`, `arm.reach`,
  `vision.describe`, `status.report`. `arm.pick` / `arm.place` replay a
  hardcoded first-demo trajectory (small joint deltas around zero pose) —
  swapped for skill-store lookup in Phase 2.
- **Hardware smoke tests** (`--run-hardware`) for servo read + nudge and
  OAK-D frame capture.

### Added dependency

- `feetech-servo-sdk>=1.0` joins the `feetech-depthai` optional extra.
  Install with `pip install robot-md[feetech-depthai]`.

### Scope note

`arm.pick`/`arm.place` in v0.4.0 replay a hardcoded trajectory embedded in
the capability handler. Real grasps arrive in v0.5.0 (Phase 2 — skill store).
Perception is opened but not yet consulted during motion (Phase 3);
pose-adjust and hand-eye are Phase 4. See the spec for the full rollout.

---

## [0.3.1] - 2026-04-18

Follow-up patches from the v0.3.0 final review.

### Changed

- **Safety ordering.** `execute_capability_tool` now checks the
  process-wide E-stop before evaluating the HITL gate. E-stop is a
  hard-stop signal that should outrank any consent workflow; this
  matches the spec's intent and eliminates a theoretical race where a
  gate satisfied between estop-set and dispatch could slip through.
- **`RobotSpec.MetadataBlock`** gains a `device_id: str | None` field.
  Backends that want to log or report a robot's per-unit identity no
  longer need to re-parse `raw_yaml`.
- **Documented token semantics.** `_gate_satisfied`'s docstring now
  states plainly that v0.3's `confirm_token` is an opaque stub — not
  verified, not single-use, not scope-bound. Cryptographic tokens
  land in v0.4 per the original spec's out-of-scope list.

### Removed

- **Dead `probe_cameras()` in `autodetect.py`.** Replaced by the typed
  `probe_depthai_cameras` / `probe_realsense_cameras` /
  `probe_v4l2_cameras` probes in v0.3.0; the legacy function was left
  defined but uncallable. Gone now.

### Docs

- **`docs/mcp-server-options.md`** — side-by-side comparison of the
  npm TypeScript MCP and the Python MCP, with registration snippets
  for each. README points at it.

---

## [0.3.0] - 2026-04-18

Camera intrinsics, Python MCP server (as an alternative to the TypeScript
npm `robot-md-mcp`), and pluggable backends. Both MCP implementations
coexist — users pick whichever fits their install story; tools are
protocol-compatible.

### Added

- **Camera intrinsics in schema.** Per-stream `intrinsic` block on
  `drivers[].streams[]` (fx/fy/cx/cy/width/height + distortion model).
  `physics.solver.cameras[]` cross-references `drivers[].id` and carries
  deployment-specific mount + extrinsic. Autodetected from factory
  calibration at `robot-md init` for OAK-D (depthai), RealSense stub,
  and v4l2 (emits `null` intrinsic + provenance note).
- **Python MCP server** shipped as `robot-md-mcp` entry point. New
  tools: `estop` (process-wide software E-stop), `execute_capability`
  (deterministic primitive with HITL gate enforcement),
  `execute_task` (natural-language prompt → planner → capability
  sequence via `brain.planning` declared in the manifest).
- **Pluggable `CapabilityBackend`** interface. Backends register via
  Python entry points under `robot_md.backends`; resolution is
  alphabetical by backend name, with optional `drivers[].backend`
  override. Reference `feetech_depthai` backend ships in-repo
  (install with `pip install robot-md[feetech-depthai]`).
- **`robot-md calibrate-intrinsic`** — session-file-driven checkerboard
  calibration CLI. Init generates a printable 9×6 checkerboard PNG;
  `--frame` captures advance coverage; `--finalize` solves via OpenCV
  and writes the intrinsic block back into ROBOT.md.
- **`integrations/claude-code-skill/intrinsic-calibration.md`** — guided
  wizard skill that drives the CLI through its stable JSON session
  protocol.
- **`robot-md mcp <path>`** convenience subcommand (same as running
  `robot-md-mcp <path>` directly).

### Changed

- **Validator** gains a `warnings` list. Null intrinsic on a
  `primary_stream` surfaces as a warning (with a pointer to
  `robot-md calibrate-intrinsic`); legacy singular
  `physics.solver.camera` emits a deprecation warning after being
  auto-upgraded at parse time.
- **Presets** migrated to the `cameras[]` shape. ALOHA 2 now declares
  four cameras with matching driver entries; arm-only presets
  (SO-ARM101, UR5e, Franka, Koch) no longer bundle a camera block.

### Deprecated

- `physics.solver.camera` (singular) — still auto-upgraded at read
  time; validator emits a deprecation warning. Removed in v2.

### Notes

- The TypeScript npm `robot-md-mcp` continues to be maintained in
  parallel (current: v0.2.1+). The new Python MCP server is an
  alternative install path, not a replacement. Both speak the same
  tool protocol for `render` and `validate`; `estop`,
  `execute_capability`, and `execute_task` are Python-only for now.

### Added dependencies

- `mcp>=1.0` — MCP SDK (required; server over stdio)
- `anthropic>=0.30` — for `execute_task` with `provider: anthropic`
- Optional extra `robot-md[feetech-depthai]`: `pyserial`, `depthai`,
  `opencv-python`, `numpy`

---

## [0.2.7] - 2026-04-18

Claude Desktop + Claude Mobile support lands. Every surface Anthropic
ships now has a documented, tested install path.

### Added

- **`robot-md install-desktop ROBOT.md`** — merges a `robot-md` entry
  into the OS-appropriate `claude_desktop_config.json` (macOS:
  `~/Library/Application Support/Claude/`, Windows: `%APPDATA%/Claude/`,
  Linux best-effort: `~/.config/Claude/`). Preserves any existing
  `mcpServers` entries. Idempotent re-run. `--force` overrides a
  conflicting existing entry. Claude Desktop launches `npx -y
  robot-md-mcp <absolute path>` on startup via stdio.
- **`integrations/claude-desktop/README.md`** — full install + verify
  + troubleshooting flow. Replaces the outdated "when v0.2 lands"
  draft.
- **`integrations/claude-mobile/README.md`** — URL-fetch pattern.
  Host `ROBOT.md` + `.well-known/robot-md.json` at any public HTTPS
  URL; paste URL into Claude Mobile; Claude fetches + reasons over
  capabilities/safety. The CLAUDE.md auto-generated by init makes the
  safety posture explicit, so mobile operators get the gate-check
  logic without needing `/check-safety` the tool.

### Changed

- **README Claude-integration table** now reflects shipped reality
  instead of "v0.2 coming soon." Every row is ✅ shipped with a
  concrete one-command install.

---

## [0.2.6] - 2026-04-18

### Changed

- **Refreshed bundled `using-robot-md` skill** to reference the MCP
  prompts (slash commands) that ship in `robot-md-mcp` v0.2.1+:
  `/brief-me`, `/check-safety action=<text>`, `/explain-capability
  capability=<name>`, `/manifest-status`. The skill now tells Claude:
  when an operator's intent matches a slash command, mention the
  command exists so the operator can invoke it explicitly next time.
  Upgrade via `pip install --upgrade robot-md && robot-md install-skill --force`.

---

## [0.2.5] - 2026-04-18

Zero-touch agent-path release. Install robot-md → run init → Claude
Code recognizes the robot. No separate commands to learn.

### Added

- **`robot-md init --with-claude-md` (default: on)** — after writing
  `ROBOT.md`, init now also generates a `CLAUDE.md` next to it. Uses
  the same sentinel-wrapped append/update-in-place merge logic from
  0.2.4, so an existing `CLAUDE.md` with operator notes is preserved.
  Opt out with `--no-claude-md`.
- **`robot-md install-skill`** — copies the bundled `using-robot-md`
  skill into `~/.claude/skills/using-robot-md/SKILL.md` (or a custom
  `--dest`). For operators running [superpowers](https://github.com/obra/superpowers)
  or any skill-aware harness, this wires the "Claude auto-invokes
  robot-md when you mention the robot" behavior in one command. Pass
  `--stdout` to preview.
- **Skill bundled in the wheel** at `robot_md/skills/using-robot-md.SKILL.md`.
  Single source of truth: the dev-tree copy at
  `integrations/claude-code-skill/SKILL.md` is kept in sync.

### One-command agent path

The installed + recognized flow is now:

    pip install robot-md && \\
        robot-md init my-bob --preset so-arm101 --register --contact-email me@co.com && \\
        robot-md install-skill && \\
        claude mcp add robot-md -- npx -y robot-md-mcp "$(pwd)/ROBOT.md"

After that, Claude Code routes robot-related questions through the
manifest automatically — no operator mention of robot-md needed.

---

## [0.2.4] - 2026-04-18

### Changed

- **`robot-md claude-md` now preserves existing `CLAUDE.md` content.**
  Old behavior was to refuse writing unless `--force` was passed, which
  destroyed any operator-authored notes. New behavior:
    - File does not exist → write it (with sentinel comments around
      the robot-md block).
    - File exists, has our sentinels → **update the delimited block in
      place.** Operator content above AND below the block is preserved.
    - File exists, no sentinels → **append our block at the end** (with
      sentinels). Operator's original content stays at the top.
    - `--force` → overwrite the entire file (unchanged).
  The sentinel markers are `<!-- BEGIN robot-md ... -->` /
  `<!-- END robot-md -->`; re-running the command multiple times is
  idempotent (file size stabilizes, exactly one delimited region).

---

## [0.2.3] - 2026-04-17

Agent-affordances release — ships tooling explicitly designed for
Claude Code (and any CLAUDE.md-aware agent harness) to recognize when
to dispatch robot-md verbs. Two new verbs, one new discovery standard,
all focused on "let Claude figure out what the operator wants."

### Added

- **`robot-md claude-md ROBOT.md`** — generates a `CLAUDE.md` file
  tailored to a specific robot. The template declares which operator
  intents should trigger which `robot-md` verb (diagnose →
  `doctor`, manifest queries → MCP resources, motion → check HITL
  gates first). Pre-fills robot name, RRN, declared gates, primary
  driver, public resolver. Drop it next to `ROBOT.md` and Claude Code
  reads it at session start.
- **`robot-md publish-discovery ROBOT.md --url <URL>`** — emits a
  `.well-known/robot-md.json` document so MCP clients, crawlers, and
  federated registries can locate a manifest without prior
  configuration. Includes sha256 digest of the served file + derived
  public resolver URL.
- **Spec §6.1** documents the `.well-known/robot-md.json` discovery
  standard.
- **`integrations/claude-code/CLAUDE.md.template`** — canonical
  template consumed by `robot-md claude-md` (and usable directly by
  operators who want to craft their own).

### Note

v0.2.2's CHANGELOG mentioned `publish-discovery`, but the verb
actually shipped after the v0.2.2 tag was cut (commit `8a990e1`).
`pip install robot-md==0.2.2` gets the older code without the verb.
0.2.3 is the first release where `publish-discovery` and
`publish-discovery`-related spec text are both in the package.

---

## [0.2.2] - 2026-04-17

"Proceed with all recommendations" release. Adds a diagnostic verb, five
new presets, a Claude-Code-native onboarding path, and clear labeling of
the terminal vs. in-session on-ramps.

### Added

- **`robot-md doctor`** — diagnostic verb. Runs five buckets of checks
  (install, manifest, network, drivers, keystore) and prints a rich
  table. `--json` for CI, `--strict` to exit non-zero on warnings.
  Read-only: never writes files, never touches servo state.
- **Five new presets**: `franka-panda` (7-DoF Franka FCI arm),
  `ur5e` (6-DoF Universal Robots cobot), `koch-arm` (5+1-DoF LeRobot
  teleop rig, Dynamixel), `aloha2` (bimanual 12-DoF ViperX-300s),
  `unitree-go2` (12-DoF quadruped via Unitree SDK 2). All ship with
  realistic DH params + driver blocks; operators calibrate from there.
- **`docs/getting-started-claude-code.md`** — onboarding walkthrough
  for operators who want Claude Code itself to run the setup. Paste
  one English sentence; Claude uses its `Bash` tool to run the same
  one-liner as the terminal path and wires up MCP afterwards.
- **Two-path getting-started section** in the README and the website.
  The one-liner is now explicitly labeled "▶ On your machine
  (terminal)" and a parallel "▶ Inside Claude Code" card shows the
  prompt-driven flow. SessionStart hook becomes Option C.

### Fixed

- **`bob.ROBOT.md`** `network.rrf_endpoint` was pointing at
  `robotregistryfoundation.org` (the governance site). Updated to
  `https://rcan.dev` so `robot-md doctor` against the example
  resolves correctly.

---

## [0.2.1] - 2026-04-18

One-command-complete-setup release. Patch-bump to land three audit-driven
fixes that turned the v0.2.0 register flow from "4 commands + manual edit
afterwards" into a genuine single-command experience.

### Fixed

- **Register endpoint URL drift** (silent failure in v0.2.0). The CLI
  default was `https://robotregistryfoundation.org/api/v1/robots` — but
  the live registry service runs at `https://rcan.dev/api/v1/robots`
  (the foundation's governance home is at robotregistryfoundation.org;
  the service is hosted separately on rcan.dev). Anyone who ran
  `robot-md register` in v0.2.0 got an HTML response from the marketing
  site back, not a minted RRN. Now points at `rcan.dev`.
- **Manifest/RRF metadata drift.** When `init --register` was called
  with CLI overrides (`--manufacturer`, `--model`, etc.), the override
  was sent to RRF's mint endpoint but the *manifest on disk* kept the
  preset defaults — silently creating a ROBOT.md whose identity fields
  didn't match the RRF entry. Now overrides land in the manifest before
  register runs, so the two stay self-consistent.
- **Preset-generated manifests missing required mint fields.** `preset:
  so-arm101` previously left `metadata.manufacturer/model/version/
  device_id` empty, so `--register` would fail with "missing required
  mint fields" until the operator hand-edited the file. Now the preset
  seeds defaults: manufacturer=device_id=robot_name, model=preset_name,
  version="1.0". Operator overrides win.

### Added

- **`robot-md init --register [--contact-email ... --manufacturer ...
  --model ... --version- ... --device-id ...]`** — one-command complete
  setup. Validates + POSTs to rcan.dev + updates the manifest with the
  assigned RRN + prints the `claude mcp add` line. No other commands
  needed. No OpenCastor. Live-verified end-to-end: `RRN-000000000006`
  minted, manifest + RRF entry consistent, MCP server streams the 4
  resources cleanly. (Test entry cleaned up via new `unregister` verb.)
- **`robot-md unregister <RRN> [--api-key PATH]`** — DELETEs an RRF
  entry using the issued API key (reads from
  `~/.robot-md/keys/<rrn>.apikey` by default). Removes the local key
  file after a successful delete. Does not touch local ROBOT.md files.

### Examples updated

- `examples/bob.ROBOT.md` now reflects the live Bob entry on rcan.dev:
  RRN-000000000003 (minted 2026-04-15), manufacturer=craigm26,
  model=opencastor-rpi5-hailo-soarm101, version=1.0, device_id=bob-001.
  Verify live: https://rcan.dev/r/RRN-000000000003

## [0.2.0] - 2026-04-18

Big release. `robot-md` goes from "validator for a file format" to
"operator toolkit" — one command takes a new user from plugged-in
hardware to a manifest Claude Code can ingest, with physical calibration
and RRF identity minted in the loop.

### Added

- **`robot-md init [NAME] [--preset NAME] [--wizard]`** — super-duper-quick
  zero-to-ROBOT.md. Default mode emits a validated draft in one shot by
  matching a preset from the built-in library; `--wizard` opens a 7-step
  interactive flow for custom hardware. `--list-presets` prints the
  library.
- **Preset library** at `cli/src/robot_md/presets/` — 5 shipped:
  `so_arm101`, `so_arm101_leader`, `turtlebot4`, `picar_x`, `minimal`.
  YAML (not code) so community preset PRs stay low-friction.
- **`robot-md calibrate --zero`** — operator poses arm in declared zero
  configuration, CLI reads every joint's Present Position, rewrites
  `physics.kinematics[].zero_pose_steps` in place (ruamel.yaml
  preserves comments).
- **`robot-md calibrate --sign`** — per-joint test move, operator
  confirms direction, `encoder_sign` written.
- **`robot-md calibrate --hand-eye --marker-pos X,Y,Z`** — ArUco +
  `cv2.solvePnP` camera-to-arm-base extrinsic. Writes
  `physics.solver.camera.extrinsic` as `[tx, ty, tz, rx, ry, rz]` (mm +
  Rodrigues radians). OAK-D intrinsics pulled via
  `depthai.Device.readCalibration()` — no external calibration file.
- **`robot-md register`** — POSTs manifest metadata to RRF's mint
  endpoint (`https://robotregistryfoundation.org/api/v1/robots`). Writes
  the assigned RRN back into `metadata.rrn`, stores the one-time API
  key at `~/.robot-md/keys/<rrn>.apikey` (mode 600). `--dry-run` and
  `--endpoint` override supported.
- **`robot-md autodetect --bus feetech:<port>[:<baud>]`** — Tier B
  servo-bus scan. Pings IDs 1..253 (3 retries × 20 ms); reads min/max
  angle limits + present position; emits a populated
  `physics.kinematics[]` block with `joint_<N>` placeholders.
- **Baseline `Kinematics` module** (`robot_md.kinematics`) — reads
  `physics.solver` + `physics.kinematics[]` and provides FK / 3-link
  planar IK / encoder-step ↔ joint-angle conversions. Any planner with
  just a validated ROBOT.md can reach a pose from the manifest alone —
  no URDF, no MoveIt.
- **v1.1 schema additions**:
  - `physics.solver.{convention, base_frame, encoder, camera, gripper}`.
  - Per-joint `servo_id`, `encoder_sign`, `zero_pose_steps`, `a_mm`,
    `d_mm` (DH params).
  - All backwards-compatible: 0.1.x manifests validate unchanged.
- **Tier A autodetect polish**:
  - `DRIVER_PROFILES` table — autodetect now pre-fills
    `drivers[].baud_rate` from protocol (Feetech bus → 1 Mbps etc.).
  - `probe_cameras()` — OAK-D via DepthAI + v4l2-ctl enumeration.
    Emits a `cameras:` block when real cameras are found; filters Pi
    ISP plumbing (bcm2835-isp/codec, pispbe, rpi-hevc-dec).
- **RCAN 3.0+ + RRF-aware generated manifests.** `init` writes a
  default `network` block with `rrf_endpoint`,
  `signing_alg: ml-dsa-65`, `transports: [http]`.
- **Spec `autodetect-prefill-roadmap.md`** maps which fields are
  auto-fillable at what tier (host scan / bus scan / preset) and where
  operator walk-through takes over.

### Changed

- `examples/bob.ROBOT.md` carries the full solver block + DH params +
  `/dev/ttyACM0` port + `tip_offset_mm: [30, 0, 0]`.
- Core deps: `ruamel.yaml>=0.18`, `numpy>=1.24`. New optional extras:
  `feetech` (servo SDK) and `vision` (opencv-contrib-python + depthai).
- CLI help output rewritten with examples for every new command.

### Fixed

- Schema-sync CI gate — canonical, CLI-bundled, and site-served
  `robot.schema.json` copies must all match.

### Tests

Suite grows 59 → 127 passing. New test files: `test_kinematics.py`,
`test_calibrate.py`, `test_autodetect_tier_a.py`, `test_bus_scan.py`,
`test_init.py`, `test_register.py`, `test_hand_eye.py`.

## [0.1.3] - 2026-04-17

### Added

- **Autodetect hardware DB expansion.** Eight additional device families,
  each tagged with provenance in-source and covered by synthetic-fixture
  tests:
  - **Cameras:** Intel RealSense D435i, D455, L515; Stereolabs ZED 2.
  - **MCUs:** Arduino Uno R1/R3, Arduino Mega 2560, Arduino Leonardo,
    Raspberry Pi RP2040 (including BOOTSEL), PJRC Teensy.
  - **Motor control:** ODrive V3 BLDC controller.
- Introduces two new device roles in the autodetect schema: `mcu` and
  `motor-controller`. Existing `npu`, `camera`, `serial-bus`, and
  `serial-port` roles unchanged.

### Internal

- Test suite expanded from 13 → 17 autodetect cases; total CLI suite now
  59 tests.

## [0.1.2] - 2026-04-17

### Added

- **`robot-md autodetect`** — scan visible hardware and emit a draft
  `ROBOT.md`. Detects Hailo-8 / Hailo-10H (PCI), Intel Movidius NCS 1/2 (USB),
  Luxonis OAK-D (USB), Google Coral USB Accelerator (USB), Intel RealSense
  D435 (USB), and common USB-serial bridges (CH340, CH341, CP210x, FTDI
  FT232R). Also probes `/dev/ttyACM*` / `/dev/ttyUSB*` and common
  robot-stack tools (`claude`, `opencastor`, `castor`, `rcan-validate`,
  `hailortcli`, `i2cdetect`). Linux-only in this release.
  - Default emits draft to stdout. `--write PATH` writes to a file and
    refuses to overwrite.
  - Emitted draft uses `"CHANGE-ME"` / `"other"` placeholders for identity
    fields and schema-validates — but will not claim to know actuator count
    or physics type without operator review.
  - Hardware DB lives in `robot_md/autodetect.py` with VID:PID provenance
    comments on every entry. PRs to extend it are welcome.
- **v0.2 design document** at `spec/v0.2-design.md` (published at
  `robotmd.dev/spec/v0.2-design.md`): signing, registry ingestion, and
  tamper-evidence plan. Design-only; no code. Evaluates blockchain
  options and recommends centralized D1 baseline for v0.2 (cheapest,
  simplest) with Merkle transparency log as a documented v0.3+ upgrade
  path. §13 collects four Decision Required items gating implementation.

### Changed

- README: added v0.2 design link to Spec + docs. Removed broken
  proposal link (outreach materials live in the private repo).

## [0.1.1] - 2026-04-17

### Fixed

- **`robot-md validate` could not find the JSON schema when installed as a wheel.** `validate.py` computed `_SCHEMA_PATH` relative to `__file__` using a four-level `parent` walk that only resolved correctly in the source tree — once `pip install`'d, the path pointed outside `site-packages` and every `validate` call raised `FileNotFoundError`. Fixed by bundling `schema/v1/robot.schema.json` as a package resource under `robot_md/schemas/v1/` and loading it via `importlib.resources.files()`. Canonical schema source remains `schema/v1/robot.schema.json` at the repo root; `scripts/sync-schema.sh` keeps the bundled copy in sync.
- **`robotmd.dev/schema/v1/robot.schema.json` was serving the landing page HTML** instead of the schema (same for `/examples/*`, `/hook`, and `/spec/v1`). Cloudflare Pages SPA-falls-back to `index.html` for missing paths, making the 404 invisible. Added the canonical assets under `site/` so Pages deploys them, with `Content-Type` rules in `_headers` so the schema serves as `application/schema+json`, examples and spec as `text/markdown`, and `/hook` as `text/x-shellscript`. All gain `Access-Control-Allow-Origin: *` for cross-origin validators.

### Security

- Tightened schema bounds on physical-safety fields so manifests claiming absurd values (unbounded velocity, 10-tonne payloads, 10-second E-stop response) are rejected at validation. Full hardened bounds in `SECURITY.md`. Existing examples (Bob, SO-ARM101, minimal, TurtleBot 4) all still validate.
- Added new optional declarative fields: `safety.workspace_bounds_m` (spatial envelope) and `safety.failsafe_behavior` (`stop` / `hold` / `home` / `custom` — planner's mandated behavior on comms loss).
- Added **"Known v0.1 Limitations"** section to `SECURITY.md` documenting gaps in physical safety (manifest is declarative, not enforcing), digital security (no signing yet — planned v0.2), and registry integration (no RRF-side manifest ingestion yet — planned v0.2). Includes the Tier 0 threat model: **"trusted operator + trusted planner"** only; do not expose a Tier 0 robot to untrusted prompts without a gateway layer.

### Changed

- Repo migrated to the **Robot Registry Foundation** GitHub org (`github.com/RobotRegistryFoundation/robot-md`). Old URL 301-redirects indefinitely. Cloudflare Pages secrets + the `production` and `pypi` GitHub environments were preserved through the transfer; no downstream action required from consumers.
- Dogfood `ROBOT.md` `metadata.manufacturer` updated from `craigm26` to `RobotRegistryFoundation` to match the new steward.

## [0.1.0] - 2026-04-17

### Added

Initial v0.1 release.

- `ROBOT.md` format specification (`spec/robot-md-v1.md`)
- JSON Schema for the frontmatter block (`schema/v1/robot.schema.json`)
- Python CLI `robot-md` with subcommands:
  - `robot-md validate PATH` — schema + RCAN 3.0 conformance check
  - `robot-md render PATH` — strip prose, emit pure YAML
  - `robot-md context PATH` — emit Claude-ready text block
- Four worked examples: `bob.ROBOT.md`, `minimal.ROBOT.md`, `so-arm101.ROBOT.md`, `turtlebot4.ROBOT.md`
- Claude Code SessionStart hook (`integrations/claude-code/session-start.sh`)
- Documented MCP + URL-bridge approaches for Claude Desktop and Mobile
- Draft Anthropic adoption proposal

### Not yet

- `robot-md register` (RRF integration) — planned for v0.2
- Working MCP server for Claude Desktop — planned for v0.2
- URL bridge Cloudflare Worker for Claude Mobile — planned for v0.2
- TypeScript port (`@robotmd/spec`) — planned for v0.2

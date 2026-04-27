# SP2 — Init Autodetect → Preset/Backend with Confidence

**Date:** 2026-04-26
**Status:** Design — pending implementation plan
**Sub-project:** 2 of 5 (see `2026-04-26-sp1-wire-python-mcp-server-design.md` for SP1)

> **REVISION 2026-04-27:** Several sections superseded by `2026-04-27-sp1-5-simplification-revisions.md` — Revisions 2 and 6 specifically apply to SP2. Notably: silent auto-pick on MEDIUM tier (no prompt unless `--explain`); manifest schema gets only `backend:` field, not both `backend` + `preferred_backend` (the hint stays preset-internal).

## Problem

`robot-md init` already runs `autodetect.scan_system()` (PCI/USB/tty/cameras/runtime probes) and scores 16 presets via `match_score()` heuristics. But it then silently picks the top scorer via `pick_best()` and writes the manifest with no operator visibility into:

- **How confident** the match was (was it a clear winner or a 15-15 tie?)
- **What alternatives** existed (operator never sees the match table)
- **Which backend** will drive each declared protocol (runtime resolves at call time, manifest doesn't pre-fill `backend:`)
- **Which cameras** were detected and where they end up in the manifest (autodetect probes them but their landing in `physics.cameras[]` is unclear)

For bob's hardware (SO-ARM101 + OAK-D), `so_arm101.yaml` and `so_arm101_leader.yaml` tie at score 15. Today the deterministic name-tiebreaker silently picks `so_arm101` even though the leader/follower distinction is a real choice. The operator only finds out by reading the manifest. SP2 surfaces this kind of ambiguity at init time, makes the backend resolution visible in the manifest, and pre-fills cameras correctly.

## Scope

**In scope:**
- A. Confidence tiering (HIGH/MEDIUM/LOW) on top score + runner-up gap.
- B. Interactive confirmation in guided init when tier is MEDIUM.
- C. Backend pre-fill in manifest via `preferred_backend` hint + registry resolution.
- D. Camera autodetect → manifest with preset overrides per `driver_id`.
- E. Operator-friendly explanation of what was matched and why.
- F. Minimal-manifest + TODO markers when tier is LOW.

**Out of scope** (handled by other sub-projects):
- New autodetect probes (current DepthAI/RealSense/V4L2 coverage is enough).
- Backend implementations (SP3 covers manufacturer-SDK adapters).
- Interactive driver-author flow when no backend matches detected hardware (SP4).
- Gap → GitHub issue feedback loop (SP5).

## Design

### Architecture

Five components, all in `robot-md/cli/`:

1. **`cli/src/robot_md/init.py`** — Extend `MatchResult` with a `tier` field. Add `classify_tier(top, runner_up)`. Replace `pick_best()`'s silent top-pick with `select_preset(scan, *, interactive)` that branches HIGH/MEDIUM/LOW.
2. **`cli/src/robot_md/presets/*.yaml`** (×16) — Add `drivers[].preferred_backend` per driver. Add optional `cameras:` section to known-kit presets (e.g., `so_arm101.yaml` + OAK-D defaults).
3. **`cli/src/robot_md/init_phases/write_manifest.py`** — Compose manifest with resolved backends + camera merge logic.
4. **`cli/src/robot_md/backends/registry.py`** — Add `try_resolve(protocol, preferred_backend) -> str | None` for init-time resolution that doesn't import backend code.
5. **`cli/src/robot_md/schemas/robot.schema.json`** (+ TS sync) — Schema additions for `drivers[].backend`, `drivers[].preferred_backend`, `physics.cameras[].extrinsic_source` enum.

**Out of scope for architecture:**
- New autodetect probes.
- Backend implementations (SP3).
- Driver-author flow (SP4).

**Design principles preserved:**
- Pre-fill is opt-in per tier.
- Never silently guess Tier D fields — emit TODO markers.
- Presets are YAML, not code.

**Backward compatibility:** Existing manifests without `drivers[].backend` still validate (new field is optional). Existing `--non-interactive` callers map to `--yes` semantics.

### Components

#### 1. `init.py` — tier classification + `select_preset`

```python
def classify_tier(top: int, runner_up: int) -> Literal["HIGH", "MEDIUM", "LOW"]:
    if top >= 10 and (top - runner_up) >= 5:
        return "HIGH"
    if top >= 5:
        return "MEDIUM"
    return "LOW"


def select_preset(
    presets: list[Preset],
    scan: Scan,
    *,
    interactive: bool = True,
    show_top_n: int = 3,
) -> tuple[Preset | None, str, list[MatchResult]]:
    """Returns (chosen_preset, tier, all_scored).

    chosen_preset is None only when tier == "LOW" — caller writes a
    minimal manifest with TODO markers.
    """
    scored = sorted(
        (match_score(p, scan) for p in presets),
        key=lambda r: (-r.score, r.preset.name),
    )
    if not scored:
        return None, "LOW", []

    top = scored[0].score
    runner_up = scored[1].score if len(scored) > 1 else 0
    tier = classify_tier(top, runner_up)

    if tier == "LOW":
        return None, "LOW", scored
    if tier == "HIGH":
        return scored[0].preset, "HIGH", scored
    if interactive:
        return _prompt_pick(scored[:show_top_n]), "MEDIUM", scored
    print(
        f"warning: MEDIUM-confidence preset match "
        f"({scored[0].preset.name} score={top}, "
        f"runner-up={scored[1].preset.name if len(scored)>1 else 'none'} "
        f"score={runner_up}). Review manifest before motion.",
        file=sys.stderr,
    )
    return scored[0].preset, "MEDIUM", scored
```

`_prompt_pick` uses `rich.prompt.IntPrompt` (existing dep) — numbered list with score + reasons, default `1`.

`pick_best()` becomes a compat wrapper: `select_preset(presets, scan, interactive=False)[0]`. Marked deprecated, kept for tests/CLI callers.

#### 2. Preset YAML schema additions

Per-driver hint and optional cameras. Example diff for `so_arm101.yaml`:

```yaml
drivers:
  - id: arm_servos
    protocol: feetech
    preferred_backend: feetech_depthai   # NEW
    port: /dev/ttyACM0
    baud_rate: 1000000
    model: STS3215
    count: 6

cameras:                                  # NEW (optional, only for known-kit presets)
  - driver_id: vision
    mount: world
    primary_stream: rgb
    extrinsic: [457.0, 0.0, 0.0, -1.5708, 0.0, 1.5708]
    extrinsic_source: preset_default
```

Generic-platform presets (`franka_panda.yaml`, `ur5e.yaml`) get `preferred_backend` only; no `cameras:` section.

`minimal.yaml` stays unchanged — no `preferred_backend`, no `cameras:`. LOW-tier path doesn't touch it.

#### 3. `init_phases/write_manifest.py` — composition

New signature (additive args, defaults preserve existing call sites):

```python
def phase_write_manifest(
    out_path: Path,
    *,
    preset: Preset | None,
    scan: Scan,
    tier: str,
    backend_resolutions: dict[str, str | None],   # driver_id → resolved backend name
    overrides: dict[str, Any] | None = None,
) -> PhaseResult:
    ...
```

Composition rules:

- **drivers[]**: start from preset's `drivers[]` (or autodetect's `_drivers_from_devices` if no preset). For each driver, fill `backend:` from `backend_resolutions[driver.id]` if not None.
- **physics.cameras[]**:
  1. Start with autodetect's `Scan.cameras[]` → emit a baseline entry per detected camera (`mount: world`, `primary_stream` picked from streams, extrinsic zero placeholder, `extrinsic_source: autodetect_default`).
  2. If `preset.cameras` is set, override per-camera matched by `driver_id`: copy preset fields, set `extrinsic_source: preset_default`.
  3. Cameras autodetect found but the preset doesn't override stay as `autodetect_default`. Cameras the preset declares but autodetect didn't find are **not** written.
- **Tier marker**: stamp top-of-file YAML comment: `# preset: so_arm101 (tier=HIGH, score=18)` or `# preset: minimal (tier=LOW, no autodetect match)`. Outside frontmatter; survives round-trips.
- **TODO markers** (LOW tier only): emit explicit `# TODO: ...` comments on `metadata.manufacturer`, `physics.dof`, `drivers[]` if scan returned nothing useful.

#### 4. `backends/registry.py` — `try_resolve` for init time

Init time can't import backends — they may need hardware deps not yet installed.

```python
def try_resolve(
    protocol: str,
    preferred_backend: str | None = None,
) -> str | None:
    """Init-time backend resolution. Returns a backend NAME, not an instance.

    Order:
      1. If preferred_backend is registered as an entry-point name, return it.
      2. If preferred_backend is set but not registered, return it anyway
         (manifest pre-fills the hint; runtime resolves later if pkg installed).
      3. If neither, scan entry-points for the first protocol match (alphabetical).
      4. Return None if nothing matches.

    Does NOT instantiate the backend (avoids importing hardware SDKs at init).
    """
```

Init runs `try_resolve` for each preset driver, builds `backend_resolutions: {driver_id: name_or_None}`, hands to `write_manifest`. Operators without motion extras still get the manifest pre-filled with the hint name — runtime resolves on first call.

#### 5. Schema updates — `schemas/robot.schema.json` (+ TS sync)

```json
"drivers": {
  "items": {
    "properties": {
      "backend": {
        "type": "string",
        "description": "Resolved backend name (entry-point or preset hint). Optional; runtime falls back to protocol-only resolution if absent."
      },
      "preferred_backend": {
        "type": "string",
        "description": "Hint from preset: which backend implementation is recommended for this driver. Used by `robot-md init`; not consulted at runtime."
      }
    }
  }
},
"physics": {
  "properties": {
    "cameras": {
      "items": {
        "properties": {
          "extrinsic_source": {
            "type": "string",
            "enum": ["preset_default", "autodetect_default", "user_declared", "hand_eye_calibrated"],
            "description": "Provenance of the extrinsic pose. user_declared/hand_eye_calibrated mean the operator owns it; defaults are starting points."
          }
        }
      }
    }
  }
}
```

Run `scripts/sync-schema.mjs` to mirror into rcan-spec / rcan-ts.

**Schema validation note:** the `extrinsic_source` enum is additive (existing `user_declared` value stays valid). New values don't break existing manifests.

### Data Flow

#### Path: HIGH-tier, guided mode

```
Operator                                State
─────────────────────────────────────────────────────────────────
$ robot-md init stretch3-rig       →    Autodetect runs:
                                          devices: hello-robot Stretch3 (USB)
                                                   feetech bus on /dev/ttyACM0
                                          cameras: RealSense D435 (USB)
                                          hostname: stretch3-rig

                                        Score:
                                          stretch3.yaml:    18 (proto+count+usb+hostname)
                                          minimal.yaml:      0
                                          gap = 18, top ≥ 10 → HIGH

                                        select_preset returns (stretch3, "HIGH").

                                        write_manifest composes:
                                          drivers[]:
                                            - id: arm_servos
                                              protocol: feetech
                                              preferred_backend: feetech_depthai
                                              backend: feetech_depthai      ← try_resolve
                                          physics.cameras[]:
                                            - driver_id: vision
                                              extrinsic_source: preset_default
                                              extrinsic: [...preset values...]

                                        Output:
                                          ✓ Wrote ROBOT.md
                                          Matched preset stretch3 (tier=HIGH, score=18,
                                            +protocol +count +usb +hostname).
                                          Override with --preset.
```

No prompts. One closing confirmation line.

#### Path: HIGH-tier, --yes mode

Identical to guided HIGH — no prompts in either mode at this tier.

#### Path: MEDIUM-tier, guided mode (bob's case)

```
Operator                                State
─────────────────────────────────────────────────────────────────
$ robot-md init bob                →    Autodetect runs:
                                          devices: feetech bus on /dev/ttyACM0 (6 servos)
                                          cameras: Luxonis OAK-D (USB)
                                          hostname: bob

                                        Score:
                                          so_arm101.yaml:        15 (proto+count)
                                          so_arm101_leader.yaml: 15 (proto+count)
                                          koch_arm.yaml:         10 (proto only)
                                          minimal.yaml:           0
                                          top=15, runner_up=15, gap=0 → MEDIUM

                                        select_preset prompts:

                                          Multiple presets matched (MEDIUM confidence):

                                          [1] so_arm101         score=15  +protocol +count
                                          [2] so_arm101_leader  score=15  +protocol +count
                                          [3] koch_arm          score=10  +protocol

                                          Pick [1]: ▌

> 1                                 →   select_preset returns (so_arm101, "MEDIUM").

                                        write_manifest composes (same fields as HIGH).

                                        Output:
                                          ✓ Wrote ROBOT.md
                                          Matched preset so_arm101 (tier=MEDIUM, score=15,
                                            +protocol +count). Operator-confirmed.
                                          Override with --preset.
```

#### Path: MEDIUM-tier, --yes mode

```
Operator                                State
─────────────────────────────────────────────────────────────────
$ robot-md init bob --yes          →    (same scoring as guided MEDIUM)

                                        select_preset returns (so_arm101, "MEDIUM").
                                        Stderr: warning: MEDIUM-confidence preset match
                                          (so_arm101 score=15, runner-up=so_arm101_leader
                                          score=15). Review manifest before motion.

                                        Output (stdout):
                                          ✓ Wrote ROBOT.md
                                          Matched preset so_arm101 (tier=MEDIUM, score=15,
                                            +protocol +count, --yes auto-picked).
                                          Override with --preset.
```

Auto-picks deterministic top, warns to stderr (visible to humans, parseable by CI).

#### Path: LOW-tier, guided mode

```
Operator                                State
─────────────────────────────────────────────────────────────────
$ robot-md init prototype          →    Autodetect runs (bare RPi5, no robot):
                                          devices: (none useful)
                                          cameras: (none)

                                        Score: all presets = 0 → LOW

                                        select_preset returns (None, "LOW").

                                        write_manifest emits minimal manifest:
                                          # preset: minimal (tier=LOW, no autodetect match)
                                          ---
                                          metadata:
                                            robot_name: prototype
                                            manufacturer: # TODO: declare manufacturer
                                          physics:
                                            type: # TODO: arm | nav | composite | ...
                                            dof: # TODO: integer DOF
                                          drivers: []     # TODO: declare driver(s)
                                          capabilities: []
                                          safety:
                                            estop:
                                              software: true
                                              response_ms: 50

                                        Output:
                                          ✓ Wrote ROBOT.md (minimal, LOW tier)
                                          No specific preset matched (top score=0).
                                          Wrote minimal manifest with 4 TODO markers.
                                          Run `robot-md autodetect` to see what was probed.
                                          Run `robot-md doctor ROBOT.md` to see what's missing.
```

#### Path: LOW-tier, --yes mode

Identical to LOW guided — no prompt at this tier in either mode.

#### State summary

| Mode | HIGH | MEDIUM | LOW |
|---|---|---|---|
| Guided | Silent prefill + closing line | Prompt top-3 | Minimal + TODOs + advisory |
| `--yes` | Silent prefill + closing line | Auto-pick top + warning to stderr | Minimal + TODOs + advisory |
| Manifest passes `validate` immediately? | Yes | Yes | No (TODOs are placeholders) |

LOW-tier manifests deliberately fail `validate` — TODO markers aren't valid values for required fields. Operator must edit before motion.

### Error Handling

#### (a) Caught — structured handling

| Failure | Where caught | Operator sees |
|---|---|---|
| `autodetect.scan_system()` empty/partial | `select_preset` | Treats as LOW tier; minimal manifest. No exception. |
| `try_resolve` finds no entry-point AND no preset hint | `write_manifest` | Manifest written without `backend:` field. Runtime falls back to protocol-only resolution at first call. |
| `try_resolve` returns preset hint but entry-point not installed | `write_manifest` | Manifest pre-filled with hint name. Closing output: `Note: backend 'feetech_depthai' not installed; will activate after pip install 'robot-md[feetech-depthai]'`. Bridges to SP1's lazy path. |
| Preset YAML malformed | `load_presets` | Existing warn-and-skip preserved. SP2 doesn't crash on bad presets. |
| Preset's `cameras:` references unfound `driver_id` | `write_manifest` camera merge | Override skipped. Closing line notes the omission. |
| Schema validation fails on new enum value | `validate.py` | Clear schema error. Preset-author bug, not operator-facing. |
| `write_manifest` can't write to disk | OS-level | `PhaseResult(status="failed")`. Init aborts cleanly. |

#### (b) Pass-through

| Failure | Surface |
|---|---|
| Optional probe deps missing (`depthai`, `pyrealsense2`) | Probes lazy-import; missing dep → empty result. Not surfaced as error. |
| OS commands missing (`lspci`, `lsusb`, `v4l2-ctl`) | `_run()` returns `None` → no contribution. Existing behavior. |
| Operator hits Ctrl-C during MEDIUM prompt | `KeyboardInterrupt`; init exits non-zero with no manifest. Existing typer behavior. |

#### (c) Edge cases

| Edge case | Defense |
|---|---|
| Operator types non-numeric or out-of-range at MEDIUM prompt | `rich.prompt.IntPrompt(choices=["1","2","3"])` validates and re-prompts. |
| Camera with no detected streams | Emit baseline entry with `primary_stream: null` + warning line. Don't omit — operator might fix and retry. |
| Multiple cameras of same model | Autodetect de-duplicates by USB serial. Manifest gets distinct `driver_id` per device. Preset overrides apply by exact match. |
| Preset hint backend name typo | `try_resolve` returns the typo verbatim. Manifest pre-filled with bad name. Runtime fails on first call (SP1 error path). |
| `--yes` on LOW tier | Invalid manifest with TODOs. Closing output uses red text + non-zero exit code: `EXIT 2: minimal manifest written with 4 TODOs; not motion-ready.` |
| `--yes` on MEDIUM tier in CI without TTY | Auto-pick + stderr warning works without TTY. Warning is grep-able. |
| Operator picks runner-up at MEDIUM that doesn't have `cameras:` | Camera composition uses *chosen* preset's overrides. Picking `koch_arm` skips SO-ARM101 camera defaults. Correct — operator's pick is authoritative. |
| Preset declares `extrinsic` but autodetect entry has different stream count | Preset values for declared fields win. Discrepancy logged. |

#### Explicit non-goals

- Auto-installing missing backends (SP3).
- Recovering from broken hardware mid-init.
- Schema-validating presets at runtime (preset YAMLs are author-time correct).
- Choosing between two installed backends for the same protocol (SP3).

### Testing

#### Python unit tests — `cli/tests/unit/`

| Test | Verifies |
|---|---|
| `test_classify_tier.py` (NEW) | Classifier returns HIGH for `(18, 0)`, HIGH for `(15, 5)`, MEDIUM for `(15, 15)`, MEDIUM for `(7, 0)`, LOW for `(4, 0)`, LOW for `(0, 0)`. Boundary: `(10, 5)` HIGH, `(10, 6)` MEDIUM. |
| `test_select_preset_high.py` (NEW) | HIGH-tier returns top regardless of `interactive`. No prompt. |
| `test_select_preset_medium_guided.py` (NEW) | MEDIUM + `interactive=True` invokes `_prompt_pick`; mocked `IntPrompt` returns `2` → `scored[1].preset` returned. |
| `test_select_preset_medium_yes.py` (NEW) | MEDIUM + `interactive=False` returns top deterministically. Stderr warning includes runner-up name + score. |
| `test_select_preset_low.py` (NEW) | LOW returns `(None, "LOW", scored)` in both modes. |
| `test_select_preset_no_presets.py` (NEW) | Empty preset list returns `(None, "LOW", [])`. |
| `test_camera_merge_autodetect_only.py` (NEW) | Autodetect cameras + preset without `cameras:` → entries with `extrinsic_source: autodetect_default`. |
| `test_camera_merge_preset_override.py` (NEW) | Preset declares camera with same `driver_id` as autodetect → preset extrinsic + `extrinsic_source: preset_default`. |
| `test_camera_preset_decls_unfound_camera.py` (NEW) | Preset declares `driver_id` autodetect didn't find → entry NOT in manifest; closing output mentions omission. |
| `test_camera_no_streams.py` (NEW) | Camera with empty `streams` → manifest entry with `primary_stream: null` + warning. |
| `test_try_resolve_entry_point_match.py` (NEW) | Mock entry-points to register `feetech_depthai`; `try_resolve("feetech", "feetech_depthai")` returns `"feetech_depthai"`. |
| `test_try_resolve_preset_hint_no_install.py` (NEW) | No entry-points; `try_resolve("feetech", "feetech_depthai")` returns hint verbatim. |
| `test_try_resolve_protocol_fallback.py` (NEW) | Entry-points registered for protocol `feetech`; `try_resolve("feetech", None)` returns first-match name. |
| `test_try_resolve_no_match.py` (NEW) | No entry-points, no hint → returns `None`. |
| `test_pick_best_compat_shim.py` (UPDATE) | `pick_best()` still returns top via `select_preset(interactive=False)`. |

#### Python integration tests — `cli/tests/integration/`

| Test | Verifies |
|---|---|
| `test_init_high_tier_guided.py` (NEW) | Mock `scan_system()` → Stretch3. Run `init` interactively (HIGH never prompts). Assert manifest contains `# preset: stretch3 (tier=HIGH, score=18)`, drivers have `backend: feetech_depthai`. |
| `test_init_medium_tier_guided.py` (NEW) | Mock `scan_system()` → bob fingerprint. Pipe `1\n` to stdin. Assert `so_arm101` chosen, manifest correct, tier comment present. |
| `test_init_medium_tier_yes.py` (NEW) | Same scan, `--yes`. No prompt; top auto-picked; stderr contains MEDIUM warning. |
| `test_init_low_tier_yes.py` (NEW) | Mock `scan_system()` → bare-RPi. `--yes`. Minimal manifest with TODOs, exit code 2, stderr explains. |
| `test_init_camera_merge_e2e.py` (NEW) | bob fingerprint + `so_arm101`. Manifest has one `physics.cameras[0]` with preset extrinsic + `extrinsic_source: preset_default`. |
| `test_init_runs_without_motion_extras.py` (NEW) | Mock entry-points empty. Manifest still pre-filled with `preferred_backend` copied to `backend`. Closing output mentions upgrade. Bridges to SP1. |

#### Schema tests

| Test | Verifies |
|---|---|
| `test_schema_drivers_backend_optional.py` (NEW) | Schema validates with AND without `drivers[].backend`. Same for `preferred_backend`. |
| `test_schema_extrinsic_source_enum.py` (NEW) | Schema accepts all four enum values. Rejects unknown values. |
| `test_schema_backward_compat.py` (UPDATE) | Existing manifests in `examples/` and `cli/tests/fixtures/` validate against updated schema. |
| `test_schema_sync_ts.py` (NEW or UPDATE) | After `scripts/sync-schema.mjs`, TS schema bundle (rcan-ts) contains same enum values. |

#### Preset YAML tests

| Test | Verifies |
|---|---|
| `test_presets_have_preferred_backend.py` (NEW) | All preset YAMLs that declare `drivers[]` also declare `preferred_backend` per driver. Skip `minimal.yaml`. |
| `test_presets_camera_driver_ids_unique.py` (NEW) | Within each preset's `cameras:`, `driver_id` values are unique. |
| `test_presets_load_clean.py` (UPDATE) | All 16 preset YAMLs load without warnings under updated schema. |

#### Hardware tests — `cli/tests/hardware/`

| Test | Verifies |
|---|---|
| `test_sp2_init_bob_medium_tier.py` (NEW, `@hardware`) | Real autodetect on bob's RPi5. Score table shows `so_arm101: 15` tied with `so_arm101_leader: 15`. Tier returns MEDIUM. Skipped in CI. |
| `test_sp2_init_bob_yes_path.py` (NEW, `@hardware`) | Real autodetect + `--yes`. Manifest validates. Drivers populated with `backend: feetech_depthai`. Camera entry with preset extrinsic. |

#### Manual smoke checklist — `cli/tests/manual/sp2_init_smoke.md`

1. Bare-RPi smoke: `robot-md init prototype` → minimal manifest + 4 TODOs + exit 2.
2. Bob guided smoke: `robot-md init bob` → prompt shows top 3, defaults `[1] so_arm101`, manifest written.
3. Bob `--yes` smoke: `robot-md init bob --yes` → stderr warning visible, manifest written.
4. Camera-only smoke: rig with OAK-D but no arm → LOW tier (no arm preset matches) but camera still appears with `autodetect_default`.

#### Coverage gaps acknowledged

- Cross-platform autodetect coverage — tests mock `scan_system()`. Real divergence stays smoke-tested.
- Real entry-point registration timing — tests mock entry-points. Production verified via `test_init_runs_without_motion_extras`.
- Preset author errors at runtime — preset schema validation is aspirational; SP2 doesn't add a preset linter.

## Open Questions

1. **Scoring weights re-tune.** Current weights (proto=10, count=5, hint=5, hostname=3) were calibrated for the existing preset library. SP2's confidence thresholds assume these weights stay. If new presets shift the score distribution, thresholds may need re-tuning. **Action:** monitor MEDIUM-tier rate after SP3 lands new backends.
2. **Tier marker comment placement.** YAML round-trip libraries (ruamel.yaml) preserve top-of-file comments only when handled explicitly. **Action:** verify in implementation; fall back to a structured `metadata.preset_provenance:` field if comment doesn't survive.
3. **Preset linter scope.** SP2 ships preset YAML test asserting `preferred_backend` is declared. Should we add a stricter preset schema (separate from manifest schema)? **Action:** defer to follow-up; SP2's tests catch the obvious cases.

## Success Criteria

SP2 is done when:

- [ ] All five components updated and merged.
- [ ] All 16 presets have `preferred_backend` declarations (where applicable); known-kit presets have `cameras:` sections.
- [ ] Schema additions sync to rcan-ts bundle.
- [ ] Unit + integration test suites pass.
- [ ] Manual smoke checklist passes 4/4.
- [ ] Hardware tests pass on bob's RPi5 (MEDIUM tier path verified).
- [ ] Demo dry-run: `robot-md init bob` shows the operator the so_arm101 vs so_arm101_leader choice with reasons; `--yes` produces a working manifest with backend pre-filled.

## Sub-project Relationships

- **SP1 → SP2.** SP1 wires the Python MCP server. SP2 makes init produce manifests with `backend:` pre-filled so the runtime never has to guess.
- **SP2 → SP3.** SP3 ships manufacturer-SDK adapter backends. Once SP2 lands, adding a new backend means: register entry-point, add `preferred_backend:` hints to relevant presets, done. SP3 doesn't have to re-design init.
- **SP2 → SP4.** When SP4's claude-authored driver workflow activates (no preset matches, no backend matches), it runs in the LOW-tier path SP2 already defines. SP4 layers on top of LOW; doesn't replace it.
- **SP2 unblocks the autodetect demo beat.** "Watch Claude show you what it found and why it picked this preset" is the SP2 reveal. Most visible piece of the demo after SP1.

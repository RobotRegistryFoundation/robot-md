# SP1-SP5 Simplification Revisions

**Date:** 2026-04-27
**Status:** Authoritative — supersedes specific sections of SP1-SP5 specs
**Applies to:** `2026-04-26-sp{1,2,3,4,5}-*-design.md`

## Guiding principle

> **Simplicity by default; complexity when the user wants it.**

After SP1-SP5 specs were committed, applied this principle as a sweep. Each original spec optimized within its own boundary; this revision optimizes across them for operator UX. **Plans + implementation should follow this revision when it conflicts with the original specs.**

---

## Revision 1 — SP1: Drop manifest-only mode by default

**Original (SP1 Architecture):** Two MCP servers coexist additively — `robot-md` (npm, manifest-only) + `robot-md-motion` (Python, motion+manifest). Operator sees both in `/mcp`.

**Revision:** **One MCP server.** Plugin install requires the Python CLI from day one. Plugin's `.mcp.json`:

```json
{
  "robot-md": {
    "command": "robot-md",
    "args": ["mcp"]
  }
}
```

If `robot-md` not on PATH at first session start, the connection fails — `/mcp` shows the failure with a clear error. Skill text routes operator to `pip install 'robot-md[hardware]'`.

**Consequences:**
- npm `robot-md-mcp` package becomes optional / deprecated. Drop the v0.3.1 publish step from SP1's success criteria.
- "Two-server additive" model from SP1 §1 → **one-server, Python-required.**
- Banner D (server `instructions` payload) and SP1 trigger A (lazy detection) collapse into one path: operator runs install commands, then `/mcp` → Reconnect.
- Plugin install becomes more honest about its dependency. Marketplace description states "requires Python 3.10+ and `pip install robot-md[hardware]`."

**Opt-in complexity:** Operators on Python-less environments (rare) use the manifest-only npm server via `claude mcp add robot-md-manifest -- npx -y robot-md-mcp@^0.3` manually. Documented as an advanced path; not the default story.

**Files affected in SP1 spec:**
- §1 (Architecture): one entry in `.mcp.json`, not two.
- §2 (Components): drop component #5 (npm `server.ts` instructions update); v0.3.1 publish not required.
- §3 (Data Flow): both paths converge — operator either has Python pre-installed or hits the install prompt mid-session.
- §4 (Error Handling): "tool overlap" edge case removed.

---

## Revision 2 — SP2: Silent default for MEDIUM tier

**Original (SP2 §2):** `select_preset(interactive=True)` prompts operator with top-3 candidates on MEDIUM tier (e.g., bob's case: so_arm101 vs so_arm101_leader vs koch_arm).

**Revision:** **No interactive prompt by default.** All tiers behave the same in default and `--yes` modes:
- HIGH: silent prefill + closing line.
- MEDIUM: silent top-1 pick (deterministic tiebreak by name) + closing line: *"Matched so_arm101 (also fit: so_arm101_leader). Override: `--preset so_arm101_leader`."*
- LOW: minimal manifest + TODOs.

**Opt-in complexity:** `robot-md init --explain` reveals the full match score table and prompts on MEDIUM. `robot-md autodetect` always shows the table (existing command). Operators who want to see alternatives have a clear lever.

**Consequences:**
- `select_preset(interactive: bool)` parameter still exists but defaults to `False`.
- `_prompt_pick` still implemented but only invoked under `--explain`.
- Stderr warning on MEDIUM auto-pick stays (so CI/scripts can grep).

**Files affected in SP2 spec:**
- §2 (Components #1): `select_preset` default flipped; `_prompt_pick` callsite gated on `--explain`.
- §3 (Data Flow): "MEDIUM-tier guided" path renamed to "MEDIUM-tier with --explain"; default path is the same as `--yes`.
- §5 (Testing): `test_select_preset_medium_guided` becomes `test_select_preset_medium_explain_flag`; default-mode test asserts NO prompt.

---

## Revision 3 — SP3: Consolidate to a `[hardware]` meta-extra

**Original (SP3 §2 #5):** Three separate extras — `[lerobot]`, `[realsense]`, `[feetech-depthai]`. Operator picks based on hardware.

**Revision:** **Add a `[hardware]` meta-extra** that pulls everything in the curated baseline:

```toml
[project.optional-dependencies]
hardware = [
    "lerobot>=0.5,<0.8",
    "pyrealsense2>=2.55",
    "depthai>=2.24",
    "feetech-servo-sdk>=1.0",
    "pyserial>=3.5",
    "opencv-python>=4.8",
]
# Granular extras kept for cost-conscious / minimal installs:
lerobot = [...]
realsense = [...]
feetech-depthai = [...]
```

Default install instruction across all docs and SP1's "lazy install" prompt becomes:

```
pip install 'robot-md[hardware]'
```

**Opt-in complexity:** Granular extras stay documented under "minimal installs" or "advanced." Operators on disk-constrained systems pick `[lerobot]` alone, etc.

**Consequences:**
- Install size grows to ~2 GB (PyTorch + DepthAI + OpenCV + RealSense). Acceptable for the demo audience; documented in the install hint.
- One install hint string used everywhere (SP1 motion-extras hint, init's LOW-tier output, README, plugin description).
- Granular extras become "if you know you only need X" advanced flags.

**Files affected in SP3 spec:**
- §2 (Components #5): pyproject.toml gets `[hardware]` extra in addition to granular ones.
- §3 (Data Flow): all examples switch `pip install 'robot-md[lerobot]'` → `pip install 'robot-md[hardware]'`.
- §5 (Testing): no functional change; extras still install per their declarations.

---

## Revision 4 — SP4: Three phases instead of six

**Original (SP4 §1):** Six mandatory operator-confirmed phases (Discovery, Scaffold, Read-only, Motion dry_run, Live motion, Finalize).

**Revision:** **Three operator-facing phases** with the same internal safety properties:

| Operator phase | Internal sub-phases (state machine still tracks these) | Operator confirmation |
|---|---|---|
| **A. Setup** | Discovery + Scaffold + Read-only impl + read-test | Once at start: "yes, write a backend for this hardware." |
| **B. Motion testing** | Motion impl (dry_run) + Live motion (per-command HiTL) | Once at A→B boundary: "yes, ready to test motion." Per-command HiTL still applies in live sub-phase. |
| **C. Finalize** | Install + manifest update + contribution menu | None mandatory; menu is optional. |

**Opt-in complexity:** `robot-md author-backend --strict-phases` preserves the 6-phase model with confirmation between every sub-phase. Default is the 3-phase flow.

**Consequences:**
- Two operator confirmations instead of five. Faster demo flow.
- Safety properties unchanged: read-only-before-write still enforced (sub-phase boundary inside Setup); per-command HiTL during live still active.
- AuthorGate logic unchanged — it operates on internal sub-phase, not operator-facing phase.
- Phase-failure escalation (3 failures → SP5 or pair-program) operates on operator-facing phase. Three failures in Setup = escalate; three in Motion testing = escalate; etc.
- Skill text guides Claude through internal sub-phases without surfacing them to operator unless `--strict-phases`.

**Files affected in SP4 spec:**
- §1 (Architecture): operator phase count = 3; internal state machine retains 6 for AuthorGate.
- §2 (Components): SKILL.md description simplifies (3 operator phases shown; sub-phases internal).
- §3 (Data Flow): walkthrough collapses several confirmation beats into two; outcome unchanged.
- §4 (Error Handling): `failed_attempts` resets on operator-phase advance, not sub-phase.
- §5 (Testing): unit tests still cover sub-phase logic; integration tests assert two operator confirmations on default path, five on `--strict-phases`.

---

## Revision 5 — SP5: One CTA in init LOW-tier output

**Original (SP5 §2 #5 + SP4 §2 #4):** Two one-liners after LOW-tier init — one for `author-backend`, one for `report-hardware-gap`.

**Revision:** **One CTA.** Init's LOW-tier output:

```
No backend matches detected hardware.
  → To author one with Claude's help: `robot-md author-backend`
    (or pass --report-instead to file a structured issue without authoring)
```

**Opt-in complexity:** `--report-instead` flag on `author-backend` skips Phase A and goes straight to SP5's report flow. Standalone `robot-md report-hardware-gap` still works for operators who want it. Skill text routes "this hardware isn't supported" intent to `author-backend`; mentions `--report-instead` if operator declines authoring.

**Consequences:**
- `report-hardware-gap` is no longer the default discovery surface for the report flow — `author-backend --report-instead` is.
- Standalone `report-hardware-gap` CLI command still exists; not surfaced in init output.
- SP4's `escalate_to_sp5` integration unchanged.

**Files affected in SP5 spec:**
- §2 (Components #5): single one-liner instead of two.
- §3 (Data Flow): "filing the gap (CLI path)" example shows `author-backend --report-instead` first; standalone CLI is a sub-example.

---

## Revision 6 — Manifest schema: one `backend` field, not two

**Original (SP2 §2 #5):** Manifest schema gains both `drivers[].backend` (resolved) AND `drivers[].preferred_backend` (preset hint).

**Revision:** **Manifest has only `drivers[].backend`** (the resolved name). `preferred_backend` stays as a **preset-internal field** (in `cli/src/robot_md/presets/*.yaml`), but is NEVER copied to the operator-visible manifest.

```yaml
# Preset (internal): so_arm101.yaml
drivers:
  - id: arm_servos
    protocol: feetech
    preferred_backend: lerobot   # internal hint, used by init's try_resolve

# Manifest (operator-visible): ROBOT.md
drivers:
  - id: arm_servos
    protocol: feetech
    backend: lerobot              # the only backend field operator sees
```

**Opt-in complexity:** Operator overrides via the single `backend:` field. No two-field reasoning needed.

**Consequences:**
- Schema only adds `drivers[].backend`. `preferred_backend` not in `robot.schema.json`.
- `try_resolve` still consults preset's `preferred_backend` — but writes only `backend` to manifest.
- Reduces operator confusion ("which one wins, the hint or the resolved?").

**Files affected:**
- SP2 §2 (Components #2 and #5): schema additions exclude `preferred_backend`.
- SP2 §3 (Data Flow): manifest examples show only `backend`.
- SP3 §2 (Components #6): preset YAML examples retain `preferred_backend`; explanation clarifies it's preset-internal.

---

## Revision 7 — Skill text: one canonical source + build sync

**Pre-existing problem (not introduced by SP1-SP5 but blocking):** Two copies of `using-robot-md` SKILL.md exist:
- `~/robot-md-mcp/skills/using-robot-md/SKILL.md` (179 lines, ships with plugin)
- `~/robot-md/cli/src/robot_md/skills/using-robot-md.SKILL.md` (142 lines, ships with Python CLI)

They've drifted (37 lines difference). SP1+SP4 both edit it.

**Revision:** **`robot-md-mcp/skills/using-robot-md/SKILL.md` is canonical.** Build script in `~/robot-md/scripts/sync-skill.sh` copies it to `cli/src/robot_md/skills/using-robot-md.SKILL.md` at release time. CI in `~/robot-md` asserts the two are in sync.

**Consequences:**
- One file to edit; no drift.
- Non-plugin operators (`robot-md install-skill`) still get the same content.
- Sync check in CI catches drift early.
- Existing `cli/src/robot_md/skills/using-robot-md.SKILL.md` gets clobbered by the sync — verify nothing important is lost (likely the 37-line drift is one-directional accretion in the npm copy).

**Action required before SP1 implementation:**
1. Diff the two files; verify the 37 lines are the more-recent additions in npm copy.
2. Designate npm copy as canonical.
3. Add the sync script + CI check.
4. Treat as SP1 prerequisite (block SP1 plan until done).

---

## Net effect on operator UX

### New user, plugin-install path

```
1. claude plugin install robot-md     (~30s)
   → Plugin's .mcp.json fails to spawn server (robot-md not on PATH).
   → /mcp shows: ✗ robot-md (command not found: robot-md)
   → Plugin description + skill text says: "Run pip install 'robot-md[hardware]' first."

2. pip install 'robot-md[hardware]'   (~3min, ~2GB)
   → Python CLI on PATH; entry-points registered for all common backends.

3. /mcp → Reconnect robot-md          (~3s)
   → Server connects ✓; full tool surface available.

4. robot-md init bob                   (~10s)
   → Silent MEDIUM auto-pick of so_arm101.
   → Closing line shows match + how to override.

5. claude → "find a red lego..."       (~30s motion)
   → Skill activates → safety check → motion runs.
```

**5 commands. Zero interactive prompts. Operator sees: plugin failure → install command → reconnect → init success → motion.**

### New user, Python-first path (skip plugin marketplace)

```
1. pip install 'robot-md[hardware]'   (~3min, ~2GB)
2. robot-md init bob                   (~10s)
3. claude mcp add robot-md -- robot-md mcp /home/u/bob/ROBOT.md  (~5s)
4. claude → "find a red lego..."       (~30s motion)
```

**4 commands. No plugin marketplace needed. Operator's choice for non-marketplace environments.**

### Existing user upgrading

```
1. pip install --upgrade robot-md     (~30s)
2. /plugin update robot-md             (~10s)
3. (existing ROBOT.md continues working — no changes required)
```

**Zero new operator steps. Optional: re-run `robot-md init` to refresh manifest with `backend:` field.**

### SP4 author-backend (3 phases)

```
1. claude → "write a backend for my X"
2. (Phase A: Setup) Claude does discovery, scaffold, read-only impl.
   → Operator confirms: "ready to test motion?"
3. (Phase B: Motion) Claude implements motion, dry_run, then live with per-command HiTL.
4. (Phase C: Finalize) Auto: install + manifest update + contribution menu.
```

**Two operator decisions. Same safety properties.**

---

## Implementation order (unchanged)

SP1 → SP2 → SP3 → SP4 → SP5. Plan-writing should use this revisions doc as the authoritative source where it conflicts with the original specs.

## Skipped revisions (considered, kept as-is)

- **HiTL gates and per-command auth** — safety; complexity user implicitly wants.
- **Schema validation** — no fast path; every manifest validates.
- **Failure escalation in SP4** — 3-failure trigger is the right complexity at that moment.
- **Backend authoring template + docs** (SP3) — already opt-in; only invoked when operator wants to write a backend.
- **Strict-default redaction in SP5** — privacy is non-negotiable; opt-in include flags are the right model.

## Rollback policy

If any simplification creates more friction than it removes (e.g., MEDIUM tier silent default leads to operators writing wrong-preset bug reports), roll back to the original spec section for that area only. Document in CHANGELOG.

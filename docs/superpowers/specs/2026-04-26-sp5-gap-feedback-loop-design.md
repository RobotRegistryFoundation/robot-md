# SP5 — Gap Feedback Loop (Hardware Gap → Issue → Future Discovery)

**Date:** 2026-04-26
**Status:** Design — pending implementation plan
**Sub-project:** 5 of 5 (final; see SP1-SP4 specs in this directory)

## Problem

SP4 ships the Claude-authored driver workflow for operators willing to pair-program a backend. But many operators won't take that path — they hit unsupported hardware, want to file something for someone else to handle, and move on. Without a structured way for that signal to land, every future operator with the same hardware repeats the same dead-end discovery: lookup empty, context7 empty, WebFetch fragmented, manual SDK research from scratch.

SP4 already produces SP5-shaped issue drafts on escalation; SP5 owns the *writer* side of the loop — the CLI command, the issue structure, the `known_hardware.json` data file SP4 reads, and the maintainer triage flow that turns issues into shipped data. Without SP5, the gap-feedback story is half-built.

## Scope

**In scope:**
- A `robot-md report-hardware-gap` CLI command (the standalone trigger).
- A shared `gap_report` package used by both the CLI and SP4's `escalate_to_sp5()`.
- Strict-default redaction (hostname, USB serials, OS minor version) with opt-in flags.
- Pre-submission editor + redaction diff + confirmation — operator always sees what they're filing.
- Bundled `known_hardware.json` data file at `cli/src/robot_md/data/known_hardware.json` (shared with SP4's reader).
- JSON-Schema for the data file with `schema_version: 1` enforcement.
- Manual-triage maintainer flow with a `scripts/issue-to-json-entry.py` helper.
- GitHub issue template enforcing structured body for manual filers.
- Init's LOW-tier output adds a second one-liner pointing operators at SP5 as an alternative to SP4.
- Skill text update routing "file an issue for this hardware" intent to the CLI.

**Out of scope** (deferred to SP5.x or other systems):
- Bot-driven auto-PR from issue body.
- Remote fetch of `known_hardware.json` (bundled-with-package only in v1).
- Per-field consent prompting (strict-default + opt-in flags is the model).
- Maintainer-side automation beyond the helper script.
- Cross-repo coordination (issues + data both live in `robot-md`).
- Integration with RRF's incident-reporting (different domain).
- Schema migration v1 → v2 (deferred until v2 needed).
- Sharding `known_hardware.json` (only at >10K entries).

## Design

### Architecture

Ten components, all in-tree to `robot-md/cli/`:

1. **`cli/src/robot_md/gap_report/`** (NEW package) — Issue body generator + redactor + filer.
2. **`cli/src/robot_md/__main__.py`** — New CLI command `robot-md report-hardware-gap`.
3. **`cli/src/robot_md/data/known_hardware.json`** (NEW, shared with SP4) — Bundled hardware lookup data, seeded ~20 entries.
4. **`cli/src/robot_md/schemas/known_hardware.schema.json`** (NEW) — JSON-Schema, stamped `schema_version: 1`.
5. **`cli/src/robot_md/init_phases/install_mcp.py`** (UPDATED, additive on SP1+SP4) — LOW-tier output adds second one-liner.
6. **`cli/src/robot_md/author_backend/contribution.py`** (UPDATED, from SP4) — `escalate_to_sp5()` becomes thin wrapper around `gap_report.generate`.
7. **`integrations/claude-code-skill/SKILL.md`** (UPDATED, the `using-robot-md` skill) — Hardware-gap intent stanza routes to `report-hardware-gap`.
8. **`docs/triaging-hardware-gaps.md`** (NEW) — Maintainer guide.
9. **`.github/ISSUE_TEMPLATE/hardware-gap.md`** (NEW) — GitHub issue template for manual filers.
10. **`scripts/issue-to-json-entry.py`** (NEW) — Maintainer helper to extract structured fields from issue body.

**Out of scope for architecture:**
- Bot infrastructure.
- Remote fetch endpoint.
- Cross-repo aggregation.

**Design principles:**
- **Single source of truth.** SP4 escalation and standalone CLI both call the same generator.
- **Operator-controlled submission.** Body always shown for review; nothing auto-filed without operator consent.
- **Strict redaction default.** Hostname and serials redacted unless opt-in. Pre-submission diff highlights what's missing.
- **Loop closes through standard release cadence.** No special infrastructure to deliver updates — `pip install --upgrade` carries the new entries.
- **Bundled JSON is the contract.** Schema validates in CI; PRs touching the data file run through validation.

**Backward compatibility:**
- `known_hardware.json` seeded conservatively; missing entries don't break SP4 (lookup returns None gracefully).
- Init's LOW-tier output already had the SP4 one-liner; SP5 adds a second alternative.
- SP4's `escalate_to_sp5` method already exists in SP4's spec; SP5 just provides its target.

### Components

#### 1. `gap_report/` package

```
cli/src/robot_md/gap_report/
├── __init__.py        # generate(opts) → IssueBody, file(body, opts) → IssueResult
├── generator.py       # IssueBody dataclass + body composition
├── redact.py          # Redactor: hostname, serials, OS minor
└── filer.py           # gh CLI invocation; fallback to draft + manual instructions
```

**`IssueBody` dataclass:**

```python
@dataclass
class IssueBody:
    title: str
    body_markdown: str
    label: str = "hardware-gap"
    redacted_fields: list[str]
    raw_redactions: dict[str, str]
```

**Generator function:**

```python
def generate(
    *,
    autodetect_scan: Scan | None = None,
    manifest_path: Path | None = None,
    sdk_hint: str | None = None,
    operator_note: str | None = None,
    include_hostname: bool = False,
    include_serials: bool = False,
    authoring_log: list[dict] | None = None,
) -> IssueBody:
    """Build a structured issue body. Used by CLI and SP4 escalation."""
```

Body composed from a Markdown template with sections: title, hardware fingerprint table, operator notes, autodetect summary (JSON block), authoring log (if escalated from SP4), suggested next step for maintainers, robot-md version footer.

**Redactor:**

```python
class Redactor:
    def __init__(self, *, include_hostname=False, include_serials=False):
        self.include_hostname = include_hostname
        self.include_serials = include_serials
        self.applied: dict[str, str] = {}

    def hostname(self, value: str) -> str:
        if self.include_hostname:
            return value
        self.applied[value] = "<hostname-redacted>"
        return "<hostname-redacted>"

    def label(self, value: str) -> str:
        if self.include_serials:
            return value
        return _strip_serials(value, self.applied)

    def os_version(self, value: str) -> str:
        # "Linux 6.12.75+rpt-rpi-2712" → "Linux 6.x"
        ...
```

**Filer:**

```python
def file_issue(
    body: IssueBody,
    *,
    no_edit: bool = False,
    dry_run: bool = False,
) -> IssueResult:
    """File via gh, or fall back to draft + manual instructions.
    Always shows operator the body before invoking gh.
    """
    # 1. Write body to /tmp/hardware-gap-<ts>.md
    # 2. If no_edit: print body inline. Else: open in $EDITOR.
    # 3. Show redaction diff: stripped fields + originals
    # 4. Confirm: "File this to RobotRegistryFoundation/robot-md? [y/N]"
    # 5. If yes + gh available + authed: gh issue create --label hardware-gap
    # 6. Else: write draft to /tmp/, print fallback instructions
```

#### 2. CLI command

```python
@app.command("report-hardware-gap")
def report_hardware_gap_cmd(
    include_hostname: bool = typer.Option(False, "--include-hostname"),
    include_serials: bool = typer.Option(False, "--include-serials"),
    no_edit: bool = typer.Option(False, "--no-edit"),
    note: str | None = typer.Option(None, "--note"),
    sdk_hint: str | None = typer.Option(None, "--sdk-hint"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Report unsupported hardware to robot-md so future operators benefit."""
    from robot_md.gap_report import generate, file_issue
    from robot_md.autodetect import scan_system
    scan = scan_system()
    body = generate(
        autodetect_scan=scan,
        manifest_path=_find_robot_md_in_cwd(),
        sdk_hint=sdk_hint,
        operator_note=note,
        include_hostname=include_hostname,
        include_serials=include_serials,
    )
    result = file_issue(body, no_edit=no_edit, dry_run=dry_run)
    raise typer.Exit(code=0 if result.ok else 1)
```

#### 3. `known_hardware.json` (bundled data)

Lives at `cli/src/robot_md/data/known_hardware.json`. Initial seed ~20 entries:

```json
{
  "schema_version": 1,
  "updated": "2026-04-26",
  "entries": [
    {
      "vid": "0403",
      "pid": "6014",
      "vendor_name": "FTDI (commonly used by Trossen U2D2, Robotis U2D2)",
      "hardware_label": "FT232H USB-to-serial adapter",
      "suggested_sdk": "dynamixel-sdk",
      "docs_url": "https://emanual.robotis.com/docs/en/software/dynamixel/dynamixel_sdk/overview/",
      "community_backend_hints": ["robot-md-backend-trossen-wx (PyPI, alpha)"]
    },
    {
      "vid": "1ffb",
      "pid": "0089",
      "vendor_name": "Pololu",
      "hardware_label": "Pololu Maestro Servo Controller",
      "suggested_sdk": null,
      "docs_url": "https://www.pololu.com/docs/0J40",
      "community_backend_hints": []
    }
  ]
}
```

Seed entries cover: FTDI USB-serial (Dynamixel ecosystem), CP210x (Feetech), DepthAI/Luxonis cameras, Intel RealSense, ODrive, common Arduino/STM32 boards used in custom robotics.

#### 4. `known_hardware.schema.json`

```json
{
  "$id": "https://robotmd.dev/schemas/known_hardware.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "robot-md known_hardware lookup",
  "type": "object",
  "required": ["schema_version", "entries"],
  "properties": {
    "schema_version": {"const": 1},
    "updated": {"type": "string", "format": "date"},
    "entries": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["vid", "pid", "vendor_name"],
        "properties": {
          "vid": {"type": "string", "pattern": "^[0-9a-f]{4}$"},
          "pid": {"type": "string", "pattern": "^[0-9a-f]{4}$"},
          "vendor_name": {"type": "string", "minLength": 1},
          "hardware_label": {"type": "string"},
          "suggested_sdk": {"type": ["string", "null"]},
          "docs_url": {"type": ["string", "null"], "format": "uri"},
          "community_backend_hints": {
            "type": "array",
            "items": {"type": "string"},
            "default": []
          },
          "added_via_issue": {"type": "string"}
        }
      }
    }
  }
}
```

#### 5. Init LOW-tier output (additive on SP1+SP4)

```python
if tier == "LOW" and any_unrecognized_devices(scan):
    print(
        "No backend matches detected hardware. To author one with "
        "Claude's help: `robot-md author-backend`.",
        file=sys.stderr,
    )
    print(
        "Or `robot-md report-hardware-gap` to file a structured issue "
        "so others can write a backend.",
        file=sys.stderr,
    )
```

Two one-liners — operator picks the path matching their time budget.

#### 6. SP4 escalation integration

SP4's `contribution.escalate_to_sp5(state)` (specced in SP4 §2.7) becomes:

```python
def escalate_to_sp5(state: WorkflowState) -> EscalationResult:
    from robot_md.gap_report import generate, file_issue
    body = generate(
        autodetect_scan=_scan_from_state(state),
        manifest_path=state.workdir.parent / "ROBOT.md",
        sdk_hint=state.sdk_hint,
        operator_note=state.authoring_log[-1].get("operator_note"),
        authoring_log=state.authoring_log,
        include_hostname=False,  # always strict on auto-escalation
        include_serials=False,
    )
    return file_issue(body, no_edit=False)
```

Always strict on auto-escalation — operator can re-run CLI manually with opt-in flags for richer context.

#### 7. Skill text addition (using-robot-md)

```
### Hardware-gap intent

If the operator says "this hardware isn't supported," "file an issue
for this," "report this," or similar, AND no `execute_capability`
succeeded for the relevant driver, suggest:

> "Run `robot-md report-hardware-gap` — I can help you fill in the
>  operator notes section, then it'll generate a structured issue you
>  can review and file."

If operator agrees, walk them through running the CLI command and
reviewing the generated body before they file.
```

#### 8. `docs/triaging-hardware-gaps.md` (~600 words)

Sections:
1. **What this is.** SP5's flow + relationship to SP4 + `known_hardware.json`.
2. **Triage checklist.**
   - Read issue. Verify vid:pid is hex 4-char.
   - Run `python scripts/issue-to-json-entry.py <issue-url>`.
   - Verify SDK + docs URL.
   - Open PR titled `data(known_hardware): add <vendor> <model> (#<issue>)`.
   - Set `added_via_issue`. Bump `updated`.
   - Merge after CI passes. Close issue with PR link.
3. **What NOT to add.** Generic vid:pids shared across many products (case-by-case). Hardware already covered by an existing backend (noise).
4. **When to escalate to a backend PR.** If multiple operators file the same hardware, prioritize commissioning a backend (use `examples/backend-template/`).

#### 9. `.github/ISSUE_TEMPLATE/hardware-gap.md`

GitHub issue template enforcing structure for operators who file manually (no CLI):

```markdown
---
name: Hardware gap report
about: Report hardware that robot-md doesn't have a backend for
labels: hardware-gap
---

> Recommended: use `robot-md report-hardware-gap` to generate this issue
> automatically with proper redaction. Manual filing is also fine.

## Hardware fingerprint
- USB vid:pid: `XXXX:XXXX`
- Vendor (USB descriptor): ``
- Operator-supplied vendor/model: ``
- Detected protocol: ``
- OS major: ``
- robot-md version: ``

## Operator notes
<!-- Free-text -->

## Autodetect summary
<!-- Output of `robot-md autodetect` -->

## What you're asking for
- [ ] An entry in `known_hardware.json` so future SP4 sessions get the SDK hint upfront.
- [ ] Optional: a maintainer-curated backend in robot-md core.
```

#### 10. `scripts/issue-to-json-entry.py`

Small Python helper:

```python
"""Parse a hardware-gap issue body and emit a known_hardware.json entry."""
# Reads issue body (URL via gh api, or stdin/file).
# Extracts vid, pid, vendor_name, hardware_label, sdk_hint via regex on
# the structured fingerprint section.
# Validates against known_hardware.schema.json.
# Prints JSON entry; maintainer pastes into the data file.
```

### Data Flow

#### Operator A: filing the gap (CLI path)

```
Operator A (has Trossen WX250)        State
─────────────────────────────────────────────────────────────────
$ robot-md init wx250 --yes        →    LOW tier; init prints two one-liners.

$ robot-md report-hardware-gap \   →    gap_report.generate():
    --note "Trossen WX250 6-DoF             - autodetect.scan_system() runs
            arm via U2D2 dongle"            - manifest read from cwd-walked ROBOT.md
                                            - Redactor active: hostname stripped, etc.
                                            - IssueBody composed

                                        Pre-submission UX:
                                          [editor opens with body in $EDITOR]
                                          [operator reviews, saves, exits]
                                          Diff of redactions:
                                            hostname: bob → <hostname-redacted>
                                            label: "FT232 USB Serial Adapter SN:0403xxxx"
                                              → "FT232 USB Serial Adapter"
                                            os: "Linux 6.12.75..." → "Linux 6.x"
                                          File this to RobotRegistryFoundation/robot-md? [y/N]

> "y"                               →   gh issue create --label hardware-gap ...

                                        Output:
                                          ✓ Filed issue #142 at:
                                          https://github.com/RobotRegistryFoundation/robot-md/issues/142
```

#### Operator A: filing via SP4 escalation

```
(In SP4's Phase 3, after 3 failures, operator picks "a" to escalate.)

SP4 contribution.escalate_to_sp5(state)
  → calls gap_report.generate(
      autodetect_scan=..., sdk_hint=..., operator_note=...,
      authoring_log=state.authoring_log,
      include_hostname=False, include_serials=False,
    )
  → IssueBody includes "Authoring log" section with phase failure details:
       - Attempt 1: SDK ImportError
       - Attempt 2: Port permission denied
       - Attempt 3: Servo ping no-ack
  → file_issue(body, no_edit=False)
    Operator reviews, confirms.
    gh issue create runs.

  Output:
    ✓ Filed issue #143 with full authoring log.
    Workflow exits with status=5 (escalated).
```

#### Operator A: filing manually (no `gh` CLI)

```
$ robot-md report-hardware-gap     →    Same generation.
                                        gh CLI not on PATH.

                                        Output:
                                          gh CLI not available. Saved body to:
                                          /tmp/hardware-gap-2026-04-26.md

                                          To file:
                                          1. Open https://github.com/RobotRegistryFoundation/robot-md/issues/new
                                          2. Choose "Hardware gap report" template
                                          3. Paste the contents of /tmp/hardware-gap-2026-04-26.md
                                          4. Add label `hardware-gap`
                                          5. Submit

                                          Or install gh CLI: brew install gh / apt install gh
```

#### Maintainer triage

```
$ gh issue list --label hardware-gap \  →   Issue #142 visible.
    --repo RobotRegistryFoundation/robot-md

$ python scripts/issue-to-json-entry.py \  →   Extracts:
    https://github.com/.../issues/142            vid: "0403", pid: "6014"
                                                  vendor_name: "Trossen Robotics
                                                    (via FTDI U2D2)"
                                                  hardware_label: "WX250 6-DoF arm"
                                                  suggested_sdk: "dynamixel-sdk"
                                                  docs_url: "https://emanual.robotis.com/..."
                                                Validates against schema.

(Maintainer pastes entry into known_hardware.json,
 bumps "updated", sets added_via_issue.)

$ gh pr create \                   →    PR opened.
                                        CI runs: schema validation passes.
                                        Maintainer self-approves + merges.

$ gh issue close 142 \             →    Issue closed with PR link.
    --comment "Added in #143"

(robot-md release vN.N+1 in 2-4 weeks.)
```

Median triage target: **1 week from issue → PR merged.**

#### Operator B: benefiting (the loop closes)

```
Operator B (also has Trossen WX250)   State
─────────────────────────────────────────────────────────────────
$ pip install --upgrade robot-md   →    robot-md vN.N+1 installed.
                                        New known_hardware.json bundled.

$ robot-md init wx250b --yes       →    LOW tier; two one-liners.

$ claude                           →    Session starts.

> "Claude, write a backend for     →   authoring-a-backend skill activates.
   my WX250"                            Phase 1 (Discovery):

                                        Step 1: lookup_hardware("0403", "6014")
                                          → known_hardware.json hit:
                                              vendor: "Trossen Robotics (via FTDI U2D2)"
                                              suggested_sdk: "dynamixel-sdk"
                                              docs_url: "https://emanual.robotis.com/..."

                                        Output:
                                          Phase 1: Discovery
                                          Hardware: Trossen WX250 (FTDI U2D2)
                                          known_hardware.json suggests: dynamixel-sdk
                                            (docs at https://emanual.robotis.com/...)
                                          Confirm to proceed.

> "yes"                             →   Phase 1 complete in seconds.
                                        Operator B skips entire context7+WebFetch loop.

(Phases 2-6 proceed as normal.)
```

The loop closes when Operator B's Phase 1 takes seconds instead of minutes.

#### Loop progression over time

| Time | Operator state | known_hardware.json state |
|---|---|---|
| t=0 | Operator A hits gap | Entry absent |
| t+1 day | Operator A files issue #142 | Entry absent |
| t+1 week | Maintainer triages, PR #143 merged | Entry on `main` |
| t+2-4 weeks | robot-md release vN.N+1 ships | Entry bundled |
| t+1-3 months | Operator B installs upgrade | Entry available — Phase 1 finds SDK in seconds |
| t+3-6 months | Community publishes `robot-md-backend-trossen-wx250` to PyPI | community_backend_hints grows; Operator C just `pip install`s |
| t+6-12 months | Hardware common enough → first-party adapter PR | Entry stays as historical context; SP3's adapter set grows |

#### State summary

| Phase | Who | Output | Latency |
|---|---|---|---|
| Filing | Operator A | GitHub issue with structured body | Minutes |
| Triage | Maintainer | PR adding `known_hardware.json` entry | ~1 week (target) |
| Release | RRF maintainers | New robot-md version with bundled data | 2-4 weeks |
| Discovery | Operator B | Phase 1 of SP4 short-circuits via lookup | Immediate (`pip install --upgrade`) |
| Productization | Community | PyPI backend published + SP3 PR upstream | Months |

### Error Handling

#### (a) Caught — structured handling

| Failure | Where caught | Operator sees |
|---|---|---|
| `gh` CLI not installed | `filer.file_issue` checks `which gh` | Falls back: writes body to `/tmp/`, prints browser-paste instructions + `gh install` hint. |
| `gh` CLI not authed | `gh issue create` returns auth error | Same fallback as gh-missing. Surfaces `gh auth login`. |
| `$EDITOR` not set | `filer` checks env first | Inline display via `rich.console.print`. Operator confirms via `[y/N]`. |
| `$EDITOR` exits non-zero (operator quit without saving) | `filer` checks return code | Treats as abort; body saved to `/tmp/` for retry. |
| `autodetect.scan_system()` returns empty | `generate` falls through | Body composed from operator notes + manifest. Mentions "no autodetect data captured." |
| Manifest not found via cwd-walk | `generate` skips manifest section | Body composed from autodetect alone. |
| Issue body exceeds GitHub max (65,536 chars) | `filer` checks length pre-submission | Truncates `authoring_log` first, then `autodetect_summary`. Marks `_truncated_`. Falls back to draft if still too large. |
| Bundled `known_hardware.json` corrupt | `known_hardware.load_known_hardware()` validates at load | Returns empty dict + logs warning. SP4 lookup returns None. SP5 write side unaffected. |
| Operator passes invalid vid:pid via `--note` | Schema validation runs PRE-submission | Pre-submission warning: `vid '12345' is not 4-char hex; entry will need maintainer correction.` |
| Network outage during `gh issue create` | gh returns network error; filer catches | Saves draft, prints retry command. |
| Operator declines confirmation prompt | `filer` aborts cleanly | Saves draft to `/tmp/` for retry. Exit 0. |
| Issue template missing in target repo | `gh issue create --label hardware-gap` works without template | Issue created from raw body; no template enforcement. Acceptable degradation. |

#### (b) Pass-through

| Failure | Surface |
|---|---|
| gh rate limiting | gh's own error. SP5 doesn't retry. |
| GitHub repo permissions changed | gh returns 403; same draft-on-disk fallback. |
| GitHub-side issue body sanitization | Out of SP5 scope; operator sees rendered issue, can edit on web. |
| Operator's $EDITOR is `nano` and they can't save | Out of scope — `nano` UX. |

#### (c) Edge cases — defensive handling

| Edge case | Defense |
|---|---|
| vid:pid collision in `known_hardware.json` (FTDI shared across products) | Schema allows multiple entries with same vid:pid. SP4 lookup returns first-match; ordering convention "most-specific first." Triage doc covers. SP5.x may add narrower matchers (USB serial, device path pattern). |
| Operator runs `report-hardware-gap` multiple times | Each run files a new issue. Maintainer dedupes during triage. CLI suggests `gh issue list --search "0403:6014"` after filing. |
| Operator on shared lab machine with multiple ROBOT.md files | cwd-walk picks closest. Wrong-one selection visible in editor pre-submission; `--manifest /path` overrides. |
| Malicious operator submits prompt-injection in operator notes | Maintainer review catches. Helper script operates on extracted structured fields only, not free-text. |
| `known_hardware.json` grows beyond practical size | At ~10K entries, JSON load slows. SP5.x may shard by vid prefix. v1 doesn't optimize. |
| Schema version bump (v1 → v2) | SP4's loader rejects v2 with clear error. Migration path: bundle v1 until major bump. |
| Autodetect output contains binary garbage from malformed USB descriptor | `generate` runs `repr()` on suspect strings, captures with `<binary>` placeholder. JSON serialization safe. |
| Privacy regret after filing | Issue is public; can't unfile. CLI message after filing: instructions for editing/deleting via GitHub. |
| Operator without ROBOT.md (just exploring hardware pre-purchase) | CLI works without manifest. Body composed from autodetect alone. |
| Operator note contains secrets (API key pasted by accident) | Pre-submission editor opens — operator sees and can edit. |
| `gh issue create` reports wrong repo URL | Filer captures stdout; if URL doesn't match expected, prints warning. |
| `--include-hostname` but autodetect didn't capture one | Skip silently; flag becomes no-op. |
| Stale pip cache means operator's `--upgrade` doesn't pull new data file | Out of SP5 scope. Document `pip install --upgrade --no-cache-dir robot-md` in troubleshooting. |
| Two operators file simultaneously for same hardware | Both issues exist independently; maintainer dedupes. Acceptable. |
| Maintainer accidentally merges PR with malformed entry | CI runs schema validation on every PR. Should not happen. If it does: fix-forward. |

#### Workflow safeguards

1. Pre-submission body always shown — no silent file-and-forget.
2. Pre-submission diff for redactions — operator sees what was stripped.
3. Schema validation pre-submission — catches bad vid:pid before maintainer's time wasted.
4. Helper script never auto-PRs — maintainer always reviews and opens by hand.
5. Bundled JSON loads gracefully on corruption — SP4's reader doesn't crash.

#### Explicit non-goals

- Auto-PR from issue body (SP5.x).
- Issue deduplication on operator side (suggested, not enforced).
- Privacy guarantees beyond redaction defaults.
- Maintainer SLAs (best-effort).
- Cross-repo aggregation.
- Live `known_hardware.json` updates via remote fetch.

### Testing

#### Generator unit tests

| Test | Verifies |
|---|---|
| `test_gap_generator_minimal_body.py` (NEW) | Empty inputs → minimal valid body with placeholders. |
| `test_gap_generator_full_body.py` (NEW) | All inputs populated → all sections present. Title format correct. |
| `test_gap_generator_with_authoring_log.py` (NEW) | Stubbed SP4 state with 3 phase failures → body's "Authoring log" section enumerates each. |
| `test_gap_generator_no_manifest_falls_back_to_autodetect.py` (NEW) | `manifest_path=None` → composes without manifest fields. |
| `test_gap_generator_body_size_within_github_limit.py` (NEW) | Max-realistic inputs → body under 65,536 chars. |
| `test_gap_generator_body_truncation.py` (NEW) | Forced over-limit → truncates authoring_log, then autodetect; markers added. |
| `test_gap_generator_invalid_vid_pid_warning.py` (NEW) | Invalid format in operator note → warning emitted, doesn't fail. |

#### Redactor unit tests

| Test | Verifies |
|---|---|
| `test_redact_hostname_default.py` (NEW) | Default → `<hostname-redacted>`; recorded in `applied`. |
| `test_redact_hostname_opt_in.py` (NEW) | `include_hostname=True` → passes through; `applied` empty for hostname. |
| `test_redact_serials_from_label.py` (NEW) | Hex-shaped serials and `S/N:` patterns stripped from labels. |
| `test_redact_serials_opt_in.py` (NEW) | `include_serials=True` → labels unchanged. |
| `test_redact_os_version.py` (NEW) | `"Linux 6.12.75+rpt..."` → `"Linux 6.x"`. |
| `test_redact_diff_for_pre_submission.py` (NEW) | Multiple redactions → `applied` contains exact original→redacted pairs. |
| `test_redact_no_false_positives.py` (NEW) | vid:pid (`0403:6014`) not stripped — must survive as lookup key. |

#### Filer unit tests

| Test | Verifies |
|---|---|
| `test_filer_gh_available_and_authed.py` (NEW) | Mocked happy path → IssueResult(ok=True, url=...). |
| `test_filer_gh_missing.py` (NEW) | `which gh` → None → fallback path with manual instructions. |
| `test_filer_gh_auth_failure.py` (NEW) | gh auth error → same fallback. |
| `test_filer_gh_network_failure.py` (NEW) | gh network error → save draft + retry instructions. |
| `test_filer_editor_unset.py` (NEW) | No `$EDITOR` → inline display. |
| `test_filer_editor_aborted.py` (NEW) | `$EDITOR` non-zero → abort, save draft, exit 0. |
| `test_filer_operator_declines_confirmation.py` (NEW) | Confirmation `n` → save draft, no gh call, exit 0. |
| `test_filer_dry_run.py` (NEW) | `dry_run=True` → no gh call, no /tmp write, prints body. |

#### Schema validation tests

| Test | Verifies |
|---|---|
| `test_known_hardware_schema_loads.py` (NEW) | Schema parses as valid JSON-Schema (draft 2020-12). |
| `test_known_hardware_bundled_validates.py` (NEW, CI) | Bundled `known_hardware.json` validates. Runs on every PR. |
| `test_known_hardware_schema_rejects_invalid_vid.py` (NEW) | Bad vid format → schema validation fails clearly. |
| `test_known_hardware_schema_rejects_uppercase_hex.py` (NEW) | Forces lowercase canonical form. |
| `test_known_hardware_schema_version_const.py` (NEW) | Schema enforces `schema_version: 1`. |
| `test_known_hardware_schema_seed_entry_count.py` (NEW) | Seed has at least 15 entries. |

#### Helper script tests

| Test | Verifies |
|---|---|
| `test_issue_to_json_entry_full_body.py` (NEW) | Full sample body → script extracts all fields; output validates. |
| `test_issue_to_json_entry_partial_body.py` (NEW) | Partial body → entry with nulls for optional fields. |
| `test_issue_to_json_entry_invalid_body.py` (NEW) | Missing fingerprint section → warning + asks maintainer to fill in. |
| `test_issue_to_json_entry_safe_against_injection.py` (NEW) | Markdown injection → script extracts only structured fields. |

#### CLI tests

| Test | Verifies |
|---|---|
| `test_cli_report_hardware_gap_basic.py` (NEW) | Mocked happy path → issue filed with correct title + label. |
| `test_cli_report_hardware_gap_redaction_default.py` (NEW) | Default → hostname + serials stripped; diff shown. |
| `test_cli_report_hardware_gap_include_hostname.py` (NEW) | Flag keeps hostname. |
| `test_cli_report_hardware_gap_no_edit.py` (NEW) | `--no-edit` → inline body, no $EDITOR; confirmation still required. |
| `test_cli_report_hardware_gap_dry_run.py` (NEW) | `--dry-run` → no gh, no /tmp; just prints body. |
| `test_cli_report_hardware_gap_no_manifest.py` (NEW) | No ROBOT.md → autodetect-only body works. |

#### SP4 integration tests

| Test | Verifies |
|---|---|
| `test_sp4_escalate_to_sp5_calls_generator.py` (NEW) | SP4's escalate invokes `gap_report.generate` with state's authoring_log. |
| `test_sp4_escalate_strict_redaction_default.py` (NEW) | SP4 escalation always uses strict redaction. |
| `test_sp4_escalate_writes_draft_on_gh_failure.py` (NEW) | gh missing → SP4's EscalationResult carries draft path. |

#### Init integration test

| Test | Verifies |
|---|---|
| `test_init_low_tier_two_one_liners.py` (NEW) | Mocked LOW tier with unrecognized devices → both SP4 and SP5 one-liners in stderr. With recognized devices, neither appears. |

#### Skill text — manual smoke checklist (`cli/tests/manual/sp5_skill_smoke.md`)

1. Operator says "this hardware isn't supported, file an issue" → using-robot-md suggests `report-hardware-gap`.
2. Operator says "what hardware does robot-md support?" → manifest tools, no SP5 invocation.
3. End-to-end: run CLI, type operator notes, review body, file. Visit issue URL — verify structure.

#### Maintainer-side manual checklist

In `docs/triaging-hardware-gaps.md`:
1. `gh issue list --label hardware-gap`. Pick oldest open.
2. Run helper script. Inspect output.
3. Verify SDK + docs URL by visiting them.
4. Grep `known_hardware.json` for vid:pid; if duplicate, comment + close.
5. Otherwise: paste entry, bump `updated`, set `added_via_issue`, open PR.
6. Verify CI passes. Merge after review.
7. Close issue with PR link.

#### Hardware tests

None for SP5 — all paths are file-generation + GitHub interaction. SP4's hardware tests cover the `escalate_to_sp5()` integration end-to-end.

#### Documentation tests

| Test | Verifies |
|---|---|
| `test_issue_template_present.py` (NEW) | `.github/ISSUE_TEMPLATE/hardware-gap.md` exists with the structured fingerprint section. |
| `test_triaging_doc_helper_script_referenced.py` (NEW) | Triaging doc references the helper script; helper exists at expected path. |
| `test_known_hardware_seed_entries_have_realistic_fields.py` (NEW) | Each seed entry has either `suggested_sdk` OR non-empty `community_backend_hints`. Catches lazy seeding. |

#### Coverage gaps acknowledged

- Live `gh` and GitHub API behavior — mocked; smoke-tested manually.
- Maintainer triage UX in practice — manual checklist only; iterate after first 5-10 real issues.
- Schema migration v1 → v2 — not exercised; will be when SP5.x bumps.
- Loop closure timing — depends on real release cadence; manual narrative validation only.
- Seed entry quality — depends on hand curation; tests catch structural correctness only.

## Open Questions

1. **Seed entry sourcing.** SP5 ships ~20 seed entries. **Action:** before SP5 implementation, do a 1-day hardware-survey pass: walk through SP3's preset list + the LeRobot/Reachy/Stretch/UR/Franka ecosystems and curate the seed file. Avoid shipping a stub that says "0 entries" at v1.0.
2. **Issue template auto-application.** GitHub auto-loads the template when operators click "New issue" — but only if the file path matches GitHub's conventions exactly. **Action:** verify template path during implementation; add to manual checklist.
3. **`gh` repo permissions.** `gh issue create` works for any GitHub user against a public repo without write access (issue creation is allowed for everyone). **Action:** confirm during implementation; if not the case, document the permission requirement upfront.

## Success Criteria

SP5 is done when:

- [ ] Ten components built and merged.
- [ ] `cli/src/robot_md/data/known_hardware.json` seeded with at least 15 realistic entries.
- [ ] All unit + integration tests pass.
- [ ] Schema validation runs in CI on every PR touching the data file.
- [ ] Manual skill smoke checklist passes 3/3.
- [ ] Maintainer triage doc reviewed by one external robotics maintainer; feedback incorporated.
- [ ] End-to-end loop verification: file a real test issue against a staging branch, run helper script, open PR, merge, verify next `pip install` carries the entry. (One-time bootstrap test.)
- [ ] Demo dry-run: operator (Anthropic acquisition demo audience) runs `robot-md report-hardware-gap`, watches the redacted body assemble, sees the issue land in GitHub. Then a maintainer-persona walks through the triage in <5 minutes ending with a merged PR.

## Sub-project Relationships

- **SP4 → SP5.** SP4's escalation path produces SP5-shaped issues via the shared `gap_report.generator`. Without SP5, SP4 escalations would have nowhere to land.
- **SP5 → SP4.** SP5's `known_hardware.json` is the substrate SP4's Phase 1 (Discovery) reads. Without SP5, every novel hardware repeats the same dead-end research.
- **SP5 closes the loop.** Operator A files → maintainer triages → Operator B benefits. The Anthropic demo's "robot-md self-improves" beat depends on this entire loop being visible.
- **SP5 is the lightest of the five sub-projects.** No new infrastructure beyond a labeled issue + a JSON file + a helper script. Designed for v1 ship without bots, remote fetch, or special automation.

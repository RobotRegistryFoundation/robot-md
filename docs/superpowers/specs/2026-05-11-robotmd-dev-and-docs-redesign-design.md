# robotmd.dev + docs.robotmd.dev redesign — design

**Status:** Design (spec) — written 2026-05-11.
**Closes:** [robot-md#20](https://github.com/RobotRegistryFoundation/robot-md/issues/20) (apex redesign), [robot-md#21](https://github.com/RobotRegistryFoundation/robot-md/issues/21) (docs area).
**Supersedes:** [`2026-04-30-robotmd-site-redesign-brief.md`](./2026-04-30-robotmd-site-redesign-brief.md) — that brief was the constraints-and-intent layer; this document is the spec.
**Out of scope:** [robot-md#3](https://github.com/RobotRegistryFoundation/robot-md/issues/3) (`robot-md-http` OpenAPI bridge) — separate project.

---

## Context

The 2026-04-30 brief assumed `robotmd.dev` was one large `index.html` with no information architecture and no docs area. In the 11 days since, both gaps closed incrementally:

- `site/` now has eight sub-pages (`/agents/`, `/actuators/`, `/case-studies/`, `/cookbook/`, `/managed-agents/`, `/registry/`, `/robots/`, `/status/`), waitlist plumbing (`js/waitlist.js`), and a build-time proof bar (`scripts/inject-stats.js`).
- `docs.robotmd.dev` is live on a MkDocs Material stack in a separate repo (`robot-md-docs`), with spec/, mcp/, compliance/, examples/, and getting-started prose migrated off the apex.

What remains is not a redesign so much as a consolidation pass: the apex `index.html` has grown to 1,400 lines with all CSS inline; per-surface coverage for Claude Code does not yet exist as its own page; the apex visual system and the docs Material theme look like two sites; and several pages need a contrast + copy audit before they meet the reviewer-grade quality bar the brief targets.

This spec covers that consolidation as a single big-bang PR per repo (one PR in `robot-md`, one in `robot-md-docs`), landed in that order.

## Goals

1. **Maintainability.** Split the 1,400-line `site/index.html` into header / footer / section partials assembled by a tiny build script; extract page-specific CSS to `site/css/apex.css`.
2. **Cross-surface design-system unification.** Extract design tokens (palette, type, spacing, radii) to `site/css/tokens.css` as a single source of truth, mirrored into `robot-md-docs/docs/stylesheets/tokens.css`. Apex header/footer and docs header/footer visually match.
3. **Visual polish.** Copy + contrast + Lighthouse audit across the nine apex sections and eight sub-pages.
4. **Targeted content.** Ship one new per-surface page (`/agents/claude-code/`), rewrite `/agents/` as a directory, and deepen the existing `/case-studies/bob-so-arm101/` page.

## Non-goals

- Stack change. Apex stays hand-written HTML; docs stays MkDocs Material. No Astro/Next/11ty introduction.
- Per-surface pages for Gemini, Codex, ChatGPT, or Q. Deferred to a follow-up issue.
- robot-md-http OpenAPI bridge (#3). Separate project.
- Asciinema casts on `/cookbook/` (Cookbook v3 Task 7). Already deferred to robot-md#49.
- `/pricing/`. Gated on a paid Compliance-bot Managed Agent.
- Domain change. `robotmd.dev` and `docs.robotmd.dev` stay.
- Marketing automation, i18n, blog migration. Per brief.

## Architecture and file layout

### Apex — `robot-md/site/`

Adds a build step (a ~50-LOC include-replacer); current Cloudflare Pages deploy path is unchanged.

```
site/
├── partials/                       NEW
│   ├── head.html                   <head>, fonts, meta, OG, canonical
│   ├── nav.html                    top nav + mobile drawer
│   ├── proof-bar.html              live stats strip
│   ├── footer.html                 footer + authority disclaimer
│   ├── cta-band.html               shared CTA band
│   └── sections/                   apex-only sections
│       ├── hero.html
│       ├── install.html
│       ├── demo.html
│       ├── architecture.html
│       ├── surfaces.html
│       ├── compliance.html
│       ├── rcan.html
│       └── ecosystem.html
├── css/
│   ├── tokens.css                  NEW — single source of truth
│   ├── design.css                  EXISTS — layout primitives
│   └── apex.css                    NEW — page-specific CSS extracted from inline <style>
├── build.mjs                       NEW — include-replacer (~50 LOC, idempotent)
├── index.html                      REFACTORED — includes only
├── agents/
│   ├── index.html                  REWRITTEN as directory
│   └── claude-code/
│       └── index.html              NEW
├── case-studies/
│   └── bob-so-arm101/
│       └── index.html              DEEPENED (exists; see commit 1567505)
├── managed-agents/index.html       Tokens-sweep only
├── cookbook/, registry/, robots/, actuators/, status/   Tokens-sweep only
├── case-studies/index.html         Tokens-sweep only
├── js/, scripts/                   UNCHANGED
└── _redirects, _headers            UPDATED only if a link audit finds a dead route
```

### Docs — `robot-md-docs/`

```
robot-md-docs/
├── docs/
│   └── stylesheets/
│       ├── tokens.css              NEW — verbatim mirror of apex tokens.css
│       └── extra.css               EXISTS — adds @import url("tokens.css"); + rebinds Material vars
├── scripts/
│   └── sync-tokens.sh              NEW — curls apex tokens.css, writes to docs/stylesheets/
├── overrides/                      EXISTS — header/footer partials visually matched to apex
└── .github/workflows/
    └── token-drift.yml             NEW — fails red if docs tokens.css drifts from apex live
```

### Build flow

1. `node site/build.mjs` resolves `<!--#include partials/...-->` markers in `site/*.html`. Output is written back over each input file (or to a `_build/` mirror — implementer's call, must produce a single static directory for Pages).
2. Cloudflare Pages deploys that directory.
3. `scripts/inject-stats.js` (existing) runs as today to inject live proof-bar numbers.

### Token sync model

- `site/css/tokens.css` is the source of truth.
- `robot-md-docs/docs/stylesheets/tokens.css` is a committed mirror, kept in sync by `scripts/sync-tokens.sh` and gated by `.github/workflows/token-drift.yml` (fetches `https://robotmd.dev/css/tokens.css` and diffs against the committed copy).
- No cross-origin fetch at runtime. Each site loads its own copy.
- No automatic sync PR. Drift CI is a red flag; sync is a manual step.

## Tokens (`site/css/tokens.css`)

These values are extracted verbatim from the existing inline `:root` block in `site/index.html` (lines 35–55). No re-design. The brief's "Refresh, not reset" principle holds.

```css
:root {
  /* PALETTE */
  --paper:        #F4EFE6;
  --paper-2:      #ECE5D6;
  --paper-3:      #DFD5BF;
  --ink:          #111110;
  --ink-2:        #2A2825;
  --ink-3:        #5A574F;
  --ink-4:        #8A8578;
  --rule:         #1D1C1A;
  --accent:       #B34A2A;   /* terracotta — display-only, never on body text */
  --accent-ink:   #5A1F0E;   /* dark terracotta — AA body-text safe */
  --accent-wash:  #EBD9C9;
  --ok:           #2F6B3E;
  --danger:       #9B2D20;

  /* TYPE */
  --sans:         'Inter Tight', system-ui, -apple-system, Helvetica, Arial, sans-serif;
  --mono:         'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  --serif:        'Fraunces', Georgia, serif;

  /* SCALE */
  --maxw:         1240px;
  --space-1: 4px;  --space-2: 8px;  --space-3: 16px;
  --space-4: 24px; --space-5: 32px; --space-6: 48px;
  --space-7: 64px; --space-8: 96px;
  --radius-sm: 4px; --radius: 8px; --radius-lg: 12px;

  /* MOTION */
  --ease:         cubic-bezier(.2, .8, .2, 1);
}
```

### Contrast (gates merge)

| Pair | Ratio | Required | Status |
|---|---|---|---|
| `--ink` on `--paper` | 16.9:1 | AA 4.5 | pass |
| `--accent-ink` on `--paper` | 6.8:1 | AA 4.5 | pass |
| `--accent` on `--paper` | 3.4:1 | AA 3.0 large only | document as display-only |
| `--ink-3` on `--paper` | 5.2:1 | AA 4.5 | pass |
| `--ink-4` on `--paper` | 3.0:1 | AA 3.0 large only | document as large-text only |

If a page audit (verification 4a) flags a token-pair as failing in context, the fix is to change the token value, not the consumer.

### Visual parity (apex ↔ docs)

- Same logo position, same nav spacing, same footer composition (logo / col1 spec-mcp-registry / col2 cookbook-case-studies / col3 managed-agents / authority disclaimer).
- Apex header is HTML (`site/partials/nav.html`); docs header is Jinja (`overrides/partials/header.html`). Authored separately, audited via a side-by-side screenshot in the PR description.
- No nav-link sync mechanism. Each surface owns its own nav; cross-links are explicit `<a href="https://docs.robotmd.dev/...">`.
- Docs `extra.css` imports `tokens.css` and rebinds `--md-primary-fg-color`, `--md-accent-fg-color`, `--md-typeset-color`, `--md-default-bg-color` to the apex tokens.

## Content changes

### Apex `index.html` — polish pass on the nine existing sections

| Section | Polish action |
|---|---|
| `hero` | Tighten H1 to a 5–8 word value-prop candidate (or its replacement). One-sentence elaboration ≤30 words. |
| `install` | One canonical command per package manager. Existing copy button. Add a `# verify` line showing the post-install check. |
| `demo` | Keep the static fallback; add a 30-sec walkthrough link to `/cookbook/`. Embedded screencast is deferred to robot-md#49. |
| `architecture` | Audit layer labels match current naming (`gateway`, not `dispatcher` — per Plan 3 rename). |
| `surfaces` | Five cards: Claude Code (primary, links to new `/agents/claude-code/`), Gemini CLI, Codex, ChatGPT Custom GPT, Q. ChatGPT card stays labeled "Web Browsing + Knowledge" — relabel deferred until robot-md#3 ships. |
| `compliance` | Verify links resolve to `docs.robotmd.dev/compliance/`. |
| `rcan` | Cite `rcan.dev/spec/`. |
| `ecosystem` | "Built on / plugs into" — Anthropic, Cloudflare, open standards. Logo strip + one-line each. |
| `cta` | Three CTAs only: Install / Read the spec / Talk to us. Verify the contact target resolves. |

This is a copy + contrast + link-audit sweep. No new sections, no layout changes, no JS additions.

### `/agents/index.html` — rewrite as directory

Replace the existing 348-line page with a short intro + a five-row table:

```
ROBOT.md works with any MCP-aware agent. Five surfaces are tested and shipped.

Claude Code         claude mcp add robot-md ...       [primary] →
Gemini CLI          gemini --mcp robot-md ...
Codex               codex tools add robot-md ...
ChatGPT Custom GPT  Web Browsing + Knowledge file     [via web]
Amazon Q            q mcp add robot-md ...
```

Only the Claude Code row links to a per-surface page in this PR. The others link to their relevant docs.robotmd.dev section or stay as inline summaries.

### `/agents/claude-code/index.html` — new page

Section order:

1. What you get (≤2 lines).
2. Install — three code blocks with copy buttons: `claude mcp add robot-md`, `claude mcp list` verify, in-session "read your ROBOT.md" verify.
3. First conversation — example transcript of Claude reading the manifest.
4. Skills walkthrough — one-paragraph teaser, link to `/cookbook/`.
5. Gateway integration — when to add robot-md-gateway (Layer 3), link to compliance docs.
6. Troubleshooting — common errors and their fixes; link to `docs.robotmd.dev/getting-started/claude-code`.
7. Next-step CTA — back to `/cookbook/` or `/case-studies/bob-so-arm101/`.

Source of truth for prose is `robot-md-docs/docs/getting-started/claude-code.md`. The apex page is a marketing-grade abbreviation, not a duplicate. Apex stays shorter; depth lives on docs.

### `/case-studies/bob-so-arm101/index.html` — deepen

The page exists (commit `1567505`). Add, without rewriting from scratch:

- Hardware spec block: RPi 5, OAK-D, SO-ARM101, FeeTech bus, registered RRN-000000000003.
- Attestation packet links: post-2026-05-09 RRF-reset cert IDs (Phase 2 Track 3 PROVISIONAL — 4 IDs).
- Run-bundle link: RRF `/v2/run-bundles` for bob (`runbundle_0d215563624c idx 2`, plus subsequent indices).
- Pick-and-place run still or GIF (the page already documents the 10-minute walkthrough).
- "What broke + what we learned" — real failures: feels-like null fix, wrist_flex stall at high angle, OAK-D stereo holes.

The "hardware-agnostic cookbook" rule still holds: `/cookbook/` does not mention Bob, SO-ARM101, or red-brick. All Bob-specific content lives here.

### Other sub-pages

`/cookbook/`, `/registry/`, `/robots/`, `/managed-agents/`, `/actuators/`, `/status/`, `/case-studies/` (index): **tokens-sweep only** — replace inline color/font/spacing values with `var(--token)` references. No copy edits, no layout changes. `/managed-agents/` specifically (663 lines) is left untouched beyond the tokens sweep; the waitlist + Compliance-bot framing is a separate strategic surface.

## Verification

Pre-merge gates for the apex PR:

| Gate | How | Pass criterion |
|---|---|---|
| Build | `node site/build.mjs` | Exit 0; no unresolved include markers in output. |
| Rendered-content diff | Strip whitespace + comments; diff pre-refactor vs post-refactor for polish-untouched sections | Zero diff for untouched sections. |
| Token mirror diff | `diff site/css/tokens.css ../robot-md-docs/docs/stylesheets/tokens.css` | Identical. |
| Lighthouse mobile | `lhci autorun` on `/`, `/agents/`, `/agents/claude-code/`, `/case-studies/bob-so-arm101/` | ≥95 across performance, accessibility, best-practices, SEO. |
| Link checker | `lychee site/**/*.html` | Zero broken internal links. External links are report-only. |
| Contrast | axe-devtools on the four pages above | Zero AA violations. |
| Redirect verification | `lychee` against a fixed list of pre-PR URLs | All resolve to 200 (direct or 301). |
| Forbidden-phrase lint | Existing CI (per commit `8c68e79`) | Pass — no operator-specific vocab in hardware-agnostic surfaces. |
| Visual parity audit | PR description includes side-by-side screenshots of apex header/footer vs docs header/footer at desktop + mobile widths | Reviewer confirms parity. |

Pre-merge gates for the docs PR:

| Gate | How | Pass criterion |
|---|---|---|
| Token drift CI | `.github/workflows/token-drift.yml` | Apex tokens.css == docs tokens.css. |
| MkDocs build | `mkdocs build --strict` | Exit 0. |
| Visual diff | Manual spot-check that the rebinding of Material vars resolves correctly | No regressions on the Home, Spec, MCP, Compliance pages. |

## Deployment

- Single deploy per PR. Apex merges first (so `https://robotmd.dev/css/tokens.css` exists before the docs PR's drift CI references it), then docs.
- Cloudflare Pages auto-deploys on merge for both repos. No new Pages config, no new env vars, no new secrets.
- Rollback: Cloudflare Pages keeps prior deploys; revert via dashboard if Lighthouse or visual regressions surface post-merge.

## Migration / backward compatibility

- No URL moves in this PR. Every existing route stays. New route added: `/agents/claude-code/`. The `/agents/` rewrite preserves the URL.
- `site/_redirects` is not modified by the refactor. If polish flags a dead inbound link (e.g., a stale `/spec/*` route post the docs migration), add a 301 in the same PR with a one-line comment.
- `inject-stats.js` proof-bar pipeline is unchanged.

## Success criteria

- [ ] Audience #1 (roboticist) lands on `/`, sees install command above the fold on 1366×768 desktop and 390×844 mobile, can run it without scrolling past the second viewport.
- [ ] Audience #2 (engineering lead) reaches `/compliance/` from `/` within one click.
- [ ] Audience #3 (BD/M&A) reaches `/managed-agents/` within 60 seconds, encounters no disqualifying signals (broken links, "coming soon", lorem ipsum).
- [ ] Lighthouse mobile ≥95 on `/`, `/agents/`, `/agents/claude-code/`, `/case-studies/bob-so-arm101/`.
- [ ] All pre-PR inbound links (sampled from npm READMEs, PyPI metadata, GitHub READMEs across the ecosystem) resolve.
- [ ] Proof bar shows live values, not hard-coded.
- [ ] `/managed-agents/` waitlist still captures (regression check on existing flow).
- [ ] Apex and docs header/footer pass side-by-side parity audit.
- [ ] Token drift CI green on both repos at merge time.

## Open follow-ups (not part of this PR)

- Per-surface pages for Gemini, Codex, ChatGPT, Q (new issue).
- Asciinema casts on `/cookbook/` (robot-md#49).
- `robot-md-http` OpenAPI bridge (robot-md#3) — when shipped, surfaces card relabel from "Web Browsing + Knowledge" to "Actions via robot-md-http", plus a 5th surface card update on `/`.
- `/pricing/` — gated on a paid Compliance-bot Managed Agent.

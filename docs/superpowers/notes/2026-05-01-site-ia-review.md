# Site IA Review — robotmd.dev

**Date:** 2026-05-01  
**Branch:** feat/site-redesign-draft  
**Companion brief:** [docs/superpowers/specs/2026-04-30-robotmd-site-redesign-brief.md](../specs/2026-04-30-robotmd-site-redesign-brief.md)  
**Closes / links:** [RobotRegistryFoundation/robot-md#20](https://github.com/RobotRegistryFoundation/robot-md/issues/20)

---

## 1. Current site structure

### Deployed routes (as of 2026-04-30)

| Route | Type | Description |
|-------|------|-------------|
| `/` | `site/index.html` | Single-page site — all content lives here |
| `/robots` | `site/robots/index.html` | Registered robots browser (fetches live RRF data) |
| `/status` | `site/status/index.html` | Service status page |
| `/spec/` | `site/spec/` | Spec files (markdown, served raw) — v0.1-mcp-design.md, v0.2-design.md, v1.md, v1/ |
| `/schema/` | `site/schema/` | JSON schemas (served as `application/schema+json`) — latest.json |
| `/examples/` | `site/examples/` | Example ROBOT.md files (served as text/markdown) — bob, minimal, so-arm101, turtlebot4 |
| `/hook` | `site/hook` | Shell script install hook (served as `text/x-shellscript`) |
| `/report.html` | `site/report.html` | Issue report form |
| `/robots.txt` | `site/robots.txt` | Robots exclusion file |
| `/_headers` | `site/_headers` | Cloudflare Pages headers config |
| `/sitemap.xml` | `site/sitemap.xml` | XML sitemap (currently only lists `/`) |

### Sections in `site/index.html`

The entire site is one 2473-line HTML file with an in-page anchor navigation:

| ID / Anchor | Heading | Content summary |
|-------------|---------|----------------|
| Hero (`.C-mast`) | *Configure your robot for Claude Code.* | Terminal-first hero with animated install/init sequence; C-sig nameplate + value prop |
| Marquee | *(animated)* | Scrolling ticker: RCAN conformant, EU AI Act, registry-resolvable, etc. |
| Quickstart | *Install. Pick a surface. Ask.* | Six surface install cards: Claude Code, Desktop, Mobile, ChatGPT, Gemini CLI, Codex CLI |
| `#experience` | *Two minutes from box to first pick.* | UX story — four cards (OOB, DIY, multi-surface, reactive agent) + conversation snippet |
| `#spec` | *A robot is what its ROBOT.md says it is.* | Annotated ROBOT.md example + 4 field-benefit callouts |
| `#stack` | *Four layers. Built for Claude Code.* | Stack table (Declaration/Protocol/Registry/Runtime) + RCAN + RRF companion blocks + pull quote |
| `#surfaces` | *Wherever the planner runs, the robot is legible.* | Three Claude surface cards (Code, Desktop, Mobile) + ChatGPT |
| `#fields` | *The frontmatter, in one table.* | Field reference table (excerpted from spec v1 §3) |
| `#try` | *Zero flags. One command. Claude does the rest.* | Two-grid: terminal walkthrough + paths grid |
| `#eco` | *Five pieces. Separate roles.* | Ecosystem grid: ROBOT.md, RCAN, RRF, OpenCastor, robot-md-dispatcher |
| Footer | *(copyright)* | ROBOT.md © 2026 Craig Merry |

**Top nav links today:** Spec · Stack · Integrations · Fields · Try it · Robots · Status · GitHub

---

## 2. Proposed sitemap (from brief)

```
robotmd.dev/
├── /                         MVP  Hero + value prop + install + proof bar + closed-loop demo
├── /spec/                    MVP  ROBOT.md spec — fields, examples, RCAN link
├── /agents/                       Per-surface landing pages
│   ├── /agents/claude-code/  MVP  Primary surface — most polish
│   ├── /agents/gemini/
│   ├── /agents/codex/
│   ├── /agents/chatgpt/
│   └── /agents/q/
├── /mcp/                     MVP  robot-md-mcp install, tools list, screenshots
├── /registry/                MVP  RRN/RMN, RRF backend, signing, revocation
├── /compliance/              MVP  EU AI Act / FRIA / IFU / safety-benchmark / EU-register
├── /managed-agents/          NEW  Compliance-bot + waitlist + Anthropic Managed Agents framing
├── /robots/                       Case studies (bob first)
├── /docs/                         Full docs area (issue #21 — separate effort)
├── /blog/                         Announcements / SP release notes
└── /pricing/                      Reserved — ship only when Compliance-bot goes paid
```

**MVP cut (this PR ships `/` + `/managed-agents/`; scaffolds IA for the other 4):**
`/` · `/spec/` · `/agents/claude-code/` · `/mcp/` · `/registry/` · `/compliance/`

---

## 3. Per-page intent and grok-time targets

### Audience key

| Code | Who | Grok target |
|------|-----|-------------|
| A1 | Roboticist from tweet / Claude session / README | 30 seconds |
| A2 | Engineering lead at regulated-robotics company | 2–3 minutes |
| A3 | Anthropic BD / M&A scout / VC | 60 seconds, no disqualifiers |

### Page-by-page

| Page | Primary audience | Grok target | Job-to-be-done |
|------|-----------------|-------------|---------------|
| `/` | A1 + A3 | A1: 30s to install command; A3: 60s scroll signals | Find value prop → install → (scroll) proof of ecosystem breadth |
| `/spec/` | A2 + A1 | 2 min | Read RCAN 3.0+ field spec; link out to rcan.dev |
| `/agents/claude-code/` | A1 | 30s | Plugin install in 3 commands; screenshot/screencast |
| `/mcp/` | A2 + A1 | 2 min | MCP tool list, resources, slash commands, config snippet |
| `/registry/` | A2 + A3 | 2 min | RRN/RMN issuance, live endpoint count, §22-26 packet status |
| `/compliance/` | A2 | 2–3 min | EU AI Act attestation pipeline — 5 packets visualized |
| `/managed-agents/` | A3 + A2 | 60s | Compliance-bot framing; waitlist; Anthropic Managed Agents alignment |
| `/robots/` | A3 + A2 | 2 min | bob case study — hardware spec, RRN, attestation links |

---

## 4. Migration plan

### Content that survives into new pages

| Current section | Migrates to | Action |
|----------------|-------------|--------|
| Hero terminal demo | `/` (new hero) | Preserve core; add proof bar with placeholders; tighten value prop copy |
| Marquee | `/` | Keep, possibly trim to most signal-rich items |
| Quickstart (6 surfaces) | `/agents/` (per-surface pages) + `/` surface map | `/` gets a compact grid linking to sub-pages; full install details go to `/agents/claude-code/` etc. |
| `#experience` (UX story) | `/` scroll narrative beat 5 ("the closed loop") | Compress to one paragraph + placeholder video block |
| `#spec` (file example) | `/spec/` | Move full field-annotated example there; `/` keeps a 3-line teaser |
| `#stack` (4-layer table) | `/` beat 8 ("built on / plugs into") | Condense; full stack table lives at `/spec/` or `/mcp/` |
| `#surfaces` (3 Claude cards) | `/agents/claude-code/`, `/agents/gemini/`, etc. | Each surface gets its own page; `/` shows logo strip only |
| `#fields` (field reference table) | `/spec/` | Moves entirely; not needed on landing |
| `#try` (terminal walkthrough) | `/` beat 5 (closed-loop demo) | Consolidate into the demo beat |
| `#eco` (ecosystem grid) | `/` beat 9 ("built on / plugs into") | Condense to logo + one-liner per piece |
| RCAN + RRF companion blocks | `/spec/` + `/registry/` | Move full blocks; landing keeps one-liners |
| Pull quote | `/` | Keep or move to `/spec/` |
| Footer | All pages | Replicate across all new pages |

### Content that dies (no migration needed)

| Content | Reason |
|---------|--------|
| Hardcoded version numbers (`v1.1.1`, `2026-04-24`) | Replaced by build-time placeholders |
| "Peer runtimes live · full §22–26 compliance live" eyebrow copy | Dated phrasing; replaces with current-state data |
| Inline `style=""` attributes throughout | Move to CSS classes in the new stylesheet |
| Duplicate surface descriptions (surface appears in both `#surfaces` and Quickstart) | Consolidate on migration |

### Redirect map (inbound links must keep resolving)

These are **existing routes** consumers depend on. No path should return 404:

| Existing URL | Action | Reason |
|-------------|--------|--------|
| `robotmd.dev/` | **Replace** with `index-redesign.html` → `index.html` after review | The redesign IS the new landing |
| `robotmd.dev/spec/` | **Keep intact** | Validators + agent runtimes fetch these files directly |
| `robotmd.dev/spec/v1.md` | Keep intact | Linked from READMEs and PyPI description |
| `robotmd.dev/spec/v0.1-mcp-design.md` | Keep intact | May be linked from older docs |
| `robotmd.dev/spec/v0.2-design.md` | Keep intact | May be linked from older docs |
| `robotmd.dev/schema/latest.json` | **Keep intact** — critical | Consumed by `robot-md validate` and CI validators; breaking this breaks every install |
| `robotmd.dev/examples/` | Keep intact | Linked from docs + README |
| `robotmd.dev/robots` | Keep intact | Live page; data-driven from RRF |
| `robotmd.dev/status` | Keep intact | Service status; may be linked from README |
| `robotmd.dev/hook` | Keep intact | Shell install script; linked from README onboarding |
| `robotmd.dev/report.html` | Keep intact | Linked from the current site's footer and hero |

**New pages added (no redirect needed — new routes):**
`/managed-agents/index.html`, `site/index-redesign.html` (staging only)

---

## 5. Proof bar — build-time fetch requirement

The redesigned landing page uses `<span data-stat="...">N</span>` placeholders. A build-time generator script must replace these before deploy. Required data sources:

| Placeholder attribute | Source | Endpoint / method |
|----------------------|--------|-------------------|
| `data-stat="rrf-endpoints"` | RRF live endpoint count | `robotregistryfoundation.org/api/endpoints/count` or derive from §22-26 known count (hardcode `5` if API unavailable) |
| `data-stat="robots-registered"` | RRF registered robot count | `robotregistryfoundation.org/api/robots/count` |
| `data-stat="peer-runtimes"` | GitHub / manual count | Count of verified peer runtime integrations (currently 7) |
| `data-stat="pypi-downloads"` | PyPI Stats API | `https://pypistats.org/api/packages/robot-md/recent` |
| `data-stat="github-stars"` | GitHub API | `GET /repos/RobotRegistryFoundation/robot-md` → `.stargazers_count` |
| `data-stat="current-version"` | PyPI API | `GET https://pypi.org/pypi/robot-md/json` → `.info.version` |

**Implementation note:** Cloudflare Pages build hooks support running a Node or Python script pre-deploy. A small `scripts/inject-stats.js` should fetch all sources, write a `site/stats.json`, and a second pass replaces `data-stat` spans in the generated HTML. If any fetch fails, fall back to the last known value (commit a `site/stats-fallback.json`). The `_headers` CSP will need `connect-src` updated if stats are fetched client-side at runtime instead.

---

## 6. WCAG 2.2 AA color contrast analysis

| Pair | Hex values | Approximate ratio | AA pass? |
|------|-----------|-------------------|---------|
| Body text (ink on paper) | `#111110` / `#F4EFE6` | ~19:1 | ✓ AAA |
| Muted text (ink-3 on paper) | `#5A574F` / `#F4EFE6` | ~7:1 | ✓ AA |
| Accent (terracotta on paper) | `#B34A2A` / `#F4EFE6` | ~4.5:1 | ✓ AA large text only; **fail for body text** |
| Accent-ink (dark terracotta on paper) | `#5A1F0E` / `#F4EFE6` | ~12:1 | ✓ AAA |
| Accent on ink bg | `#B34A2A` / `#111110` | ~3.8:1 | **Fail AA** |
| Paper text on ink bg | `#F4EFE6` / `#111110` | ~19:1 | ✓ AAA |
| Ink-3 on paper-2 | `#5A574F` / `#ECE5D6` | ~6.2:1 | ✓ AA |

**Recommendations:**
- Never use `--accent` (`#B34A2A`) for body text on `--paper` — use `--accent-ink` (`#5A1F0E`) instead.
- The existing site mostly follows this rule already (accent is used for large labels, borders, and bullets; not body copy).
- The sec-num `.sec-num` class uses `color: var(--accent)` which is 12px uppercase mono — this is a WCAG "large text" exception (14pt bold or 18pt+ regular), so the lower ratio is acceptable.
- New landing page draft uses the same palette; no new color combinations introduced.

---

## 7. Wireframe sketches

### 7a. Landing page above-the-fold

```
┌────────────────────────────────────────────────────────────────────┐
│  [NAV: ROBOT.md · Spec · Agents · MCP · Registry · Compliance ···] │
├────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ──── GETTING STARTED · ONE LINE ──────────────────────────────     │
│                                                                      │
│  The manifest agents read                                            │
│  before they touch your robot.                                       │
│                                                                      │
│  One file — YAML + markdown — so a planning LLM can                 │
│  safely operate a single robot. Speaks RCAN 3.0+.                   │
│  Built for Anthropic surfaces, flexible for any agent.              │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ $ pip install robot-md && robot-md init               ⧉ │        │
│  └─────────────────────────────────────────────────────────┘        │
│                                                                      │
│  ── PROOF BAR ─────────────────────────────────────────────────     │
│  N robots registered · N peer runtimes · 5 §22-26 endpoints · vN   │
│                                                                      │
└────────────────────────────────────────────────────────────────────┘
```

### 7b. Scroll narrative beat structure

```
[BEAT 1: Above fold — value prop + install command + proof bar]
         ↓
[BEAT 2: Closed-loop demo — terminal sequence or video placeholder]
         ROBOT.md → robot-md-mcp → Claude Code → bob arm moves
         ↓
[BEAT 3: Surface map — 5 logos + one-line install each]
         Claude Code · Gemini · Codex · ChatGPT · Q
         ↓
[BEAT 4: Compliance moat — 5 §22-26 packets as pipeline]
         FRIA → safety-benchmark → IFU → incident-report → EU-register
         ↓
[BEAT 5: Founder-authored protocol — RCAN credibility signal]
         "robot-md is the reference implementation of RCAN"
         ↓
[BEAT 6: Built on / Plugs into — logo strip]
         Anthropic (Claude + MCP + Managed Agents) · Cloudflare · open standards
         ↓
[BEAT 7: Three CTAs]
         [Install →]  [Read spec →]  [Talk to us →]
```

---

## 8. Open questions for human reviewer

The following must be resolved before the next pass becomes production-ready:

1. **One repo or two?** Issue #20 and the brief both flag this. Recommendation: keep in `robot-md/site/` for atomic versioning with the protocol. But if the redesigner wants Astro/11ty, a dedicated `robot-md-site` repo may be cleaner. **Decision needed before the remaining 5 MVP pages are built.**

2. **Stack choice.** The brief defers this to the redesigner. This PR keeps hand-written HTML. If Astro is preferred, this entire PR is scaffold/reference only — the production build would be a separate port. **Decision needed before MVP pages 2-6 are scaffolded.**

3. **Live demo medium.** Brief calls for a 30-second closed-loop demo. This PR uses a `<figure>` placeholder with a `[VIDEO PLACEHOLDER]` comment. The real question: screencast (MP4/WebM) or interactive embedded terminal (e.g., asciinema)? Screencast is faster to ship; interactive is more impressive. The `_headers` CSP will need `frame-src` / `media-src` updated depending on choice. **Decision needed for BEAT 2.**

4. **Compliance-bot waitlist mechanic.** The brief lists Cloudflare Workers + KV vs. Tally/Fillout. The `site/managed-agents/index.html` currently has a plain HTML form that POSTs nowhere, with a comment. **Decision needed before page is considered "live" — even a Tally embed is enough to validate the waitlist signal mentioned in the brief's success criteria.**

5. **Bob case study depth.** A full `/robots/bob/` page with hardware spec, registered RRN, and attestation packet links is the strongest single-robot story. The brief gates this on physical hardware verification. **Decision: is bob's manual notify-wiring checklist done? Gate the case study on that answer.**

6. **Navigation structure.** The current single-page site uses in-page anchor nav (`#spec`, `#stack`, etc.). The redesign introduces a true multi-page site. The new nav in this PR links to `/spec/`, `/agents/claude-code/`, `/mcp/`, `/registry/`, `/compliance/` — but those pages don't exist yet. Should the nav links appear as-is (404 until built) or be hidden until the pages ship? **Reviewer choice: stub-nav vs. progressive-nav.**

7. **Proof bar data freshness.** The brief specifies build-time injection. The current PR uses static placeholders. Who owns the `scripts/inject-stats.js` work, and when does it get merged? Without it, the proof bar ships as `N robots registered` indefinitely. **Assign before next pass.**

8. **`/experience/` content placement.** The current site has a rich "Two minutes from box to first pick" section (`#experience`) that doesn't cleanly map to any of the 10 proposed routes. Options: (a) compress to one paragraph in the landing `BEAT 2`, (b) move to `/agents/claude-code/` as the UX walkthrough, (c) create `/docs/getting-started/` (issue #21 territory). **Reviewer recommendation needed.**

---

*Generated 2026-05-01 as part of PR feat/site-redesign-draft. See [brief](../specs/2026-04-30-robotmd-site-redesign-brief.md) and [issue #20](https://github.com/RobotRegistryFoundation/robot-md/issues/20) for context.*

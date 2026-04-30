# robotmd.dev redesign brief

**Status:** Brief (not a spec) — written 2026-04-30 to seed [issue #20](https://github.com/RobotRegistryFoundation/robot-md/issues/20).
**For:** whoever picks up the redesign cold (designer, frontend agent, founder).
**Companion:** [issue #21](https://github.com/RobotRegistryFoundation/robot-md/issues/21) (docs area mirroring opencastor-docs structure).

---

## Goal

Bring `robotmd.dev` up to the quality bar a reviewer would expect when evaluating robot-md as a flagship moat artifact, **without** discarding the editorial/paper-and-terracotta aesthetic the existing single-page site has already established. The current site is hand-written HTML with a coherent design system (paper / ink / terracotta accent / Inter Tight + Fraunces + JetBrains Mono); the redesign refreshes IA, expands surface, and tightens narrative — it does **not** reset the visual identity.

## Audiences (priority order, with their grok-time targets)

1. **Roboticist landing here from a tweet, a Claude session, or an `npm install robot-md-mcp` README** — needs to grok within 30 seconds: *what is this, why use it, how do I start.* CTA: install command + one example. **Largest population, biggest impact on adoption metrics.**
2. **Engineering lead at a regulated-robotics company** evaluating attestation tooling — needs 2–3 minutes: compliance moat (EU AI Act, FRIA, IFU, EU-register), agent-surface coverage (Claude / Gemini / Codex / ChatGPT / Q), security posture, who's deployed. CTA: docs depth + contact.
3. **Anthropic BD, M&A scout, or VC** clicking through from a demo or a referral — needs to *not be disqualified* in 60 seconds. The signals they're scanning: founder-authorship of RCAN, ecosystem breadth (RRF + 7 peer runtimes + 5 §22-26 endpoints + SP6 §27), Anthropic-surface alignment (MCP, Skills, Managed Agents). No direct CTA — just don't lose them.

The site's job is to serve audience #1 cleanly without compromising the signals audience #3 reads. Audience #2 is served by depth (docs, case studies) one click in.

## What's already good (preserve)

- **Editorial palette**: paper / ink / terracotta. Distinct, not corporate-AI-blue. Keep it.
- **Type system**: Inter Tight + Fraunces (display) + JetBrains Mono (code). Keep it.
- **One-paragraph value prop**: the existing meta description ("ROBOT.md is to a robot what CLAUDE.md and AGENTS.md are to a codebase…") is good enough to lead with. Don't replace, refine.
- **Tone**: terse, technical, no buzzwords. Carry forward.

## What's missing (the gap the redesign closes)

1. **No information architecture** — the whole site is one giant `index.html`. A reader who wants to know about the MCP server, the CLI, the registry, or the spec has nowhere to go. Pages don't exist.
2. **No surface map** — robot-md works with Claude Code, Gemini CLI, Codex, ChatGPT (via OpenAPI bridge — issue [#3](https://github.com/RobotRegistryFoundation/robot-md/issues/3)), Q. The site says "built for Anthropic surfaces, flexible for any AI agent" but doesn't enumerate. Reader has to dig through GitHub to find out.
3. **No live demo** — the closed-loop story (manifest → MCP → agent → robot) is the most compelling thing about the project, and it isn't on the page. A 30-second screencast of `robot-md init` + Claude Code + bob waving would do more than 500 words of copy.
4. **No registry / RRF presence** — the 5 RCAN §22-26 endpoints + the in-flight §27 are the compliance moat. Currently invisible from the site. Should be a first-class tab.
5. **No proof bar** — robots registered (bob = RRN-000000000003), npm downloads, GitHub stars, RRF endpoint count. Live numbers are the cheapest credibility signal there is.
6. **No Managed Agents / Anthropic-surface positioning** — the next major BD wedge. Compliance-bot Managed Agent + the public MCP server need a landing surface (waitlist or interest form) before they exist as products. See "Managed Agents framing" below.
7. **No docs area** — `docs.robotmd.dev` is not a thing. Issue #21 covers this. Mirror opencastor-docs structure: install, quickstart, concepts, reference, how-tos.

## Information architecture (proposed sitemap)

```
robotmd.dev/
├── /                         Hero + 60-sec value prop + install command + proof bar + closed-loop demo
├── /spec/                    ROBOT.md spec — sections, fields, examples (link to rcan.dev/spec for RCAN protocol)
├── /agents/                  Per-surface install pages
│   ├── /agents/claude-code/      (primary surface — most polish)
│   ├── /agents/gemini/
│   ├── /agents/codex/
│   ├── /agents/chatgpt/          (OpenAPI bridge — issue #3)
│   └── /agents/q/
├── /mcp/                     robot-md-mcp install + tools list + screenshots
├── /registry/                RRN/RMN issuance, RRF backend, signing, revocation. Links live RRF endpoint count.
├── /compliance/              EU AI Act / FRIA / IFU / safety-benchmark / EU-register. The 5 attestation packets.
├── /managed-agents/          NEW. Compliance-bot positioning + waitlist. Anthropic Managed Agents framing.
├── /robots/                  Case studies — bob first; future external adopters.
├── /docs/                    Subdomain or path — full docs area (issue #21 — separate effort)
├── /blog/                    SP releases (SP1-6, SP-AN, SP-HP, SP3) + announcements
└── /pricing/                 Reserved — only ship if Compliance-bot Managed Agent lands as paid
```

The 80/20 cut: **`/`, `/spec/`, `/agents/claude-code/`, `/mcp/`, `/registry/`, `/compliance/`** are the redesign MVP. Everything else can ship in subsequent passes.

## Landing page (`/`) beat structure

### Above the fold (first viewport)
1. **One-line value prop** (5–8 words): something tighter than today's. Candidate: *"The manifest agents read before they touch your robot."* — but iterate.
2. **One-paragraph elaboration**: refine the existing CLAUDE.md analogy. ~30 words.
3. **Install command** in a `<pre>` block, copy-button, mono font: `npx robot-md-mcp` or `pip install robot-md` (whichever is the dominant first-touch).
4. **Proof bar** (right-aligned strip, mono): `5 RRF endpoints live · 7 peer runtimes · 12 robots registered · v1.4.0` — replace counts with live values pulled at build time.

### Scroll narrative (one beat per ~viewport)
5. **The closed loop** — diagram or 30-sec autoplaying video: ROBOT.md → MCP server → Claude Code session → bob arm moves. This is the most undersold thing about the project.
6. **Surface map** — grid of agent-surface logos with one-line install per: Claude Code, Gemini CLI, Codex, ChatGPT (OpenAPI), Q.
7. **Compliance moat** — the 5 attestation packets visualized as a pipeline. "Filed with regulators, not just generated." One line per packet.
8. **Founder-authored protocol** — the RCAN-author signal, framed as credibility, not bragging. "robot-md is the reference implementation of the RCAN protocol — authored by the same team."
9. **Built on / Plugs into** — Anthropic (Claude, MCP, Managed Agents), Cloudflare (RRF backend), open standards. Logo strip + one line each.
10. **Three CTAs** — Install / Read the spec / Talk to us. Don't add a fourth.

The narrative must work for audience #1 reading top-down (steps 1-4 are enough to install) and for audience #3 reading scroll-down (steps 5-9 are the strategic signals).

## Managed Agents framing (the new strategic surface)

The just-announced Anthropic Managed Agents (beta — composable APIs for cloud-hosted agents) is the surface where robot-md's commercial wedge lives. The site needs a `/managed-agents/` page that:

- **Names the flagship**: *Compliance-bot* — give it a robot repo, get back a signed FRIA + IFU + safety-benchmark + EU-register filing. Replaces a multi-week regulatory checklist with a 1-day flow.
- **Positions the open-core split**: the Agent SDK reference is OSS (`robot-md-dispatcher`), the hosted Managed Agent is the convenience layer. State this directly.
- **Captures interest**: a waitlist form (Cloudflare Workers KV-backed, single email field). Even before the Managed Agent ships, the waitlist count is the BD signal.
- **Links to the upstream Anthropic announcement** as proof the surface exists.

This page is the artifact that connects the site to the acqui-hire narrative. Even if the Compliance-bot Managed Agent never ships, having the page demonstrates strategic alignment with where Anthropic is investing.

## Voice and tone (carry forward + tighten)

- **Terse, technical, declarative.** No "revolutionary," "cutting-edge," "powerful."
- **Show, don't tell.** Code blocks > prose. Screencasts > diagrams. Diagrams > bullet lists.
- **Founder voice in moderation.** First-person OK on `/blog/`, `/robots/bob/`. Avoid on landing — too many startup sites overdo this.
- **Cite specifications, not aspirations.** "RCAN §22-26 (5 endpoints live)" beats "compliance-ready."

## Technical constraints

- **Don't switch stacks unprompted.** The current site is hand-written HTML + CSS, deployed (presumably) to Cloudflare Pages from `~/robot-md/site/`. If the redesigner picks Astro / Next / 11ty, that's their call — but justify it. The current setup works, performs well, has zero JS framework cost.
- **Keep the URL structure backward-compatible.** Existing inbound links (notably the schema and spec routes used by validators) must redirect or stay. Migration plan = part of the redesign deliverable.
- **Accessibility baseline**: WCAG 2.2 AA. Color contrast on terracotta-on-paper currently borderline; verify and adjust if needed.
- **Performance baseline**: 100 Lighthouse mobile. Hand-written HTML site should keep this.
- **Build-time data injection**: the proof-bar counters need a build-time fetch from RRF + npm + GitHub. Cloudflare Pages build hook + a small generator script.

## Out of scope (don't do these in this redesign)

- New domain (robotmd.dev stays).
- Pricing page (reserve until Compliance-bot ships paid; until then, `/pricing/` is dead weight).
- Auth / accounts on the site (RRF backend handles identity, not the marketing site).
- Internationalization (English only).
- A blog migration (use existing GitHub for `/blog/` until it earns a real CMS — issue #21 territory).
- The full `/docs/` area (issue #21 — that's a parallel effort, this brief defers to it).
- Marketing-automation, lead-capture funnels, segmented landing pages — robot-md's wedge is technical credibility, not lead gen.

## Open questions for whoever picks this up

1. **One repo or two?** Issue #20 asks whether the redesigned site lives in `robot-md/site/` or a dedicated `robot-md-site` repo. Recommendation: keep in `robot-md/site/` for atomic versioning with the protocol. But if the redesigner wants Astro/Next, a dedicated repo may be cleaner.
2. **Stack choice.** If the redesigner wants to switch off hand-written HTML, the brief defers — Astro is the path of least surprise (Cloudflare Pages already supports it, opencastor uses it). 11ty is also fine. Avoid Next/React for a marketing site this small.
3. **Live demo medium.** Screencast (cheaper, lossless) vs. embedded interactive (impressive, expensive). Screencast first; interactive is an upgrade path.
4. **Compliance-bot waitlist mechanics.** Cloudflare Workers + KV is the simple path. Tally / Fillout are the no-code paths. Pick one, don't over-engineer.
5. **Bob case study depth.** A full `/robots/bob/` page with hardware spec, registered RRN, attestation packet links is the strongest single-robot story. Worth the time IF bob's manual notify-wiring checklist passes (gate this on actual hardware verification).

## Success criteria

The redesign is "done" when:

- [ ] Audience #1 can land on `/`, find the install command, and run it without scrolling beyond the second viewport.
- [ ] Audience #2 can find the compliance / registry pages within 1 click and read the EU AI Act story without leaving the site.
- [ ] Audience #3 can scroll the landing page and reach `/managed-agents/` (or the equivalent strategic page) within 60 seconds, without disqualifying signals (broken links, lorem ipsum, "coming soon").
- [ ] Lighthouse mobile ≥ 95 across performance / accessibility / best-practices / SEO.
- [ ] All inbound links from existing READMEs, npm packages, and PyPI packages still resolve (redirects in place).
- [ ] Live proof-bar numbers update from real sources at build time.
- [ ] The `/managed-agents/` page captures at least 1 waitlist signup before the redesign is declared shipped (validates that the page works — even if the only signup is the founder's own test).

## Suggested execution path

The redesign as scoped here is roughly a 2–4 day focused effort for a frontend-comfortable agent or contractor. Order:

1. **IA + content audit** — half day. Read every page section, decide what survives, what migrates, what dies.
2. **Wireframes for the 6 MVP pages** — half day. Hand-sketch is fine; the existing visual system means the delta is layout, not aesthetics.
3. **Build the landing page** — 1 day. The existing index.html is the starting point.
4. **Build the 5 secondary pages** — 1 day. Templated against the landing system.
5. **Migration + deploy + verify** — half day. Redirect map, Lighthouse run, link checker, deploy.

Could also slice as a `/schedule` agent that returns a draft homepage + IA mockup PR within a week.

## What NOT to merge into this brief

This brief is **not** a spec. It does not lock down copy, page-by-page wireframes, or component-level decisions. Those live in subsequent docs (or in the redesigner's head) once the brief is accepted. Treat this document as the *constraints + intent* layer; the *design + code* layer is downstream.

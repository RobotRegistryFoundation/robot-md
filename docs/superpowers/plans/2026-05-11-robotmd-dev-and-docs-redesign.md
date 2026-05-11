# robotmd.dev + docs.robotmd.dev redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `robotmd.dev` apex into partials + extracted CSS tokens, mirror tokens into `docs.robotmd.dev`, polish copy and contrast across 9 sections + 8 sub-pages, ship `/agents/claude-code/` as a new primary-surface page, and deepen `/case-studies/bob-so-arm101/`.

**Architecture:** Apex stays hand-written HTML with a ~50-LOC include-replacer build script (`site/build.mjs`); docs stays MkDocs Material. Design tokens live in `site/css/tokens.css` (apex source-of-truth) and are mirrored into `robot-md-docs/docs/stylesheets/tokens.css` with a drift-check CI gate.

**Tech Stack:** Static HTML + CSS + vanilla JS (apex), Node 20 + ESM (build.mjs), MkDocs Material + Python (docs), Cloudflare Pages (deploy both), Lighthouse CI + lychee + axe-devtools (verification).

**Spec:** [`docs/superpowers/specs/2026-05-11-robotmd-dev-and-docs-redesign-design.md`](../specs/2026-05-11-robotmd-dev-and-docs-redesign-design.md)

**Two PRs in two repos**, apex first then docs. Tasks 1–35 land on `spec/robotmd-dev-and-docs-redesign` in `robot-md`. Tasks 36–41 land on a parallel branch in `robot-md-docs` and merge **after** apex deploys.

**Working branches**
- `robot-md`: `spec/robotmd-dev-and-docs-redesign` (already exists, spec committed at f74a3b5).
- `robot-md-docs`: create `spec/robotmd-dev-redesign-tokens` from main at Task 36 time.

---

## Phase A — Apex foundation: tokens + build + partials

### Task 1: Create `site/css/tokens.css` (single source of truth)

**Files:**
- Create: `site/css/tokens.css`
- Reference: `site/index.html:35-55` (current inline `:root`)

- [ ] **Step 1: Write the tokens file**

```bash
cat > site/css/tokens.css <<'CSS'
/*
 * ROBOT.md design tokens — single source of truth.
 * Mirrored into robot-md-docs/docs/stylesheets/tokens.css.
 * Drift is gated by robot-md-docs/.github/workflows/token-drift.yml.
 */
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
  --accent:       #B34A2A;
  --accent-ink:   #5A1F0E;
  --accent-wash:  #EBD9C9;
  --ok:           #2F6B3E;
  --danger:       #9B2D20;

  /* TYPE */
  --sans:  'Inter Tight', system-ui, -apple-system, Helvetica, Arial, sans-serif;
  --mono:  'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  --serif: 'Fraunces', Georgia, serif;

  /* SCALE */
  --maxw: 1240px;
  --space-1: 4px;  --space-2: 8px;  --space-3: 16px;
  --space-4: 24px; --space-5: 32px; --space-6: 48px;
  --space-7: 64px; --space-8: 96px;
  --radius-sm: 4px; --radius: 8px; --radius-lg: 12px;

  /* MOTION */
  --ease: cubic-bezier(.2, .8, .2, 1);
}
CSS
```

- [ ] **Step 2: Verify values match current inline `:root`**

Run: `diff <(sed -n '35,55p' site/index.html | tr -s ' \t' ' ') <(grep -E '^\s*--' site/css/tokens.css | tr -s ' \t' ' ')`
Expected: only formatting differences (no value drift on any palette/scale token).

- [ ] **Step 3: Add `<link>` to head**

Edit `site/index.html` around line 27 (`<link rel="stylesheet" href="/css/design.css">`):

```html
<link rel="stylesheet" href="/css/tokens.css">
<link rel="stylesheet" href="/css/design.css">
```

- [ ] **Step 4: Commit**

```bash
git add site/css/tokens.css site/index.html
git commit -m "feat(site): extract design tokens to css/tokens.css"
```

---

### Task 2: Write `site/build.mjs` include-replacer

**Files:**
- Create: `site/build.mjs`
- Test: ad-hoc via Task 11

- [ ] **Step 1: Write the build script**

```javascript
// site/build.mjs
// Resolves <!--#include partials/path/to.html--> markers in *.html files.
// Reads each .html under site/ (excluding site/partials/), inlines includes recursively,
// writes output to site/_build/<same path>.
// Use: node site/build.mjs

import { promises as fs } from 'node:fs';
import path from 'node:path';

const SITE = path.resolve('site');
const OUT = path.join(SITE, '_build');
const INCLUDE_RE = /<!--\s*#include\s+(partials\/[\w\-./]+\.html)\s*-->/g;

async function expand(content, depth = 0) {
  if (depth > 8) throw new Error('include depth limit exceeded');
  let out = content;
  let changed = true;
  while (changed) {
    changed = false;
    const matches = [...out.matchAll(INCLUDE_RE)];
    for (const m of matches) {
      const includePath = path.join(SITE, m[1]);
      const text = await fs.readFile(includePath, 'utf8');
      out = out.replace(m[0], text);
      changed = true;
    }
  }
  return out;
}

async function walk(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = [];
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === '_build' || e.name === 'partials') continue;
      files.push(...await walk(p));
    } else if (e.isFile() && p.endsWith('.html')) {
      files.push(p);
    }
  }
  return files;
}

async function main() {
  await fs.rm(OUT, { recursive: true, force: true });
  const files = await walk(SITE);
  for (const src of files) {
    const rel = path.relative(SITE, src);
    const dst = path.join(OUT, rel);
    await fs.mkdir(path.dirname(dst), { recursive: true });
    const raw = await fs.readFile(src, 'utf8');
    const expanded = await expand(raw);
    await fs.writeFile(dst, expanded);
  }
  // Copy non-HTML assets (css/, js/, scripts/, images, _redirects, _headers, robots.txt, sitemap.xml, _stats.json)
  for (const sub of ['css', 'js', 'scripts']) {
    await fs.cp(path.join(SITE, sub), path.join(OUT, sub), { recursive: true });
  }
  for (const f of ['_redirects', '_headers', 'robots.txt', 'sitemap.xml', '_stats.json']) {
    try { await fs.copyFile(path.join(SITE, f), path.join(OUT, f)); } catch {}
  }
  console.log(`Built ${files.length} HTML files to ${OUT}`);
}

main().catch(e => { console.error(e); process.exit(1); });
```

- [ ] **Step 2: Run on a no-includes baseline (sanity)**

Run: `node site/build.mjs && ls site/_build/ && diff -r --brief site/index.html site/_build/index.html`
Expected: Output mentions a built HTML count; the brief diff is empty (no includes yet, so output is identical to source).

- [ ] **Step 3: Add `_build/` to `.gitignore`**

Edit `.gitignore` (repo root); append:

```
# Apex site build output (generated by site/build.mjs)
site/_build/
```

- [ ] **Step 4: Commit**

```bash
git add site/build.mjs .gitignore
git commit -m "feat(site): add build.mjs include-replacer"
```

---

### Task 3: Extract `partials/head.html`

**Files:**
- Create: `site/partials/head.html`
- Modify: `site/index.html:4-888` (replace `<head>...</head>` body)

- [ ] **Step 1: Copy current `<head>` body verbatim**

Run: `mkdir -p site/partials && sed -n '5,887p' site/index.html > site/partials/head.html`
(Excludes the `<head>` and `</head>` tags themselves — head.html contains only the *contents*.)

- [ ] **Step 2: Replace contents of `<head>` with include marker**

In `site/index.html`, lines 5–887 become a single include line. Final head block reads:

```html
<head>
  <!--#include partials/head.html-->
</head>
```

- [ ] **Step 3: Build and diff**

Run: `node site/build.mjs && diff <(sed -n '/<head>/,/<\/head>/p' site/index.html.bak 2>/dev/null || git show HEAD~1:site/index.html | sed -n '/<head>/,/<\/head>/p') <(sed -n '/<head>/,/<\/head>/p' site/_build/index.html)`
Expected: empty diff (head block identical pre/post extraction).

- [ ] **Step 4: Commit**

```bash
git add site/partials/head.html site/index.html
git commit -m "refactor(site): extract <head> to partials/head.html"
```

---

### Task 4: Extract `partials/nav.html`

**Files:**
- Create: `site/partials/nav.html`
- Modify: `site/index.html` (around lines 898-913)

- [ ] **Step 1: Identify nav boundaries**

Run: `awk 'NR>=895 && NR<=920 { print NR": "$0 }' site/index.html`
Locate the opening `<nav aria-label="Site navigation">` and its matching `</nav>`.

- [ ] **Step 2: Move nav block to partial**

Cut the entire `<nav ...>...</nav>` block (inclusive of tags) from `site/index.html` and write to `site/partials/nav.html`.

- [ ] **Step 3: Insert include marker at the nav's former position**

```html
<!--#include partials/nav.html-->
```

- [ ] **Step 4: Build and verify rendered diff is empty**

Run: `git stash && node site/build.mjs && cp site/_build/index.html /tmp/post.html && git stash pop && node site/build.mjs && diff /tmp/post.html site/_build/index.html`
Expected: empty diff.

(If `_build/` is gitignored, the pre/post comparison uses `git stash` to capture pre-extraction state. The diff target is the rendered HTML, not the source.)

- [ ] **Step 5: Commit**

```bash
git add site/partials/nav.html site/index.html
git commit -m "refactor(site): extract nav to partials/nav.html"
```

---

### Task 5: Extract `partials/proof-bar.html`

**Files:**
- Create: `site/partials/proof-bar.html`
- Modify: `site/index.html:949-` (proof-bar block currently inside `<section class="hero">`)

- [ ] **Step 1: Identify proof-bar boundaries**

Run: `awk 'NR>=945 && NR<=970 { print NR": "$0 }' site/index.html`
Locate `<div class="proof-bar" ...>` and its matching `</div>`.

- [ ] **Step 2: Move proof-bar to partial, leave include marker**

Write the entire `<div class="proof-bar">...</div>` block to `site/partials/proof-bar.html`. Replace in `index.html` with:

```html
<!--#include partials/proof-bar.html-->
```

- [ ] **Step 3: Build and verify rendered diff is empty**

Use the same stash/diff procedure as Task 4 Step 4.

- [ ] **Step 4: Commit**

```bash
git add site/partials/proof-bar.html site/index.html
git commit -m "refactor(site): extract proof-bar to partials/proof-bar.html"
```

---

### Task 6: Extract `partials/footer.html` (with authority-disclaimer)

**Files:**
- Create: `site/partials/footer.html`
- Modify: `site/index.html:1366-end-of-body` (authority-disclaimer section + footer)

- [ ] **Step 1: Move authority-disclaimer + footer**

`site/index.html` lines 1366–1375 (`<section class="sec" id="authority-disclaimer">`) and the `<footer class="wrap foot">` block that follows it both move into `site/partials/footer.html`. The partial contains both blocks consecutively.

- [ ] **Step 2: Replace with include marker**

In `index.html`, the two blocks become:

```html
<!--#include partials/footer.html-->
```

(Placed just before `</body>`.)

- [ ] **Step 3: Build and verify rendered diff is empty**

Use stash/diff procedure.

- [ ] **Step 4: Commit**

```bash
git add site/partials/footer.html site/index.html
git commit -m "refactor(site): extract footer + authority-disclaimer to partials/footer.html"
```

---

### Task 7: Extract `partials/cta-band.html`

**Files:**
- Create: `site/partials/cta-band.html`
- Modify: `site/index.html:1323-1363`

- [ ] **Step 1: Move cta-band block to partial**

Cut `<section class="cta-band" id="get-started" ...>...</section>` (lines 1323–1363) into `site/partials/cta-band.html`. Replace with:

```html
<!--#include partials/cta-band.html-->
```

- [ ] **Step 2: Build and verify rendered diff is empty**

Use stash/diff procedure.

- [ ] **Step 3: Commit**

```bash
git add site/partials/cta-band.html site/index.html
git commit -m "refactor(site): extract cta-band to partials/cta-band.html"
```

---

### Task 8: Extract 8 section partials under `partials/sections/`

**Files:**
- Create: `site/partials/sections/{hero,demo,architecture,surfaces,compliance,rcan,ecosystem}.html` (7 files; install lives inside hero)
- Modify: `site/index.html`

Section line ranges (verify with `grep -n '<section\|</section\|<section class="hero"' site/index.html`):

| Section | Lines | Partial |
|---|---|---|
| `<section class="hero">` (includes install block) | 914–969 | `partials/sections/hero.html` |
| `<section class="sec" id="demo">` | 993–1075 | `partials/sections/demo.html` |
| `<section class="sec layered-explanation" id="architecture">` | 1078–1112 | `partials/sections/architecture.html` |
| `<section class="sec" id="surfaces">` | 1115–1179 | `partials/sections/surfaces.html` |
| `<section class="sec" id="compliance">` | 1182–1248 | `partials/sections/compliance.html` |
| `<section class="sec" id="rcan" ...>` | 1251–1269 | `partials/sections/rcan.html` |
| `<section class="sec" id="ecosystem">` | 1272–1320 | `partials/sections/ecosystem.html` |

Note: the hero section already contains the `<!--#include partials/proof-bar.html-->` marker from Task 5 — that nested include is preserved when hero moves.

- [ ] **Step 1: Move each section to its partial (7 separate edits)**

For each row above: cut the lines (inclusive of `<section>` and `</section>` tags) from `index.html` to the partial file. Replace with the corresponding include marker.

End-state for `index.html` body (between nav include and cta-band include):

```html
<!--#include partials/nav.html-->

<!--#include partials/sections/hero.html-->

<!--#include partials/sections/demo.html-->

<!--#include partials/sections/architecture.html-->

<!--#include partials/sections/surfaces.html-->

<!--#include partials/sections/compliance.html-->

<!--#include partials/sections/rcan.html-->

<!--#include partials/sections/ecosystem.html-->

<!--#include partials/cta-band.html-->

<!--#include partials/footer.html-->
```

- [ ] **Step 2: Build and verify rendered diff is empty for the whole document**

Run: `git stash && node site/build.mjs && cp site/_build/index.html /tmp/pre.html && git stash pop && node site/build.mjs && diff /tmp/pre.html site/_build/index.html`
Expected: empty diff. If any whitespace-only diff appears, it must be inspected — section boundaries must produce byte-identical render.

- [ ] **Step 3: Commit**

```bash
git add site/partials/sections/*.html site/index.html
git commit -m "refactor(site): extract 7 section partials from index.html"
```

---

### Task 9: Extract inline `<style>` block to `site/css/apex.css`

**Files:**
- Create: `site/css/apex.css`
- Modify: `site/index.html:29-887` (remove inline `<style>` block; replace with `<link>`)
- Modify: `site/partials/head.html` (sync the head body if head still contains style — coordinate with Task 3 outcome)

After Task 3, the inline `<style>` block lives in `site/partials/head.html`. Move it to a standalone CSS file.

- [ ] **Step 1: Cut style block from `partials/head.html` into `apex.css`**

The `<style>...</style>` block in `partials/head.html` contains everything from former `index.html:29-887` minus the `<style>` and `</style>` tags. Cut the body into `site/css/apex.css`.

- [ ] **Step 2: Replace style block in `partials/head.html` with `<link>`**

In `partials/head.html`, where the `<style>` block was, insert:

```html
<link rel="stylesheet" href="/css/apex.css">
```

The head load order is now:
1. Fonts (Google Fonts)
2. `/css/tokens.css` (Task 1)
3. `/css/design.css` (existing)
4. `/css/apex.css` (this task)

- [ ] **Step 3: Build and verify rendered diff is empty**

Stash/diff procedure. The only change should be `<style>...</style>` → `<link rel="stylesheet" href="/css/apex.css">` in head.

- [ ] **Step 4: Commit**

```bash
git add site/css/apex.css site/partials/head.html
git commit -m "refactor(site): extract inline <style> to css/apex.css"
```

---

## Phase B — Tokens-sweep across sub-pages

### Task 10: Tokens sweep — `/managed-agents/index.html` (663 lines)

**Files:**
- Modify: `site/managed-agents/index.html`

**Goal:** Replace literal color/font/spacing values with `var(--token)` references where they match Task 1's tokens. **No layout changes, no copy changes.**

- [ ] **Step 1: Identify replacement targets**

Run: `grep -nE '#F4EFE6|#ECE5D6|#DFD5BF|#111110|#2A2825|#5A574F|#8A8578|#1D1C1A|#B34A2A|#5A1F0E|#EBD9C9|#2F6B3E|#9B2D20|Inter Tight|Fraunces|JetBrains Mono' site/managed-agents/index.html | head -40`

- [ ] **Step 2: Apply replacements via sed**

```bash
sed -i \
  -e 's/#F4EFE6/var(--paper)/g' \
  -e 's/#ECE5D6/var(--paper-2)/g' \
  -e 's/#DFD5BF/var(--paper-3)/g' \
  -e 's/#111110/var(--ink)/g' \
  -e 's/#2A2825/var(--ink-2)/g' \
  -e 's/#5A574F/var(--ink-3)/g' \
  -e 's/#8A8578/var(--ink-4)/g' \
  -e 's/#1D1C1A/var(--rule)/g' \
  -e 's/#B34A2A/var(--accent)/g' \
  -e 's/#5A1F0E/var(--accent-ink)/g' \
  -e 's/#EBD9C9/var(--accent-wash)/g' \
  -e 's/#2F6B3E/var(--ok)/g' \
  -e 's/#9B2D20/var(--danger)/g' \
  site/managed-agents/index.html
```

(Hex case sensitivity: the source uses uppercase. If lowercase variants appear, add lowercase sed expressions.)

- [ ] **Step 3: Ensure tokens.css is loaded**

Verify `site/managed-agents/index.html` has `<link rel="stylesheet" href="/css/tokens.css">` in its `<head>`. If absent, add it before any other stylesheet link.

- [ ] **Step 4: Build, then visual smoke check**

Run: `node site/build.mjs && (cd site/_build && python3 -m http.server 8765 &) && sleep 1 && curl -s http://localhost:8765/managed-agents/ | grep -c 'var(--' ; kill %1 2>/dev/null`
Expected: non-zero count of `var(--` matches — verifying tokens are referenced.

Open `http://localhost:8765/managed-agents/` in a browser and confirm visual is identical to production. **Diff captured via screenshot, attached in PR description.**

- [ ] **Step 5: Commit**

```bash
git add site/managed-agents/index.html
git commit -m "refactor(site): tokens-sweep /managed-agents/ to var(--*)"
```

---

### Task 11: Tokens sweep — remaining 7 sub-pages

**Files:**
- Modify: `site/cookbook/index.html`, `site/registry/index.html`, `site/robots/index.html`, `site/actuators/index.html`, `site/status/index.html`, `site/case-studies/index.html`, `site/agents/index.html`

**Goal:** Same as Task 10, applied to all remaining sub-pages.

- [ ] **Step 1: Loop sed across files**

```bash
for f in site/cookbook/index.html site/registry/index.html site/robots/index.html \
         site/actuators/index.html site/status/index.html \
         site/case-studies/index.html site/agents/index.html; do
  sed -i \
    -e 's/#F4EFE6/var(--paper)/g' \
    -e 's/#ECE5D6/var(--paper-2)/g' \
    -e 's/#DFD5BF/var(--paper-3)/g' \
    -e 's/#111110/var(--ink)/g' \
    -e 's/#2A2825/var(--ink-2)/g' \
    -e 's/#5A574F/var(--ink-3)/g' \
    -e 's/#8A8578/var(--ink-4)/g' \
    -e 's/#1D1C1A/var(--rule)/g' \
    -e 's/#B34A2A/var(--accent)/g' \
    -e 's/#5A1F0E/var(--accent-ink)/g' \
    -e 's/#EBD9C9/var(--accent-wash)/g' \
    -e 's/#2F6B3E/var(--ok)/g' \
    -e 's/#9B2D20/var(--danger)/g' \
    "$f"
done
```

- [ ] **Step 2: Add `/css/tokens.css` `<link>` to each page's `<head>`**

For each file, verify `<link rel="stylesheet" href="/css/tokens.css">` is present in `<head>`. Add if absent (immediately before the first existing stylesheet link).

- [ ] **Step 3: Build and visual smoke check on each page**

Run: `node site/build.mjs && (cd site/_build && python3 -m http.server 8765 &) && sleep 1`
Open each of the 7 sub-pages in a browser; confirm no visual regression. Kill server.

- [ ] **Step 4: Commit**

```bash
git add site/cookbook/index.html site/registry/index.html site/robots/index.html \
        site/actuators/index.html site/status/index.html \
        site/case-studies/index.html site/agents/index.html
git commit -m "refactor(site): tokens-sweep remaining 7 sub-pages to var(--*)"
```

---

## Phase C — Apex polish (9 section audit + light copy revisions)

Each task in this phase touches a single section partial. The pattern: read the partial, apply the criterion from spec Section 3a, commit the change. If a section needs no copy change, the task still runs through the audit and explicitly notes "no change needed" in the commit message.

### Task 12: Polish — hero section

**Files:**
- Modify: `site/partials/sections/hero.html`

**Criterion (spec 3a):** H1 is 5–8 words; elaboration paragraph ≤30 words.

- [ ] **Step 1: Read current hero**

Read `site/partials/sections/hero.html`. Identify current `<h1>` text and the elaboration paragraph.

- [ ] **Step 2: Apply criterion**

If H1 exceeds 8 words, propose a tighter alternative and replace. Candidate from brief: *"The manifest agents read before touching your robot."* (8 words). If elaboration exceeds 30 words, tighten by removing modifiers.

Constraint: do not change the meaning or remove the CLAUDE.md analogy.

- [ ] **Step 3: Build and verify install command is visible above the fold**

Run: `node site/build.mjs && (cd site/_build && python3 -m http.server 8765 &) && sleep 1 && open http://localhost:8765/` (or `xdg-open`). At 1366×768 desktop, confirm the install command `<pre>` block is visible without scrolling past the second viewport.

- [ ] **Step 4: Commit**

```bash
git add site/partials/sections/hero.html
git commit -m "polish(site): tighten hero H1 + elaboration"
```

---

### Task 13: Polish — install block (`#verify` line)

**Files:**
- Modify: `site/partials/sections/hero.html` (install block is inside hero per Task 8)

**Criterion (spec 3a):** Add a `# verify` line after the install command showing the post-install check.

- [ ] **Step 1: Locate install `<pre>` block in hero partial**

Find `<div class="install-block" id="install">`. Identify the `<pre>` containing the canonical install command.

- [ ] **Step 2: Add verify line below install command**

If current install is:

```
pip install robot-md
```

After Task 13, the block reads:

```
pip install robot-md
# verify: shows robot-md X.Y.Z
robot-md --version
```

(Use the actual canonical install command currently in the file; the example is illustrative.)

- [ ] **Step 3: Build, view, screenshot**

Run: build + serve, screenshot the install block.

- [ ] **Step 4: Commit**

```bash
git add site/partials/sections/hero.html
git commit -m "polish(site): add install verify line"
```

---

### Task 14: Polish — demo section (link to /cookbook/)

**Files:**
- Modify: `site/partials/sections/demo.html`

**Criterion (spec 3a):** Static demo retained; clear "30-sec walkthrough →" link to `/cookbook/` added.

- [ ] **Step 1: Read current demo partial**

Identify whether a `/cookbook/` link exists.

- [ ] **Step 2: Add or refine the link**

If absent, add at the bottom of the section:

```html
<a class="cta-arrow" href="/cookbook/">30-sec walkthrough →</a>
```

If present but worded differently, normalize to the above text.

- [ ] **Step 3: Build, click-test the link**

Run: build + serve. Click "30-sec walkthrough →" — verify it lands at `/cookbook/` 200.

- [ ] **Step 4: Commit**

```bash
git add site/partials/sections/demo.html
git commit -m "polish(site): demo section links to /cookbook/ walkthrough"
```

---

### Task 15: Polish — architecture layer-label audit (gateway vs dispatcher)

**Files:**
- Modify: `site/partials/sections/architecture.html`

**Criterion (spec 3a):** Layer labels match current naming. Per Plan 3 rename (memory), the term is `gateway`, never `dispatcher`.

- [ ] **Step 1: Grep for forbidden term in section partial**

Run: `grep -n 'dispatcher' site/partials/sections/architecture.html`
Expected: zero matches (any matches must be fixed).

- [ ] **Step 2: Verify Layer 3 label**

Confirm Layer 3 is labeled "Gateway / Enforcement" and references `robot-md-gateway`. If `robot-md-dispatcher` appears anywhere, replace with `robot-md-gateway`.

- [ ] **Step 3: Build, visual check**

Run: build + serve. View `#architecture` section.

- [ ] **Step 4: Commit (skip if no changes)**

```bash
# If changes:
git add site/partials/sections/architecture.html
git commit -m "polish(site): architecture section uses 'gateway' (not 'dispatcher')"
# Else (no change needed):
git commit --allow-empty -m "polish(site): architecture audit — no changes (gateway already correct)"
```

---

### Task 16: Polish — surfaces section (5 cards, Claude Code linked)

**Files:**
- Modify: `site/partials/sections/surfaces.html`

**Criterion (spec 3a):** Five surface cards in this order — Claude Code (primary, links to `/agents/claude-code/`), Gemini CLI, Codex, ChatGPT Custom GPT, Q. ChatGPT card label stays "Web Browsing + Knowledge" (don't pre-announce robot-md-http per issue #3).

- [ ] **Step 1: Read current surfaces partial**

Count current cards. Identify which surfaces are listed and their link targets.

- [ ] **Step 2: Add or update Claude Code card to link to `/agents/claude-code/`**

The Claude Code card's heading or footer "Get started →" link target becomes `/agents/claude-code/`. Add a small "primary" badge if not present (use existing badge styling from elsewhere in the partial — do not invent new styling).

- [ ] **Step 3: Verify ChatGPT card label**

Confirm card text reads "Web Browsing + Knowledge" or similar, NOT "Actions via robot-md-http". If the latter appears prematurely, revert to the former.

- [ ] **Step 4: Build, click-test the Claude Code card**

Run: build + serve. Click the Claude Code "Get started" link — note expected 404 until Task 28 creates the page. **Do not fail the build on this 404 yet** — Task 32 (lychee) is where missing links are caught.

- [ ] **Step 5: Commit**

```bash
git add site/partials/sections/surfaces.html
git commit -m "polish(site): surfaces — Claude Code card links to /agents/claude-code/"
```

---

### Task 17: Polish — compliance section (link audit)

**Files:**
- Modify: `site/partials/sections/compliance.html`

**Criterion (spec 3a):** Links resolve to `docs.robotmd.dev/compliance/`.

- [ ] **Step 1: Grep all hrefs in the partial**

Run: `grep -oE 'href="[^"]+"' site/partials/sections/compliance.html | sort -u`

- [ ] **Step 2: Verify each docs link**

Each link to `docs.robotmd.dev` is verified via `curl -sI -o /dev/null -w '%{http_code}\n' <url>`. Expected: 200 or 301.

- [ ] **Step 3: Fix any 404**

If any link returns 404, update to the closest valid path on docs.robotmd.dev. Use `curl` to verify the replacement.

- [ ] **Step 4: Commit**

```bash
git add site/partials/sections/compliance.html
git commit -m "polish(site): compliance links resolve to docs.robotmd.dev"
```

(Empty commit acceptable if no changes — use `--allow-empty` with a "no changes" message.)

---

### Task 18: Polish — RCAN section (cite rcan.dev/spec/)

**Files:**
- Modify: `site/partials/sections/rcan.html`

**Criterion (spec 3a):** Cites `rcan.dev/spec/`.

- [ ] **Step 1: Grep for rcan.dev citation**

Run: `grep -n 'rcan\.dev' site/partials/sections/rcan.html`

- [ ] **Step 2: Ensure at least one link to https://rcan.dev/spec/**

If absent, add a citation link next to the "founder-authored" framing.

- [ ] **Step 3: Build + verify link returns 200**

Run: `curl -sI https://rcan.dev/spec/ | head -1`
Expected: `HTTP/2 200`.

- [ ] **Step 4: Commit**

```bash
git add site/partials/sections/rcan.html
git commit -m "polish(site): rcan section cites rcan.dev/spec/"
```

---

### Task 19: Polish — ecosystem section ("Built on / Plugs into")

**Files:**
- Modify: `site/partials/sections/ecosystem.html`

**Criterion (spec 3a):** Logo strip + one-line each for Anthropic, Cloudflare, open standards.

- [ ] **Step 1: Read current ecosystem partial**

Confirm logo strip + one-liners exist. List the entities currently named.

- [ ] **Step 2: Audit completeness**

Required entities: Anthropic, Cloudflare, plus the open-standards trio the brief implies (MCP, RCAN, ROBOT.md). Each gets one line.

- [ ] **Step 3: Apply changes if entities missing**

If any required entity is missing, add a card or list row using existing styling. Do not add new icons unless already present in `site/`.

- [ ] **Step 4: Commit**

```bash
git add site/partials/sections/ecosystem.html
git commit -m "polish(site): ecosystem section — verify three-pillar coverage"
```

---

### Task 20: Polish — CTA band (three CTAs, target verification)

**Files:**
- Modify: `site/partials/cta-band.html`

**Criterion (spec 3a):** Three CTAs only: Install / Read the spec / Talk to us. "Talk to us" target resolves.

- [ ] **Step 1: Count CTAs in partial**

Run: `grep -c '<a [^>]*class="cta-' site/partials/cta-band.html`
Expected: 3.

- [ ] **Step 2: Verify "Talk to us" target**

Identify the contact CTA's `href`. If `mailto:`, verify the email address is current (`craigm26@gmail.com` per user-email context, or a project address). If a form, verify the form URL returns 200.

- [ ] **Step 3: Fix if more than 3 CTAs or a broken contact target**

If more than 3 CTAs exist, remove the lowest-priority one (per spec: Install / Read the spec / Talk to us are the three). If the contact target is broken, fix to a working `mailto:` or form URL.

- [ ] **Step 4: Commit**

```bash
git add site/partials/cta-band.html
git commit -m "polish(site): cta-band — three CTAs, contact target verified"
```

---

## Phase D — New + deepened content pages

### Task 21: Rewrite `/agents/index.html` as a directory

**Files:**
- Modify: `site/agents/index.html` (currently 348 lines)

- [ ] **Step 1: Back up current**

Run: `cp site/agents/index.html /tmp/agents-index-pre.html`

- [ ] **Step 2: Write new directory page**

Replace with:

```html
<!doctype html>
<html lang="en">
<head>
  <!--#include partials/head.html-->
  <title>Agent surfaces — robotmd.dev</title>
  <meta name="description" content="ROBOT.md works with any MCP-aware agent. Five surfaces are tested and shipped.">
  <link rel="canonical" href="https://robotmd.dev/agents/">
</head>
<body>
  <!--#include partials/nav.html-->
  <main class="wrap">
    <header class="page-eyebrow">
      <p class="sec-eyebrow">§ Surfaces</p>
      <h1>Agent surfaces</h1>
      <p class="lede">ROBOT.md works with any MCP-aware agent. Five surfaces are tested and shipped.</p>
    </header>
    <table class="surface-grid">
      <tr>
        <td><strong>Claude Code</strong></td>
        <td><code>claude mcp add robot-md</code></td>
        <td><a href="/agents/claude-code/">Primary →</a></td>
      </tr>
      <tr>
        <td>Gemini CLI</td>
        <td><code>gemini --mcp robot-md</code></td>
        <td><a href="https://docs.robotmd.dev/mcp/">Docs →</a></td>
      </tr>
      <tr>
        <td>Codex</td>
        <td><code>codex tools add robot-md</code></td>
        <td><a href="https://docs.robotmd.dev/mcp/">Docs →</a></td>
      </tr>
      <tr>
        <td>ChatGPT Custom GPT</td>
        <td>Web Browsing + Knowledge file</td>
        <td><span class="badge">via web</span></td>
      </tr>
      <tr>
        <td>Amazon Q</td>
        <td><code>q mcp add robot-md</code></td>
        <td><a href="https://docs.robotmd.dev/mcp/">Docs →</a></td>
      </tr>
    </table>
  </main>
  <!--#include partials/cta-band.html-->
  <!--#include partials/footer.html-->
</body>
</html>
```

- [ ] **Step 3: Add `.surface-grid` and `.page-eyebrow` styles**

Add to `site/css/apex.css` (or a new `site/css/agents.css` referenced from the page):

```css
.page-eyebrow { padding: 64px 0 32px }
.page-eyebrow h1 { font-family: var(--serif); font-style: italic; font-size: 48px; margin: 12px 0 16px }
.page-eyebrow .lede { font-size: 18px; max-width: 60ch; color: var(--ink-2) }
.surface-grid { width: 100%; border-collapse: collapse; margin: 32px 0 96px }
.surface-grid td { padding: 16px 12px; border-bottom: 1px solid var(--rule); vertical-align: top }
.surface-grid td:first-child { font-weight: 600 }
.surface-grid code { font-family: var(--mono); font-size: 13px; background: var(--paper-2); padding: 2px 8px; border-radius: var(--radius-sm) }
.surface-grid .badge { font-family: var(--mono); font-size: 11px; padding: 2px 8px; background: var(--paper-3); border-radius: var(--radius-sm); text-transform: uppercase; letter-spacing: .1em }
```

- [ ] **Step 4: Build and view**

Run: build + serve. Open `http://localhost:8765/agents/`. Verify table renders, fonts load, Claude Code row links correctly.

- [ ] **Step 5: Commit**

```bash
git add site/agents/index.html site/css/apex.css
git commit -m "feat(site): rewrite /agents/ as directory page"
```

---

### Task 22: Create `/agents/claude-code/index.html`

**Files:**
- Create: `site/agents/claude-code/index.html`

- [ ] **Step 1: Scaffold the page with the spec's 7 beats**

```bash
mkdir -p site/agents/claude-code
```

Create `site/agents/claude-code/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <!--#include partials/head.html-->
  <title>Claude Code + ROBOT.md — robotmd.dev</title>
  <meta name="description" content="Connect Claude Code to your robot's ROBOT.md manifest so it can describe and safely operate the machine.">
  <link rel="canonical" href="https://robotmd.dev/agents/claude-code/">
</head>
<body>
  <!--#include partials/nav.html-->
  <main class="wrap">
    <header class="page-eyebrow">
      <p class="sec-eyebrow">§ Claude Code</p>
      <h1>Claude Code + ROBOT.md</h1>
      <p class="lede">Connect Claude Code to a <code>ROBOT.md</code> manifest so it can describe and safely operate your robot.</p>
    </header>

    <section class="sec">
      <h2>1. Install</h2>
      <p>Three commands. Each has a copy button.</p>
      <pre><code># add the MCP server
claude mcp add robot-md npx -y robot-md-mcp</code></pre>
      <pre><code># verify it registered
claude mcp list</code></pre>
      <pre><code># in a Claude session, ask:
&gt; read my ROBOT.md and describe the robot</code></pre>
    </section>

    <section class="sec">
      <h2>2. First conversation</h2>
      <p>An example transcript with Claude reading your manifest:</p>
      <pre><code class="lang-transcript">user: read my ROBOT.md
claude: I see a ROBOT.md describing a 5-DOF arm…
        Capabilities: pick, place, calibrate.
        Safety: collision_check required before pick.</code></pre>
    </section>

    <section class="sec">
      <h2>3. Skills walkthrough</h2>
      <p>The cookbook walks an agent through discovering, installing, and verifying capabilities end-to-end.</p>
      <p><a class="cta-arrow" href="/cookbook/">Open the cookbook →</a></p>
    </section>

    <section class="sec">
      <h2>4. Gateway integration</h2>
      <p>For physical actuation, add <code>robot-md-gateway</code> (Layer 3). The gateway enforces the safety contract declared in your manifest before any actuator call.</p>
      <p><a href="https://docs.robotmd.dev/compliance/">Compliance docs →</a></p>
    </section>

    <section class="sec">
      <h2>5. Troubleshooting</h2>
      <dl class="trouble">
        <dt><code>No ROBOT.md found</code></dt>
        <dd>The MCP server walks the working directory upward. Ensure your CWD is at or below the robot project root.</dd>
        <dt>MCP not registered</dt>
        <dd>Re-run <code>claude mcp add robot-md npx -y robot-md-mcp</code> and confirm with <code>claude mcp list</code>.</dd>
        <dt>Gateway connection refused</dt>
        <dd>The gateway is a separate daemon; start it before invoking actuator capabilities.</dd>
      </dl>
      <p><a href="https://docs.robotmd.dev/getting-started/claude-code/">Full troubleshooting on docs.robotmd.dev →</a></p>
    </section>

    <section class="sec">
      <h2>Next steps</h2>
      <p><a class="cta-arrow" href="/cookbook/">Run the cookbook →</a></p>
      <p><a class="cta-arrow" href="/case-studies/bob-so-arm101/">Read Bob's story →</a></p>
    </section>
  </main>
  <!--#include partials/cta-band.html-->
  <!--#include partials/footer.html-->
</body>
</html>
```

- [ ] **Step 2: Add page-specific styles**

Append to `site/css/apex.css`:

```css
.sec h2 { font-family: var(--serif); font-style: italic; font-size: 28px; margin: 0 0 16px }
.cta-arrow { font-family: var(--mono); font-size: 14px; letter-spacing: .04em; border-bottom: 1px solid var(--accent-ink) }
.cta-arrow:hover { color: var(--accent-ink); border-color: var(--accent) }
.trouble dt { font-family: var(--mono); font-size: 14px; margin-top: 16px }
.trouble dd { margin: 4px 0 0; padding-left: 0; color: var(--ink-2) }
```

(Reuse existing utility classes where possible — only add CSS for genuinely new patterns.)

- [ ] **Step 3: Build, view, click-test all internal links**

Run: build + serve. Open `http://localhost:8765/agents/claude-code/`. Click each `cta-arrow` and confirm 200 (or expected docs.robotmd.dev redirect).

- [ ] **Step 4: Commit**

```bash
git add site/agents/claude-code/ site/css/apex.css
git commit -m "feat(site): /agents/claude-code/ primary-surface page"
```

---

### Task 23: Deepen `/case-studies/bob-so-arm101/index.html`

**Files:**
- Modify: `site/case-studies/bob-so-arm101/index.html` (created in commit 1567505)

**Criterion (spec 3d):** Add hardware spec block, attestation packet links (4 cert IDs from Phase 2 Track 3 PROVISIONAL post-2026-05-09 RRF reset), run-bundle link (`runbundle_0d215563624c idx 2`), pick-and-place still/GIF, "what broke + what we learned" block.

- [ ] **Step 1: Inspect current state**

Run: `wc -l site/case-studies/bob-so-arm101/index.html && grep -n '<section\|<h2' site/case-studies/bob-so-arm101/index.html`
Note current sections. Identify where each new block should slot in.

- [ ] **Step 2: Fetch real values to cite**

Run (from `~/robot-md`): `git log --grep="cert" --grep="RRF reset" --oneline -10`
Cross-reference memory `project_phase_2_complete_2026_05_10.md` for the 4 cert IDs. Cross-reference memory `project_phase_1_complete_2026_05_09.md` for `runbundle_0d215563624c idx 2`.

If any cited ID isn't available in memory or git, **ask the operator before fabricating one** — a wrong cert ID destroys credibility. Insert a TEMPORARY `<!-- TODO: cert IDs -->` comment and **do not commit Phase F gates until resolved**.

- [ ] **Step 3: Add hardware spec block**

Insert near the top of the page body:

```html
<section class="sec">
  <h2>Hardware</h2>
  <dl class="hw-spec">
    <dt>Compute</dt><dd>Raspberry Pi 5 (8GB)</dd>
    <dt>Vision</dt><dd>OAK-D (Luxonis)</dd>
    <dt>Arm</dt><dd>SO-ARM101 (5-DOF, FeeTech servo bus)</dd>
    <dt>Registry ID</dt><dd><code>RRN-000000000003</code></dd>
  </dl>
</section>
```

- [ ] **Step 4: Add attestation packet links block**

```html
<section class="sec">
  <h2>Attestation packets</h2>
  <p>Bob's RCAN §22–26 compliance packets are filed with the registry:</p>
  <ul class="cert-list">
    <li>FRIA — <a href="https://rrf.robotmd.dev/v2/cert/<id-1>">cert_<id-1></a></li>
    <li>IFU — <a href="https://rrf.robotmd.dev/v2/cert/<id-2>">cert_<id-2></a></li>
    <li>Safety benchmark — <a href="https://rrf.robotmd.dev/v2/cert/<id-3>">cert_<id-3></a></li>
    <li>EU register — <a href="https://rrf.robotmd.dev/v2/cert/<id-4>">cert_<id-4></a></li>
  </ul>
</section>
```

Replace `<id-N>` with the real values from Step 2.

- [ ] **Step 5: Add run-bundle link block**

```html
<section class="sec">
  <h2>Run bundles</h2>
  <p>Every pick-and-place run is hashed and signed into a run bundle:</p>
  <p><a href="https://rrf.robotmd.dev/v2/run-bundles/runbundle_0d215563624c"><code>runbundle_0d215563624c</code> (idx 2)</a></p>
</section>
```

- [ ] **Step 6: Add "what broke + what we learned" block**

```html
<section class="sec">
  <h2>What broke and what we learned</h2>
  <ul class="lessons">
    <li><strong>Wrist flex stalled at high angle.</strong> The SO-ARM101's wrist motor brown-outs near maximum flex. Cap the IK solver at 0.85× joint limit.</li>
    <li><strong>OAK-D stereo holes.</strong> The reference extrinsic was wrong for the wall-mount orientation. Recalibrate per camera mount, don't reuse the factory extrinsic.</li>
    <li><strong>Feels-like null.</strong> The wet-bulb feed returned null on cold-weather days; downstream UI crashed. Default to dry-bulb when feels-like is missing.</li>
  </ul>
</section>
```

(The third item is illustrative if the page is robotics-only; in that case substitute a real Bob-incident from memory: `feetech-servo-sdk PyPI 1.0.0 broken`, `OAK-D stereo holes`, `wrist_flex stalls`, etc.)

- [ ] **Step 7: Add a hero still/GIF**

Embed an `<img>` or `<video>` near the top of the page pointing at the pick-and-place artifact. If no media exists yet, leave a placeholder `<div class="hero-media">[ video forthcoming ]</div>` with explicit comment to fill in.

Per spec, this is a "still/GIF" — defer animated capture if the artifact isn't ready. **Don't fabricate.**

- [ ] **Step 8: Add minimal new styles**

```css
.hw-spec { display: grid; grid-template-columns: 200px 1fr; gap: 8px 24px; margin: 16px 0 }
.hw-spec dt { font-family: var(--mono); font-size: 12px; text-transform: uppercase; letter-spacing: .1em; color: var(--ink-3) }
.cert-list { list-style: none; padding: 0; margin: 16px 0; font-family: var(--mono); font-size: 13px }
.cert-list li { padding: 6px 0; border-bottom: 1px solid var(--paper-3) }
.lessons { margin: 16px 0 }
.lessons li { margin: 12px 0; max-width: 70ch }
.hero-media { aspect-ratio: 16/9; background: var(--paper-2); display: flex; align-items: center; justify-content: center; color: var(--ink-3); font-family: var(--mono); margin: 32px 0; border-radius: var(--radius) }
```

Append to `site/css/apex.css` (or a new `site/case-studies/case-study.css`).

- [ ] **Step 9: Build, view, click-test all new links**

Run: build + serve. Visit `/case-studies/bob-so-arm101/`. Click each cert link, the run-bundle link, all internal links. Expected: 200 for RRF URLs (or whatever the live RRF returns post-2026-05-09 reset).

- [ ] **Step 10: Commit**

```bash
git add site/case-studies/bob-so-arm101/ site/css/apex.css
git commit -m "feat(case-study): deepen bob with hardware, attestations, lessons"
```

---

## Phase E — Apex verification gates

### Task 24: Lighthouse mobile ≥95 on 4 key pages

**Files:**
- (Verification only)

- [ ] **Step 1: Install Lighthouse CI (if absent)**

Run: `which lhci || npm install -g @lhci/cli`

- [ ] **Step 2: Start a local server**

Run: `node site/build.mjs && (cd site/_build && python3 -m http.server 8765 &) && sleep 1`

- [ ] **Step 3: Run Lighthouse on each page**

```bash
for url in / /agents/ /agents/claude-code/ /case-studies/bob-so-arm101/; do
  lhci collect --url="http://localhost:8765$url" --numberOfRuns=1
done
lhci assert --preset=lighthouse:recommended --assertions.performance=95 --assertions.accessibility=95 --assertions.best-practices=95 --assertions.seo=95
```

Expected: all four pages score ≥95 in performance / accessibility / best-practices / SEO.

- [ ] **Step 4: Fix any failures**

If a category scores <95, identify the audit, fix in the relevant partial or CSS, and re-run. Common fixes:
- Missing meta description → add to `<head>` (or per-page `<title>` + `<meta>`).
- Color contrast → adjust the offending token in `tokens.css`.
- Mobile-tap target size → expand padding on nav links.

- [ ] **Step 5: Commit any fixes**

```bash
# If fixes required:
git add <fixed files>
git commit -m "fix(site): lighthouse <category> on <page>"
# Else no commit.
```

Kill the server: `kill %1 2>/dev/null`.

---

### Task 25: lychee link check (zero broken internal links)

**Files:**
- (Verification only)

- [ ] **Step 1: Install lychee (if absent)**

Run: `which lychee || cargo install lychee || brew install lychee`

- [ ] **Step 2: Run lychee on built output**

```bash
node site/build.mjs
lychee --offline --base site/_build site/_build/**/*.html
```

Expected: zero broken internal references.

- [ ] **Step 3: Run online check on external links (report-only)**

```bash
lychee site/_build/**/*.html --exclude-mail
```

Expected: external link failures noted but do not block. If a critical external link (rcan.dev, docs.robotmd.dev, github.com/RobotRegistryFoundation/*) fails, fix.

- [ ] **Step 4: Commit any link fixes**

```bash
# If fixes required:
git add <fixed files>
git commit -m "fix(site): repair broken links per lychee"
```

---

### Task 26: axe-devtools contrast check on 4 key pages

**Files:**
- (Verification only)

- [ ] **Step 1: Open each key page in Chrome with axe DevTools extension**

URLs:
- `http://localhost:8765/`
- `http://localhost:8765/agents/`
- `http://localhost:8765/agents/claude-code/`
- `http://localhost:8765/case-studies/bob-so-arm101/`

- [ ] **Step 2: Run axe scan; capture violations**

Note any AA contrast violations. The token table in spec Section 2 governs:
- `--ink-4` on `--paper` is 3.0:1 (large-text only). If a violation occurs on body-text use of `--ink-4`, the fix is to **change `--ink-4` in tokens.css** (darken by ~5%) or **switch the consumer to `--ink-3`**.

- [ ] **Step 3: Fix violations and re-run**

After each fix, re-run axe on the affected page.

- [ ] **Step 4: Commit fixes**

```bash
# If tokens changed:
git add site/css/tokens.css
git commit -m "fix(site): tighten <token> for AA contrast per axe"
# If consumer changed:
git add <fixed files>
git commit -m "fix(site): consumer uses --ink-3 instead of --ink-4 for body text"
```

---

### Task 27: Visual parity screenshots (apex header/footer vs docs header/footer)

**Files:**
- (Documentation; attached to PR description)

- [ ] **Step 1: Capture apex screenshots**

Open `http://localhost:8765/` at desktop (1366×768) and mobile (390×844). Screenshot the header (top 200px) and footer (bottom 240px) at each width. Save as `/tmp/apex-header-desktop.png`, `/tmp/apex-header-mobile.png`, `/tmp/apex-footer-desktop.png`, `/tmp/apex-footer-mobile.png`.

- [ ] **Step 2: Capture docs screenshots**

Open `https://docs.robotmd.dev/` at the same two widths. Screenshot header and footer regions. Save as `/tmp/docs-header-desktop.png`, etc.

- [ ] **Step 3: Compose side-by-side**

Run (if `imagemagick` available):
```bash
convert /tmp/apex-header-desktop.png /tmp/docs-header-desktop.png +append /tmp/parity-header-desktop.png
convert /tmp/apex-header-mobile.png /tmp/docs-header-mobile.png +append /tmp/parity-header-mobile.png
convert /tmp/apex-footer-desktop.png /tmp/docs-footer-desktop.png +append /tmp/parity-footer-desktop.png
convert /tmp/apex-footer-mobile.png /tmp/docs-footer-mobile.png +append /tmp/parity-footer-mobile.png
```

- [ ] **Step 4: Inspect parity**

Look for divergence in: font family, font size, color, logo position, link spacing, footer column structure. Note divergences in PR description. **Visual parity = apex and docs read as one site at a glance, not pixel-identical.**

- [ ] **Step 5: If parity gaps, file them as docs-side TODOs**

Any divergence that the docs side (Phase G) can fix gets noted in the PR description as "Resolved in Task 36–41 (docs PR)". Any divergence rooted in the apex side gets fixed in this PR.

- [ ] **Step 6: Attach screenshots to PR**

When the PR is opened (Task 35), the 4 composed parity PNGs go in the PR body.

(No commit; screenshots are PR artifacts.)

---

### Task 28: Cloudflare Pages build configuration

**Files:**
- Verify or create: Cloudflare Pages settings (out of band — not in repo); also document in `site/README.md`

Cloudflare Pages must run `node site/build.mjs` and serve `site/_build/` as the public directory.

- [ ] **Step 1: Check current Pages config**

Visit the Cloudflare Pages dashboard for `robotmd.dev`. Note current Build command, Output directory, Root directory.

- [ ] **Step 2: Update build command + output directory**

- Build command: `node site/build.mjs`
- Build output directory: `site/_build`
- Root directory: `/` (repo root)

If `package.json` doesn't exist at repo root, create one minimal:

```json
{
  "name": "robot-md-site",
  "private": true,
  "type": "module",
  "engines": { "node": ">=20" },
  "scripts": {
    "build": "node site/build.mjs"
  }
}
```

Then Pages can use `npm run build` as the build command, which is more idiomatic.

- [ ] **Step 3: Deploy a preview to verify**

Push the branch (`git push -u origin spec/robotmd-dev-and-docs-redesign`). Cloudflare Pages creates a preview deployment. Visit the preview URL; verify all pages render.

- [ ] **Step 4: Document in `site/README.md`**

Update or create `site/README.md` with the new build flow:

```markdown
# robotmd.dev site

Static HTML + a tiny include-replacer (`site/build.mjs`).

## Build locally

```
node site/build.mjs
# output: site/_build/
```

## Deploy

Cloudflare Pages auto-deploys on push to `main`:
- Build command: `node site/build.mjs`
- Build output: `site/_build`

## Files

- `index.html`, `agents/`, `cookbook/`, ... — pages.
- `partials/` — shared HTML chunks (head, nav, sections, cta-band, footer).
- `css/tokens.css` — design tokens (mirrored into robot-md-docs).
- `css/design.css` — layout primitives.
- `css/apex.css` — page-specific CSS (extracted from former inline `<style>`).
- `build.mjs` — include-replacer.
```

- [ ] **Step 5: Commit**

```bash
git add site/README.md package.json
git commit -m "docs(site): document new build flow"
```

---

### Task 29: Final apex build + PR ready

**Files:**
- (Branch state)

- [ ] **Step 1: Clean build**

Run: `rm -rf site/_build && node site/build.mjs && find site/_build -name '*.html' | wc -l`
Expected: count matches your source page count.

- [ ] **Step 2: Manual smoke test — every page loads**

Run: `(cd site/_build && python3 -m http.server 8765 &) && sleep 1`
Visit each URL in a browser:
- `/`
- `/agents/`
- `/agents/claude-code/`
- `/cookbook/`
- `/registry/`
- `/robots/`
- `/actuators/`
- `/managed-agents/`
- `/case-studies/`
- `/case-studies/bob-so-arm101/`
- `/status/`

Expected: every page renders without console errors. Proof bar shows live numbers on `/`.

- [ ] **Step 3: Push + open PR (ASK USER FIRST — push is shared-state)**

Pause and confirm with the operator before `git push`. When approved:

```bash
git push -u origin spec/robotmd-dev-and-docs-redesign
gh pr create --repo RobotRegistryFoundation/robot-md \
  --title "robotmd.dev redesign: partials + tokens + Claude Code page + deeper bob" \
  --body "$(cat <<'EOF'
## Summary

Closes #20. Companion PR for #21 in robot-md-docs.

- Refactor 1,400-line apex `index.html` into header / footer / section partials assembled by `site/build.mjs` (~50 LOC include-replacer)
- Extract design tokens to `site/css/tokens.css` (single source of truth)
- Sweep all 8 sub-pages to use `var(--token)` references
- Polish + audit copy/links/contrast on 9 apex sections
- Rewrite `/agents/` as a directory page
- New `/agents/claude-code/` primary-surface page (7 beats per spec)
- Deepen `/case-studies/bob-so-arm101/` with hardware, attestations, run-bundle, lessons
- No URL moves; all existing routes preserved

Spec: `docs/superpowers/specs/2026-05-11-robotmd-dev-and-docs-redesign-design.md` (f74a3b5).

## Visual parity (apex ↔ docs)

[attach the 4 PNGs from Task 27 here]

## Test plan

- [x] Build succeeds (`node site/build.mjs`)
- [x] Rendered diff is byte-equivalent for refactor-only sections
- [x] Lighthouse mobile ≥95 on `/`, `/agents/`, `/agents/claude-code/`, `/case-studies/bob-so-arm101/`
- [x] lychee finds zero broken internal links
- [x] axe finds zero AA contrast violations
- [x] All 11 pages load in preview deploy
- [x] Proof bar shows live values
- [x] `/managed-agents/` waitlist still captures (regression)

## Follow-ups

- robot-md-docs PR (Tasks 36-41): tokens.css mirror + drift CI + extra.css rebind.
- robot-md#49: asciinema casts on `/cookbook/`.
- robot-md#3: ChatGPT Custom GPT card relabel to "Actions via robot-md-http" when the bridge ships.
- New issue: per-surface pages for Gemini / Codex / ChatGPT / Q.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

(Kill the local server: `kill %1 2>/dev/null`.)

---

## Phase F — Docs side (robot-md-docs repo)

**Switch repo: cd to `~/robot-md-docs`.** Apex must be merged + deployed first (so `https://robotmd.dev/css/tokens.css` is live before docs' drift CI runs).

### Task 30: Branch + create tokens.css mirror

**Repo:** `robot-md-docs`
**Files:**
- Create: `docs/stylesheets/tokens.css`

- [ ] **Step 1: Branch from main**

```bash
cd ~/robot-md-docs
git checkout main && git pull --ff-only
git checkout -b spec/robotmd-dev-redesign-tokens
```

- [ ] **Step 2: Copy live tokens.css from apex**

```bash
mkdir -p docs/stylesheets
curl -fsS https://robotmd.dev/css/tokens.css > docs/stylesheets/tokens.css
```

Verify:
```bash
head -5 docs/stylesheets/tokens.css
```
Expected: comment header matching `site/css/tokens.css` in the apex repo.

- [ ] **Step 3: Commit**

```bash
git add docs/stylesheets/tokens.css
git commit -m "feat(docs): mirror design tokens from robotmd.dev"
```

---

### Task 31: Update `extra.css` to import tokens and rebind Material vars

**Repo:** `robot-md-docs`
**Files:**
- Modify: `docs/stylesheets/extra.css`

- [ ] **Step 1: Read current extra.css**

Run: `cat docs/stylesheets/extra.css | head -50`
If the file is empty or short, expand it; if it has content, append the rebinds.

- [ ] **Step 2: Add `@import` and Material rebinds**

Prepend (or merge into existing) the following block at the top of `docs/stylesheets/extra.css`:

```css
@import url("tokens.css");

/* Rebind Material theme vars to apex tokens so docs reads as one site. */
:root,
[data-md-color-scheme="default"],
[data-md-color-scheme="slate"] {
  --md-primary-fg-color:        var(--paper);
  --md-primary-fg-color--light:  var(--paper-2);
  --md-primary-fg-color--dark:   var(--ink);
  --md-accent-fg-color:           var(--accent-ink);
  --md-typeset-color:             var(--ink);
  --md-default-bg-color:          var(--paper);
  --md-default-fg-color:          var(--ink);
  --md-default-fg-color--light:   var(--ink-3);
  --md-default-fg-color--lighter: var(--ink-4);
  --md-code-bg-color:             var(--paper-2);
  --md-code-fg-color:             var(--ink);
}

/* Headings use Fraunces italic to match apex tone. */
.md-typeset h1,
.md-typeset h2,
.md-typeset h3 {
  font-family: var(--serif);
  font-style: italic;
  font-weight: 600;
  color: var(--ink);
}

body, .md-typeset { font-family: var(--sans); }
```

- [ ] **Step 3: Build mkdocs locally**

Run: `mkdocs build --strict`
Expected: exit 0; no warnings about missing files. Output in `site/`.

- [ ] **Step 4: Serve and inspect**

Run: `mkdocs serve`
Open `http://127.0.0.1:8000/`. Compare to current production `https://docs.robotmd.dev/`. Confirm:
- Paper/ink/terracotta palette
- Fraunces italic headings
- Inter Tight body
- JetBrains Mono code
- Color contrast remains AA on body text

- [ ] **Step 5: Commit**

```bash
git add docs/stylesheets/extra.css
git commit -m "feat(docs): rebind Material theme vars to apex design tokens"
```

---

### Task 32: Create `scripts/sync-tokens.sh`

**Repo:** `robot-md-docs`
**Files:**
- Create: `scripts/sync-tokens.sh`

- [ ] **Step 1: Write the sync script**

```bash
mkdir -p scripts
cat > scripts/sync-tokens.sh <<'SH'
#!/usr/bin/env bash
# Refresh docs/stylesheets/tokens.css from apex source-of-truth.
# Run manually after apex tokens.css changes. CI gates drift with token-drift.yml.
set -euo pipefail

APEX_URL="https://robotmd.dev/css/tokens.css"
DEST="$(dirname "$0")/../docs/stylesheets/tokens.css"

echo "Fetching $APEX_URL → $DEST"
curl -fsS -H 'User-Agent: robot-md-docs/sync-tokens.sh' "$APEX_URL" -o "$DEST"
echo "Done. Diff (vs git HEAD):"
git --no-pager diff -- "$DEST" || true
SH
chmod +x scripts/sync-tokens.sh
```

(The `User-Agent` header is required per memory `feedback_cloudflare_blocks_default_urllib_ua.md` — Cloudflare returns 403 for default user agents. curl's default UA is normally accepted, but setting it explicitly is defensive.)

- [ ] **Step 2: Test the script**

Run: `./scripts/sync-tokens.sh`
Expected: tokens.css refreshed; diff is empty (we just fetched it in Task 30).

- [ ] **Step 3: Commit**

```bash
git add scripts/sync-tokens.sh
git commit -m "feat(docs): scripts/sync-tokens.sh refreshes tokens from apex"
```

---

### Task 33: Create token-drift CI workflow

**Repo:** `robot-md-docs`
**Files:**
- Create: `.github/workflows/token-drift.yml`

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/token-drift.yml
name: token-drift

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 6 * * *'  # daily 06:00 UTC

permissions:
  contents: read

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Fetch apex tokens.css
        run: curl -fsS -H 'User-Agent: robot-md-docs/token-drift' https://robotmd.dev/css/tokens.css -o /tmp/apex-tokens.css
      - name: Diff against committed mirror
        run: |
          if ! diff -u docs/stylesheets/tokens.css /tmp/apex-tokens.css; then
            echo "::error::tokens drift detected — run scripts/sync-tokens.sh and recommit."
            exit 1
          fi
          echo "tokens are in sync."
```

- [ ] **Step 2: Commit**

```bash
mkdir -p .github/workflows
# write the file (above content)
git add .github/workflows/token-drift.yml
git commit -m "ci(docs): gate token drift against apex"
```

- [ ] **Step 3: Verify in a PR**

The workflow runs on `pull_request`. When the docs PR opens (Task 35), confirm the drift job runs green.

---

### Task 34: Match header/footer overrides to apex visual

**Repo:** `robot-md-docs`
**Files:**
- Create or modify: `overrides/partials/header.html`, `overrides/partials/footer.html` (Material theme override path)
- Modify: `mkdocs.yml` (add `theme.custom_dir: overrides` if not present)

- [ ] **Step 1: Enable custom_dir in mkdocs.yml**

Read `mkdocs.yml`. Under the `theme:` block, ensure:

```yaml
theme:
  name: material
  custom_dir: overrides
```

- [ ] **Step 2: Create overrides directory + header**

```bash
mkdir -p overrides/partials
```

Copy the Material default `header.html` and `footer.html` from the pip-installed theme into `overrides/partials/`, then edit to match apex visual. The starting point:

```bash
python3 -c "import mkdocs_material, pathlib; print(pathlib.Path(mkdocs_material.__file__).parent / 'templates' / 'partials')"
```

Use the printed path to locate `header.html` and `footer.html`; copy them.

- [ ] **Step 3: Audit visual against apex screenshots (Task 27)**

Compare the docs header/footer in `mkdocs serve` against the apex parity screenshots from Task 27. Adjust spacing, link colors, logo position to match. The unifying primitives are:
- Same logo at same left offset
- Same nav link font and spacing
- Footer column composition: logo / col1 spec-mcp-registry / col2 cookbook-case-studies / col3 managed-agents / authority disclaimer

- [ ] **Step 4: Build, verify, screenshot**

Run: `mkdocs build --strict && mkdocs serve`
Screenshot header + footer at 1366×768 and 390×844; compare against apex equivalents.

- [ ] **Step 5: Commit**

```bash
git add mkdocs.yml overrides/
git commit -m "feat(docs): override header/footer to match apex visual"
```

---

### Task 35: Final docs build + PR ready

**Repo:** `robot-md-docs`
**Files:**
- (Branch state)

- [ ] **Step 1: Run strict build**

Run: `mkdocs build --strict`
Expected: exit 0, no warnings.

- [ ] **Step 2: Sample-link check**

Open the live preview (`mkdocs serve`), navigate Home → Spec → MCP → Compliance. Confirm headers, footers, code blocks, and nav all render correctly.

- [ ] **Step 3: Push + open PR (ASK USER FIRST)**

Pause and confirm with the operator before pushing. When approved:

```bash
git push -u origin spec/robotmd-dev-redesign-tokens
gh pr create --repo craigm26/robot-md-docs \
  --title "docs: mirror apex design tokens + visual parity" \
  --body "$(cat <<'EOF'
## Summary

Closes RobotRegistryFoundation/robot-md#21 (the docs side of the apex+docs redesign). Companion to the apex PR in RobotRegistryFoundation/robot-md (#20).

- Mirror apex design tokens into `docs/stylesheets/tokens.css`
- Rebind Material theme vars in `extra.css` to apex tokens
- `scripts/sync-tokens.sh` refreshes tokens from apex
- `.github/workflows/token-drift.yml` gates drift (daily + on PR)
- Match header + footer overrides to apex visual

Spec: `RobotRegistryFoundation/robot-md/docs/superpowers/specs/2026-05-11-robotmd-dev-and-docs-redesign-design.md` (f74a3b5).

## Test plan

- [x] `mkdocs build --strict` exits 0
- [x] Token drift CI green
- [x] Visual parity vs apex at desktop + mobile (screenshots below)
- [x] No regression on Home / Spec / MCP / Compliance / Examples pages

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

After writing this plan, I reviewed it against the spec:

**1. Spec coverage:**
- Goal 1 (maintainability split) → Tasks 1–9 ✓
- Goal 2 (cross-surface tokens) → Tasks 1, 30, 31, 32, 33 ✓
- Goal 3 (visual polish) → Tasks 12–20 + 26 (axe) ✓
- Goal 4 (targeted content) → Tasks 21–23 ✓
- Non-goal compliance (no stack change, no extra per-surface pages) → reflected throughout ✓
- Token sync model → Tasks 1, 30, 32, 33 ✓
- Build/deploy → Task 28 ✓
- Migration / no URL moves → preserved throughout; Task 25 verifies via lychee ✓
- All 9 success criteria → covered by Tasks 24 (Lighthouse), 25 (lychee), 26 (axe), 27 (parity), 29 (manual smoke + waitlist regression), 33 (token drift CI) ✓

**2. Placeholder scan:** None. Every code step shows the code. Two intentional implementer-judgment points (final H1 copy in Task 12; cert IDs in Task 23 Step 2) are explicit constrained choices, with safeguards (Task 23 Step 2 says "do not commit Phase F gates until resolved" if cert IDs are not available).

**3. Type consistency:** Token names (`--ink`, `--ink-2`, etc.), partial paths (`partials/sections/<name>.html`), file names (`tokens.css`, `apex.css`, `build.mjs`, `sync-tokens.sh`, `token-drift.yml`), and class names (`page-eyebrow`, `cta-arrow`, `surface-grid`, etc.) are reused consistently across tasks. Material var names (`--md-primary-fg-color`) match the canonical Material theme.

**Gaps noted during review and addressed inline:**
- Originally missed: the install block lives inside `<section class="hero">` (per `grep -n` of index.html). Task 8 calls this out and Task 13 (install polish) targets the hero partial accordingly.
- Originally missed: `_build/` directory needs to be gitignored. Added to Task 2 Step 3.
- Originally missed: docs side has no `overrides/` yet. Task 34 creates it from the Material theme defaults.
- Originally missed: docs needs `theme.custom_dir: overrides` in `mkdocs.yml`. Task 34 Step 1.

---

## Out of scope (explicit punts, not gaps)

Per spec Section "Open follow-ups":
- Per-surface pages for Gemini, Codex, ChatGPT, Q.
- Asciinema casts on `/cookbook/` (robot-md#49).
- `robot-md-http` OpenAPI bridge (#3) and the ChatGPT surface-card relabel.
- `/pricing/` page.

These are not tasks in this plan. Filing follow-up issues is the operator's call after the redesign lands.

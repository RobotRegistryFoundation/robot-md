# site/

The `robotmd.dev` landing page.

## What's here

- `index.html` — single-file landing page. Fully static. No build step. No external JS beyond Google Fonts.
- `_headers` — Cloudflare Pages security + caching headers (HSTS, CSP, referrer policy, cache control).
- `robots.txt`, `sitemap.xml` — SEO basics.

## Design source

Generated via Claude's design tool (`api.anthropic.com/v1/design`) on 2026-04-17. The design handoff bundle is archived (not committed) — the authoritative version is this directory. Updates go here directly.

## Deploy

Three options.

### 1. Cloudflare Pages dashboard (simplest)

1. Go to <https://dash.cloudflare.com/> → Pages → Create project → Connect to Git
2. Select the `craigm26/robot-md` repository
3. Configure:
   - **Production branch**: `main`
   - **Build command**: (leave empty — static site)
   - **Output directory**: `site`
   - **Root directory**: (leave empty)
4. Create project. First deploy runs automatically.
5. Settings → Custom domains → Add `robotmd.dev` (and `www.robotmd.dev` if desired). Follow the CNAME instructions.

Auto-deploys on every push to `main` that touches `site/**`.

### 2. GitHub Actions (auto-deploy via CI)

`.github/workflows/deploy-site.yml` deploys to Pages on every push. To enable:

1. Create a Cloudflare API token at <https://dash.cloudflare.com/profile/api-tokens>
   - Template: **Edit Cloudflare Pages**
   - Account: the account hosting `robotmd-dev`
2. Find your Account ID: dashboard → right sidebar → "Account ID"
3. In the GitHub repo → Settings → Secrets and variables → Actions, add:
   - `CLOUDFLARE_API_TOKEN` — the token from step 1
   - `CLOUDFLARE_ACCOUNT_ID` — the ID from step 2
4. Push to `main`. The workflow deploys + smoke-tests.

### 3. Wrangler CLI (manual / one-off)

```bash
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
npx wrangler pages deploy site --project-name=robotmd-dev --branch=main
```

Useful for previews or out-of-band deploys.

## Local preview

```bash
cd site
python3 -m http.server 8787
open http://localhost:8787/
```

No build step — what's in `site/` is what ships.

## Iterating on the design

The design system (colors, type, spacing) lives in the `<style>` block inside `index.html`. Look for the `:root` CSS custom properties at the top — those are the design tokens. Change them in one place, the whole page follows.

Type pairing:
- **Inter Tight** — sans, display + body
- **JetBrains Mono** — mono, UI chrome + code
- **Fraunces** (italic only) — serif, pull quotes + the letter

Color:
- Paper warm `#F4EFE6`
- Ink `#111110`
- Accent terracotta `#B34A2A` (single accent — don't add a second)

## Accessibility

- Semantic landmarks (`header`, `section`, `article`, `footer`, `nav`).
- All decorative elements marked `aria-hidden="true"`.
- Color contrast: body text meets WCAG AA on paper; accent on paper borderline AA for body but fine for display sizes.
- No keyboard traps. No modal dialogs.

## What's deliberately NOT here

- No JavaScript framework.
- No analytics / trackers / cookies.
- No images — the design ethos is "the file is the artifact." Imagery goes in the ROBOT.md itself, not the marketing site.
- No sign-up form. CTA is the GitHub repo.

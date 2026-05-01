#!/usr/bin/env python3
"""
render-spec.py — regenerate site/spec/index.html from site/spec/v1.md.

Usage:
    python3 site/scripts/render-spec.py

The committed site/spec/index.html is always the output of the most recent
run of this script. CI also runs this script before every deploy, so the
live HTML is at most one deploy cycle behind the markdown source.

Design notes:
- The first `# ` heading in v1.md is extracted as the page title; it is NOT
  fed into the markdown renderer (it renders as the page-header H1 instead).
- A sticky TOC sidebar is auto-generated from the h2/h3 headings found in the
  rendered body after markdown conversion.
- markdown.extensions.toc adds id attributes to headings automatically.
- Output must be idempotent: no timestamps, no random data.
"""

import re
import sys
from pathlib import Path

try:
    import markdown
    from markdown.extensions.toc import TocExtension
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

# ── paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MD_SRC    = REPO_ROOT / "site" / "spec" / "v1.md"
HTML_OUT  = REPO_ROOT / "site" / "spec" / "index.html"


# ── hand-rolled fallback (used only if `markdown` is not importable) ─────────
def _escape_html(s: str) -> str:
    return (s
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _inline(text: str) -> str:
    """Apply inline markdown: **bold**, *italic*, `code`, [text](url)."""
    # links first so we don't double-escape
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                  lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*',     r'<em>\1</em>', text)
    text = re.sub(r'`([^`]+)`',     lambda m: f'<code>{_escape_html(m.group(1))}</code>', text)
    return text


def _slugify(text: str) -> str:
    """Simple slug: lowercase, alphanumeric + hyphens."""
    text = re.sub(r'[^a-z0-9 -]', '', text.lower())
    return re.sub(r'\s+', '-', text.strip())


def _render_fallback(body_md: str) -> str:
    """Hand-rolled renderer for the feature subset used in v1.md."""
    lines   = body_md.splitlines()
    out     = []
    i       = 0
    in_pre  = False
    pre_buf = []
    in_table = False
    in_list  = None   # 'ul' or 'ol'
    in_para  = False
    para_buf = []

    def flush_para():
        nonlocal in_para, para_buf
        if in_para and para_buf:
            combined = " ".join(para_buf)
            out.append(f"<p>{_inline(combined)}</p>")
        in_para = False
        para_buf = []

    def flush_list():
        nonlocal in_list
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None

    while i < len(lines):
        line = lines[i]

        # fenced code block
        if line.strip().startswith("```"):
            flush_para()
            flush_list()
            if not in_pre:
                in_pre = True
                pre_buf = []
            else:
                content = _escape_html("\n".join(pre_buf))
                out.append(f"<pre><code>{content}</code></pre>")
                in_pre = False
            i += 1
            continue

        if in_pre:
            pre_buf.append(line)
            i += 1
            continue

        # headings
        m = re.match(r'^(#{2,3})\s+(.*)', line)
        if m:
            flush_para()
            flush_list()
            level  = len(m.group(1))
            title  = m.group(2)
            slug   = _slugify(re.sub(r'`([^`]*)`', r'\1', title))
            tag    = f"h{level}"
            out.append(f'<{tag} id="{slug}">{_inline(title)}</{tag}>')
            i += 1
            continue

        # table (pipe rows)
        if line.startswith("|"):
            flush_para()
            flush_list()
            if not in_table:
                in_table = True
                out.append('<table>')
                # parse header row
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                out.append("<thead><tr>")
                for c in cells:
                    out.append(f"<th>{_inline(c)}</th>")
                out.append("</tr></thead><tbody>")
                i += 1
                # skip separator row
                if i < len(lines) and re.match(r'^\|[-:| ]+\|', lines[i]):
                    i += 1
            else:
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                out.append("<tr>")
                for c in cells:
                    out.append(f"<td>{_inline(c)}</td>")
                out.append("</tr>")
                i += 1
            continue
        elif in_table:
            out.append("</tbody></table>")
            in_table = False
            # fall through to process current line

        # unordered list
        m = re.match(r'^[-*]\s+(.*)', line)
        if m:
            flush_para()
            if in_list == 'ol':
                out.append("</ol>")
                in_list = None
            if in_list != 'ul':
                out.append("<ul>")
                in_list = 'ul'
            out.append(f"<li>{_inline(m.group(1))}</li>")
            i += 1
            continue

        # ordered list
        m = re.match(r'^\d+\.\s+(.*)', line)
        if m:
            flush_para()
            if in_list == 'ul':
                out.append("</ul>")
                in_list = None
            if in_list != 'ol':
                out.append("<ol>")
                in_list = 'ol'
            out.append(f"<li>{_inline(m.group(1))}</li>")
            i += 1
            continue

        # blank line
        if not line.strip():
            flush_para()
            flush_list()
            if in_table:
                out.append("</tbody></table>")
                in_table = False
            i += 1
            continue

        # paragraph accumulation
        flush_list()
        in_para = True
        para_buf.append(line)
        i += 1

    flush_para()
    flush_list()
    if in_table:
        out.append("</tbody></table>")
    if in_pre:
        content = _escape_html("\n".join(pre_buf))
        out.append(f"<pre><code>{content}</code></pre>")

    return "\n".join(out)


# ── TOC extraction ────────────────────────────────────────────────────────────
def _extract_toc(html_body: str) -> list[dict]:
    """
    Return list of {'level': 2|3, 'id': str, 'text': str} from rendered HTML.
    Only h2 and h3 are included.
    """
    toc = []
    for m in re.finditer(r'<h([23])[^>]*id="([^"]+)"[^>]*>(.*?)</h\1>',
                         html_body, re.DOTALL):
        level = int(m.group(1))
        slug  = m.group(2)
        text  = re.sub(r'<[^>]+>', '', m.group(3))   # strip inner tags for display
        toc.append({'level': level, 'id': slug, 'text': text})
    return toc


# ── HTML template ─────────────────────────────────────────────────────────────
NAV_HTML = """\
  <header class="site-nav" role="banner">
    <div class="wrap site-nav-inner">
      <a class="wordmark" href="/" aria-label="ROBOT.md home">
        ROBOT<span class="dot">.</span><span class="md">md</span>
      </a>
      <nav aria-label="Site navigation">
        <a href="/spec/" class="current" aria-current="page">Spec</a>
        <a href="/agents/">Agents</a>
        <a href="/mcp/">MCP</a>
        <a href="/registry/">Registry</a>
        <a href="/compliance/">Compliance</a>
        <a href="/managed-agents/">Managed Agents</a>
        <a href="/robots">Robots</a>
        <a href="https://github.com/RobotRegistryFoundation/robot-md" aria-label="GitHub repository">GitHub</a>
      </nav>
    </div>
  </header>"""

FOOTER_HTML = """\
  <footer class="wrap foot">
    <div>ROBOT.md · © 2026 Craig Merry · <a href="https://www.craigmerry.com">craigmerry.com</a></div>
    <div>
      <a href="/">Home</a> ·
      <a href="/spec/">Spec</a> ·
      <a href="/registry/">Registry</a> ·
      <a href="/compliance/">Compliance</a> ·
      <a href="/robots">Robots</a> ·
      <a href="/status">Status</a> ·
      <a href="/report.html">Report issue</a> ·
      <a href="https://github.com/RobotRegistryFoundation/robot-md">GitHub</a>
    </div>
  </footer>"""

PAGE_STYLES = """\
  <style>
    /* ============================================================
       SPEC PAGE — two-column layout with sidebar
       ============================================================ */
    .spec-layout {
      display: grid;
      grid-template-columns: 220px 1fr;
      gap: 48px;
      padding: 48px 0 80px;
      align-items: start;
    }
    @media (max-width: 900px) {
      .spec-layout { grid-template-columns: 1fr; gap: 32px }
    }

    /* ---- Sidebar ---- */
    .spec-sidebar {
      position: sticky;
      top: 72px;
    }
    @media (max-width: 900px) {
      .spec-sidebar { position: static }
    }

    .spec-sidebar .sidebar-label {
      font-family: var(--mono);
      font-size: 10px;
      letter-spacing: .18em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 12px;
    }

    .spec-sidebar .ver-block {
      border: 1px solid var(--rule);
      background: var(--paper-2);
      padding: 16px;
      margin-bottom: 24px;
    }

    .spec-sidebar .ver-block .ver-current {
      font-family: var(--mono);
      font-size: 13px;
      font-weight: 600;
      color: var(--ink);
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
    }
    .spec-sidebar .ver-block .ver-badge {
      font-size: 9px;
      letter-spacing: .12em;
      text-transform: uppercase;
      background: var(--ok);
      color: var(--paper);
      padding: 2px 6px;
      border-radius: 2px;
    }

    .spec-sidebar .ver-block ul {
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .spec-sidebar .ver-block ul li {
      font-family: var(--mono);
      font-size: 12px;
      color: var(--ink-3);
      padding: 3px 0;
      border-top: 1px solid var(--rule);
    }
    .spec-sidebar .ver-block ul li a {
      color: var(--ink-3);
      border: none;
    }
    .spec-sidebar .ver-block ul li a:hover { color: var(--accent) }

    .spec-sidebar nav.toc ul {
      margin: 0;
      padding: 0;
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .spec-sidebar nav.toc ul li a {
      font-family: var(--mono);
      font-size: 11.5px;
      color: var(--ink-3);
      border: none;
      padding: 3px 0;
      display: block;
    }
    .spec-sidebar nav.toc ul li a:hover { color: var(--accent) }
    .spec-sidebar nav.toc ul li.toc-sub a {
      padding-left: 14px;
      font-size: 11px;
      color: var(--ink-4);
    }

    .spec-sidebar .schema-link {
      display: block;
      font-family: var(--mono);
      font-size: 11px;
      letter-spacing: .06em;
      background: var(--ink);
      color: var(--paper);
      text-align: center;
      padding: 9px 12px;
      border: none;
      margin-top: 20px;
      transition: background .15s;
    }
    .spec-sidebar .schema-link:hover { background: var(--accent) }

    .spec-sidebar .validate-hint {
      margin-top: 12px;
      font-family: var(--mono);
      font-size: 11px;
      color: var(--ink-4);
      background: var(--paper-2);
      border: 1px solid var(--rule);
      padding: 10px 12px;
      line-height: 1.5;
    }
    .spec-sidebar .validate-hint code {
      color: var(--accent-ink);
      background: none;
    }

    /* ---- Spec body ---- */
    .spec-body h2 {
      font-family: var(--sans);
      font-weight: 600;
      font-size: clamp(20px, 2.4vw, 28px);
      letter-spacing: -0.018em;
      line-height: 1.15;
      margin: 48px 0 12px;
      padding-top: 8px;
      border-top: 2px solid var(--rule);
      color: var(--ink);
    }
    .spec-body h2:first-child { margin-top: 0; border-top: none }

    .spec-body h3 {
      font-family: var(--mono);
      font-size: 14px;
      font-weight: 600;
      letter-spacing: .04em;
      margin: 28px 0 8px;
      color: var(--ink);
    }
    .spec-body h3 code {
      font-family: var(--mono);
      font-size: 14px;
      background: var(--paper-2);
      padding: 2px 7px;
      border-radius: 2px;
    }

    .spec-body p {
      font-size: 15px;
      color: var(--ink-2);
      line-height: 1.65;
      margin: 0 0 14px;
    }

    .spec-body ul, .spec-body ol {
      margin: 0 0 14px;
      padding-left: 22px;
    }
    .spec-body li {
      font-size: 14.5px;
      color: var(--ink-2);
      line-height: 1.6;
      margin-bottom: 4px;
    }
    .spec-body li code {
      font-family: var(--mono);
      font-size: 12.5px;
      background: var(--paper-2);
      padding: 1px 5px;
      border-radius: 2px;
    }

    .spec-body code {
      font-family: var(--mono);
      font-size: 13px;
      background: var(--paper-2);
      padding: 1px 5px;
      border-radius: 2px;
    }

    .spec-body pre {
      background: var(--ink);
      color: #E8E3D3;
      font-family: var(--mono);
      font-size: 13px;
      line-height: 1.6;
      padding: 18px 20px;
      margin: 8px 0 20px;
      overflow-x: auto;
      border-radius: 2px;
      border: 1px solid var(--rule);
    }
    .spec-body pre code {
      background: none;
      padding: 0;
      font-size: 13px;
      color: inherit;
    }

    .spec-body table {
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0 20px;
      font-size: 13.5px;
    }
    .spec-body th {
      font-family: var(--mono);
      font-size: 11px;
      letter-spacing: .1em;
      text-transform: uppercase;
      color: var(--ink-3);
      text-align: left;
      padding: 8px 12px;
      border-bottom: 2px solid var(--rule);
      background: var(--paper-2);
    }
    .spec-body td {
      padding: 8px 12px;
      border-bottom: 1px solid var(--rule);
      color: var(--ink-2);
      vertical-align: top;
      line-height: 1.5;
    }
    .spec-body td code {
      font-family: var(--mono);
      font-size: 12px;
      background: var(--paper-2);
      padding: 1px 4px;
      border-radius: 2px;
    }
    .spec-body tr:last-child td { border-bottom: none }
  </style>"""


def _build_toc_html(toc: list[dict]) -> str:
    items = []
    for entry in toc:
        cls = ' class="toc-sub"' if entry['level'] == 3 else ''
        items.append(
            f'            <li{cls}><a href="#{entry["id"]}">{entry["text"]}</a></li>'
        )
    return "\n".join(items)


def render(md_path: Path, html_path: Path) -> None:
    source = md_path.read_text(encoding="utf-8")

    # Split off the frontmatter-style metadata block at top (not YAML ---),
    # then strip the H1 title line.
    lines = source.splitlines()

    # First non-blank line should be the H1 title
    title_raw = ""
    body_start = 0
    for idx, line in enumerate(lines):
        m = re.match(r'^#\s+(.*)', line)
        if m:
            title_raw = m.group(1)
            body_start = idx + 1
            break

    body_md = "\n".join(lines[body_start:])

    if HAS_MARKDOWN:
        md = markdown.Markdown(
            extensions=[
                TocExtension(permalink=False, toc_depth="2-3"),
                "tables",
                "fenced_code",
                "attr_list",
            ]
        )
        body_html = md.convert(body_md)
    else:
        print("WARNING: `markdown` library not found — using hand-rolled fallback",
              file=sys.stderr)
        body_html = _render_fallback(body_md)

    toc = _extract_toc(body_html)
    toc_html = _build_toc_html(toc)

    page = f"""<!doctype html>
<html lang="en">

<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>ROBOT.md Spec v1 — Format Specification</title>
  <meta name="description"
    content="The ROBOT.md format specification — v1. YAML frontmatter schema, required fields, body sections, validation rules, and RCAN 3.0+ conformance requirements.">
  <meta name="theme-color" content="#F4EFE6">

  <meta property="og:title" content="ROBOT.md Spec v1">
  <meta property="og:description"
    content="ROBOT.md format specification — one file per robot, YAML + markdown, RCAN 3.0+ conformant.">
  <meta property="og:url" content="https://robotmd.dev/spec/">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary_large_image">

  <link rel="canonical" href="https://robotmd.dev/spec/">

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link
    href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Fraunces:ital,wght@1,400;1,600&display=swap"
    rel="stylesheet">

  <link rel="stylesheet" href="/css/design.css">

{PAGE_STYLES}
</head>

<body>

  <!-- ===== SITE NAV ===== -->
{NAV_HTML}

  <!-- ===== PAGE HEADER ===== -->
  <header class="page-header">
    <div class="wrap">
      <div class="page-eyebrow">
        <span>Specification · v1</span>
        <span class="rule-line" aria-hidden="true"></span>
        <span>Draft · 2026-04-17</span>
      </div>
      <h1 class="page-heading">
        ROBOT<span style="color:var(--accent)">.</span><span style="font-family:var(--serif);font-weight:400;font-style:italic;color:var(--ink-3)">md</span>
        <b>Format</b> Specification
      </h1>
      <p class="page-lede">
        One file — YAML frontmatter + markdown prose — so a planning LLM can
        safely operate a single robot. Validated against a JSON Schema.
        Conformant with RCAN 3.0+.
      </p>
    </div>
  </header>

  <!-- ===== TWO-COLUMN LAYOUT ===== -->
  <div class="wrap">
    <div class="spec-layout">

      <!-- ---- SIDEBAR ---- -->
      <aside class="spec-sidebar" aria-label="Spec navigation">

        <div class="sidebar-label">Spec versions</div>
        <div class="ver-block">
          <div class="ver-current">
            <span>v1</span>
            <span class="ver-badge">Current</span>
          </div>
          <ul>
            <li><a href="/spec/v0.2-design.md">v0.2-design (historical)</a></li>
            <li><a href="/spec/v0.1-mcp-design.md">v0.1-mcp-design (historical)</a></li>
          </ul>
        </div>

        <div class="sidebar-label">On this page</div>
        <nav class="toc" aria-label="Table of contents">
          <ul>
{toc_html}
          </ul>
        </nav>

        <a class="schema-link" href="/schema/v1/robot.schema.json">
          JSON Schema v1 →
        </a>

        <div class="validate-hint">
          Validate a local file:<br>
          <code>robot-md validate ROBOT.md</code>
        </div>

      </aside>

      <!-- ---- SPEC BODY ---- -->
      <article class="spec-body" aria-label="ROBOT.md Format Specification v1">
{body_html}
      </article>

    </div>
  </div>

  <!-- ===== FOOTER ===== -->
{FOOTER_HTML}

</body>

</html>
"""

    html_path.write_text(page, encoding="utf-8")
    print(f"Rendered {md_path} → {html_path} ({html_path.stat().st_size} bytes)")


if __name__ == "__main__":
    render(MD_SRC, HTML_OUT)

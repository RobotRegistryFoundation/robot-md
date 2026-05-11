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

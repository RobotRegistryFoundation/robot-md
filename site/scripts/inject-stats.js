#!/usr/bin/env node
/**
 * inject-stats.js — build-time stats fetcher for the robotmd.dev proof bar.
 *
 * Writes site/_stats.json with live numbers from GitHub, npm, and RRF.
 * Called by the Cloudflare Pages build command (or the deploy-site workflow).
 *
 * Usage:
 *   node site/scripts/inject-stats.js
 *
 * Never throws — every source wraps in try/catch and uses a fallback value
 * so a flaky external API never breaks the build.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SITE_DIR  = resolve(__dirname, "..");
const OUT_PATH  = resolve(SITE_DIR, "_stats.json");
const PYPROJECT = resolve(__dirname, "../../cli/pyproject.toml");

const GH_API    = "https://api.github.com";
const REPO      = "RobotRegistryFoundation/robot-md";
const USER_AGENT = "robot-md-inject-stats/1.0 (+https://github.com/RobotRegistryFoundation/robot-md)";

// TODO: bump to 6 when §27 lands (RRF #73)
const RRF_ENDPOINTS_LIVE = 5;

/** Fetch with a shared User-Agent and a 10 s timeout. */
async function ghFetch(url) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 10_000);
  try {
    const headers = { "User-Agent": USER_AGENT, "Accept": "application/vnd.github+json" };
    if (process.env.GITHUB_TOKEN) {
      headers["Authorization"] = `Bearer ${process.env.GITHUB_TOKEN}`;
    }
    const r = await fetch(url, { headers, signal: ctrl.signal });
    clearTimeout(timer);
    if (!r.ok) throw new Error(`HTTP ${r.status} from ${url}`);
    return r;
  } catch (e) {
    clearTimeout(timer);
    throw e;
  }
}

async function apiFetch(url, timeout = 10_000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const r = await fetch(url, {
      headers: { "User-Agent": USER_AGENT },
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (!r.ok) throw new Error(`HTTP ${r.status} from ${url}`);
    return r;
  } catch (e) {
    clearTimeout(timer);
    throw e;
  }
}

// ---------------------------------------------------------------------------
// Source: GitHub repo metadata (stars)
// ---------------------------------------------------------------------------
async function fetchGitHubStars() {
  try {
    const r = await ghFetch(`${GH_API}/repos/${REPO}`);
    const data = await r.json();
    return data.stargazers_count ?? 0;
  } catch (e) {
    process.stderr.write(`[inject-stats] WARN github stars: ${e.message}\n`);
    return 0;
  }
}

// ---------------------------------------------------------------------------
// Source: GitHub contributors count (parse Link header last-page)
// ---------------------------------------------------------------------------
async function fetchGitHubContributors() {
  try {
    const r = await ghFetch(
      `${GH_API}/repos/${REPO}/contributors?per_page=1&anon=true`
    );
    const link = r.headers.get("link") || "";
    // Link: <https://api.github.com/...?page=7>; rel="last"
    const match = link.match(/[?&]page=(\d+)>;\s*rel="last"/);
    if (match) return parseInt(match[1], 10);
    // If no Link header, the single page IS the full list — count JSON array.
    const data = await r.json();
    return Array.isArray(data) ? data.length : 1;
  } catch (e) {
    process.stderr.write(`[inject-stats] WARN github contributors: ${e.message}\n`);
    return 1;
  }
}

// ---------------------------------------------------------------------------
// Source: npm weekly downloads
// ---------------------------------------------------------------------------
async function fetchNpmDownloads() {
  try {
    const r = await apiFetch(
      "https://api.npmjs.org/downloads/point/last-week/robot-md-mcp"
    );
    const data = await r.json();
    return data.downloads ?? 0;
  } catch (e) {
    process.stderr.write(`[inject-stats] WARN npm downloads: ${e.message}\n`);
    return 0;
  }
}

// ---------------------------------------------------------------------------
// Source: robot-md version from cli/pyproject.toml
// ---------------------------------------------------------------------------
function readVersion() {
  try {
    const text = readFileSync(PYPROJECT, "utf8");
    const m = text.match(/^version\s*=\s*"([^"]+)"/m);
    return m ? m[1] : "unknown";
  } catch (e) {
    process.stderr.write(`[inject-stats] WARN version read: ${e.message}\n`);
    return "unknown";
  }
}

// ---------------------------------------------------------------------------
// Source: RRF registered robots
// ---------------------------------------------------------------------------
async function fetchRobotsRegistered() {
  try {
    const r = await apiFetch("https://robotregistryfoundation.org/v2/robots");
    const data = await r.json();
    if (typeof data.count === "number") return data.count;
    if (Array.isArray(data)) return data.length;
    if (data.robots && Array.isArray(data.robots)) return data.robots.length;
    process.stderr.write(
      "[inject-stats] WARN RRF /v2/robots: unexpected shape — falling back to 1\n"
    );
    return 1;
  } catch (e) {
    process.stderr.write(`[inject-stats] WARN RRF robots: ${e.message} — falling back to 1\n`);
    return 1;
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
const [stars, contributors, npmDownloads, robotsRegistered] = await Promise.all([
  fetchGitHubStars(),
  fetchGitHubContributors(),
  fetchNpmDownloads(),
  fetchRobotsRegistered(),
]);

const version = readVersion();

const stats = {
  github_stars:        stars,
  github_contributors: contributors,
  npm_weekly_downloads: npmDownloads,
  robot_md_version:    version,
  rrf_endpoints_live:  RRF_ENDPOINTS_LIVE,
  robots_registered:   robotsRegistered,
  generated_at:        new Date().toISOString(),
};

writeFileSync(OUT_PATH, JSON.stringify(stats, null, 2) + "\n");
process.stdout.write(`[inject-stats] wrote ${OUT_PATH}\n`);
process.stdout.write(JSON.stringify(stats, null, 2) + "\n");

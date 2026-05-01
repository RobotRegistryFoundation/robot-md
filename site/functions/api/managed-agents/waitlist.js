/**
 * Cloudflare Pages Function — Compliance-bot waitlist
 * Route: POST  /api/managed-agents/waitlist        → subscribe
 *        GET   /api/managed-agents/waitlist/count  → public count
 *
 * KV binding: WAITLIST_KV  (set in wrangler.toml [[kv_namespaces]])
 *   - waitlist:<sha256(email)>  → { email, ts, ua }
 *   - rl:<ip>                   → submission count (TTL 3600 s)
 */

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "https://robotmd.dev",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Vary": "Origin",
};

const RATE_LIMIT = 5;          // submissions per IP per hour
const RATE_WINDOW_TTL = 3600;  // seconds

/** Basic email shape check — deliberately lenient. */
function isValidEmail(s) {
  return typeof s === "string" && /^\S+@\S+\.\S+$/.test(s.trim());
}

/** Hex-encode a Web Crypto SHA-256 digest. */
async function sha256hex(text) {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text)
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS, ...extra },
  });
}

// ---------------------------------------------------------------------------
// POST handler — subscribe
// ---------------------------------------------------------------------------
async function handlePost(request, env) {
  // Parse body
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "invalid JSON body" }, 400);
  }

  const email = (body.email || "").trim().toLowerCase();
  if (!isValidEmail(email)) {
    return json({ ok: false, error: "invalid email address" }, 400);
  }

  // Rate-limit per IP
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const rlKey = `rl:${ip}`;
  const rlRaw = await env.WAITLIST_KV.get(rlKey);
  const rlCount = rlRaw ? parseInt(rlRaw, 10) : 0;
  if (rlCount >= RATE_LIMIT) {
    return json({ ok: false, error: "rate limit exceeded — try again later" }, 429);
  }

  // Check for duplicate
  const hash = await sha256hex(email);
  const entryKey = `waitlist:${hash}`;
  const existing = await env.WAITLIST_KV.get(entryKey);
  if (existing) {
    return json({ ok: true, already_subscribed: true });
  }

  // Store entry
  const ua = (request.headers.get("User-Agent") || "").slice(0, 200);
  const entry = { email, ts: Date.now(), ua };
  await env.WAITLIST_KV.put(entryKey, JSON.stringify(entry));

  // Increment rate-limit counter (TTL resets window per new IP or after expiry)
  await env.WAITLIST_KV.put(rlKey, String(rlCount + 1), {
    expirationTtl: RATE_WINDOW_TTL,
  });

  return json({ ok: true, already_subscribed: false });
}

// ---------------------------------------------------------------------------
// GET handler — count
// ---------------------------------------------------------------------------
async function handleGetCount(env) {
  // Count by listing all waitlist:* keys (fast at low volume)
  const list = await env.WAITLIST_KV.list({ prefix: "waitlist:" });
  const count = list.keys.length;
  return json({ count });
}

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------
export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const method = request.method.toUpperCase();

  // Preflight
  if (method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }

  // GET /api/managed-agents/waitlist/count
  if (method === "GET" && url.pathname.endsWith("/count")) {
    return handleGetCount(env);
  }

  // POST /api/managed-agents/waitlist
  if (method === "POST") {
    return handlePost(request, env);
  }

  return json({ ok: false, error: "method not allowed" }, 405);
}

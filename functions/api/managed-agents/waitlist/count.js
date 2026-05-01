/**
 * Cloudflare Pages Function — Public waitlist count
 * Route: GET /api/managed-agents/waitlist/count
 *
 * Returns: { count: <int> }  — counts keys with prefix "waitlist:" in WAITLIST_KV.
 */

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "https://robotmd.dev",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Vary": "Origin",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}

export async function onRequestGet({ env }) {
  const list = await env.WAITLIST_KV.list({ prefix: "waitlist:" });
  return json({ count: list.keys.length });
}

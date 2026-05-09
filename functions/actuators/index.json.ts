/**
 * GET /actuators/index.json — serve the catalog mirror from KV.
 * KV is populated by the standalone mirror Worker (mirror-worker/).
 * Empty fallback shape preserves CLI offline-cache behavior on KV miss.
 */

export interface Env {
  MIRROR_KV: KVNamespace;
}

const EMPTY_BODY = JSON.stringify({
  schema_version: "2.0",
  generated_at: null,
  entries: [],
});

const HEADERS = {
  "Content-Type": "application/json",
  "Cache-Control": "public, max-age=300, must-revalidate",
};

export const onRequestGet: PagesFunction<Env> = async ({ env }) => {
  const cached = await env.MIRROR_KV.get("actuators-index");
  return new Response(cached ?? EMPTY_BODY, { status: 200, headers: HEADERS });
};

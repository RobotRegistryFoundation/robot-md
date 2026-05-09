import { describe, it, expect, vi } from "vitest";
import { onRequestGet } from "./index.json";

function makeEnv(stored: string | null) {
  return {
    MIRROR_KV: {
      get: vi.fn(async () => stored),
      put: vi.fn(),
      list: vi.fn(),
      delete: vi.fn(),
    },
  };
}

describe("GET /actuators/index.json", () => {
  it("returns KV-stored body when present", async () => {
    const stored = JSON.stringify({ schema_version: "2.0", entries: [{ rpn: "RPN-000000000001" }] });
    const env = makeEnv(stored);
    const res = await onRequestGet({ env } as any);
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toContain("application/json");
    expect(await res.json()).toEqual(JSON.parse(stored));
  });

  it("returns empty schema when KV miss", async () => {
    const env = makeEnv(null);
    const res = await onRequestGet({ env } as any);
    expect(res.status).toBe(200);
    const body = await res.json() as { schema_version: string; entries: any[] };
    expect(body.schema_version).toBe("2.0");
    expect(body.entries).toEqual([]);
  });

  it("sets Cache-Control: max-age=300", async () => {
    const env = makeEnv(null);
    const res = await onRequestGet({ env } as any);
    expect(res.headers.get("Cache-Control")).toContain("max-age=300");
  });
});

import { describe, it, expect, vi } from "vitest";
import worker, { toMirrorEntry } from "./index.js";

describe("toMirrorEntry", () => {
  it("flattens versions to latest version + history", () => {
    const rec = {
      rpn: "RPN-000000000001",
      package_type: "actuator",
      name: "feetech-arm",
      description: "arm driver",
      hardware_tags: ["arm"],
      manifest_signals: ["SO-ARM101"],
      skill_files: ["using-feetech-arm.SKILL.md"],
      has_plugin_layout: false,
      versions: [
        { version: "1.0.0", released_at: "2026-05-09T00:00:00Z" },
        { version: "1.1.0", released_at: "2026-05-10T00:00:00Z" },
      ],
      publisher: { pq_kid: "publisher-x", pq_signing_pub: "PUB", ed25519_pub: "EPUB" },
      registered_at: "2026-05-09T00:00:00Z",
      status: "active",
    };
    const e = toMirrorEntry(rec as any);
    expect(e.rpn).toBe("RPN-000000000001");
    expect(e.type).toBe("actuator");
    expect(e.version).toBe("1.1.0");
    expect(e.version_history).toHaveLength(2);
    expect(e.publisher.pq_kid).toBe("publisher-x");
    expect(e.status).toBe("active");
    expect(e.install).toEqual({
      package_manager: "pip",
      package: "feetech-arm",
      post_install: "robot-md install-skill feetech-arm",
    });
  });
});

describe("scheduled handler", () => {
  it("fetches RRF list and writes to KV", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        packages: [
          {
            rpn: "RPN-000000000001", package_type: "actuator", name: "x",
            description: "x", hardware_tags: [], manifest_signals: [],
            skill_files: [], has_plugin_layout: false,
            versions: [{ version: "1.0.0", released_at: "2026-05-09T00:00:00Z" }],
            publisher: {}, registered_at: "2026-05-09T00:00:00Z", status: "active",
          },
        ],
      }),
    });
    globalThis.fetch = fetchSpy as any;

    const putSpy = vi.fn();
    const env = {
      MIRROR_KV: { put: putSpy, get: vi.fn(), delete: vi.fn(), list: vi.fn() },
      RRF_LIST_URL: "https://robotregistryfoundation.org/v2/packages?limit=1000",
    };

    await worker.scheduled({} as any, env as any, { waitUntil: vi.fn(), passThroughOnException: vi.fn() });
    expect(fetchSpy).toHaveBeenCalledWith(env.RRF_LIST_URL);
    expect(putSpy).toHaveBeenCalledWith("actuators-index", expect.stringContaining("RPN-000000000001"));
  });

  it("logs error on RRF fetch failure", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 }) as any;
    const env = {
      MIRROR_KV: { put: vi.fn(), get: vi.fn(), delete: vi.fn(), list: vi.fn() },
      RRF_LIST_URL: "https://robotregistryfoundation.org/v2/packages",
    };
    await expect(
      worker.scheduled({} as any, env as any, { waitUntil: vi.fn(), passThroughOnException: vi.fn() }),
    ).resolves.not.toThrow();
    expect(env.MIRROR_KV.put).not.toHaveBeenCalled();
  });
});

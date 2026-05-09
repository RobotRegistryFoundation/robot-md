/**
 * Scheduled Worker — refreshes the actuator catalog mirror at robotmd.dev.
 *
 * Triggered by cron (every 10 min via wrangler.toml). Pulls RRF's
 * /v2/packages list, transforms each record into the mirror entry shape,
 * and writes the assembled JSON to KV under key "actuators-index".
 *
 * The Pages Function at functions/actuators/index.json reads this KV
 * value to serve the public mirror endpoint.
 */

interface PackageVersion {
  version: string;
  released_at: string;
  artifact_hash?: string;
}

interface PackagePublisher {
  pq_kid?: string;
  pq_signing_pub?: string;
  ed25519_pub?: string;
}

interface PackageRecord {
  rpn: string;
  package_type: "actuator" | "skill" | "plugin" | "mcp";
  name: string;
  description: string;
  hardware_tags: string[];
  manifest_signals: string[];
  skill_files: string[];
  has_plugin_layout: boolean;
  versions: PackageVersion[];
  publisher: PackagePublisher;
  registered_at: string;
  status: "active" | "revoked";
  revoked_at?: string;
  revocation_reason?: string;
}

interface MirrorEntry {
  rpn: string;
  type: PackageRecord["package_type"];
  name: string;
  version: string;
  version_history: PackageVersion[];
  description: string;
  hardware_tags: string[];
  manifest_signals: string[];
  install: { package_manager: "pip"; package: string; post_install: string };
  skill_files: string[];
  plugin_marketplace_entry?: { marketplace: string; plugin_name: string; install_command: string };
  publisher: PackagePublisher;
  registered_at: string;
  verified: boolean;
  status: PackageRecord["status"];
}

export function toMirrorEntry(rec: PackageRecord): MirrorEntry {
  const latest = rec.versions[rec.versions.length - 1];
  const entry: MirrorEntry = {
    rpn: rec.rpn,
    type: rec.package_type,
    name: rec.name,
    version: latest?.version ?? "0.0.0",
    version_history: rec.versions,
    description: rec.description,
    hardware_tags: rec.hardware_tags,
    manifest_signals: rec.manifest_signals,
    install: {
      package_manager: "pip",
      package: rec.name,
      post_install: `robot-md install-skill ${rec.name}`,
    },
    skill_files: rec.skill_files,
    publisher: rec.publisher,
    registered_at: rec.registered_at,
    verified: rec.status === "active",
    status: rec.status,
  };
  if (rec.has_plugin_layout) {
    entry.plugin_marketplace_entry = {
      marketplace: "robotregistryfoundation",
      plugin_name: rec.name,
      install_command: `/plugin install ${rec.name}@robotregistryfoundation`,
    };
  }
  return entry;
}

export interface Env {
  MIRROR_KV: KVNamespace;
  RRF_LIST_URL: string;
}

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    try {
      const res = await fetch(env.RRF_LIST_URL);
      if (!res.ok) {
        console.error(`mirror-worker: RRF list returned HTTP ${res.status}`);
        return;
      }
      const data = (await res.json()) as { packages: PackageRecord[] };
      const out = {
        schema_version: "2.0",
        generated_at: new Date().toISOString(),
        entries: data.packages.map(toMirrorEntry),
      };
      await env.MIRROR_KV.put("actuators-index", JSON.stringify(out));
    } catch (e) {
      console.error("mirror-worker: refresh failed", e);
    }
  },
};

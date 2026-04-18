# robot-md-mcp v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a TypeScript MCP server in a new repo (`RobotRegistryFoundation/robot-md-mcp`) that exposes a local `ROBOT.md` file as MCP resources and provides `validate` / `render` tools. No robot dispatch.

**Architecture:** Pure TypeScript Node 18+ package. In-house parser using `yaml` for frontmatter and raw markdown for body. Validation via `ajv` against the bundled JSON schema from the canonical `robot-md` repo. MCP wiring via `@modelcontextprotocol/sdk` over stdio. Build with `tsup`, test with `vitest`.

**Tech Stack:**
- TypeScript 5.x, Node 18+
- Runtime: `@modelcontextprotocol/sdk` 1.29.x, `yaml` 2.x, `ajv` 8.x (`ajv-formats` for standard formats)
- Dev: `tsup`, `vitest`, `@types/node`
- License: Apache-2.0

**Design reference:** `/home/craigm26/robot-md/spec/v0.1-mcp-design.md` (§§1-12).

**Working directory for this plan:** `/home/craigm26/robot-md-mcp/` (new, sibling to `robot-md`).

---

## Task 0: Scaffold the repo

**Files:**
- Create: `/home/craigm26/robot-md-mcp/package.json`
- Create: `/home/craigm26/robot-md-mcp/tsconfig.json`
- Create: `/home/craigm26/robot-md-mcp/tsup.config.ts`
- Create: `/home/craigm26/robot-md-mcp/vitest.config.ts`
- Create: `/home/craigm26/robot-md-mcp/.gitignore`
- Create: `/home/craigm26/robot-md-mcp/LICENSE` (Apache-2.0)
- Create: `/home/craigm26/robot-md-mcp/README.md` (stub; final content in Task 8)

- [ ] **Step 1: Create the directory and init git**

```bash
mkdir -p /home/craigm26/robot-md-mcp
cd /home/craigm26/robot-md-mcp
git init -b main
```

- [ ] **Step 2: Write `package.json`**

`/home/craigm26/robot-md-mcp/package.json`:

```json
{
  "name": "robot-md-mcp",
  "version": "0.1.0",
  "description": "MCP server that exposes a ROBOT.md file to Claude Desktop and any other MCP client",
  "keywords": ["mcp", "robot", "robotics", "claude", "robot-md", "model-context-protocol"],
  "type": "module",
  "main": "dist/index.cjs",
  "module": "dist/index.mjs",
  "types": "dist/index.d.ts",
  "bin": {
    "robot-md-mcp": "dist/bin.mjs"
  },
  "exports": {
    ".": {
      "import": { "types": "./dist/index.d.ts", "default": "./dist/index.mjs" },
      "require": { "types": "./dist/index.d.cts", "default": "./dist/index.cjs" }
    }
  },
  "files": ["dist", "README.md", "LICENSE"],
  "scripts": {
    "build": "tsup",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit",
    "sync-schema": "node scripts/sync-schema.mjs"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.29.0",
    "ajv": "^8.18.0",
    "ajv-formats": "^3.0.1",
    "yaml": "^2.8.3"
  },
  "devDependencies": {
    "@types/node": "^20.11.0",
    "tsup": "^8.5.0",
    "typescript": "^5.6.0",
    "vitest": "^2.1.0"
  },
  "engines": {
    "node": ">=18.20"
  },
  "license": "Apache-2.0",
  "author": "craigm26 <craigm26@gmail.com>",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/RobotRegistryFoundation/robot-md-mcp.git"
  },
  "bugs": "https://github.com/RobotRegistryFoundation/robot-md-mcp/issues",
  "homepage": "https://robotmd.dev"
}
```

- [ ] **Step 3: Write `tsconfig.json`**

`/home/craigm26/robot-md-mcp/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "outDir": "dist",
    "rootDir": "."
  },
  "include": ["src/**/*", "tests/**/*", "scripts/**/*"]
}
```

- [ ] **Step 4: Write `tsup.config.ts`**

`/home/craigm26/robot-md-mcp/tsup.config.ts`:

```ts
import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts", "src/bin.ts"],
  format: ["esm", "cjs"],
  dts: true,
  clean: true,
  target: "node18",
  outDir: "dist",
  // Force .mjs/.cjs extensions so they match package.json's
  // "bin": "dist/bin.mjs" and "exports" entries. Without this, tsup
  // emits dist/bin.js for ESM (because package.json has
  // "type": "module"), and the bin entry 404s.
  outExtension: ({ format }) => ({
    js: format === "esm" ? ".mjs" : ".cjs",
  }),
  // NOTE: Task 6 replaces this banner with a literal shebang at the top of
  // src/bin.ts so the shebang only lands on bin, not on dist/index.mjs.
  banner: ({ format }) =>
    format === "esm" ? { js: "#!/usr/bin/env node" } : {},
});
```

- [ ] **Step 5: Write `vitest.config.ts`**

`/home/craigm26/robot-md-mcp/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
```

- [ ] **Step 6: Write `.gitignore`**

`/home/craigm26/robot-md-mcp/.gitignore`:

```
node_modules/
dist/
coverage/
*.tgz
.DS_Store
*.log
```

- [ ] **Step 7: Write `LICENSE` (Apache-2.0)**

Copy the text verbatim from `/home/craigm26/robot-md/LICENSE`:

```bash
cp /home/craigm26/robot-md/LICENSE /home/craigm26/robot-md-mcp/LICENSE
```

- [ ] **Step 8: Write the stub `README.md`**

`/home/craigm26/robot-md-mcp/README.md`:

```markdown
# robot-md-mcp

> MCP server that exposes a [`ROBOT.md`](https://robotmd.dev) file to Claude Desktop and any other MCP client.

**Status:** v0.1 — read-only (resources + local tools). No robot dispatch. Full README lands in Task 8 of the implementation plan.
```

- [ ] **Step 9: Install dependencies**

```bash
cd /home/craigm26/robot-md-mcp
npm install
```

Expected: `package-lock.json` created, `node_modules/` populated with 0 vulnerabilities.

- [ ] **Step 10: Verify tsup runs (no source yet, so clean output)**

```bash
mkdir -p src
echo 'export const VERSION = "0.1.0";' > src/index.ts
# Minimal bin stub — Task 6 replaces this with the real entrypoint.
# Empty default export only, so TDD tests in Task 6 start RED.
echo 'export {};' > src/bin.ts
npx tsup 2>&1 | tail -5
```

Expected: `DTS ⚡️ Build success in` + produces `dist/index.{mjs,cjs,d.ts}` and `dist/bin.{mjs,cjs}`.

- [ ] **Step 11: Create the GitHub repo**

```bash
gh repo create RobotRegistryFoundation/robot-md-mcp \
  --public \
  --description "MCP server that exposes a ROBOT.md to Claude Desktop — resources + validate/render tools" \
  --homepage "https://robotmd.dev"
```

Expected: `✓ Created repository RobotRegistryFoundation/robot-md-mcp on github.com`.

- [ ] **Step 12: Initial commit + push**

```bash
cd /home/craigm26/robot-md-mcp
rm -rf dist
git add .
git commit -m "chore(scaffold): initial repo — tsup + vitest + TypeScript strict

Node 18+, Apache-2.0. Dependencies: @modelcontextprotocol/sdk,
ajv, ajv-formats, yaml. No source yet — Task 1+ brings parser,
validator, render, and MCP wiring."
git remote add origin https://github.com/RobotRegistryFoundation/robot-md-mcp.git
git push -u origin main
```

Expected: push succeeds, 0 files under `dist/` tracked.

---

## Task 1: Schema sync script + bundled schema

**Files:**
- Create: `/home/craigm26/robot-md-mcp/scripts/sync-schema.mjs`
- Create: `/home/craigm26/robot-md-mcp/src/schema/robot.schema.json` (generated)

- [ ] **Step 1: Write the sync script**

`/home/craigm26/robot-md-mcp/scripts/sync-schema.mjs`:

```js
// Sync the JSON schema from the canonical robot-md repo.
// Usage: `npm run sync-schema`
// Source: ../robot-md/schema/v1/robot.schema.json (if present)
//         else https://robotmd.dev/schema/v1/robot.schema.json
//
// CI will fail if the bundled copy drifts — see .github/workflows/ci.yml.

import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..");
const localSrc = resolve(repoRoot, "..", "robot-md", "schema", "v1", "robot.schema.json");
const dest = resolve(repoRoot, "src", "schema", "robot.schema.json");

async function fetchSchema() {
  if (existsSync(localSrc)) {
    return readFileSync(localSrc, "utf8");
  }
  const url = "https://robotmd.dev/schema/v1/robot.schema.json";
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`failed to fetch ${url}: ${res.status} ${res.statusText}`);
  }
  return await res.text();
}

const text = await fetchSchema();
mkdirSync(dirname(dest), { recursive: true });
writeFileSync(dest, text);
console.log(`wrote ${dest} (${text.length} bytes)`);
```

- [ ] **Step 2: Run the sync**

```bash
cd /home/craigm26/robot-md-mcp
npm run sync-schema
```

Expected: `wrote /home/craigm26/robot-md-mcp/src/schema/robot.schema.json (<N> bytes)`.

- [ ] **Step 3: Verify the bundle matches the canonical**

```bash
diff -q /home/craigm26/robot-md/schema/v1/robot.schema.json /home/craigm26/robot-md-mcp/src/schema/robot.schema.json
echo "exit: $?"
```

Expected: no output, `exit: 0` (files identical).

- [ ] **Step 4: Commit**

```bash
git add scripts/sync-schema.mjs src/schema/robot.schema.json
git commit -m "feat(schema): bundle canonical schema + sync script

Mirrors robot-md's schema-sync pattern. CI verifies the bundled copy
matches the canonical source at RobotRegistryFoundation/robot-md."
git push
```

---

## Task 2: Parser (TDD)

**Files:**
- Create: `/home/craigm26/robot-md-mcp/tests/fixtures/minimal.ROBOT.md`
- Create: `/home/craigm26/robot-md-mcp/tests/fixtures/no-frontmatter.md`
- Create: `/home/craigm26/robot-md-mcp/tests/fixtures/bad-yaml.ROBOT.md`
- Create: `/home/craigm26/robot-md-mcp/tests/parser.test.ts`
- Create: `/home/craigm26/robot-md-mcp/src/parser.ts`

- [ ] **Step 1: Copy fixtures from robot-md**

```bash
mkdir -p /home/craigm26/robot-md-mcp/tests/fixtures
cp /home/craigm26/robot-md/cli/tests/fixtures/valid/minimal.ROBOT.md \
   /home/craigm26/robot-md-mcp/tests/fixtures/minimal.ROBOT.md
cp /home/craigm26/robot-md/cli/tests/fixtures/invalid/no-frontmatter.md \
   /home/craigm26/robot-md-mcp/tests/fixtures/no-frontmatter.md
cp /home/craigm26/robot-md/cli/tests/fixtures/invalid/bad-yaml.ROBOT.md \
   /home/craigm26/robot-md-mcp/tests/fixtures/bad-yaml.ROBOT.md
```

- [ ] **Step 2: Write the failing tests**

`/home/craigm26/robot-md-mcp/tests/parser.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseRobotMd, ParseError } from "../src/parser.js";

const here = resolve(fileURLToPath(import.meta.url), "..");
const fixture = (name: string) =>
  readFileSync(resolve(here, "fixtures", name), "utf8");

describe("parseRobotMd", () => {
  it("parses a valid minimal ROBOT.md", () => {
    const parsed = parseRobotMd(fixture("minimal.ROBOT.md"));
    expect(parsed.frontmatter).toMatchObject({
      rcan_version: "3.0",
      metadata: { robot_name: "test-bot" },
      physics: { type: "wheeled", dof: 2 },
    });
    expect(parsed.body).toContain("# test-bot");
    expect(parsed.body).toContain("Minimal test robot.");
  });

  it("preserves the raw input text", () => {
    const text = fixture("minimal.ROBOT.md");
    const parsed = parseRobotMd(text);
    expect(parsed.rawText).toBe(text);
  });

  it("throws ParseError when no frontmatter is present", () => {
    expect(() => parseRobotMd(fixture("no-frontmatter.md"))).toThrow(ParseError);
    expect(() => parseRobotMd(fixture("no-frontmatter.md"))).toThrow(/frontmatter/i);
  });

  it("throws ParseError on malformed YAML", () => {
    expect(() => parseRobotMd(fixture("bad-yaml.ROBOT.md"))).toThrow(ParseError);
  });

  it("throws ParseError when text does not start with ---", () => {
    expect(() => parseRobotMd("hello world")).toThrow(ParseError);
  });

  it("throws ParseError when frontmatter is an array (not a mapping)", () => {
    const text = "---\n- a\n- b\n---\n\n# foo\n";
    expect(() => parseRobotMd(text)).toThrow(/mapping/i);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /home/craigm26/robot-md-mcp
npx vitest run tests/parser.test.ts 2>&1 | tail -10
```

Expected: all tests FAIL — `Cannot find module '../src/parser.js'` or equivalent.

- [ ] **Step 4: Implement the parser**

`/home/craigm26/robot-md-mcp/src/parser.ts`:

```ts
import { parse as yamlParse } from "yaml";

export interface ParsedRobotMd {
  /** Frontmatter as a plain object. */
  frontmatter: Record<string, unknown>;
  /** Body markdown, verbatim, after the closing `---`. */
  body: string;
  /** The exact input text that was parsed. */
  rawText: string;
}

export class ParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ParseError";
  }
}

const FRONTMATTER_RE = /^---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n?([\s\S]*)$/;

export function parseRobotMd(text: string): ParsedRobotMd {
  if (!text.trimStart().startsWith("---")) {
    throw new ParseError(
      "no frontmatter found — ROBOT.md must start with a YAML frontmatter block delimited by '---'.",
    );
  }
  const m = text.match(FRONTMATTER_RE);
  if (!m) {
    throw new ParseError("frontmatter block is not properly closed with '---'.");
  }
  const [, yamlText, body] = m;
  let frontmatter: unknown;
  try {
    frontmatter = yamlParse(yamlText);
  } catch (e) {
    throw new ParseError(`invalid YAML frontmatter: ${(e as Error).message}`);
  }
  if (
    typeof frontmatter !== "object" ||
    frontmatter === null ||
    Array.isArray(frontmatter)
  ) {
    throw new ParseError("frontmatter must be a YAML mapping (object), not a list or scalar.");
  }
  return {
    frontmatter: frontmatter as Record<string, unknown>,
    body: body ?? "",
    rawText: text,
  };
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
npx vitest run tests/parser.test.ts 2>&1 | tail -10
```

Expected: `Tests  6 passed (6)`.

- [ ] **Step 6: Commit**

```bash
git add src/parser.ts tests/parser.test.ts tests/fixtures/
git commit -m "feat(parser): parseRobotMd — YAML frontmatter + markdown body

Raises ParseError on missing/malformed frontmatter, non-mapping
frontmatter, or YAML syntax errors. Preserves raw input text for
downstream consumers that want byte-exact content."
git push
```

---

## Task 3: Validator (TDD)

**Files:**
- Create: `/home/craigm26/robot-md-mcp/tests/fixtures/missing-safety.ROBOT.md`
- Create: `/home/craigm26/robot-md-mcp/tests/fixtures/missing-identity-section.ROBOT.md`
- Create: `/home/craigm26/robot-md-mcp/tests/validate.test.ts`
- Create: `/home/craigm26/robot-md-mcp/src/validate.ts`

- [ ] **Step 1: Copy additional fixtures**

```bash
cp /home/craigm26/robot-md/cli/tests/fixtures/invalid/missing-safety.ROBOT.md \
   /home/craigm26/robot-md-mcp/tests/fixtures/missing-safety.ROBOT.md
cp /home/craigm26/robot-md/cli/tests/fixtures/invalid/missing-identity-section.ROBOT.md \
   /home/craigm26/robot-md-mcp/tests/fixtures/missing-identity-section.ROBOT.md
```

- [ ] **Step 2: Write the failing tests**

`/home/craigm26/robot-md-mcp/tests/validate.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseRobotMd } from "../src/parser.js";
import { validateParsed } from "../src/validate.js";

const here = resolve(fileURLToPath(import.meta.url), "..");
const fixture = (name: string) =>
  readFileSync(resolve(here, "fixtures", name), "utf8");

describe("validateParsed", () => {
  it("accepts a valid minimal manifest", () => {
    const result = validateParsed(parseRobotMd(fixture("minimal.ROBOT.md")));
    expect(result.ok).toBe(true);
    expect(result.errors).toEqual([]);
    expect(result.summary).toContain("test-bot");
    expect(result.summary).toContain("wheeled");
    expect(result.summary).toContain("2 DoF");
  });

  it("reports schema violations when required fields are missing", () => {
    const result = validateParsed(parseRobotMd(fixture("missing-safety.ROBOT.md")));
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.toLowerCase().includes("safety"))).toBe(true);
  });

  it("flags mismatch between H1 and metadata.robot_name", () => {
    const mismatched =
      `---
rcan_version: "3.0"
metadata:
  robot_name: alice
physics:
  type: wheeled
  dof: 2
drivers:
  - id: wheels
    protocol: pca9685
safety:
  estop:
    software: true
    response_ms: 200
---

# bob

## Identity
Has wrong H1.
`;
    const result = validateParsed(parseRobotMd(mismatched));
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.includes("H1"))).toBe(true);
  });

  it("flags missing H1 heading", () => {
    const noH1 =
      `---
rcan_version: "3.0"
metadata:
  robot_name: alice
physics:
  type: wheeled
  dof: 2
drivers:
  - id: wheels
    protocol: pca9685
safety:
  estop:
    software: true
    response_ms: 200
---

No heading here.
`;
    const result = validateParsed(parseRobotMd(noH1));
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.toLowerCase().includes("h1"))).toBe(true);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
npx vitest run tests/validate.test.ts 2>&1 | tail -10
```

Expected: FAIL (`Cannot find module '../src/validate.js'`).

- [ ] **Step 4: Implement the validator**

`/home/craigm26/robot-md-mcp/src/validate.ts`:

```ts
import Ajv, { type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import schema from "./schema/robot.schema.json" with { type: "json" };
import type { ParsedRobotMd } from "./parser.js";

export interface ValidateResult {
  ok: boolean;
  summary: string;
  errors: string[];
}

const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);
const validateFn = ajv.compile(schema as object);

function formatAjvError(err: ErrorObject): string {
  const path = err.instancePath || "(root)";
  return `${path}: ${err.message}`;
}

function h1(body: string): string | null {
  const m = body.match(/^\s*#\s+(.+?)\s*$/m);
  return m ? m[1].trim() : null;
}

export function validateParsed(parsed: ParsedRobotMd): ValidateResult {
  const errors: string[] = [];

  const schemaValid = validateFn(parsed.frontmatter);
  if (!schemaValid && validateFn.errors) {
    for (const err of validateFn.errors) {
      errors.push(formatAjvError(err));
    }
  }

  // Body check: H1 must match metadata.robot_name
  const fm = parsed.frontmatter as {
    metadata?: { robot_name?: string };
    physics?: { type?: string; dof?: number };
    capabilities?: unknown[];
  };
  const robotName = fm.metadata?.robot_name;
  if (typeof robotName === "string" && robotName.trim() !== "") {
    const found = h1(parsed.body);
    if (found === null) {
      errors.push(`body: missing H1 heading (expected "# ${robotName}").`);
    } else if (found !== robotName.trim()) {
      errors.push(
        `body: H1 "${found}" does not match metadata.robot_name "${robotName}".`,
      );
    }
  }

  const physicsType = fm.physics?.type ?? "?";
  const dof = typeof fm.physics?.dof === "number" ? fm.physics.dof : 0;
  const caps = Array.isArray(fm.capabilities) ? fm.capabilities.length : 0;
  const summary = `${robotName ?? "?"} (${physicsType}, ${dof} DoF, ${caps} capabilities)`;

  return { ok: errors.length === 0, summary, errors };
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
npx vitest run tests/validate.test.ts 2>&1 | tail -10
```

Expected: `Tests  4 passed (4)`.

If ajv complains about `$schema` draft 2020-12 not supported, confirm the import path is `ajv/dist/2020.js` (not the default `ajv`), which is what this code uses.

- [ ] **Step 6: Commit**

```bash
git add src/validate.ts tests/validate.test.ts tests/fixtures/
git commit -m "feat(validate): validateParsed via ajv against bundled schema

Uses ajv's 2020-12 draft support. Layers body-level H1 / robot_name
match check on top of schema validation, mirroring the Python
validator."
git push
```

---

## Task 4: Render (TDD)

**Files:**
- Create: `/home/craigm26/robot-md-mcp/tests/render.test.ts`
- Create: `/home/craigm26/robot-md-mcp/src/render.ts`

- [ ] **Step 1: Write the failing tests**

`/home/craigm26/robot-md-mcp/tests/render.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse as yamlParse } from "yaml";
import { parseRobotMd } from "../src/parser.js";
import { renderYaml } from "../src/render.js";

const here = resolve(fileURLToPath(import.meta.url), "..");
const fixture = (name: string) =>
  readFileSync(resolve(here, "fixtures", name), "utf8");

describe("renderYaml", () => {
  it("emits canonical YAML for the frontmatter", () => {
    const parsed = parseRobotMd(fixture("minimal.ROBOT.md"));
    const yaml = renderYaml(parsed);
    expect(yaml).toContain("rcan_version:");
    expect(yaml).toContain("robot_name: test-bot");
    expect(yaml).not.toContain("# test-bot"); // body stripped
  });

  it("round-trips: parse(render) equals the original frontmatter", () => {
    const parsed = parseRobotMd(fixture("minimal.ROBOT.md"));
    const rendered = renderYaml(parsed);
    const reparsed = yamlParse(rendered);
    expect(reparsed).toEqual(parsed.frontmatter);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npx vitest run tests/render.test.ts 2>&1 | tail -5
```

Expected: FAIL (`Cannot find module '../src/render.js'`).

- [ ] **Step 3: Implement the renderer**

`/home/craigm26/robot-md-mcp/src/render.ts`:

```ts
import { stringify as yamlStringify } from "yaml";
import type { ParsedRobotMd } from "./parser.js";

export function renderYaml(parsed: ParsedRobotMd): string {
  return yamlStringify(parsed.frontmatter, {
    aliasDuplicateObjects: false,
    lineWidth: 0,
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run tests/render.test.ts 2>&1 | tail -5
```

Expected: `Tests  2 passed (2)`.

- [ ] **Step 5: Commit**

```bash
git add src/render.ts tests/render.test.ts
git commit -m "feat(render): renderYaml — canonical YAML of frontmatter"
git push
```

---

## Task 5: MCP server wiring (resources + tools)

**Files:**
- Create: `/home/craigm26/robot-md-mcp/src/server.ts`
- Create: `/home/craigm26/robot-md-mcp/src/index.ts` (replace scaffold stub)
- Create: `/home/craigm26/robot-md-mcp/tests/server.test.ts`

**API caveat:** `@modelcontextprotocol/sdk` 1.29.x exposes `McpServer` from `@modelcontextprotocol/sdk/server/mcp.js` with `resource()`, `tool()`, and `connect()` methods. If the SDK version you install has diverged, verify by reading `node_modules/@modelcontextprotocol/sdk/dist/esm/server/mcp.d.ts` before adapting — the server test in Step 3 is the ground truth for what needs to work.

- [ ] **Step 1: Write the failing integration test**

`/home/craigm26/robot-md-mcp/tests/server.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { createServer } from "../src/server.js";

const here = resolve(fileURLToPath(import.meta.url), "..");
const fixturePath = resolve(here, "fixtures", "minimal.ROBOT.md");

async function connected(manifestPath: string) {
  const { server } = createServer(manifestPath);
  const [clientT, serverT] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: "test-client", version: "0.0.0" });
  await Promise.all([server.connect(serverT), client.connect(clientT)]);
  return { client, server };
}

describe("MCP server", () => {
  it("lists four resources for a valid manifest", async () => {
    const { client } = await connected(fixturePath);
    const list = await client.listResources();
    const uris = list.resources.map((r) => r.uri).sort();
    expect(uris).toEqual([
      "robot-md://test-bot/body",
      "robot-md://test-bot/capabilities",
      "robot-md://test-bot/frontmatter",
      "robot-md://test-bot/safety",
    ]);
  });

  it("returns JSON frontmatter on read", async () => {
    const { client } = await connected(fixturePath);
    const result = await client.readResource({
      uri: "robot-md://test-bot/frontmatter",
    });
    expect(result.contents[0].mimeType).toBe("application/json");
    const obj = JSON.parse(String(result.contents[0].text));
    expect(obj.metadata.robot_name).toBe("test-bot");
  });

  it("returns raw markdown on body read", async () => {
    const { client } = await connected(fixturePath);
    const result = await client.readResource({
      uri: "robot-md://test-bot/body",
    });
    expect(result.contents[0].mimeType).toBe("text/markdown");
    expect(String(result.contents[0].text)).toContain("# test-bot");
  });

  it("validate tool returns ok=true for a valid manifest", async () => {
    const { client } = await connected(fixturePath);
    const result = await client.callTool({ name: "validate", arguments: {} });
    const text = result.content.find((c) => c.type === "text")?.text;
    const parsed = JSON.parse(String(text));
    expect(parsed.ok).toBe(true);
    expect(parsed.summary).toContain("test-bot");
  });

  it("render tool returns canonical YAML", async () => {
    const { client } = await connected(fixturePath);
    const result = await client.callTool({ name: "render", arguments: {} });
    const text = result.content.find((c) => c.type === "text")?.text;
    expect(String(text)).toContain("robot_name: test-bot");
  });

  it("reflects file changes between calls", async () => {
    const dir = mkdtempSync(join(tmpdir(), "mcp-"));
    const path = join(dir, "ROBOT.md");
    writeFileSync(path, readFileSync(fixturePath, "utf8"));
    const { client } = await connected(path);

    // Mutate the file on disk.
    const mutated = readFileSync(fixturePath, "utf8").replace("Minimal test robot.", "Changed!");
    writeFileSync(path, mutated);

    const body = await client.readResource({ uri: "robot-md://test-bot/body" });
    expect(String(body.contents[0].text)).toContain("Changed!");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npx vitest run tests/server.test.ts 2>&1 | tail -5
```

Expected: FAIL — server module not found.

- [ ] **Step 3: Implement the server**

`/home/craigm26/robot-md-mcp/src/server.ts`:

```ts
import { readFileSync } from "node:fs";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { parseRobotMd, type ParsedRobotMd } from "./parser.js";
import { validateParsed } from "./validate.js";
import { renderYaml } from "./render.js";

export interface ServerHandle {
  server: McpServer;
  robotName: string;
  manifestPath: string;
}

function loadCurrent(manifestPath: string): ParsedRobotMd {
  const text = readFileSync(manifestPath, "utf8");
  return parseRobotMd(text);
}

function robotNameFrom(parsed: ParsedRobotMd): string {
  const name = (parsed.frontmatter as { metadata?: { robot_name?: string } })
    .metadata?.robot_name;
  if (typeof name !== "string" || name.trim() === "") {
    throw new Error(
      "manifest is missing metadata.robot_name; robot-md-mcp needs it to namespace resource URIs.",
    );
  }
  return name.trim();
}

export function createServer(manifestPath: string): ServerHandle {
  const initial = loadCurrent(manifestPath);
  const robotName = robotNameFrom(initial);
  const base = `robot-md://${robotName}`;

  const server = new McpServer({
    name: "robot-md-mcp",
    version: "0.1.0",
  });

  const register = (
    kind: "frontmatter" | "capabilities" | "safety" | "body",
    mimeType: string,
    getBody: (parsed: ParsedRobotMd) => string,
  ) => {
    const uri = `${base}/${kind}`;
    server.resource(kind, uri, async () => ({
      contents: [
        {
          uri,
          mimeType,
          text: getBody(loadCurrent(manifestPath)),
        },
      ],
    }));
  };

  register("frontmatter", "application/json", (p) => JSON.stringify(p.frontmatter));
  register("capabilities", "application/json", (p) =>
    JSON.stringify((p.frontmatter as { capabilities?: unknown[] }).capabilities ?? []),
  );
  register("safety", "application/json", (p) =>
    JSON.stringify((p.frontmatter as { safety?: unknown }).safety ?? {}),
  );
  register("body", "text/markdown", (p) => p.body);

  server.tool(
    "validate",
    "Validate the served ROBOT.md against the v1 schema and body rules.",
    {},
    async () => {
      const result = validateParsed(loadCurrent(manifestPath));
      return {
        content: [{ type: "text", text: JSON.stringify(result) }],
      };
    },
  );

  server.tool(
    "render",
    "Strip prose and return the frontmatter as canonical YAML.",
    {},
    async () => {
      const yaml = renderYaml(loadCurrent(manifestPath));
      return {
        content: [{ type: "text", text: yaml }],
      };
    },
  );

  return { server, robotName, manifestPath };
}
```

- [ ] **Step 4: Rewrite the index barrel**

`/home/craigm26/robot-md-mcp/src/index.ts`:

```ts
export { parseRobotMd, ParseError } from "./parser.js";
export type { ParsedRobotMd } from "./parser.js";
export { validateParsed } from "./validate.js";
export type { ValidateResult } from "./validate.js";
export { renderYaml } from "./render.js";
export { createServer } from "./server.js";
export type { ServerHandle } from "./server.js";
export const VERSION = "0.1.0";
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
npx vitest run tests/server.test.ts 2>&1 | tail -10
```

Expected: `Tests  6 passed (6)`.

**If `server.tool()` argument shape differs in your SDK version** (1.29.x takes `(name, description, zodSchemaOrShape, handler)` — adjust based on the compiled `.d.ts`): the behavior the tests require is the ground truth. Change the call shape, not the tests.

- [ ] **Step 6: Commit**

```bash
git add src/server.ts src/index.ts tests/server.test.ts
git commit -m "feat(server): MCP server — 4 resources + validate/render tools

Exposes robot-md://<name>/{frontmatter,capabilities,safety,body} as
MCP resources and validate/render as tools. Every call re-reads the
manifest; no in-memory cache. In-process integration test covers the
MCP round-trip end to end."
git push
```

---

## Task 6: `bin` entrypoint + CLI smoke test

**Files:**
- Modify: `/home/craigm26/robot-md-mcp/src/bin.ts` (replace scaffold stub)
- Create: `/home/craigm26/robot-md-mcp/tests/bin.test.ts`

- [ ] **Step 1: Write the failing CLI smoke test**

`/home/craigm26/robot-md-mcp/tests/bin.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = resolve(fileURLToPath(import.meta.url), "..");
const bin = resolve(here, "..", "src", "bin.ts");
const fixture = resolve(here, "fixtures", "minimal.ROBOT.md");

// Run via tsx so we don't require a build between test iterations.
// (tsx is bundled via vitest's dep graph; if you prefer, build first and point at dist/bin.mjs.)

function run(args: string[]) {
  return spawnSync("node", ["--import", "tsx/esm", bin, ...args], {
    encoding: "utf8",
    timeout: 2000,
  });
}

describe("robot-md-mcp CLI", () => {
  it("errors when no path is provided", () => {
    const result = spawnSync("node", ["--import", "tsx/esm", bin], {
      encoding: "utf8",
      timeout: 2000,
    });
    expect(result.status).not.toBe(0);
    expect(result.stderr).toMatch(/Usage|path/i);
  });

  it("errors when the path does not exist", () => {
    const result = run(["/tmp/definitely-does-not-exist.ROBOT.md"]);
    expect(result.status).not.toBe(0);
    expect(result.stderr).toMatch(/read|ENOENT|not found/i);
  });

  // The happy-path stdio run is an integration test covered via the
  // in-process MCP client in server.test.ts. A CLI "starts then we
  // kill it" check is flaky across runners; skip it here.
});
```

- [ ] **Step 2: Install tsx as a devDependency for running .ts directly**

```bash
cd /home/craigm26/robot-md-mcp
npm install --save-dev tsx
```

- [ ] **Step 3: Run tests to confirm failure**

```bash
npx vitest run tests/bin.test.ts 2>&1 | tail -10
```

Expected: FAIL (the bin still has the scaffold stub from Task 0).

- [ ] **Step 4: Remove the tsup banner (shebang now lives in src/bin.ts)**

Edit `/home/craigm26/robot-md-mcp/tsup.config.ts` to delete the `banner:` callback added in Task 0. The shebang lives in `src/bin.ts` instead (Step 5 below), so the banner would otherwise prepend `#!/usr/bin/env node` to `dist/index.mjs` too — noise on a library entry.

Remove these lines:

```ts
  banner: ({ format }) =>
    format === "esm" ? { js: "#!/usr/bin/env node" } : {},
```

Keep the `outExtension` callback above them.

- [ ] **Step 5: Implement the bin**

`/home/craigm26/robot-md-mcp/src/bin.ts`:

```ts
#!/usr/bin/env node
import { existsSync } from "node:fs";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createServer } from "./server.js";

async function main() {
  const path = process.argv[2];
  if (!path) {
    console.error(
      "Usage: robot-md-mcp <path-to-ROBOT.md>\n\n" +
        "Add this to Claude Desktop's MCP config (claude_desktop_config.json):\n" +
        '  { "mcpServers": { "robot-md": { "command": "npx", "args": ["-y", "robot-md-mcp", "/path/to/ROBOT.md"] } } }\n',
    );
    process.exit(2);
  }
  if (!existsSync(path)) {
    console.error(`robot-md-mcp: cannot read ${path} (file does not exist).`);
    process.exit(1);
  }

  try {
    const { server, robotName } = createServer(path);
    console.error(`robot-md-mcp: serving ${path} as '${robotName}'`);
    const transport = new StdioServerTransport();
    await server.connect(transport);
  } catch (err) {
    console.error(`robot-md-mcp: failed to start: ${(err as Error).message}`);
    process.exit(1);
  }
}

main();
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
npx vitest run tests/bin.test.ts 2>&1 | tail -10
```

Expected: `Tests  2 passed (2)`.

- [ ] **Step 7: Run the full suite**

```bash
npx vitest run 2>&1 | tail -10
```

Expected: all tests across parser, validate, render, server, bin pass.

- [ ] **Step 8: Build and smoke-test the compiled bin**

```bash
npm run build 2>&1 | tail -5
# Verify the shebang only lands on bin, not on index (Task 0 follow-up):
head -1 dist/bin.mjs    # expect: #!/usr/bin/env node
head -1 dist/index.mjs  # expect: (no shebang — library entry)
node dist/bin.mjs 2>&1 | head -3; echo "exit: $?"
node dist/bin.mjs tests/fixtures/minimal.ROBOT.md </dev/null 2>&1 | head -5 &
PID=$!
sleep 1
kill $PID 2>/dev/null
wait $PID 2>/dev/null
echo "(forked-and-killed — stdio server starts cleanly)"
```

Expected: no-arg run prints Usage + exit 2. Happy path prints `robot-md-mcp: serving …` to stderr and waits for stdin.

- [ ] **Step 9: Commit**

```bash
git add src/bin.ts tests/bin.test.ts tsup.config.ts package.json package-lock.json
git commit -m "feat(bin): CLI entrypoint with stdio MCP transport

Required positional arg for the manifest path; no auto-discovery.
Fails with exit 2 on missing arg, exit 1 on unreadable file, else
starts the MCP server over stdio. tsx added as devDependency for
running the TS entry directly from tests. Also removes the tsup
banner (shebang now lives as bin.ts's first line) so dist/index.mjs
stays clean for library consumers."
git push
```

---

## Task 7: Full README

**Files:**
- Modify: `/home/craigm26/robot-md-mcp/README.md`

- [ ] **Step 1: Replace the stub README**

`/home/craigm26/robot-md-mcp/README.md`:

````markdown
# robot-md-mcp

> MCP server that exposes a [`ROBOT.md`](https://robotmd.dev) file to Claude Desktop and any other MCP-speaking client.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Node](https://img.shields.io/badge/node-18%2B-green)](https://nodejs.org)
[![CI](https://github.com/RobotRegistryFoundation/robot-md-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/RobotRegistryFoundation/robot-md-mcp/actions)

## What it does

Reads a local `ROBOT.md` and exposes it to an MCP client as:

- **Resources** — the client can read at will:
  - `robot-md://<robot_name>/frontmatter` (`application/json`)
  - `robot-md://<robot_name>/capabilities` (`application/json`)
  - `robot-md://<robot_name>/safety` (`application/json`)
  - `robot-md://<robot_name>/body` (`text/markdown`)
- **Tools** — the client invokes on operator request:
  - `validate` → `{ ok, summary, errors }`
  - `render` → canonical YAML of the frontmatter

The server re-reads the file on every call. No cache, no watcher, no runtime config.

## Not in v0.1 — deferred to v0.2

- No signature verification. `ROBOT.md` v0.2 will add signed manifests (`.sig`) and a key-binding-at-RRN-mint flow; see [`spec/v0.2-design.md`](https://robotmd.dev/spec/v0.2-design.md).
- No robot dispatch. `invoke_skill` / `query_status` arrive after the v0.2 signing decisions in §13 are finalized.
- No multi-manifest / fleet mode.

## Install

```bash
# From npm (once NPM_TOKEN is configured on the release workflow)
npx robot-md-mcp /path/to/ROBOT.md

# From GitHub release tarball (during the npm-blocked window)
npm i github:RobotRegistryFoundation/robot-md-mcp#v0.1.0
```

Node 18+ required.

## Claude Desktop config

Add this to your `claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "robot-md": {
      "command": "npx",
      "args": ["-y", "robot-md-mcp", "/absolute/path/to/ROBOT.md"]
    }
  }
}
```

Restart Claude Desktop. Open a new chat — Claude now has the robot's frontmatter, capabilities, safety block, and prose body on tap.

## Tier-0 adoption loop

```bash
# Generate a draft from visible hardware
pip install robot-md
robot-md autodetect --write ./ROBOT.md

# Edit the TODOs (robot name, physics type, DoF, capabilities)
# Then point Claude Desktop at it:
# -> add the JSON snippet above to claude_desktop_config.json
```

## API surface

```ts
import {
  parseRobotMd,
  validateParsed,
  renderYaml,
  createServer,
} from "robot-md-mcp";
```

All four are importable for programmatic use (e.g. building a custom MCP server on top).

## Development

```bash
git clone https://github.com/RobotRegistryFoundation/robot-md-mcp
cd robot-md-mcp
npm install
npm test            # vitest: parser, validator, render, server, bin
npm run build       # tsup → dist/
npm run sync-schema # refresh bundled schema from ../robot-md
```

## Contributing

- Schema lives at [`RobotRegistryFoundation/robot-md`](https://github.com/RobotRegistryFoundation/robot-md) — PR changes there, then re-run `npm run sync-schema` here.
- Small, focused PRs welcome.

## License

Apache 2.0.
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): full v0.1 readme — install, Claude Desktop config, API"
git push
```

---

## Task 8: CI workflow

**Files:**
- Create: `/home/craigm26/robot-md-mcp/.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

`/home/craigm26/robot-md-mcp/.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node: [18, 20, 22]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node }}
          cache: npm
      - run: npm ci
      - run: npm run typecheck
      - run: npm test
      - run: npm run build

  schema-sync-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Checkout canonical robot-md repo
        uses: actions/checkout@v4
        with:
          repository: RobotRegistryFoundation/robot-md
          path: robot-md-upstream
      - name: Compare bundled schema to canonical
        run: |
          set -e
          canon=$(md5sum robot-md-upstream/schema/v1/robot.schema.json | awk '{print $1}')
          bundled=$(md5sum src/schema/robot.schema.json | awk '{print $1}')
          echo "canonical: $canon"
          echo "bundled:   $bundled"
          if [ "$canon" != "$bundled" ]; then
            echo "::error::src/schema/robot.schema.json has drifted from the canonical schema."
            echo "Run: npm run sync-schema"
            exit 1
          fi
          echo "OK — schema is in sync"
```

- [ ] **Step 2: Commit + push and watch CI**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: build-and-test matrix (Node 18/20/22) + schema-sync-check"
git push
```

Then:

```bash
gh run watch --repo RobotRegistryFoundation/robot-md-mcp
```

Expected: both jobs green.

If `build-and-test` fails on `typecheck` because the installed SDK API diverges from the Task 5 implementation, fix inline, re-commit, push again.

---

## Task 9: Release workflow

**Files:**
- Create: `/home/craigm26/robot-md-mcp/.github/workflows/release.yml`

- [ ] **Step 1: Write the workflow**

`/home/craigm26/robot-md-mcp/.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - "v*.*.*"
  workflow_dispatch:
    inputs:
      publish_npm:
        description: "Publish to npm (requires NPM_TOKEN secret)"
        required: true
        type: boolean
        default: false

permissions:
  contents: read

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    outputs:
      tarball: ${{ steps.pack.outputs.filename }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm test
      - run: npm run build
      - name: Pack tarball
        id: pack
        run: |
          name=$(npm pack --silent)
          echo "filename=$name" >> "$GITHUB_OUTPUT"
      - name: Upload build output
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: |
            dist/
            *.tgz
          if-no-files-found: error

  github-release:
    if: startsWith(github.ref, 'refs/tags/v')
    needs: build-and-test
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: artifacts/
      - name: Extract tag message
        id: tag
        run: |
          echo "message<<EOF" >> $GITHUB_OUTPUT
          git tag -l --format='%(contents)' ${{ github.ref_name }} >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          body: ${{ steps.tag.outputs.message }}
          generate_release_notes: true
          files: artifacts/*.tgz

  npm-publish:
    # Manual-only. Trigger via Actions → Release → Run workflow → publish_npm=true.
    # Requires NPM_TOKEN repository secret (Automation token with publish rights).
    if: github.event_name == 'workflow_dispatch' && github.event.inputs.publish_npm == 'true'
    needs: build-and-test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          registry-url: https://registry.npmjs.org
          cache: npm
      - run: npm ci
      - run: npm run build
      - name: Publish to npm
        run: npm publish --access public --provenance
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

- [ ] **Step 2: Commit + push**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): tag→GH Release, workflow_dispatch→npm publish"
git push
```

---

## Task 10: Tag v0.1.0 and verify the release

- [ ] **Step 1: Tag**

```bash
cd /home/craigm26/robot-md-mcp
git tag -a v0.1.0 -m "robot-md-mcp 0.1.0 — first release

MCP server exposing a ROBOT.md to Claude Desktop and any other
MCP-speaking client. Four resources (frontmatter, capabilities,
safety, body) and two tools (validate, render). Node 18+.

Not yet on npm — install from the attached tarball or via
  npm i github:RobotRegistryFoundation/robot-md-mcp#v0.1.0
until NPM_TOKEN is configured on the release workflow."
git push origin v0.1.0
```

- [ ] **Step 2: Watch the release workflow**

```bash
gh run watch --repo RobotRegistryFoundation/robot-md-mcp
```

Expected: `build-and-test` + `github-release` both green, `npm-publish` skipped.

- [ ] **Step 3: Verify the GitHub release + tarball**

```bash
gh release view v0.1.0 --repo RobotRegistryFoundation/robot-md-mcp --json tagName,assets --jq '"tag: \(.tagName)", (.assets[] | "asset: \(.name) (\(.size) bytes)")'
```

Expected:
```
tag: v0.1.0
asset: robot-md-mcp-0.1.0.tgz (<size> bytes)
```

- [ ] **Step 4: Smoke test the published tarball**

```bash
cd /tmp
mkdir mcp-smoke && cd mcp-smoke
npm init -y >/dev/null
npm install github:RobotRegistryFoundation/robot-md-mcp#v0.1.0 2>&1 | tail -3
cp /home/craigm26/robot-md/cli/tests/fixtures/valid/minimal.ROBOT.md ./ROBOT.md
npx robot-md-mcp ./ROBOT.md </dev/null &
PID=$!
sleep 1
kill $PID 2>/dev/null
wait $PID 2>/dev/null
echo "smoke exit: OK if 'serving ROBOT.md as test-bot' appeared above"
```

Expected: the stderr log line `robot-md-mcp: serving ./ROBOT.md as 'test-bot'` appears.

---

## Task 11: Post-release cross-links

**Files:**
- Modify: `/home/craigm26/robot-md/README.md`
- Modify: `/home/craigm26/robot-md/site/index.html`
- Modify: `/home/craigm26/robot-md/integrations/claude-desktop/README.md`

- [ ] **Step 1: Update robot-md's Claude-integration table**

In `/home/craigm26/robot-md/README.md`, find the row:

```markdown
| **Claude Desktop** | 🚧 v0.2 | MCP server `robot-md-mcp` — resources + tools |
```

Replace with:

```markdown
| **Claude Desktop** | ✅ v0.1 (read-only) | [`robot-md-mcp`](https://github.com/RobotRegistryFoundation/robot-md-mcp) — resources + validate/render; dispatch tools arrive with v0.2 signing |
```

- [ ] **Step 2: Update the homepage status badge**

Find in `/home/craigm26/robot-md/site/index.html` the Claude Desktop surface card's status pill (currently `◑ Shipping v0.2`) and change it to `● Shipping v0.1 (read-only)`. Also add a link to the new repo in the card's CTA line.

```bash
cd /home/craigm26/robot-md
grep -n '◑ Shipping v0.2' site/index.html
```

Edit the two occurrences — the Claude Desktop one becomes read-only-v0.1; the Claude Mobile one stays as `◑ Shipping v0.2` (unchanged).

- [ ] **Step 3: Update integrations/claude-desktop/README.md**

Replace the `"Working MCP server code lands in v0.2"` status banner with:

```markdown
> **Status:** v0.1 shipped — read-only (resources + validate/render tools). Robot-dispatch tools (`invoke_skill`, `query_status`) arrive with v0.2 signing. See [`spec/v0.1-mcp-design.md`](../../spec/v0.1-mcp-design.md) and the separate repo [`robot-md-mcp`](https://github.com/RobotRegistryFoundation/robot-md-mcp).
```

- [ ] **Step 4: Commit + push robot-md**

```bash
cd /home/craigm26/robot-md
git add README.md site/index.html integrations/claude-desktop/README.md
git commit -m "docs: robot-md-mcp v0.1 shipped — update status + links

Claude Desktop surface flips from 🚧 v0.2 to ✅ v0.1 (read-only).
Homepage card + README table + integrations README all point at
RobotRegistryFoundation/robot-md-mcp."
git push
```

---

## What lands after this plan is done

- `RobotRegistryFoundation/robot-md-mcp@v0.1.0` — installable from GitHub.
- Claude Desktop config snippet in the README that any operator can paste.
- Four MCP resources + two tools, all backed by tests.
- CI matrix on Node 18/20/22 + schema-sync-check.
- Release workflow ready to publish to npm the moment `NPM_TOKEN` is configured.
- robot-md ecosystem docs updated to reflect Claude Desktop as shipped.

## Explicitly not in scope here

- npm publish itself (blocked on `NPM_TOKEN` — separate task).
- Signature verification or robot-dispatch tools (v0.2 — blocked on `spec/v0.2-design.md` §13).
- Filesystem-watcher hot-reload.
- Multi-manifest / fleet mode.

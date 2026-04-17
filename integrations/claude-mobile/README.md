# Claude Mobile (iOS / Android) integration

> **Status:** v0.1 documents the approach. Cloudflare Worker template lands in v0.2.

Claude Mobile runs in the chat app on iOS/Android. It has no local tool execution and no MCP support — but it can fetch URLs and reason over their contents, and the conversation history persists across turns. That's enough to operate a robot described by a `ROBOT.md` hosted at a public URL.

## The pattern: URL-based ROBOT.md delivery

1. Host your robot's `ROBOT.md` at a stable public URL. Options:
   - Your own domain: `https://mycompany.com/robots/bob.ROBOT.md`
   - Hosted by `robotmd.dev` (v0.2 feature): `https://robotmd.dev/r/RRN-000000000001`
   - GitHub raw URL: `https://raw.githubusercontent.com/<you>/<repo>/main/ROBOT.md`

2. In Claude Mobile, paste the URL + a question:

   > "My robot is declared at https://robotmd.dev/r/RRN-000000000001 — what are its capabilities and how do I make it pick up a red cube?"

3. Claude Mobile fetches the URL, parses the ROBOT.md frontmatter + body, and reasons over the robot's declared capabilities + safety constraints.

4. For actual command dispatch, the `ROBOT.md`'s `network.rrf_endpoint` + `network.ruri` give Claude everything it needs to construct an authenticated RCAN INVOKE — but Claude Mobile itself cannot make outbound HTTP calls with your credentials. You have two options:

   **(a) Copy-paste loop**: Claude generates the invocation payload; you copy it into a terminal or mobile SSH to dispatch; you paste the result back.

   **(b) Invoke bridge** (v0.2): a thin HTTPS endpoint at `https://robotmd.dev/invoke/<rrn>` that Claude Mobile can POST to (with a per-robot bearer token you generate offline). The bridge relays to the robot's gateway.

Pattern (a) is "MVP works today with v0.1." Pattern (b) is "real product" and lands in v0.2.

## Example Claude Mobile session

> **You:** Here's my robot: https://robotmd.dev/r/RRN-000000000001

> **Claude:** *[fetches, parses]* I see you have **bob**, a 6-DOF SO-ARM101 arm with an OAK-D camera, running OpenCastor on a Raspberry Pi 5. Declared capabilities: `arm.pick`, `arm.place`, `arm.reach`, `vision.describe`, `status.report`. Max payload 0.5 kg. Software E-stop at 100 ms. Destructive actions require human approval.

> **You:** How do I ask bob to pick up a red cube?

> **Claude:** *[reasoning over capabilities]* You'd dispatch `arm.pick` with params specifying the object. First run `vision.describe` to locate the cube, then `arm.pick` with the detected pose. Do you want me to generate the RCAN INVOKE payloads?

> **You:** Yes.

> **Claude:** *[generates JSON]*

```json
{
  "msg_type": 11,
  "skill": "vision.describe",
  "params": { "query": "red cube" }
}
```

> Dispatch this to `https://robot.local:8001/rcan` with your auth token. Once you have the bounding box + depth, I'll generate the `arm.pick` payload.

## Hosting your ROBOT.md for Mobile

Three tiers:

### Tier 1 — static HTTPS (works today)

Upload `ROBOT.md` to any static host (Cloudflare Pages, GitHub Pages, S3, your own server). Claude Mobile fetches plain text. If you want URL stability with an RRN, use a redirect.

### Tier 2 — `robotmd.dev/r/<rrn>` (v0.2)

Register your robot with RRF, host your ROBOT.md anywhere, and `robotmd.dev/r/<rrn>` becomes a stable alias that Claude Mobile (and any other client) can fetch. The `robotmd.dev` edge fetches from the canonical location declared in your RRF entry.

### Tier 3 — authenticated (v1.0)

For private robots: the ROBOT.md served from `robotmd.dev/r/<rrn>` redacts sensitive fields (`network.rrf_endpoint`, `compliance.fria_ref`) unless the caller presents a valid RRF-issued token. Claude Mobile can still reason over the capability list, but can't construct direct commands without operator involvement.

## Why not MCP on mobile?

Claude Mobile today doesn't support MCP servers — those are a desktop feature. If that changes, this integration will switch to MCP (see `../claude-desktop/README.md`) and this URL-based pattern becomes a fallback.

## References

- Claude Mobile: <https://claude.ai/> (works on iOS/Android via browser + native apps)
- RCAN INVOKE message format: <https://rcan.dev/spec/section-19/>
- Robot Registry Foundation: <https://robotregistryfoundation.org/>

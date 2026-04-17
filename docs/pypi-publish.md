# Publishing `robot-md` to PyPI

v0.1.0 is tagged locally + on GitHub but not yet on PyPI. This page documents the three steps to publish.

The release workflow (`.github/workflows/release.yml`) uses **PyPI Trusted Publishing (OIDC)** — no tokens checked into the repo.

## One-time setup (5 min)

### 1. PyPI pending publisher

Go to <https://pypi.org/manage/account/publishing/> (create/login first if needed) → **Add a new pending publisher**.

Fill in:

| Field | Value |
|---|---|
| PyPI Project Name | `robot-md` |
| Owner | `craigm26` |
| Repository name | `robot-md` |
| Workflow filename | `release.yml` |
| Environment name | `pypi` |

Click **Add**.

> If you already have an `anthropic-sdk` / `rcan` / other PyPI project published, this uses the same account. If not, create one with the email you'd like listed on the package.

### 2. GitHub `pypi` environment

```bash
gh api repos/continuonai/robot-md/environments/pypi -X PUT --silent
```

(No protection rules needed for a first release. Optional: require manual approval to publish.)

### 3. Push a release tag

The `v0.1.0` tag already exists but was pushed while the repo was private and PyPI wasn't configured. Push a fresh patch tag to trigger the workflow:

```bash
cd /home/continuonai/robot-md
git tag -a v0.1.1 -m "robot-md v0.1.1 — initial PyPI publish

Same code as v0.1.0. Patch bump to trigger first PyPI publish after
the trusted-publisher config landed."
git push origin v0.1.1
```

Bump `cli/pyproject.toml` version to `0.1.1` first and commit it so the build produces the right wheel.

## Watching the release

```bash
gh run watch --repo continuonai/robot-md $(gh run list --repo continuonai/robot-md --workflow=release.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

The workflow:
1. Checks out the tag
2. Builds `robot-md-0.1.1` wheel + sdist from `cli/`
3. Uploads via OIDC (no secrets)
4. Creates a GitHub Release with the tag message

## Verifying the publish

```bash
pip install robot-md==0.1.1 --dry-run   # lookup on PyPI
```

Then a fresh venv smoke test:

```bash
python -m venv /tmp/pypi-smoke
source /tmp/pypi-smoke/bin/activate
pip install robot-md
robot-md --version                      # robot-md 0.1.1
curl -fsSL https://robotmd.dev/examples/bob.ROBOT.md -o /tmp/bob.ROBOT.md \
  || curl -fsSL https://raw.githubusercontent.com/continuonai/robot-md/main/examples/bob.ROBOT.md -o /tmp/bob.ROBOT.md
robot-md validate /tmp/bob.ROBOT.md     # ✓ bob (arm+camera, 6 DoF, 5 capabilities)
deactivate
```

## Future releases

Bump `cli/pyproject.toml`, commit, tag, push. That's it.

```bash
cd /home/continuonai/robot-md
# edit cli/pyproject.toml → version = "0.1.2"
git commit -am "chore(release): v0.1.2"
git tag -a v0.1.2 -m "robot-md v0.1.2 — <short reason>"
git push && git push --tags
```

## Why not publish now?

The dashboard step at <https://pypi.org/manage/account/publishing/> needs a browser + PyPI login — can't be done from the CLI session. The first publish MUST include pending-publisher config; subsequent publishes don't.

Once you do the ~5 minutes of setup, every future tag auto-publishes.

## If something breaks

- **Workflow fails at Publish step with `403`**: the pending publisher didn't activate. Re-check the PyPI dashboard settings match the repo / workflow / environment name exactly.
- **Workflow fails at build step**: check `cli/pyproject.toml` is valid. Build locally first: `cd cli && python -m build && ls dist/`.
- **Package uploaded but `pip install` 404**: PyPI has an eventual-consistency CDN; wait 2-3 min and retry.

## Related

- PyPI trusted publishing docs: <https://docs.pypi.org/trusted-publishers/>
- The release workflow: [`.github/workflows/release.yml`](../.github/workflows/release.yml)
- Spec version gate: `cli/pyproject.toml` declares `rcan_version: "3.0"` compat via the CLI's schema validation.

"""robot-md actuator — scaffolder for production actuator packages.

Plan 2 ships `actuator init`. Plans 3+ will add `actuator search` and
`actuator publish` (registry primitive).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from importlib import resources
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib as _toml
else:
    import tomli as _toml  # type: ignore[import-not-found]  # 3.10 only

from robot_md.registry import (
    extract_manifest_signals,
    format_search_results,
    score_entry,
)

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _validate_name(name: str) -> None:
    if not _KEBAB_RE.match(name):
        raise ValueError(
            f"package name {name!r} must be kebab-case (lowercase letters, digits, single hyphens)"
        )


def _kebab_to_snake(name: str) -> str:
    return name.replace("-", "_")


def _kebab_to_pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("-"))


def _read_template(name: str) -> str:
    """Read a packaged template file from `robot_md/templates/actuator/`."""
    return resources.files("robot_md.templates").joinpath("actuator", name).read_text()


def _render(
    template: str,
    *,
    name: str,
    name_underscored: str,
    NameClass: str,
    description: str,
    author: str,
) -> str:
    """Substitute scaffold-time placeholders. Other `{{ ... }}` left literal."""
    return (
        template.replace("{{ name }}", name)
        .replace("{{ name_underscored }}", name_underscored)
        .replace("{{ NameClass }}", NameClass)
        .replace("{{ description }}", description)
        .replace("{{ author }}", author)
    )


def scaffold_actuator_package(
    name: str,
    parent_dir: Path,
    *,
    author: str,
    description: str = "TODO: one-line description of what this actuator drives.",
) -> Path:
    """Create a production actuator package skeleton at `<parent_dir>/<name>/`.

    Returns the package root path.
    """
    _validate_name(name)
    snake = _kebab_to_snake(name)
    pascal = _kebab_to_pascal(name)

    pkg_root = parent_dir / name
    if pkg_root.exists():
        raise FileExistsError(f"{pkg_root} already exists")

    src_dir = pkg_root / "src" / snake
    src_skills_dir = src_dir / "skills"
    tests_dir = pkg_root / "tests"
    plugin_dir = pkg_root / "claude-plugin" / ".claude-plugin"
    plugin_skills_dir = pkg_root / "claude-plugin" / "skills" / f"using-{name}"
    plugin_hooks_dir = pkg_root / "claude-plugin" / "hooks"

    for d in (src_dir, src_skills_dir, tests_dir, plugin_dir, plugin_skills_dir, plugin_hooks_dir):
        d.mkdir(parents=True, exist_ok=True)

    common = dict(
        name=name,
        name_underscored=snake,
        NameClass=pascal,
        description=description,
        author=author,
    )

    # Top-level files.
    (pkg_root / "pyproject.toml").write_text(
        _render(_read_template("pyproject.toml.tmpl"), **common)
    )
    (pkg_root / "README.md").write_text(_render(_read_template("README.md.tmpl"), **common))

    # Python source.
    (src_dir / "__init__.py").write_text("")
    (src_dir / "actuator.py").write_text(_render(_read_template("src_actuator.py.tmpl"), **common))

    # Tests.
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_actuator.py").write_text(
        _render(_read_template("test_actuator.py.tmpl"), **common)
    )

    # Claude-plugin sibling.
    (plugin_dir / "plugin.json").write_text(_render(_read_template("plugin.json.tmpl"), **common))
    (plugin_skills_dir / "SKILL.md").write_text(_render(_read_template("skill.md.tmpl"), **common))
    (plugin_hooks_dir / "hooks.json").write_text(
        _render(_read_template("hooks.json.tmpl"), **common)
    )

    # Bundled SKILL.md inside the importable Python package — so
    # `robot-md install-skill <pkg>` (Plan 2 Task 7) finds it via
    # `importlib.import_module(<pkg>).__file__.parent / "skills"`.
    (src_skills_dir / f"using-{name}.SKILL.md").write_text(
        _render(_read_template("skill.md.tmpl"), **common)
    )

    return pkg_root


def actuator_search(
    index: dict,
    *,
    query: str,
    manifest: dict | None,
    type_filter: str = "actuator",
    threshold: float = 0.3,
    limit: int = 5,
) -> str:
    """Filter index entries by type, score them against query+manifest,
    and return the formatted output string."""
    entries = [e for e in index.get("entries", []) if e.get("type") == type_filter]
    signals = extract_manifest_signals(manifest) if manifest else None
    scored = [(e, score_entry(e, query=query, manifest_signals=signals)) for e in entries]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    nonzero = [pair for pair in scored if pair[1] > 0.0]
    if not nonzero:
        return format_search_results([], threshold=threshold, limit=limit)
    return format_search_results(nonzero, threshold=threshold, limit=limit)


def detect_package_metadata(pkg_dir: Path) -> dict:
    """Scan a scaffolded actuator package and return metadata for publish.

    Reads:
      - pyproject.toml for name, version, description, Repository URL
      - src/<snake>/skills/*.SKILL.md frontmatter for hardware_tags + manifest_signals
      - claude-plugin/.claude-plugin/plugin.json existence flag

    Raises FileNotFoundError if pyproject.toml is missing.
    """
    pyproject = pkg_dir / "pyproject.toml"
    if not pyproject.is_file():
        raise FileNotFoundError(f"missing {pyproject}")
    with pyproject.open("rb") as fh:
        data = _toml.load(fh)
    project = data.get("project", {})
    urls = project.get("urls", {}) or {}
    repo_url = urls.get("Repository") or urls.get("repository") or ""

    snake = (project.get("name") or pkg_dir.name).replace("-", "_")
    skills_dir = pkg_dir / "src" / snake / "skills"
    skill_files: list[str] = []
    hardware_tags: list[str] = []
    manifest_signals: list[str] = []
    if skills_dir.is_dir():
        import frontmatter

        for sf in sorted(skills_dir.glob("*.SKILL.md")):
            skill_files.append(sf.name)
            try:
                post = frontmatter.load(sf)
            except Exception:
                continue
            for k_src, k_dst in (
                ("hardware_tags", hardware_tags),
                ("manifest_signals", manifest_signals),
            ):
                v = post.metadata.get(k_src)
                if isinstance(v, list):
                    k_dst.extend(str(x) for x in v)

    plugin_marker = pkg_dir / "claude-plugin" / ".claude-plugin" / "plugin.json"
    return {
        "name": project.get("name", pkg_dir.name),
        "version": project.get("version", "0.0.0"),
        "description": project.get("description", ""),
        "repository_url": repo_url,
        "hardware_tags": hardware_tags,
        "manifest_signals": manifest_signals,
        "has_plugin_layout": plugin_marker.is_file(),
        "skill_files": skill_files,
    }


def build_registry_entry(
    meta: dict,
    *,
    publisher: str,
    published_at: str,
) -> dict:
    """Build the JSON entry shape that goes into site/actuators/index.json."""
    name = meta["name"]
    entry: dict = {
        "type": "actuator",
        "name": name,
        "version": meta["version"],
        "description": meta.get("description", ""),
        "install": {
            "package_manager": "pip",
            "package": name,
            "post_install": f"robot-md install-skill {name}",
        },
        "hardware_tags": meta.get("hardware_tags", []),
        "manifest_signals": meta.get("manifest_signals", []),
        "repository": meta.get("repository_url", ""),
        "skill_files": meta.get("skill_files", []),
        "publisher": publisher,
        "published_at": published_at,
        "verified": False,
    }
    if meta.get("has_plugin_layout"):
        entry["plugin_marketplace_entry"] = {
            "marketplace": "robotregistryfoundation",
            "plugin_name": name,
            "install_command": f"/plugin install {name}@robotregistryfoundation",
        }
    return entry


REGISTRY_REPO = "RobotRegistryFoundation/robot-md"
MARKETPLACE_REPO = "RobotRegistryFoundation/claude-code-plugins"


def _publish_worktree(label: str) -> Path:
    """Pick the per-publish worktree path. Allows tests to override via env."""
    base = os.environ.get("ROBOT_MD_PUBLISH_WORKTREE")
    if base:
        p = Path(base) / label
        p.mkdir(parents=True, exist_ok=True)
        return p
    return Path(tempfile.mkdtemp(prefix=f"robot-md-publish-{label}-"))


def _gh(*args: str, capture: bool = False, check: bool = True) -> str:
    """Run a gh CLI command. Returns stdout if capture=True."""
    res = subprocess.run(
        list(args),
        capture_output=capture,
        text=True,
        check=check,
    )
    return res.stdout if capture else ""


def _git(cwd: Path, *args: str, check: bool = True) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=check)


def open_registry_pr(entry: dict) -> str:
    """Fork robot-md, append entry to site/actuators/index.json, push, open PR.

    Returns the PR URL.
    """
    import json as _json

    name = entry["name"]
    version = entry["version"]
    branch = f"publish/{name}-{version}"
    wt = _publish_worktree(f"registry-{name}")

    subprocess.run(
        ["gh", "repo", "fork", REGISTRY_REPO, "--clone=false", "--remote=false"],
        check=False,
    )
    user = (
        subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        or "unknown"
    )

    fork_url = f"https://github.com/{user}/robot-md.git"
    subprocess.run(["git", "clone", fork_url, str(wt)], check=True)
    _git(wt, "checkout", "-b", branch)

    index_path = wt / "site" / "actuators" / "index.json"
    data = _json.loads(index_path.read_text()) if index_path.is_file() else {"entries": []}
    data.setdefault("entries", []).append(entry)
    data["generated_at"] = entry.get("published_at", data.get("generated_at"))
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(_json.dumps(data, indent=2) + "\n")

    _git(wt, "add", str(index_path))
    _git(wt, "commit", "-m", f"registry(actuator): publish {name} v{version}")
    _git(wt, "push", "origin", branch)

    pr_body = (
        f"Adds `{name}` v{version} to the actuator catalog.\n\n"
        "**Conformance checklist**:\n"
        "- [ ] Implements `robot_md_gateway.actuators` Protocol\n"
        "- [ ] Tests pass\n"
        "- [ ] SKILL.md present at `<pkg>/skills/`\n"
        "- [ ] Repository accessible at the URL in the entry\n"
        "- [ ] `pip install <package>` works\n"
    )
    out = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            REGISTRY_REPO,
            "--title",
            f"registry(actuator): publish {name} v{version}",
            "--body",
            pr_body,
            "--head",
            f"{user}:{branch}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def open_marketplace_pr(meta: dict) -> str:
    """Fork claude-code-plugins, append plugin block to marketplace.json, push, open PR.

    Returns the PR URL.
    """
    import json as _json

    name = meta["name"]
    version = meta["version"]
    branch = f"publish/{name}-{version}"
    wt = _publish_worktree(f"marketplace-{name}")

    subprocess.run(
        ["gh", "repo", "fork", MARKETPLACE_REPO, "--clone=false", "--remote=false"],
        check=False,
    )
    user = (
        subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        or "unknown"
    )

    fork_url = f"https://github.com/{user}/claude-code-plugins.git"
    subprocess.run(["git", "clone", fork_url, str(wt)], check=True)
    _git(wt, "checkout", "-b", branch)

    mp_path = wt / "marketplace.json"
    data = _json.loads(mp_path.read_text()) if mp_path.is_file() else {"plugins": []}
    data.setdefault("plugins", []).append(
        {
            "name": name,
            "version": version,
            "description": meta.get("description", ""),
            "repository": meta.get("repository_url", ""),
        }
    )
    mp_path.parent.mkdir(parents=True, exist_ok=True)
    mp_path.write_text(_json.dumps(data, indent=2) + "\n")

    _git(wt, "add", str(mp_path))
    _git(wt, "commit", "-m", f"marketplace: add {name} plugin")
    _git(wt, "push", "origin", branch)

    out = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            MARKETPLACE_REPO,
            "--title",
            f"marketplace: add {name} plugin",
            "--body",
            f"Adds `{name}` v{version} to the Claude Code plugin marketplace.",
            "--head",
            f"{user}:{branch}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()

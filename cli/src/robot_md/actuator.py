"""robot-md actuator — scaffolder for production actuator packages.

Plan 2 ships `actuator init`. Plans 3+ will add `actuator search` and
`actuator publish` (registry primitive).
"""

from __future__ import annotations

import base64
import json
import re
import sys
from importlib import resources
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib as _toml
else:
    import tomli as _toml  # type: ignore[import-not-found]  # 3.10 only

from rcan import sign_body

from robot_md.publisher_key import KeyPair, load_or_mint_publisher_key
from robot_md.registry import (
    extract_manifest_signals,
    format_search_results,
    score_entry,
)
from robot_md.rrf_packages import (
    append_version,
    register_package,
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


def publish_record_path(package_name: str) -> Path:
    return Path.home() / ".robot-md" / "published" / f"{package_name}.json"


def record_published_rpn(package_name: str, rpn: str, record_url: str) -> None:
    p = publish_record_path(package_name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"rpn": rpn, "record_url": record_url}))


def load_published_rpn(package_name: str) -> tuple[str | None, str | None]:
    p = publish_record_path(package_name)
    if not p.is_file():
        return (None, None)
    data = json.loads(p.read_text())
    return (data.get("rpn"), data.get("record_url"))


def _sign(fields: dict, kp: KeyPair) -> dict:
    """Wrap rcan.sign_body — returns the signed dict (fields + sig block)."""
    return sign_body(
        kp.ml_dsa,
        fields,
        ed25519_secret=kp.ed25519_sec,
        ed25519_public=kp.ed25519_pub,
    )


def _build_register_body(meta: dict, kp: KeyPair) -> dict:
    fields = {
        "name": meta["name"],
        "description": meta.get("description", ""),
        "package_type": "actuator",
        "repository_url": meta.get("repository_url", ""),
        "hardware_tags": meta.get("hardware_tags", []),
        "manifest_signals": meta.get("manifest_signals", []),
        "skill_files": meta.get("skill_files", []),
        "has_plugin_layout": meta.get("has_plugin_layout", False),
        "version": meta["version"],
        "pq_signing_pub": base64.b64encode(kp.pq_signing_pub).decode(),
        "pq_kid": kp.pq_kid,
        "ed25519_pub": base64.b64encode(kp.ed25519_pub).decode(),
    }
    return _sign(fields, kp)


def _build_version_body(version: str, kp: KeyPair) -> dict:
    return _sign({"version": version}, kp)


def actuator_publish_first_time(pkg_dir: Path, *, github_user: str) -> dict:
    """Mint RPN at RRF, cache locally, return the RRF response."""
    meta = detect_package_metadata(pkg_dir)
    kp = load_or_mint_publisher_key(github_user)
    body = _build_register_body(meta, kp)
    out = register_package(signed_body=body)
    record_published_rpn(meta["name"], out["rpn"], out["record_url"])
    return out


def actuator_publish_version_update(pkg_dir: Path, *, github_user: str) -> dict:
    """Append new version to existing RPN at RRF."""
    meta = detect_package_metadata(pkg_dir)
    rpn, _ = load_published_rpn(meta["name"])
    if not rpn:
        raise ValueError(
            f"No RPN cached for {meta['name']}. "
            "Run `robot-md actuator publish` (without --version-update flag) first."
        )
    kp = load_or_mint_publisher_key(github_user)
    body = _build_version_body(meta["version"], kp)
    return append_version(rpn, signed_body=body)

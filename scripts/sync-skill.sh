#!/usr/bin/env bash
# Canonical using-robot-md SKILL.md lives in robot-md-mcp:
#   ~/robot-md-mcp/skills/using-robot-md/SKILL.md
#
# It must be copied to:
#   cli/src/robot_md/skills/using-robot-md.SKILL.md  (bundled with Python package
#                                                     for `robot-md install-skill`)
#
# Run this after editing the canonical skill in robot-md-mcp.
# CI in robot-md verifies the two are identical.
#
# Source resolution order:
#   1. $ROBOT_MD_MCP_SRC env var (explicit path to a checkout)
#   2. ../robot-md-mcp/skills/using-robot-md/SKILL.md (sibling checkout)
#   3. fetch from raw.githubusercontent.com (CI / no local checkout)

set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO/cli/src/robot_md/skills/using-robot-md.SKILL.md"

resolve_source() {
    if [[ -n "${ROBOT_MD_MCP_SRC:-}" ]]; then
        local src="$ROBOT_MD_MCP_SRC/skills/using-robot-md/SKILL.md"
        if [[ -f "$src" ]]; then
            echo "$src"
            return 0
        fi
    fi

    local sibling="$REPO/../robot-md-mcp/skills/using-robot-md/SKILL.md"
    if [[ -f "$sibling" ]]; then
        echo "$sibling"
        return 0
    fi

    local tmp; tmp="$(mktemp)"
    local url="https://raw.githubusercontent.com/RobotRegistryFoundation/robot-md-mcp/main/skills/using-robot-md/SKILL.md"
    if curl -fsSL "$url" -o "$tmp" 2>/dev/null; then
        echo "$tmp"
        return 0
    fi

    echo "ERROR: could not locate canonical SKILL.md" >&2
    echo "  Tried: \$ROBOT_MD_MCP_SRC, ../robot-md-mcp/, $url" >&2
    return 1
}

SRC="$(resolve_source)"
cp "$SRC" "$DEST"
echo "✓ SKILL.md synced from $SRC"
echo "  → $DEST"

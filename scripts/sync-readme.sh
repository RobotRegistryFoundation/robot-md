#!/usr/bin/env bash
# The canonical README is the repository's README.md. The Python package needs
# its own copy at cli/README.md, because hatchling (1.32 and later) refuses a
# readme path outside the project directory (cli/), and the old
# `readme = "../README.md"` broke every install and build.
# Run this after editing README.md. CI verifies the two match.

set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

cp "$REPO/README.md" "$REPO/cli/README.md"
echo "✓ README.md synced to cli/README.md"

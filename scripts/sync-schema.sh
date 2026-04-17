#!/usr/bin/env bash
# Canonical schema lives at schema/v1/robot.schema.json.
# Two copies must be kept in sync:
#   - cli/src/robot_md/schemas/v1/robot.schema.json   (bundled with Python package)
#   - site/schema/v1/robot.schema.json                (served at robotmd.dev/schema/v1/)
# Run this after editing the canonical schema. CI verifies both copies match.

set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO/schema/v1/robot.schema.json"

cp "$SRC" "$REPO/cli/src/robot_md/schemas/v1/robot.schema.json"
cp "$SRC" "$REPO/site/schema/v1/robot.schema.json"
echo "✓ Schema synced to cli/ and site/"

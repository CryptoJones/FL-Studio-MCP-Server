#!/bin/bash
# Bump the project version in ONE shot so the README version badge never drifts
# from the shipped version: updates `version` in pyproject.toml AND the shields.io
# version badge in README.md. CI (the `version-badge` job) fails if they differ,
# so this is the supported way to bump.
#
# Usage:  ./scripts/bump-version.sh 0.0.2
set -euo pipefail
cd "$(dirname "$0")/.."

V="${1:-}"
if [[ ! "$V" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]]; then
  echo "usage: scripts/bump-version.sh X.Y.Z   (e.g. 0.0.2)" >&2
  exit 1
fi

# -i.bak works on both BSD (macOS) and GNU sed; remove the backup after.
sed -i.bak -E "s/^version *= *\"[0-9.]+\"/version = \"$V\"/" pyproject.toml
sed -i.bak -E "s#badge/version-[0-9.]+-orange#badge/version-$V-orange#" README.md
rm -f pyproject.toml.bak README.md.bak

echo "bumped to $V:"
grep -nE '^version' pyproject.toml
grep -no 'badge/version-[0-9.]*-orange' README.md

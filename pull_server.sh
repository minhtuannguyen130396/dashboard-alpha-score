#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/dashboard-alpha-score}"
BRANCH="${1:-dev}"

cd "$REPO_DIR"

echo "Repository: $REPO_DIR"
echo "Branch: $BRANCH"

git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

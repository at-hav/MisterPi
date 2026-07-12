#!/usr/bin/env bash
set -Eeuo pipefail

REPO_SLUG="${WAIAN_REPO_SLUG:-at-hav/MisterPi}"
BRANCH="${WAIAN_BRANCH:-main}"

curl -fsSL --proto '=https' --tlsv1.2 \
  "https://raw.githubusercontent.com/${REPO_SLUG}/${BRANCH}/install.sh" | \
  WAIAN_REPO_SLUG="$REPO_SLUG" WAIAN_BRANCH="$BRANCH" /usr/bin/bash -s -- "$@"

#!/usr/bin/env bash
set -Eeuo pipefail

REPO_SLUG="${WAIAN_REPO_SLUG:-__GITHUB_REPOSITORY__}"
BRANCH="${WAIAN_BRANCH:-main}"

if [[ "$REPO_SLUG" == "__GITHUB_REPOSITORY__" ]]; then
  echo "ERROR: repository owner is not configured yet" >&2
  exit 2
fi

curl -fsSL --proto '=https' --tlsv1.2 \
  "https://raw.githubusercontent.com/${REPO_SLUG}/${BRANCH}/install.sh" | \
  WAIAN_REPO_SLUG="$REPO_SLUG" WAIAN_BRANCH="$BRANCH" /usr/bin/bash -s -- "$@"

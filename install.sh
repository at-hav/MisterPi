#!/usr/bin/env bash
set -Eeuo pipefail

REPO_SLUG="${WAIAN_REPO_SLUG:-at-hav/MisterPi}"
BRANCH="${WAIAN_BRANCH:-main}"
FAT_ROOT="${WAIAN_FAT_ROOT:-/media/fat}"
MANAGED_ROOT="${WAIAN_MANAGED_ROOT:-${FAT_ROOT}/.waian}"
DOWNLOAD_ROOT="${MANAGED_ROOT}/.install.$$"
ARCHIVE="${DOWNLOAD_ROOT}/repository.tar.gz"
EXTRACTED="${DOWNLOAD_ROOT}/extracted"
NEW_REPO="${MANAGED_ROOT}/repo.new"

cleanup() {
  rm -rf -- "$DOWNLOAD_ROOT" "$NEW_REPO"
}
trap cleanup EXIT

if [[ $(id -u) -ne 0 && "${WAIAN_ALLOW_NON_ROOT:-0}" != 1 ]]; then
  echo "ERROR: install.sh must run as root on MiSTer" >&2
  exit 2
fi
for command in wget tar bash; do
  command -v "$command" >/dev/null || { echo "ERROR: required command not found: $command" >&2; exit 2; }
done

mkdir -p -- "$EXTRACTED"
wget -qO "$ARCHIVE" \
  "https://codeload.github.com/${REPO_SLUG}/tar.gz/refs/heads/${BRANCH}"
tar -xzf "$ARCHIVE" -C "$EXTRACTED"

SOURCE_REPO="$(find "$EXTRACTED" -mindepth 1 -maxdepth 1 -type d -print -quit)"
[[ -n "$SOURCE_REPO" && -x "${SOURCE_REPO}/manage.sh" ]] || {
  echo "ERROR: downloaded repository is missing executable manage.sh" >&2
  exit 3
}

mkdir -p -- "$MANAGED_ROOT"
rm -rf -- "$NEW_REPO"
mv -- "$SOURCE_REPO" "$NEW_REPO"

if [[ -n "${GAME_BASE_URL:-}" ]]; then
  [[ "$GAME_BASE_URL" != *$'\n'* && "$GAME_BASE_URL" != *$'\r'* ]] || {
    echo "ERROR: GAME_BASE_URL contains a newline" >&2
    exit 2
  }
  umask 077
  printf 'GAME_BASE_URL=%s\n' "$GAME_BASE_URL" >"${MANAGED_ROOT}/.env"
fi

"${NEW_REPO}/manage.sh" "$@"
rm -rf -- "${MANAGED_ROOT}/repo.previous"
if [[ -d "${MANAGED_ROOT}/repo" ]]; then
  mv -- "${MANAGED_ROOT}/repo" "${MANAGED_ROOT}/repo.previous"
fi
mv -- "$NEW_REPO" "${MANAGED_ROOT}/repo"
rm -rf -- "${MANAGED_ROOT}/repo.previous"

echo "Installed update command: ${FAT_ROOT}/Scripts/update-waian.sh"

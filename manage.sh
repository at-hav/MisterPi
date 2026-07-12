#!/usr/bin/env bash
set -Eeuo pipefail

FAT_ROOT="${WAIAN_FAT_ROOT:-/media/fat}"
MANAGED_ROOT="${WAIAN_MANAGED_ROOT:-${FAT_ROOT}/.waian}"
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GAMES_ROOT="${FAT_ROOT}/games"
MENU_NAME="_Waian's Picks"
MENU_PATH="${FAT_ROOT}/${MENU_NAME}"
INPUTS_PATH="${FAT_ROOT}/config/inputs"
STATE_FILE="${MANAGED_ROOT}/controller-maps.json"
STAGE_ROOT="${MANAGED_ROOT}/.mgl-stage.$$"
BACKUP_MENU="${MANAGED_ROOT}/.menu-previous"
SKIP_CONTROLLERS=0
NO_DOWNLOAD=0
DRY_RUN=0
MENU_SWAPPED=0
MENU_COMMITTED=0

usage() {
  echo "Usage: manage.sh [--dry-run] [--no-download] [--skip-controller-maps]"
}

while (( $# )); do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --no-download) NO_DOWNLOAD=1 ;;
    --skip-controller-maps) SKIP_CONTROLLERS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

cleanup() {
  local status=$?
  rm -rf -- "$STAGE_ROOT"
  if (( MENU_SWAPPED && ! MENU_COMMITTED )); then
    rm -rf -- "$MENU_PATH"
    if [[ -d "$BACKUP_MENU" ]]; then
      mv -- "$BACKUP_MENU" "$MENU_PATH"
    fi
  fi
  exit "$status"
}
trap cleanup EXIT

atomic_copy() {
  local source=$1 destination=$2 mode=$3 temporary="${destination}.waian-tmp.$$"
  cp -- "$source" "$temporary"
  chmod "$mode" "$temporary"
  mv -f -- "$temporary" "$destination"
}

for command in python3 flock cp mv rm chmod; do
  command -v "$command" >/dev/null || { echo "ERROR: required command not found: $command" >&2; exit 2; }
done

mkdir -p -- "$MANAGED_ROOT"
exec 9>"${MANAGED_ROOT}/update.lock"
flock -n 9 || { echo "ERROR: another Waian update is already running" >&2; exit 3; }

if (( ! SKIP_CONTROLLERS )); then
  controller_args=(
    --dest "$INPUTS_PATH"
    --state-file "$STATE_FILE"
  )
  (( DRY_RUN )) && controller_args+=(--dry-run)
  python3 "${REPO_ROOT}/sync_controller_maps.py" "${controller_args[@]}"
fi

game_args=(
  --csv "${REPO_ROOT}/game-library.csv"
  --games-root "$GAMES_ROOT"
)
(( NO_DOWNLOAD || DRY_RUN )) && game_args+=(--no-download)
python3 "${REPO_ROOT}/sync_games.py" "${game_args[@]}"

if (( DRY_RUN )); then
  python3 "${REPO_ROOT}/waians_picks.py" \
    --csv "${REPO_ROOT}/game-library.csv" \
    --fat-root "$FAT_ROOT" \
    --games-root "$GAMES_ROOT" \
    --dry-run
  exit 0
fi

rm -rf -- "$STAGE_ROOT" "$BACKUP_MENU"
mkdir -p -- "$STAGE_ROOT"
python3 "${REPO_ROOT}/waians_picks.py" \
  --csv "${REPO_ROOT}/game-library.csv" \
  --fat-root "$FAT_ROOT" \
  --games-root "$GAMES_ROOT" \
  --output-root "$STAGE_ROOT"

[[ -d "${STAGE_ROOT}/${MENU_NAME}" ]] || { echo "ERROR: generator produced no menu tree" >&2; exit 4; }

if [[ -d "$MENU_PATH" ]]; then
  mv -- "$MENU_PATH" "$BACKUP_MENU"
fi
mv -- "${STAGE_ROOT}/${MENU_NAME}" "$MENU_PATH"
MENU_SWAPPED=1

python3 "${REPO_ROOT}/check_library.py" \
  --csv "${REPO_ROOT}/game-library.csv" \
  --games-root "$GAMES_ROOT" \
  --fat-root "$FAT_ROOT" \
  --max-print 50

atomic_copy "${REPO_ROOT}/game-library.csv" "${FAT_ROOT}/game-library.csv" 0644
for script in check_library.py hash_game_library.py sync_controller_maps.py sync_games.py waians_picks.py waians_test_games.py; do
  atomic_copy "${REPO_ROOT}/${script}" "${FAT_ROOT}/${script}" 0755
done
atomic_copy "${REPO_ROOT}/update-waian.sh" "${FAT_ROOT}/Scripts/update-waian.sh" 0755

MENU_COMMITTED=1
rm -rf -- "$BACKUP_MENU"
echo "Waian managed update completed successfully."

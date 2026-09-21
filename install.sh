#!/usr/bin/env bash
#
# VICTORY LAP — one-command install (macOS)
#
#   ./install.sh          interactive: detect, confirm, patch, relaunch
#   ./install.sh --yes    no questions asked (for scripts and AI agents)
#   ./install.sh --undo   restore every stock Teams sound
#
# Replaces every Microsoft Teams call & meeting sound with
# VICTORY LAP CORPORATE REMIX. Reversible at any time with --undo.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACK="$REPO_DIR/ringtone/VICTORY LAP CORPORATE REMIX.wav"
PATCHER="$REPO_DIR/scripts/patch_cache.py"
CACHE_DIR="$HOME/Library/Containers/com.microsoft.teams2/Data/Library/Caches/Microsoft/MSTeams/EBWebView/WV2Profile_tfw/Cache/Cache_Data"
YES=0; UNDO=0
for a in "$@"; do
  case "$a" in
    --yes|-y) YES=1 ;;
    --undo) UNDO=1 ;;
  esac
done

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
ask() {
  [[ "$YES" -eq 1 ]] && return 0
  read -r -p "$1 [Y/n] " reply
  [[ -z "$reply" || "$reply" =~ ^[Yy] ]]
}
die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

teams_running() { pgrep -xq MSTeams; }
quit_teams()    { osascript -e 'quit app "Microsoft Teams"' >/dev/null 2>&1 || true; }

cached_count() {
  [[ -d "$CACHE_DIR" ]] || { echo 0; return; }
  python3 "$PATCHER" status 2>/dev/null | grep -c "bytes" || true
}

say "VICTORY LAP CORPORATE REMIX installer"
echo

# --- platform detection ------------------------------------------------------
[[ "$(uname)" == "Darwin" ]] || die "This installer is for macOS. On Windows, run windows/teams-ringtone.ps1 (see README)."

PLATFORMS=()
[[ -d "/Applications/Microsoft Teams.app" ]] && PLATFORMS+=("Microsoft Teams")
# Future platforms (Zoom, Slack, ...) get detected here.

if [[ ${#PLATFORMS[@]} -eq 0 ]]; then
  die "No supported call apps found. Currently supported: Microsoft Teams (new client).
Install it from https://www.microsoft.com/en-us/microsoft-teams/download-app and run this again."
fi
say "Detected: ${PLATFORMS[*]}"

# --- dependencies ------------------------------------------------------------
command -v python3 >/dev/null || die "python3 is required (install Xcode Command Line Tools: xcode-select --install)"
if ! command -v ffmpeg >/dev/null; then
  if command -v brew >/dev/null && ask "ffmpeg is needed to encode the track. Install it with Homebrew?"; then
    brew install ffmpeg
  else
    die "ffmpeg is required: brew install ffmpeg"
  fi
fi

# --- undo mode ---------------------------------------------------------------
if [[ "$UNDO" -eq 1 ]]; then
  if teams_running; then
    ask "Teams must be quit to restore sounds. Quit it now?" || die "Aborted."
    quit_teams; sleep 2
  fi
  python3 "$PATCHER" restore-all
  if ask "Reopen Teams?"; then open -a "Microsoft Teams"; fi
  say "Stock sounds restored."
  exit 0
fi

# --- confirm -----------------------------------------------------------------
ask "Replace ALL Teams call & meeting sounds with VICTORY LAP CORPORATE REMIX?" || die "Aborted."

# --- make sure Teams has its sounds cached -----------------------------------
if [[ "$(cached_count)" -eq 0 ]]; then
  say "Teams hasn't downloaded its sounds yet — warming up the cache."
  echo "Opening Teams. Please go to Settings > Calls > Ringtones (gear icon > Calls)."
  open -a "Microsoft Teams"
  printf "Waiting for Teams to cache its sounds"
  for _ in $(seq 1 60); do
    [[ "$(cached_count)" -gt 0 ]] && break
    printf "."; sleep 3
  done
  echo
  [[ "$(cached_count)" -gt 0 ]] || die "Timed out. Open Settings > Calls > Ringtones in Teams, then re-run."
fi

# --- quit, patch, relaunch ---------------------------------------------------
if teams_running; then
  ask "Teams must be quit while patching. Quit it now?" || die "Aborted — quit Teams and re-run."
  quit_teams
  for _ in $(seq 1 10); do teams_running || break; sleep 1; done
  teams_running && die "Teams didn't quit — quit it manually and re-run."
fi

python3 "$PATCHER" patch-all "$TRACK"
echo
if ask "Reopen Teams?"; then open -a "Microsoft Teams"; fi
say "Done. Every call is a victory lap. (Undo anytime: ./install.sh --undo)"

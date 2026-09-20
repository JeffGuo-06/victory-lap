#!/usr/bin/env bash
# End-to-end test of the macOS CLI against a sandboxed Sounds dir.
# Generates real audio with `say`, exercises add/list/reapply/remove,
# and asserts the installed file is a 16-bit 44.1 kHz WAV.
set -euo pipefail

cd "$(dirname "$0")/.."
CLI="./teams-ringtone"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export TEAMS_RINGTONE_SOUNDS_DIR="$TMP/Sounds"
export TEAMS_RINGTONE_LIBRARY="$TMP/library"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "ok: $*"; }

# Make a real audio file to convert (aiff via macOS TTS).
say -o "$TMP/track.aiff" "ring ring, incoming call" 2>/dev/null \
  || fail "could not generate test audio with 'say'"

# --- add ---
"$CLI" add "$TMP/track.aiff" "My Banger" >/dev/null
[[ -f "$TMP/Sounds/My Banger.wav" ]] || fail "add: wav not installed in Sounds dir"
[[ -f "$TMP/library/My Banger.wav" ]] || fail "add: wav not kept in library"
pass "add installs into Sounds dir and library"

# --- format spec: Teams only detects 16-bit / 44.1 kHz PCM WAV ---
afinfo "$TMP/Sounds/My Banger.wav" | grep -q "44100 Hz" || fail "format: not 44.1 kHz"
afinfo "$TMP/Sounds/My Banger.wav" | grep -q "Int16" || fail "format: not 16-bit"
afinfo "$TMP/Sounds/My Banger.wav" | grep -qi "WAVE" || fail "format: not WAV container"
pass "output is 16-bit 44.1 kHz WAV"

# --- add from mp3-style default name (no explicit name) ---
"$CLI" add "$TMP/track.aiff" >/dev/null
[[ -f "$TMP/Sounds/track.wav" ]] || fail "add: default name not derived from filename"
pass "add derives name from filename"

# --- list ---
list_out="$("$CLI" list)"
grep -q "My Banger" <<<"$list_out" || fail "list: missing installed sound"
pass "list shows installed sounds"

# --- reapply (simulate a Teams update wiping the folder) ---
rm -rf "$TMP/Sounds"; mkdir -p "$TMP/Sounds"
"$CLI" reapply >/dev/null
[[ -f "$TMP/Sounds/My Banger.wav" && -f "$TMP/Sounds/track.wav" ]] \
  || fail "reapply: library not restored"
pass "reapply restores sounds after wipe"

# --- remove ---
"$CLI" remove "My Banger" >/dev/null
[[ ! -f "$TMP/Sounds/My Banger.wav" && ! -f "$TMP/library/My Banger.wav" ]] \
  || fail "remove: files still present"
pass "remove deletes from Sounds dir and library"

# --- error handling ---
"$CLI" add "$TMP/nope.mp3" 2>/dev/null && fail "add: should fail on missing file"
pass "add rejects missing file"

printf '%s\n' "" "All tests passed."

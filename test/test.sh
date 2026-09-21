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

# --- silence trimming (simulates a DAW bounce padded with dead space) ---
python3 - "$TMP/padded.wav" <<'PY' || fail "could not generate padded test wav"
import sys, wave, array, math
path = sys.argv[1]
fr = 44100
silence = array.array("h", [0] * fr)                       # 1s silence
tone = array.array("h", [int(20000 * math.sin(2 * math.pi * 440 * i / fr)) for i in range(fr // 2)])  # 0.5s tone
w = wave.open(path, "wb")
w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr)
w.writeframes((silence + tone + silence).tobytes())
w.close()
PY

"$CLI" add "$TMP/padded.wav" "Trimmed" >/dev/null
dur="$(afinfo "$TMP/Sounds/Trimmed.wav" | awk '/estimated duration/ {print $3}')"
awk -v d="$dur" 'BEGIN { exit !(d < 1.0) }' || fail "trim: expected <1s after trimming, got ${dur}s"
pass "add trims leading/trailing silence (2.5s padded -> ${dur}s)"

"$CLI" add "$TMP/padded.wav" "Untrimmed" --no-trim >/dev/null
dur="$(afinfo "$TMP/Sounds/Untrimmed.wav" | awk '/estimated duration/ {print $3}')"
awk -v d="$dur" 'BEGIN { exit !(d > 2.0) }' || fail "no-trim: expected ~2.5s, got ${dur}s"
pass "--no-trim keeps the audio as exported"

# --- error handling ---
"$CLI" add "$TMP/nope.mp3" 2>/dev/null && fail "add: should fail on missing file"
pass "add rejects missing file"

printf '%s\n' "" "All tests passed."

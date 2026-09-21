#!/usr/bin/env python3
"""Patch the Microsoft Teams (macOS) WebView cache to replace a built-in
ringtone's cached audio with your own track.

The new Teams client fetches its ringtones from
https://teams.public.onecdn.static.microsoft/evergreen-assets/audio/<name>.mp3
and stores them in a Chromium "simple cache" sparse entry, marked immutable
with a 1-year max-age — so Teams keeps playing whatever bytes sit in that
cache entry. This script rewrites those bytes in place:

  - keeps the entry's range structure and total size identical (so the cached
    HTTP headers stay valid and the cache index is untouched)
  - re-encodes your track to mp3 sized to fit, padding the remainder inside
    an ID3v2 tag that decoders skip
  - recomputes each sparse range's CRC32 so Chromium accepts the data
  - backs up the original entry for restore

Usage:
  patch_cache.py patch <track.wav|mp3> [ringtone-name]   (default: Teams_Call_Ringing)
  patch_cache.py restore [ringtone-name]
  patch_cache.py status

Teams must be fully quit while patching.
"""

import struct
import subprocess
import sys
import zlib
from pathlib import Path

CACHE_DIR = Path.home() / (
    "Library/Containers/com.microsoft.teams2/Data/Library/Caches/"
    "Microsoft/MSTeams/EBWebView/WV2Profile_tfw/Cache/Cache_Data"
)
BACKUP_DIR = Path.home() / ".teams-ringtone/cache-backups"
DEFAULT_RINGTONE = "Teams_Call_Ringing"
SPARSE_HEADER = 24   # SimpleFileHeader (20 bytes, padded to 24)
RANGE_HEADER = 32    # SimpleFileSparseRangeHeader (28 bytes, padded to 32)
ID3_HEADER_LEN = 10


def die(msg):
    sys.exit(f"error: {msg}")


def find_entry(ringtone):
    """Locate the _s sparse file whose key is the ringtone's CDN URL."""
    needle = f"/evergreen-assets/audio/{ringtone}.mp3".encode()
    for f in CACHE_DIR.glob("*_s"):
        head = f.read_bytes()[: SPARSE_HEADER + 300]
        if needle in head:
            return f
    return None


def parse_ranges(data):
    key_len = struct.unpack_from("<I", data, 12)[0]
    pos = SPARSE_HEADER + key_len
    ranges = []
    while pos + RANGE_HEADER <= len(data):
        _magic, off, length, _crc = struct.unpack_from("<QqqI", data, pos)
        ranges.append((pos, off, length))
        pos += RANGE_HEADER + length
    if pos != len(data):
        die("unexpected trailing bytes in cache entry — format may have changed")
    return ranges


def encode_fit(track, target):
    """Encode `track` to an mp3 of exactly `target` bytes:
    mp3 frames + a zero-padded ID3v2 tag in front absorbing the slack."""
    out = BACKUP_DIR / "replacement.mp3"
    # ~20s is all Teams ever rings; 24s @ 96kbps stays safely under typical
    # ringtone sizes. Step down if the target entry is smaller.
    for secs, kbps in [(24, 96), (20, 96), (20, 64), (15, 64), (10, 48)]:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(track),
             "-t", str(secs), "-c:a", "libmp3lame", "-b:a", f"{kbps}k",
             "-ar", "44100", "-ac", "2", "-id3v2_version", "0", str(out)],
            check=True,
        )
        frames = out.read_bytes()
        if frames.startswith(b"ID3"):  # strip any tag ffmpeg still wrote
            tag_size = int.from_bytes(
                bytes(b & 0x7F for b in frames[6:10]), "big"
            )
            frames = frames[ID3_HEADER_LEN + tag_size:]
        if len(frames) + ID3_HEADER_LEN <= target:
            break
    else:
        die(f"could not encode under {target} bytes")

    pad = target - len(frames) - ID3_HEADER_LEN
    syncsafe = bytes((pad >> s) & 0x7F for s in (21, 14, 7, 0))
    id3 = b"ID3\x04\x00\x00" + syncsafe + b"\x00" * pad
    blob = id3 + frames
    assert len(blob) == target
    return blob


def cmd_patch(track, ringtone):
    track = Path(track).expanduser()
    if not track.is_file():
        die(f"track not found: {track}")
    entry = find_entry(ringtone)
    if entry is None:
        die(f"no cached entry for '{ringtone}' — open Teams' ringtone settings "
            "once (so it downloads the sound), quit Teams, then re-run")

    data = bytearray(entry.read_bytes())
    ranges = parse_ranges(data)
    total = sum(length for _, _, length in ranges)
    contiguous = all(
        off == ranges[i - 1][1] + ranges[i - 1][2] for i, (_, off, _) in
        enumerate(ranges) if i
    ) and ranges[0][1] == 0
    if not contiguous:
        die("cached entry is incomplete (partial ranges) — play the ringtone "
            "preview in Teams once so the full file is cached, then retry")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"{ringtone}_s.orig"
    if not backup.exists():
        backup.write_bytes(bytes(data))

    blob = encode_fit(track, total)
    for pos, off, length in ranges:
        chunk = blob[off: off + length]
        data[pos + RANGE_HEADER: pos + RANGE_HEADER + length] = chunk
        struct.pack_into("<I", data, pos + 24, zlib.crc32(chunk) & 0xFFFFFFFF)
    entry.write_bytes(bytes(data))
    print(f"patched '{ringtone}' ({total} bytes across {len(ranges)} ranges)")
    print("Reopen Teams — the ringtone now plays your track.")


def cmd_restore(ringtone):
    backup = BACKUP_DIR / f"{ringtone}_s.orig"
    if not backup.exists():
        die(f"no backup for '{ringtone}'")
    entry = find_entry(ringtone)
    if entry is None:
        die(f"no cached entry for '{ringtone}' to restore into")
    entry.write_bytes(backup.read_bytes())
    print(f"restored original '{ringtone}'")


def cmd_status():
    if not CACHE_DIR.is_dir():
        die("Teams cache dir not found — is (new) Teams installed and launched?")
    found = []
    for f in CACHE_DIR.glob("*_s"):
        head = f.read_bytes()[: SPARSE_HEADER + 300]
        marker = b"/evergreen-assets/audio/"
        if marker in head:
            name = head.split(marker, 1)[1].split(b".mp3", 1)[0].decode()
            found.append((name, f.stat().st_size))
    if not found:
        print("no cached ringtones — open Settings > Calls > Ringtones in "
              "Teams once, then re-run")
    for name, size in sorted(found):
        patched = (BACKUP_DIR / f"{name}_s.orig").exists()
        print(f"  {name:30} {size:>9} bytes {'[patched]' if patched else ''}")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    cmd = args[0]
    if cmd == "patch" and len(args) >= 2:
        cmd_patch(args[1], args[2] if len(args) > 2 else DEFAULT_RINGTONE)
    elif cmd == "restore":
        cmd_restore(args[1] if len(args) > 1 else DEFAULT_RINGTONE)
    elif cmd == "status":
        cmd_status()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

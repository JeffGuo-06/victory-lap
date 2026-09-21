#!/usr/bin/env python3
"""Patch the Microsoft Teams (macOS) WebView cache to replace built-in
ringtones' cached audio with your own track.

The new Teams client fetches its ringtones from
https://teams.public.onecdn.static.microsoft/evergreen-assets/audio/<name>.mp3
and stores them in a Chromium "simple cache" sparse entry, marked immutable
with a 1-year max-age — so Teams keeps playing whatever bytes sit in that
cache entry. Teams keeps a SEPARATE browser profile (and cache) per account
type — WV2Profile_tfw for work/school, WV2Profile_tfl for personal — so this
script patches every profile it finds.

For each entry it:
  - keeps the entry's range structure and total size identical (so the cached
    HTTP headers stay valid and the cache index is untouched)
  - re-encodes your track to mp3 sized to fit, padding the remainder inside
    an ID3v2 tag that decoders skip
  - recomputes each sparse range's CRC32 so Chromium accepts the data
  - backs up the original entry for restore

Usage:
  patch_cache.py patch <track.wav|mp3> [ringtone-name]   (default: ring)
  patch_cache.py patch-all <track.wav|mp3>               (every cached sound)
  patch_cache.py restore [ringtone-name]
  patch_cache.py restore-all
  patch_cache.py status

Teams must be fully quit while patching.
"""

import struct
import subprocess
import sys
import zlib
from pathlib import Path

CACHE_ROOT = Path.home() / (
    "Library/Containers/com.microsoft.teams2/Data/Library/Caches/"
    "Microsoft/MSTeams/EBWebView"
)
BACKUP_DIR = Path.home() / ".teams-ringtone/cache-backups"
DEFAULT_RINGTONE = "ring"
URL_MARKER = b"/evergreen-assets/audio/"
SPARSE_HEADER = 24   # SimpleFileHeader (20 bytes, padded to 24)
RANGE_HEADER = 32    # SimpleFileSparseRangeHeader (28 bytes, padded to 32)
ID3_HEADER_LEN = 10


def die(msg):
    sys.exit(f"error: {msg}")


def cache_dirs():
    return sorted(CACHE_ROOT.glob("*/Cache/Cache_Data"))


def profile_of(cache_dir):
    return cache_dir.parent.parent.name  # .../EBWebView/<profile>/Cache/Cache_Data


def entry_name(path):
    head = path.read_bytes()[: SPARSE_HEADER + 300]
    if URL_MARKER not in head:
        return None
    return head.split(URL_MARKER, 1)[1].split(b".mp3", 1)[0].decode()


def find_entries(ringtone):
    """All cached _s sparse files for this ringtone, across every profile."""
    hits = []
    for cd in cache_dirs():
        for f in cd.glob("*_s"):
            if entry_name(f) == ringtone:
                hits.append(f)
    return hits


def cached_names():
    names = set()
    for cd in cache_dirs():
        for f in cd.glob("*_s"):
            name = entry_name(f)
            if name:
                names.add(name)
    return sorted(names)


def backup_path(entry):
    profile = profile_of(entry.parent)
    return BACKUP_DIR / f"{profile}__{entry_name(entry)}_s.orig"


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
    mp3 frames + a zero-padded ID3v2 tag in front absorbing the slack.

    Quality-first: keep the bitrate high and fit the DURATION to the byte
    budget — a 2s crisp clip beats 5 muffled ones for the small meeting
    blips (low mp3 bitrates low-pass away all the treble). Ringtones get
    up to 24s (Teams only rings ~20s anyway). A short fade-out avoids an
    abrupt cut."""
    out = BACKUP_DIR / "replacement.mp3"
    budget_bits = (target - ID3_HEADER_LEN) * 8
    # Bitrates under 32k need MPEG-2 (22.05 kHz); 44.1 kHz MPEG-1 stops at 32k.
    for kbps, chans, rate in [(96, 2, 44100), (64, 1, 44100), (32, 1, 44100),
                              (16, 1, 22050)]:
        secs = min(24.0, budget_bits / (kbps * 1000) * 0.97)
        if secs >= 1.0:
            break

    frames = b""
    for _ in range(8):
        fade = min(0.5, secs / 4)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(track),
             "-t", f"{secs:.2f}",
             "-af", f"afade=t=out:st={secs - fade:.2f}:d={fade:.2f}",
             "-c:a", "libmp3lame", "-b:a", f"{kbps}k",
             "-ar", str(rate), "-ac", str(chans), "-id3v2_version", "0",
             str(out)],
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
        secs *= 0.95  # rare overshoot from frame padding — shave and retry
    else:
        die(f"could not encode under {target} bytes")

    pad = target - len(frames) - ID3_HEADER_LEN
    syncsafe = bytes((pad >> s) & 0x7F for s in (21, 14, 7, 0))
    id3 = b"ID3\x04\x00\x00" + syncsafe + b"\x00" * pad
    blob = id3 + frames
    assert len(blob) == target
    return blob


def patch_entry(entry, track):
    data = bytearray(entry.read_bytes())
    ranges = parse_ranges(data)
    total = sum(length for _, _, length in ranges)
    contiguous = all(
        off == ranges[i - 1][1] + ranges[i - 1][2] for i, (_, off, _) in
        enumerate(ranges) if i
    ) and ranges[0][1] == 0
    if not contiguous:
        die("cached entry is incomplete (partial ranges) — play the sound "
            "in Teams once so the full file is cached, then retry")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = backup_path(entry)
    if not backup.exists():
        backup.write_bytes(bytes(data))

    blob = encode_fit(track, total)
    for pos, off, length in ranges:
        chunk = blob[off: off + length]
        data[pos + RANGE_HEADER: pos + RANGE_HEADER + length] = chunk
        struct.pack_into("<I", data, pos + 24, zlib.crc32(chunk) & 0xFFFFFFFF)
    entry.write_bytes(bytes(data))
    print(f"patched '{entry_name(entry)}' [{profile_of(entry.parent)}] "
          f"({total} bytes across {len(ranges)} ranges)")


def cmd_patch(track, ringtone):
    track = Path(track).expanduser()
    if not track.is_file():
        die(f"track not found: {track}")
    entries = find_entries(ringtone)
    if not entries:
        die(f"no cached entry for '{ringtone}' — open Teams' ringtone settings "
            "once (so it downloads the sound), quit Teams, then re-run")
    for entry in entries:
        patch_entry(entry, track)


def cmd_patch_all(track):
    names = cached_names()
    if not names:
        die("no cached sounds — open Teams' Settings > Calls > Ringtones once, "
            "quit Teams, then re-run")
    done, skipped = 0, []
    for name in names:
        try:
            cmd_patch(track, name)
            done += 1
        except SystemExit as e:
            skipped.append((name, str(e)))
    print(f"\npatched {done}/{len(names)} sounds "
          f"across {len(cache_dirs())} profiles")
    for name, why in skipped:
        print(f"  skipped {name}: {why}")


def cmd_restore(ringtone):
    restored = 0
    for entry in find_entries(ringtone):
        backup = backup_path(entry)
        if backup.exists():
            entry.write_bytes(backup.read_bytes())
            print(f"restored '{ringtone}' [{profile_of(entry.parent)}]")
            restored += 1
    if not restored:
        die(f"nothing restored for '{ringtone}' (no backup or no cache entry)")


def cmd_restore_all():
    restored = 0
    for name in cached_names():
        try:
            cmd_restore(name)
            restored += 1
        except SystemExit:
            pass
    print(f"restored {restored} sound(s)")


def cmd_status():
    dirs = cache_dirs()
    if not dirs:
        die("Teams cache not found — is (new) Teams installed and launched?")
    any_found = False
    for cd in dirs:
        entries = [(entry_name(f), f) for f in cd.glob("*_s")]
        entries = [(n, f) for n, f in entries if n]
        if not entries:
            continue
        any_found = True
        print(f"[{profile_of(cd)}]")
        for name, f in sorted(entries):
            patched = backup_path(f).exists()
            print(f"  {name:30} {f.stat().st_size:>9} bytes "
                  f"{'[patched]' if patched else ''}")
    if not any_found:
        print("no cached sounds — open Settings > Calls > Ringtones in "
              "Teams once, then re-run")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    cmd = args[0]
    if cmd == "patch" and len(args) >= 2:
        cmd_patch(args[1], args[2] if len(args) > 2 else DEFAULT_RINGTONE)
        print("Reopen Teams — the sound now plays your track.")
    elif cmd == "patch-all" and len(args) >= 2:
        cmd_patch_all(args[1])
    elif cmd == "restore":
        cmd_restore(args[1] if len(args) > 1 else DEFAULT_RINGTONE)
    elif cmd == "restore-all":
        cmd_restore_all()
    elif cmd == "status":
        cmd_status()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

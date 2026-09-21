#!/usr/bin/env python3
"""Round-trip tests for scripts/patch_cache.py against a synthetic
Chromium simple-cache sparse entry — no real Teams install needed."""

import importlib.util
import struct
import sys
import tempfile
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "patch_cache", REPO / "scripts" / "patch_cache.py"
)
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


def make_entry(key: bytes, chunks):
    """Build a synthetic _s sparse file: 24-byte header + key + ranges."""
    out = struct.pack("<QIII4x", 0xFCFB6D1BA7725C30, 9, len(key), 0) + key
    off = 0
    for chunk in chunks:
        out += struct.pack(
            "<QqqI4x", 0xEB97BF1553676B, off, len(chunk),
            zlib.crc32(chunk) & 0xFFFFFFFF,
        ) + chunk
        off += len(chunk)
    return out


def test_parse_and_patch():
    key = (b"1/0/_dk_https://microsoft.com https://microsoft.com "
           b"https://teams.public.onecdn.static.microsoft/evergreen-assets/audio/ring.mp3")
    chunks = [b"A" * 100, b"B" * 57, b"C" * 4001]
    data = bytearray(make_entry(key, chunks))

    ranges = pc.parse_ranges(data)
    assert len(ranges) == 3, f"expected 3 ranges, got {len(ranges)}"
    assert [r[2] for r in ranges] == [100, 57, 4001], "range lengths wrong"
    assert [r[1] for r in ranges] == [0, 100, 157], "range offsets wrong"

    # Patch with a same-size blob the way cmd_patch does, then re-parse and
    # verify every range's CRC and the reassembled payload.
    total = sum(r[2] for r in ranges)
    blob = bytes(range(256)) * (total // 256 + 1)
    blob = blob[:total]
    for pos, off, length in ranges:
        chunk = blob[off: off + length]
        data[pos + pc.RANGE_HEADER: pos + pc.RANGE_HEADER + length] = chunk
        struct.pack_into("<I", data, pos + 24, zlib.crc32(chunk) & 0xFFFFFFFF)

    reassembled = b""
    for pos, off, length in pc.parse_ranges(data):
        chunk = bytes(data[pos + pc.RANGE_HEADER: pos + pc.RANGE_HEADER + length])
        stored_crc = struct.unpack_from("<I", data, pos + 24)[0]
        assert zlib.crc32(chunk) & 0xFFFFFFFF == stored_crc, "CRC mismatch"
        reassembled += chunk
    assert reassembled == blob, "patched payload does not round-trip"
    print("ok: parse + same-size patch round-trips with valid CRCs")


def test_trailing_garbage_rejected():
    key = b"1/0/_dk_x x https://host/evergreen-assets/audio/ring.mp3"
    data = make_entry(key, [b"Z" * 64]) + b"garbage"
    try:
        pc.parse_ranges(data)
    except SystemExit:
        print("ok: malformed entry rejected")
        return
    raise AssertionError("malformed entry was not rejected")


def test_encode_fit_exact_size():
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        print("skip: ffmpeg not available")
        return
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "tone.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", "sine=frequency=440:duration=30", "-ar", "44100",
             "-ac", "2", "-sample_fmt", "s16", str(src)],
            check=True,
        )
        pc.BACKUP_DIR = Path(td)
        target = 200_000
        blob = pc.encode_fit(src, target)
        assert len(blob) == target, f"blob is {len(blob)}, wanted {target}"
        assert blob.startswith(b"ID3"), "missing ID3 padding header"
        print("ok: encode_fit produces exact-size ID3-padded mp3")


if __name__ == "__main__":
    test_parse_and_patch()
    test_trailing_garbage_rejected()
    test_encode_fit_exact_size()
    print("\nAll patch_cache tests passed.")

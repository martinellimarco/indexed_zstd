"""
Heavy tests with realistic data blobs and t2sz compression.

Mirrors the 7 heavy tests from libzstd-seek's C test suite.
Each test generates large, realistic data, compresses with t2sz,
and verifies SHA256, byte-exact match, random seeks, and chunked reads.

Requirements:
  - t2sz in PATH (tests are skipped if unavailable)
  - ~1 GB free disk space

Set SKIP_HEAVY_TESTS=1 to skip these tests.
"""

import hashlib
import io
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from indexed_zstd import IndexedZstdFile

from conftest import xorshift64

pytestmark = pytest.mark.heavy

# ── Skip conditions ──────────────────────────────────────────────────────────
t2sz_available = shutil.which("t2sz") is not None
skip_heavy_env = os.environ.get("SKIP_HEAVY_TESTS", "") == "1"


def sha256_bytes(data):
    """Compute SHA256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ── Data generators ──────────────────────────────────────────────────────────

def generate_text(path, size):
    """Generate base64 text data (high compressibility)."""
    import base64
    raw_bytes_needed = size * 3 // 4 + 1
    encoded = base64.b64encode(os.urandom(raw_bytes_needed))
    Path(path).write_bytes(encoded[:size])


def generate_binary(path, size):
    """Generate random binary data (nearly incompressible)."""
    Path(path).write_bytes(os.urandom(size))


def generate_zeros(path, size):
    """Generate zero-filled data (extreme compression ratio)."""
    Path(path).write_bytes(b"\x00" * size)


def generate_mixed(path, size):
    """Generate mixed data: 1/3 text + 1/3 binary + 1/3 repetitive."""
    import base64
    third = size // 3
    rest = size - third - third

    parts = bytearray()

    # 1/3 text (base64)
    raw_bytes_needed = third * 3 // 4 + 1
    encoded = base64.b64encode(os.urandom(raw_bytes_needed))
    parts.extend(encoded[:third])

    # 1/3 binary (random)
    parts.extend(os.urandom(third))

    # 1/3 repetitive pattern
    pattern = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    rep = (pattern * (rest // len(pattern) + 1))[:rest]
    parts.extend(rep)

    Path(path).write_bytes(bytes(parts[:size]))


def compress_with_t2sz(raw_path, zst_path, frame_size, level):
    """Compress a raw file with t2sz."""
    subprocess.run(
        ["t2sz", "-r", "-s", str(frame_size), "-l", str(level),
         "-f", "-o", str(zst_path), str(raw_path)],
        check=True,
        capture_output=True,
    )


def verify_file(zst_path, raw_path, raw_data, label):
    """Full verification: SHA256, byte-exact, seek stress, chunked reads."""
    raw_hash = sha256_bytes(raw_data)
    file_size = len(raw_data)

    # ── SHA256 verification ──────────────────────────────────────────
    with IndexedZstdFile(str(zst_path)) as f:
        dec_data = f.read()
    dec_hash = sha256_bytes(dec_data)
    assert dec_hash == raw_hash, (
        f"{label}: SHA256 mismatch! expected {raw_hash[:16]}..., "
        f"got {dec_hash[:16]}..."
    )

    # ── Byte-exact verification ──────────────────────────────────────
    assert dec_data == raw_data, f"{label}: byte-exact mismatch"

    # ── Seek stress (10,000 random byte-range reads) ─────────────────
    seed = (int(time.time()) ^ os.getpid()) & ((1 << 64) - 1)
    if seed == 0:
        seed = 1
    state = seed

    with IndexedZstdFile(str(zst_path)) as f:
        for i in range(10000):
            state, val = xorshift64(state)
            pos = val % file_size

            state, val = xorshift64(state)
            max_len = min(8192, file_size - pos)
            if max_len < 1:
                continue
            length = (val % max_len) + 1

            method = i % 3
            if method == 0:
                f.seek(pos, io.SEEK_SET)
            elif method == 1:
                current = f.tell()
                f.seek(pos - current, io.SEEK_CUR)
            else:
                f.seek(pos - file_size, io.SEEK_END)

            data = f.read(length)
            expected = raw_data[pos:pos + length]
            assert data == expected, (
                f"{label}: seek_stress mismatch at op {i}, "
                f"pos={pos}, len={length}, seed={seed}"
            )

    # ── Chunked read verification (4 KB) ─────────────────────────────
    with IndexedZstdFile(str(zst_path)) as f:
        pieces = []
        while True:
            chunk = f.read(4096)
            if not chunk:
                break
            pieces.append(chunk)
        chunked = b"".join(pieces)
    assert chunked == raw_data, f"{label}: chunked read mismatch"


# ── Test cases ───────────────────────────────────────────────────────────────

@pytest.mark.skipif(not t2sz_available, reason="t2sz not found in PATH")
@pytest.mark.skipif(skip_heavy_env, reason="SKIP_HEAVY_TESTS=1")
class TestHeavy:
    """Realistic data tests with t2sz compression."""

    def test_heavy_text(self, tmp_path):
        """10 MB base64 text, 300000 B frames, level 3."""
        raw_path = tmp_path / "raw.dat"
        zst_path = tmp_path / "compressed.zst"
        size = 10 * 1048576

        generate_text(str(raw_path), size)
        raw_data = raw_path.read_bytes()
        compress_with_t2sz(raw_path, zst_path, 300000, 3)
        verify_file(zst_path, raw_path, raw_data, "heavy_text")

    def test_heavy_binary(self, tmp_path):
        """10 MB random binary, 250000 B frames, level 3."""
        raw_path = tmp_path / "raw.dat"
        zst_path = tmp_path / "compressed.zst"
        size = 10 * 1048576

        generate_binary(str(raw_path), size)
        raw_data = raw_path.read_bytes()
        compress_with_t2sz(raw_path, zst_path, 250000, 3)
        verify_file(zst_path, raw_path, raw_data, "heavy_binary")

    def test_heavy_zeros(self, tmp_path):
        """50 MB zeros, 999999 B frames, level 3."""
        raw_path = tmp_path / "raw.dat"
        zst_path = tmp_path / "compressed.zst"
        size = 50 * 1048576

        generate_zeros(str(raw_path), size)
        raw_data = raw_path.read_bytes()
        compress_with_t2sz(raw_path, zst_path, 999999, 3)
        verify_file(zst_path, raw_path, raw_data, "heavy_zeros")

    def test_heavy_mixed(self, tmp_path):
        """20 MB mixed (text+binary+pattern), 500000 B frames, level 9."""
        raw_path = tmp_path / "raw.dat"
        zst_path = tmp_path / "compressed.zst"
        size = 20 * 1048576

        generate_mixed(str(raw_path), size)
        raw_data = raw_path.read_bytes()
        compress_with_t2sz(raw_path, zst_path, 500000, 9)
        verify_file(zst_path, raw_path, raw_data, "heavy_mixed")

    def test_heavy_level_max(self, tmp_path):
        """5 MB base64 text, 350000 B frames, level 22 (max)."""
        raw_path = tmp_path / "raw.dat"
        zst_path = tmp_path / "compressed.zst"
        size = 5 * 1048576

        generate_text(str(raw_path), size)
        raw_data = raw_path.read_bytes()
        compress_with_t2sz(raw_path, zst_path, 350000, 22)
        verify_file(zst_path, raw_path, raw_data, "heavy_level_max")

    def test_heavy_small_frames(self, tmp_path):
        """5 MB random binary, 3000 B frames (~1747 frames), level 1."""
        raw_path = tmp_path / "raw.dat"
        zst_path = tmp_path / "compressed.zst"
        size = 5 * 1048576

        generate_binary(str(raw_path), size)
        raw_data = raw_path.read_bytes()
        compress_with_t2sz(raw_path, zst_path, 3000, 1)
        verify_file(zst_path, raw_path, raw_data, "heavy_small_frames")

    def test_heavy_single_frame(self, tmp_path):
        """20 MB random binary, single frame (20M), level 3."""
        raw_path = tmp_path / "raw.dat"
        zst_path = tmp_path / "compressed.zst"
        size = 20 * 1048576

        generate_binary(str(raw_path), size)
        raw_data = raw_path.read_bytes()
        # t2sz with frame size = file size → single frame
        compress_with_t2sz(raw_path, zst_path, "20M", 3)
        verify_file(zst_path, raw_path, raw_data, "heavy_single_frame")

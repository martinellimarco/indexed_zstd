"""
Round-trip tests: generate → compress → decompress via IndexedZstdFile → verify.

Mirrors the 11 round-trip tests from libzstd-seek's C test suite.
Each test generates deterministic data with gen_seekable, reads it back
through the Python binding, and verifies byte-exact match.
"""

import io
from pathlib import Path

import pytest
from indexed_zstd import IndexedZstdFile

from conftest import generate_test_data, xorshift64


# ── Parametrised round-trip matrix ───────────────────────────────────────────
# (name, seed, num_frames, frame_size, gen_flags)

ROUNDTRIP_CASES = [
    ("4frames_seekable",        1,   4,     1024,   ["--seekable"]),
    ("4frames_no_seekable",     2,   4,     1024,   []),
    ("100frames_seekable",      3,   100,   1000,   ["--seekable"]),
    ("100frames_no_seekable",   4,   100,   1000,   []),
    ("single_frame",            5,   1,     65536,  []),
    ("single_frame_seekable",   6,   1,     65536,  ["--seekable"]),
    ("large_frames",            7,   10,    1048576, []),
    ("no_content_size",         8,   4,     1024,   ["--no-content-size"]),
    ("vary_size",               9,   10,    10000,  ["--seekable", "--vary-size"]),
    ("seekable_checksum",       10,  4,     1024,   ["--seekable", "--checksum"]),
    ("100frames_no_content_size", 11, 100,  1000,   ["--no-content-size"]),
]


@pytest.mark.parametrize(
    "name,seed,frames,fsize,flags",
    ROUNDTRIP_CASES,
    ids=[c[0] for c in ROUNDTRIP_CASES],
)
class TestRoundTrip:
    """Round-trip test: full read, chunked read, random seek, byte-by-byte (small files)."""

    def _setup(self, tmp_path, seed, frames, fsize, flags):
        zst, raw = generate_test_data(tmp_path, seed, frames, fsize, *flags)
        raw_data = Path(raw).read_bytes()
        return zst, raw_data

    def test_read_all(self, tmp_path, name, seed, frames, fsize, flags):
        """Full decompression must be byte-identical to reference."""
        zst, raw_data = self._setup(tmp_path, seed, frames, fsize, flags)
        with IndexedZstdFile(zst) as f:
            data = f.read()
        assert data == raw_data, f"read_all mismatch for {name}"

    def test_read_chunks(self, tmp_path, name, seed, frames, fsize, flags):
        """Reading in 256-byte chunks must produce identical data."""
        zst, raw_data = self._setup(tmp_path, seed, frames, fsize, flags)
        chunk_size = 256
        with IndexedZstdFile(zst) as f:
            pieces = []
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                pieces.append(chunk)
            data = b"".join(pieces)
        assert data == raw_data, f"read_chunks mismatch for {name}"

    def test_seek_random(self, tmp_path, name, seed, frames, fsize, flags):
        """1000 random seek+read operations must all produce correct data."""
        zst, raw_data = self._setup(tmp_path, seed, frames, fsize, flags)
        file_size = len(raw_data)
        if file_size == 0:
            pytest.skip("Empty file")

        num_ops = 1000
        state = seed if seed > 0 else 1

        with IndexedZstdFile(zst) as f:
            for i in range(num_ops):
                state, val = xorshift64(state)
                pos = val % file_size
                f.seek(pos, io.SEEK_SET)
                byte = f.read(1)
                assert byte == bytes([raw_data[pos]]), (
                    f"seek_random mismatch at op {i}: pos={pos}, "
                    f"expected {raw_data[pos]:#x}, got {byte!r}"
                )

    def test_read_byte_by_byte(self, tmp_path, name, seed, frames, fsize, flags):
        """Sequential 1-byte reads through entire file."""
        zst, raw_data = self._setup(tmp_path, seed, frames, fsize, flags)

        with IndexedZstdFile(zst) as f:
            for i, expected_byte in enumerate(raw_data):
                byte = f.read(1)
                assert byte == bytes([expected_byte]), (
                    f"byte-by-byte mismatch at offset {i}: "
                    f"expected {expected_byte:#x}, got {byte!r}"
                )
            # Read at EOF should return empty
            assert f.read(1) == b""

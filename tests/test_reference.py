"""
Reference comparison tests: library output vs zstd CLI decompression.

Mirrors the 13 reference tests from libzstd-seek's C test suite.
Each test generates data, decompresses with both the library and the zstd CLI,
and verifies byte-identical output.
"""

import io
import shutil
import subprocess
from pathlib import Path

import pytest
from indexed_zstd import IndexedZstdFile

from conftest import generate_test_data, xorshift64

# Skip all tests if zstd CLI is not available
pytestmark = pytest.mark.reference
zstd_available = shutil.which("zstd") is not None


def zstd_decompress(zst_path, output_path):
    """Decompress a .zst file using the zstd CLI."""
    subprocess.run(
        ["zstd", "-d", "-f", "-o", str(output_path), str(zst_path)],
        check=True,
        capture_output=True,
    )


# ── Reference test matrix ────────────────────────────────────────────────────
# (name, seed, num_frames, frame_size, gen_flags)

REFERENCE_CASES = [
    ("4frames_seekable",       1,   4,    1024,   ["--seekable"]),
    ("4frames_no_seekable",    2,   4,    1024,   []),
    ("100frames_seekable",     3,   100,  1000,   ["--seekable"]),
    ("100frames_no_seekable",  4,   100,  1000,   []),
    ("single_frame",           5,   1,    65536,  []),
    ("single_frame_seekable",  6,   1,    65536,  ["--seekable"]),
    ("large_frames",           7,   10,   1048576, []),
    ("no_content_size",        8,   4,    1024,   ["--no-content-size"]),
    ("vary_size",              9,   10,   10000,  ["--seekable", "--vary-size"]),
    ("seekable_checksum",      10,  4,    1024,   ["--seekable", "--checksum"]),
    ("100frames_no_content_size", 11, 100, 1000,  ["--no-content-size"]),
    ("many_small_frames",      12,  500,  64,     ["--seekable"]),
    ("many_small_no_seekable", 13,  500,  64,     []),
]


@pytest.mark.skipif(not zstd_available, reason="zstd CLI not found in PATH")
@pytest.mark.parametrize(
    "name,seed,frames,fsize,flags",
    REFERENCE_CASES,
    ids=[c[0] for c in REFERENCE_CASES],
)
class TestReference:
    """Verify library output matches zstd CLI decompression."""

    def _setup(self, tmp_path, seed, frames, fsize, flags):
        """Generate test data and decompress with CLI."""
        zst, raw = generate_test_data(tmp_path, seed, frames, fsize, *flags)
        raw_data = Path(raw).read_bytes()

        cli_raw = tmp_path / "cli.raw"
        zstd_decompress(zst, cli_raw)
        cli_data = cli_raw.read_bytes()

        # Sanity: CLI output must match generator raw output
        assert cli_data == raw_data, "CLI output doesn't match gen_seekable raw output"

        return zst, raw_data, cli_data

    def test_read_all(self, tmp_path, name, seed, frames, fsize, flags):
        """Step A: full sequential read must match CLI output."""
        zst, raw_data, cli_data = self._setup(tmp_path, seed, frames, fsize, flags)

        with IndexedZstdFile(zst) as f:
            data = f.read()
        assert data == cli_data, f"read_all mismatch vs CLI for {name}"

    def test_seek_random(self, tmp_path, name, seed, frames, fsize, flags):
        """Step B: 10000 random seek+read ops vs CLI reference."""
        zst, raw_data, cli_data = self._setup(tmp_path, seed, frames, fsize, flags)
        file_size = len(cli_data)
        if file_size == 0:
            pytest.skip("Empty file")

        num_ops = 10000
        state = seed if seed > 0 else 1

        with IndexedZstdFile(zst) as f:
            for i in range(num_ops):
                state, val = xorshift64(state)
                pos = val % file_size
                f.seek(pos, io.SEEK_SET)
                byte = f.read(1)
                assert byte == bytes([cli_data[pos]]), (
                    f"seek_random mismatch at op {i}: pos={pos}"
                )

    def test_read_chunks(self, tmp_path, name, seed, frames, fsize, flags):
        """Step D: 256-byte chunked reads vs CLI reference."""
        zst, raw_data, cli_data = self._setup(tmp_path, seed, frames, fsize, flags)

        with IndexedZstdFile(zst) as f:
            pieces = []
            while True:
                chunk = f.read(256)
                if not chunk:
                    break
                pieces.append(chunk)
            data = b"".join(pieces)
        assert data == cli_data, f"read_chunks mismatch vs CLI for {name}"

    def test_seek_set_backward(self, tmp_path, name, seed, frames, fsize, flags):
        """Step C: backward byte-by-byte traversal."""
        zst, raw_data, cli_data = self._setup(tmp_path, seed, frames, fsize, flags)
        file_size = len(cli_data)

        with IndexedZstdFile(zst) as f:
            for pos in range(file_size - 1, -1, -1):
                f.seek(pos, io.SEEK_SET)
                byte = f.read(1)
                assert byte == bytes([cli_data[pos]]), (
                    f"backward mismatch at pos {pos}"
                )

    def test_seek_set_sequential(self, tmp_path, name, seed, frames, fsize, flags):
        """Step E: forward byte-by-byte traversal."""
        zst, raw_data, cli_data = self._setup(tmp_path, seed, frames, fsize, flags)
        file_size = len(cli_data)

        with IndexedZstdFile(zst) as f:
            for pos in range(file_size):
                f.seek(pos, io.SEEK_SET)
                byte = f.read(1)
                assert byte == bytes([cli_data[pos]]), (
                    f"sequential mismatch at pos {pos}"
                )

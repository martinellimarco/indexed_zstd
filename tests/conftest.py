"""
Shared fixtures and helpers for the indexed_zstd pytest test suite.

Provides:
  - generate_test_data(): generates .zst + .raw via gen_seekable
  - xorshift64(): deterministic PRNG matching the C test suite
  - Standard fixtures for common test data configurations
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

# ── Path to the gen_seekable binary from libzstd-seek ────────────────────────
# Resolution order:
#   1) GEN_SEEKABLE environment variable
#   2) In-repo submodule: indexed_zstd/libzstd-seek/build/tests/gen_seekable
#   3) Fallback: PATH lookup via shutil.which

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SUBMODULE_BIN = _REPO_ROOT / "indexed_zstd" / "libzstd-seek" / "build" / "tests" / "gen_seekable"

_env = os.environ.get("GEN_SEEKABLE")
if _env and os.path.isfile(_env):
    GEN_SEEKABLE = _env
elif _SUBMODULE_BIN.is_file():
    GEN_SEEKABLE = str(_SUBMODULE_BIN)
else:
    GEN_SEEKABLE = shutil.which("gen_seekable") or "gen_seekable"


def generate_test_data(tmp_path, seed, num_frames, frame_size, *flags):
    """Generate a .zst compressed file and its .raw reference using gen_seekable.

    Returns:
        (zst_path, raw_path) as strings.
    """
    zst = tmp_path / "test.zst"
    raw = tmp_path / "test.raw"
    cmd = [
        GEN_SEEKABLE,
        str(seed),
        str(num_frames),
        str(frame_size),
        str(zst),
        "--dump-raw",
        str(raw),
    ] + list(flags)
    subprocess.run(cmd, check=True, capture_output=True)
    return str(zst), str(raw)


def xorshift64(state):
    """Deterministic PRNG matching the C test suite's xorshift64.

    Args:
        state: uint64 seed (must be > 0).

    Returns:
        (next_state, value) — both uint64.
    """
    MASK = (1 << 64) - 1
    state &= MASK
    state ^= (state << 13) & MASK
    state ^= (state >> 7) & MASK
    state ^= (state << 17) & MASK
    return state, state


# ── Standard data fixtures ───────────────────────────────────────────────────

@pytest.fixture
def standard_4frame(tmp_path):
    """4 frames × 1024 bytes = 4096 bytes total, no seekable footer."""
    return generate_test_data(tmp_path, 42, 4, 1024)


@pytest.fixture
def standard_4frame_seekable(tmp_path):
    """4 frames × 1024 bytes, with seekable format footer."""
    return generate_test_data(tmp_path, 42, 4, 1024, "--seekable")


@pytest.fixture
def standard_4frame_checksum(tmp_path):
    """4 frames × 1024 bytes, seekable with checksums."""
    return generate_test_data(tmp_path, 42, 4, 1024, "--seekable", "--checksum")


@pytest.fixture
def standard_4frame_no_content_size(tmp_path):
    """4 frames × 1024 bytes, without content size in frame headers."""
    return generate_test_data(tmp_path, 42, 4, 1024, "--no-content-size")


@pytest.fixture
def multiframe_10(tmp_path):
    """10 frames × 1000 bytes = 10000 bytes total, seekable."""
    return generate_test_data(tmp_path, 42, 10, 1000, "--seekable")


@pytest.fixture
def multiframe_100(tmp_path):
    """100 frames × 1000 bytes = 100000 bytes total, seekable."""
    return generate_test_data(tmp_path, 42, 100, 1000, "--seekable")


@pytest.fixture
def single_frame(tmp_path):
    """Single frame, 4096 bytes."""
    return generate_test_data(tmp_path, 42, 1, 4096)


@pytest.fixture
def single_frame_seekable(tmp_path):
    """Single frame, 4096 bytes, seekable."""
    return generate_test_data(tmp_path, 42, 1, 4096, "--seekable")


@pytest.fixture
def large_frames(tmp_path):
    """10 frames × 1 MB each."""
    return generate_test_data(tmp_path, 7, 10, 1048576)


@pytest.fixture
def vary_size(tmp_path):
    """10 frames with varying sizes, seekable."""
    return generate_test_data(tmp_path, 9, 10, 10000, "--seekable", "--vary-size")


@pytest.fixture
def no_content_size_100(tmp_path):
    """100 frames × 1000 bytes, no content size (slow path)."""
    return generate_test_data(tmp_path, 11, 100, 1000, "--no-content-size")

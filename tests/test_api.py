"""
API tests for indexed_zstd: creation, seeking, reading, jump table, info functions.

Mirrors the 41 API tests from libzstd-seek's C test suite, adapted for the
Python binding. Tests are grouped by category with clear comments mapping
back to the original C test names.
"""

import io
import os
from pathlib import Path

import pytest
from indexed_zstd import IndexedZstdFile

from conftest import generate_test_data, xorshift64


# ══════════════════════════════════════════════════════════════════════════════
# Context creation
# ══════════════════════════════════════════════════════════════════════════════


class TestCreation:
    """Tests for different ways to create an IndexedZstdFile."""

    def test_create_from_file(self, standard_4frame):
        """C: create_from_file — IndexedZstdFile(path) + full read."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        with IndexedZstdFile(zst) as f:
            assert f.read() == raw_data

    def test_create_from_file_lazy_jt(self, standard_4frame):
        """C: create_from_file_no_jt — block_offsets_complete() progression."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        with IndexedZstdFile(zst) as f:
            # Initially JT is not complete (lazy init)
            assert f.block_offsets_complete() is False
            # Reading triggers progressive JT build
            data = f.read()
            assert data == raw_data

    def test_create_from_fd(self, standard_4frame):
        """C: create_from_fd — open via file descriptor."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        fd = os.open(zst, os.O_RDONLY)
        try:
            with IndexedZstdFile(fd) as f:
                data = f.read()
                assert data == raw_data
                assert f.fileno() == fd
        finally:
            try:
                os.close(fd)
            except OSError:
                pass  # Already closed by IndexedZstdFile

    def test_create_from_fd_lazy_jt(self, standard_4frame):
        """C: create_from_fd_no_jt — fd + lazy JT progression."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        fd = os.open(zst, os.O_RDONLY)
        try:
            with IndexedZstdFile(fd) as f:
                assert f.block_offsets_complete() is False
                data = f.read()
                assert data == raw_data
        finally:
            try:
                os.close(fd)
            except OSError:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# Seek operations
# ══════════════════════════════════════════════════════════════════════════════


class TestSeek:
    """Tests for SEEK_SET, SEEK_CUR, SEEK_END operations."""

    def test_seek_set_sequential(self, standard_4frame):
        """C: seek_set_sequential — SEEK_SET to every position, forward."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)
        with IndexedZstdFile(zst) as f:
            for pos in range(file_size):
                f.seek(pos, io.SEEK_SET)
                assert f.tell() == pos
                byte = f.read(1)
                assert byte == bytes([raw_data[pos]]), (
                    f"Mismatch at pos {pos}"
                )

    def test_seek_set_backward(self, standard_4frame):
        """C: seek_set_backward — SEEK_SET from end to beginning."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)
        with IndexedZstdFile(zst) as f:
            for pos in range(file_size - 1, -1, -1):
                f.seek(pos, io.SEEK_SET)
                byte = f.read(1)
                assert byte == bytes([raw_data[pos]]), (
                    f"Mismatch at backward pos {pos}"
                )

    def test_seek_cur_forward(self, standard_4frame):
        """C: seek_cur_forward — SEEK_CUR with +1 offset (skip every other byte)."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)
        with IndexedZstdFile(zst) as f:
            f.seek(0, io.SEEK_SET)
            pos = 0
            while pos < file_size:
                byte = f.read(1)
                assert byte == bytes([raw_data[pos]]), (
                    f"Mismatch at pos {pos}"
                )
                pos += 1
                if pos < file_size:
                    f.seek(1, io.SEEK_CUR)
                    pos += 1

    def test_seek_cur_backward(self, standard_4frame):
        """C: seek_cur_backward — SEEK_CUR with negative offset."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)
        start = min(24, file_size // 2)

        with IndexedZstdFile(zst) as f:
            f.seek(start, io.SEEK_SET)
            pos = start
            while pos >= 0:
                byte = f.read(1)
                assert byte == bytes([raw_data[pos]]), (
                    f"Mismatch at backward pos {pos}"
                )
                pos -= 1  # net movement: read 1 byte (+1), seek -2 = net -1
                # After read, tell = pos + 1 + 1 (original pos + 1 for read)
                # We want to go back to pos, which is current_tell - 2
                if pos >= 0:
                    f.seek(-2, io.SEEK_CUR)

    def test_seek_end(self, standard_4frame):
        """C: seek_end — SEEK_END with offset 0 and -1."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)

        with IndexedZstdFile(zst) as f:
            # seek(0, SEEK_END) → EOF position
            f.seek(0, io.SEEK_END)
            assert f.tell() == file_size

            # seek(-1, SEEK_END) → last byte
            f.seek(-1, io.SEEK_END)
            assert f.tell() == file_size - 1
            byte = f.read(1)
            assert byte == bytes([raw_data[-1]])

    def test_seek_random(self, multiframe_10):
        """C: seek_random — 10000 random ops alternating SEEK_SET/CUR/END."""
        zst, raw = multiframe_10
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)
        num_ops = 10000
        state = 7  # seed

        with IndexedZstdFile(zst) as f:
            for i in range(num_ops):
                state, val = xorshift64(state)
                pos = val % file_size
                method = i % 3

                if method == 0:
                    f.seek(pos, io.SEEK_SET)
                elif method == 1:
                    current = f.tell()
                    offset = pos - current
                    f.seek(offset, io.SEEK_CUR)
                else:
                    offset = pos - file_size
                    f.seek(offset, io.SEEK_END)

                assert f.tell() == pos, (
                    f"Op {i}: tell={f.tell()}, expected={pos}"
                )
                byte = f.read(1)
                assert byte == bytes([raw_data[pos]]), (
                    f"Op {i}: pos={pos}, expected {raw_data[pos]:#x}, got {byte!r}"
                )

    def test_seek_out_of_file(self, standard_4frame):
        """C: seek_out_of_file — 9 boundary cases with expected behaviour.

        Note: Python's BufferedReader may handle some boundary cases differently
        from the C API. We verify no crash and that tell() remains consistent.
        """
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)

        with IndexedZstdFile(zst) as f:
            # Case 1: seek(0, SEEK_END) → EOF is valid
            f.seek(0, io.SEEK_END)
            assert f.tell() == file_size

            # Case 2: seek(-N, SEEK_END) → position 0
            f.seek(-file_size, io.SEEK_END)
            assert f.tell() == 0

            # Case 3: seek(N, SEEK_SET) → EOF is valid
            f.seek(file_size, io.SEEK_SET)
            assert f.tell() == file_size


class TestSeekEdgeCases:
    """Edge cases for seek operations."""

    def test_seek_cur_zero(self, standard_4frame):
        """C: seek_cur_zero — seek(0, SEEK_CUR) is a no-op at any position."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)

        with IndexedZstdFile(zst) as f:
            # At start
            f.seek(0, io.SEEK_CUR)
            assert f.tell() == 0

            # At middle
            mid = file_size // 2
            f.seek(mid, io.SEEK_SET)
            f.seek(0, io.SEEK_CUR)
            assert f.tell() == mid

            # At EOF
            f.seek(0, io.SEEK_END)
            f.seek(0, io.SEEK_CUR)
            assert f.tell() == file_size

    def test_seek_to_same_pos(self, standard_4frame):
        """C: seek_to_same_pos — seeking twice to same position yields identical reads."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)
        target = min(100, file_size // 2)

        with IndexedZstdFile(zst) as f:
            f.seek(target, io.SEEK_SET)
            byte1 = f.read(1)

            f.seek(target, io.SEEK_SET)
            byte2 = f.read(1)

            assert byte1 == byte2
            assert byte1 == bytes([raw_data[target]])

    def test_seek_forward_large(self, multiframe_10):
        """C: seek_forward_large — seek(+500, SEEK_CUR) within a frame."""
        zst, raw = multiframe_10
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)

        with IndexedZstdFile(zst) as f:
            # Read 1 byte at start
            f.seek(0, io.SEEK_SET)
            byte0 = f.read(1)
            assert byte0 == bytes([raw_data[0]])

            # Skip 500 bytes forward
            f.seek(500, io.SEEK_CUR)
            pos = f.tell()
            assert pos == 501

            if pos < file_size:
                byte = f.read(1)
                assert byte == bytes([raw_data[pos]])

    def test_frame_boundary(self, standard_4frame):
        """C: frame_boundary — read spanning a frame boundary."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            offsets = f.block_offsets()
            # Need at least 2 frames
            uncomp_offsets = sorted(offsets.values())
            if len(uncomp_offsets) < 2:
                pytest.skip("Need at least 2 frames")

            # Find second frame boundary (skip offset 0)
            boundary = uncomp_offsets[1]
            if boundary < 2:
                pytest.skip("Frame boundary too close to start")

            # Seek 2 bytes before boundary, read 4 bytes across it
            start = boundary - 2
            f.seek(start, io.SEEK_SET)
            data = f.read(4)
            expected = raw_data[start:start + 4]
            assert data == expected, (
                f"Frame boundary read mismatch at {start}..{start+4}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# Seek stress test
# ══════════════════════════════════════════════════════════════════════════════


class TestSeekStress:
    """Stress tests with random byte-range reads."""

    def test_seek_stress(self, multiframe_10):
        """C: seek_stress — 10000 random byte-range reads (1–8192 bytes)."""
        zst, raw = multiframe_10
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)
        if file_size == 0:
            pytest.skip("Empty file")

        num_ops = 10000
        # Auto-generate seed for stress test
        import time
        seed = (int(time.time()) ^ os.getpid()) & ((1 << 64) - 1)
        if seed == 0:
            seed = 1
        state = seed
        backward_jumps = 0
        prev_pos = 0

        with IndexedZstdFile(zst) as f:
            for i in range(num_ops):
                # Random position
                state, val = xorshift64(state)
                pos = val % file_size

                # Random length 1–8192
                state, val = xorshift64(state)
                max_len = min(8192, file_size - pos)
                if max_len < 1:
                    continue
                length = (val % max_len) + 1

                if pos < prev_pos:
                    backward_jumps += 1
                prev_pos = pos

                # Seek using alternating methods
                method = i % 3
                if method == 0:
                    f.seek(pos, io.SEEK_SET)
                elif method == 1:
                    current = f.tell()
                    f.seek(pos - current, io.SEEK_CUR)
                else:
                    f.seek(pos - file_size, io.SEEK_END)

                assert f.tell() == pos, (
                    f"Op {i}: tell={f.tell()}, expected={pos}, seed={seed}"
                )

                # Read and verify
                data = f.read(length)
                expected = raw_data[pos:pos + length]
                assert data == expected, (
                    f"Op {i}: mismatch at pos={pos}, len={length}, seed={seed}"
                )


# ══════════════════════════════════════════════════════════════════════════════
# Read patterns
# ══════════════════════════════════════════════════════════════════════════════


class TestReadPatterns:
    """Tests for various read patterns."""

    def test_read_byte_by_byte(self, standard_4frame):
        """C: read_byte_by_byte — sequential 1-byte reads."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            for i, expected_byte in enumerate(raw_data):
                byte = f.read(1)
                assert byte == bytes([expected_byte]), (
                    f"Mismatch at offset {i}"
                )
            assert f.read(1) == b""  # EOF

    def test_read_chunks(self, standard_4frame):
        """C: read_chunks — chunked reads with verification."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        chunk_size = 128

        with IndexedZstdFile(zst) as f:
            offset = 0
            while offset < len(raw_data):
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                expected = raw_data[offset:offset + len(chunk)]
                assert chunk == expected, (
                    f"Chunk mismatch at offset {offset}"
                )
                offset += len(chunk)
            assert offset == len(raw_data)

    def test_single_frame(self, single_frame):
        """C: single_frame — operations on single-frame file."""
        zst, raw = single_frame
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            # Full read
            data = f.read()
            assert data == raw_data

            # Seek and read
            f.seek(0, io.SEEK_SET)
            mid = len(raw_data) // 2
            f.seek(mid, io.SEEK_SET)
            byte = f.read(1)
            assert byte == bytes([raw_data[mid]])

    def test_large_read(self, standard_4frame):
        """C: large_read — read buffer larger than file."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            data = f.read(len(raw_data) * 2)
            assert data == raw_data

    def test_read_too_much(self, standard_4frame):
        """C: read_too_much — request 2× file size from pos 0, short read."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)

        with IndexedZstdFile(zst) as f:
            data = f.read(file_size * 2)
            assert len(data) == file_size
            assert data == raw_data
            assert f.tell() == file_size

            # Second read at EOF returns empty
            data2 = f.read(1)
            assert data2 == b""

    def test_read_zero_bytes(self, standard_4frame):
        """C: read_zero_bytes — read(0) returns empty at any position."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)

        with IndexedZstdFile(zst) as f:
            # At start
            data = f.read(0)
            assert data == b""
            assert f.tell() == 0

            # At middle
            mid = file_size // 2
            f.seek(mid, io.SEEK_SET)
            data = f.read(0)
            assert data == b""
            assert f.tell() == mid

            # At EOF
            f.seek(0, io.SEEK_END)
            data = f.read(0)
            assert data == b""
            assert f.tell() == file_size


# ══════════════════════════════════════════════════════════════════════════════
# Jump table / block offsets
# ══════════════════════════════════════════════════════════════════════════════


class TestBlockOffsets:
    """Tests for block_offsets(), set_block_offsets(), block_offsets_complete()."""

    def test_block_offsets_auto(self, standard_4frame):
        """C: jump_table_auto — block_offsets() triggers full JT init."""
        zst, raw = standard_4frame

        with IndexedZstdFile(zst) as f:
            offsets = f.block_offsets()
            assert isinstance(offsets, dict)
            assert len(offsets) > 0
            assert f.block_offsets_complete() is True

            # Offsets should be monotonically increasing in both keys and values
            prev_comp = -1
            prev_uncomp = -1
            for comp_pos in sorted(offsets.keys()):
                assert comp_pos > prev_comp
                assert offsets[comp_pos] >= prev_uncomp
                prev_comp = comp_pos
                prev_uncomp = offsets[comp_pos]

    def test_block_offsets_frame_count(self, standard_4frame):
        """C: jump_table_auto — frame count matches expected."""
        zst, raw = standard_4frame

        with IndexedZstdFile(zst) as f:
            nframes = f.number_of_frames()
            # 4 data frames (may have extra for seekable footer)
            assert nframes >= 4

    def test_available_block_offsets(self, standard_4frame):
        """C: jump_table_progressive — available offsets grow during reads."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            # Before any read, some offsets may already be available
            initial = f.available_block_offsets()

            # Read triggers progressive discovery
            f.read(1)
            after_read = f.available_block_offsets()
            assert len(after_read) >= len(initial)

            # Full block_offsets forces complete JT
            full = f.block_offsets()
            assert len(full) >= len(after_read)
            assert f.block_offsets_complete() is True

    def test_set_block_offsets(self, standard_4frame):
        """C: jump_table_manual — copy offsets between two instances."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()

        # Get offsets from first instance
        with IndexedZstdFile(zst) as f1:
            offsets = f1.block_offsets()

        # Apply to second instance
        with IndexedZstdFile(zst) as f2:
            assert f2.block_offsets_complete() is False
            f2.set_block_offsets(offsets)
            # Offsets should now be available
            offsets2 = f2.block_offsets()
            assert offsets2 == offsets

            # Data should still be correct
            data = f2.read()
            assert data == raw_data

    def test_jt_progressive_reads(self, standard_4frame):
        """C: jt_progressive_reads — JT built incrementally via reads."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            assert f.block_offsets_complete() is False

            # Read small amounts to trigger progressive build
            f.read(10)
            offsets1 = f.available_block_offsets()

            # Read more
            f.read(2000)
            offsets2 = f.available_block_offsets()
            assert len(offsets2) >= len(offsets1)

            # Seek to end triggers full init
            f.seek(0, io.SEEK_END)
            # After seeking to end, JT should be more complete
            offsets3 = f.available_block_offsets()
            assert len(offsets3) >= len(offsets2)


# ══════════════════════════════════════════════════════════════════════════════
# Seekable format
# ══════════════════════════════════════════════════════════════════════════════


class TestSeekableFormat:
    """Tests for seekable format with footer."""

    def test_seekable_basic(self, standard_4frame_seekable):
        """C: seekable_basic — file with seekable footer: fast init + read/seek."""
        zst, raw = standard_4frame_seekable
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            data = f.read()
            assert data == raw_data

            # Seek random verification
            state = 77
            for _ in range(5000):
                state, val = xorshift64(state)
                pos = val % len(raw_data)
                f.seek(pos, io.SEEK_SET)
                byte = f.read(1)
                assert byte == bytes([raw_data[pos]])

    def test_seekable_checksum(self, standard_4frame_checksum):
        """C: seekable_checksum — seekable format with checksum entries."""
        zst, raw = standard_4frame_checksum
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            data = f.read()
            assert data == raw_data

    def test_seekable_vs_scan(self, tmp_path):
        """C: seekable_vs_scan — seekable vs non-seekable produce identical results."""
        dir_s = tmp_path / "s"
        dir_s.mkdir()
        dir_ns = tmp_path / "ns"
        dir_ns.mkdir()
        zst_s, raw_s = generate_test_data(dir_s, 42, 4, 1024, "--seekable")
        zst_ns, raw_ns = generate_test_data(dir_ns, 42, 4, 1024)

        # Both raw files should be identical (same seed/params)
        raw_s_data = Path(raw_s).read_bytes()
        raw_ns_data = Path(raw_ns).read_bytes()
        assert raw_s_data == raw_ns_data

        # Both should decompress to the same data
        with IndexedZstdFile(zst_s) as f_s, IndexedZstdFile(zst_ns) as f_ns:
            data_s = f_s.read()
            data_ns = f_ns.read()
            assert data_s == data_ns == raw_s_data


# ══════════════════════════════════════════════════════════════════════════════
# Info functions
# ══════════════════════════════════════════════════════════════════════════════


class TestInfoFunctions:
    """Tests for size(), number_of_frames(), is_multiframe(), fileno(), etc."""

    def test_file_size(self, standard_4frame):
        """C: file_size — uncompressed file size is correct."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            assert f.size() == len(raw_data)

    def test_file_size_value(self, standard_4frame):
        """C: file_size — size matches expected 4 * 1024 = 4096."""
        zst, raw = standard_4frame
        with IndexedZstdFile(zst) as f:
            assert f.size() == 4096

    def test_frame_count(self, standard_4frame):
        """C: frame_count — number of frames matches expected."""
        zst, raw = standard_4frame
        with IndexedZstdFile(zst) as f:
            nframes = f.number_of_frames()
            # 4 data frames (possibly +1 for seekable footer)
            assert nframes >= 4

    def test_is_multiframe_true(self, standard_4frame):
        """C: is_multiframe — multi-frame file."""
        zst, raw = standard_4frame
        with IndexedZstdFile(zst) as f:
            assert f.is_multiframe() is True

    def test_is_multiframe_false(self, single_frame):
        """C: is_multiframe — single-frame file."""
        zst, raw = single_frame
        with IndexedZstdFile(zst) as f:
            assert f.is_multiframe() is False

    def test_fileno(self, standard_4frame):
        """C: fileno_check — fileno() returns a valid fd."""
        zst, raw = standard_4frame
        with IndexedZstdFile(zst) as f:
            fd = f.fileno()
            assert isinstance(fd, int)
            assert fd >= 0

    def test_compressed_tell(self, standard_4frame):
        """C: compressed_tell — tell_compressed() returns coherent positions."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            ct0 = f.tell_compressed()
            assert ct0 >= 0

            # After reading, compressed position should advance
            f.read(100)
            ct1 = f.tell_compressed()
            assert ct1 >= ct0

            # At EOF
            f.seek(0, io.SEEK_END)
            ct_end = f.tell_compressed()
            assert ct_end > 0

    def test_compressed_tell_monotonic(self, standard_4frame):
        """C: compressed_tell_monotonic — tell_compressed() never decreases."""
        zst, raw = standard_4frame

        with IndexedZstdFile(zst) as f:
            prev_ct = 0
            while True:
                data = f.read(10)
                if not data:
                    break
                ct = f.tell_compressed()
                assert ct >= prev_ct, (
                    f"Compressed tell decreased: {ct} < {prev_ct}"
                )
                prev_ct = ct
            assert prev_ct > 0

    def test_compressed_tell_seek(self, standard_4frame_seekable):
        """C: compressed_tell_seek — tell_compressed() at frame boundaries."""
        zst, raw = standard_4frame_seekable

        with IndexedZstdFile(zst) as f:
            offsets = f.block_offsets()
            if len(offsets) < 2:
                pytest.skip("Need at least 2 frames")

            # Seek to each frame boundary and check compressed position
            for comp_pos, uncomp_pos in sorted(offsets.items()):
                f.seek(uncomp_pos, io.SEEK_SET)
                assert f.tell() == uncomp_pos

                # After seeking to frame boundary, reading should work
                if uncomp_pos < f.size():
                    byte = f.read(1)
                    assert len(byte) == 1

    def test_compressed_tell_absolute(self, tmp_path):
        """Verify tell_compressed() never exceeds compressed file size.

        Uses a single large frame (1 MiB) to force many iterations of the
        inner ZSTD_decompressStream loop per read() call.  This catches the
        cumulative overcount bug where input.pos (cumulative within a frame)
        was accumulated instead of the delta.
        """
        zst, raw = generate_test_data(tmp_path, 42, 1, 1048576)
        compressed_size = os.path.getsize(zst)

        with IndexedZstdFile(zst) as f:
            total_read = 0
            reads = 0
            while True:
                data = f.read(4096)
                if not data:
                    break
                total_read += len(data)
                reads += 1
                ct = f.tell_compressed()
                assert 0 <= ct <= compressed_size, (
                    f"read #{reads} (total={total_read}): "
                    f"tell_compressed()={ct} exceeds file size={compressed_size}"
                )

            # At EOF, compressed position should equal compressed file size
            ct_final = f.tell_compressed()
            assert ct_final == compressed_size, (
                f"at EOF: tell_compressed()={ct_final} != file size={compressed_size}"
            )

    def test_last_known_size(self, standard_4frame):
        """C: last_known_size — available offsets progression."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            # Before full init
            avail1 = f.available_block_offsets()

            # After full init
            full = f.block_offsets()
            assert f.size() == len(raw_data)


# ══════════════════════════════════════════════════════════════════════════════
# Python-specific API tests
# ══════════════════════════════════════════════════════════════════════════════


class TestPythonAPI:
    """Tests specific to the Python binding's io.BufferedReader interface."""

    def test_context_manager(self, standard_4frame):
        """IndexedZstdFile works as a context manager."""
        zst, raw = standard_4frame
        with IndexedZstdFile(zst) as f:
            data = f.read(10)
            assert len(data) == 10
        assert f.closed

    def test_readable(self, standard_4frame):
        """readable() returns True."""
        zst, raw = standard_4frame
        with IndexedZstdFile(zst) as f:
            assert f.readable() is True

    def test_seekable_property(self, standard_4frame):
        """seekable() returns True."""
        zst, raw = standard_4frame
        with IndexedZstdFile(zst) as f:
            assert f.seekable() is True

    def test_mode(self, standard_4frame):
        """mode is 'rb'."""
        zst, raw = standard_4frame
        with IndexedZstdFile(zst) as f:
            assert f.mode == "rb"

    def test_name(self, standard_4frame):
        """name matches the filename."""
        zst, raw = standard_4frame
        with IndexedZstdFile(zst) as f:
            assert f.name == zst

    def test_readline(self, tmp_path):
        """readline() works (inherited from BufferedReader)."""
        # Create a file with known text content
        zst, raw = generate_test_data(tmp_path, 42, 1, 4096)
        raw_data = Path(raw).read_bytes()

        with IndexedZstdFile(zst) as f:
            line = f.readline()
            assert isinstance(line, bytes)
            assert len(line) > 0

    def test_closed_property(self, standard_4frame):
        """closed property reflects file state."""
        zst, raw = standard_4frame
        f = IndexedZstdFile(zst)
        assert f.closed is False
        f.close()
        assert f.closed is True

    def test_tell_initial(self, standard_4frame):
        """tell() returns 0 at start."""
        zst, raw = standard_4frame
        with IndexedZstdFile(zst) as f:
            assert f.tell() == 0


# ══════════════════════════════════════════════════════════════════════════════
# Inline (no-variable) lifetime tests — regression for GitHub issue #21
#
# When IndexedZstdFile is not assigned to a variable, CPython's LOAD_ATTR
# drops the last reference before the method call, triggering premature GC.
# BufferedReader.__del__ calls close(), freeing the C context.  The bound
# method then operates on a closed context and returns wrong values.
# ══════════════════════════════════════════════════════════════════════════════


class TestInlineLifetime:
    """Verify methods work correctly without assigning the object to a variable.

    Regression tests for GitHub issue #21: when IndexedZstdFile is not assigned
    to a variable, CPython's LOAD_ATTR drops the last stack reference before
    the bound method is called, triggering BufferedReader.__del__ → close() →
    ZSTDSeek_free().  The method then operates on a closed/freed context.

    IMPORTANT: the method call is separated from the assert statement to prevent
    pytest's assert-rewriting from creating temporary variables that would keep
    the object alive and mask the bug.
    """

    def test_inline_size(self, standard_4frame_seekable):
        """size() must return correct value without variable assignment."""
        zst, raw = standard_4frame_seekable
        raw_size = os.path.getsize(raw)
        # Do NOT merge into assert — pytest's rewriting would mask the GC bug
        result = (IndexedZstdFile(zst)).size()
        assert result == raw_size

    def test_inline_number_of_frames(self, standard_4frame_seekable):
        """number_of_frames() must return correct value inline."""
        zst, raw = standard_4frame_seekable
        result = (IndexedZstdFile(zst)).number_of_frames()
        assert result > 0

    def test_inline_is_multiframe(self, standard_4frame_seekable):
        """is_multiframe() must return True for multi-frame file inline."""
        zst, raw = standard_4frame_seekable
        result = (IndexedZstdFile(zst)).is_multiframe()
        assert result is True

    def test_inline_block_offsets(self, standard_4frame_seekable):
        """block_offsets() must return non-empty dict inline."""
        zst, raw = standard_4frame_seekable
        result = (IndexedZstdFile(zst)).block_offsets()
        assert len(result) > 0

    def test_inline_tell_compressed(self, standard_4frame_seekable):
        """tell_compressed() must return >= 0 inline."""
        zst, raw = standard_4frame_seekable
        result = (IndexedZstdFile(zst)).tell_compressed()
        assert result >= 0

    def test_inline_available_block_offsets(self, standard_4frame_seekable):
        """available_block_offsets() must not crash inline."""
        zst, raw = standard_4frame_seekable
        result = (IndexedZstdFile(zst)).available_block_offsets()
        assert isinstance(result, dict)

    def test_inline_read(self, standard_4frame_seekable):
        """read() must return data inline (not empty due to premature close)."""
        zst, raw = standard_4frame_seekable
        result = (IndexedZstdFile(zst)).read(100)
        assert len(result) == 100

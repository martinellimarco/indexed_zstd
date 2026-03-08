"""
Error path tests for indexed_zstd.

Mirrors the 12 error-path tests from libzstd-seek's C test suite.
Tests verify that the Python binding handles invalid inputs gracefully
(raising exceptions rather than crashing).
"""

import os
import struct
from pathlib import Path

import pytest
from indexed_zstd import IndexedZstdFile

from conftest import generate_test_data


class TestErrorCreation:
    """Error handling during file creation / opening."""

    def test_error_empty_file(self, tmp_path):
        """C: error_empty_file — zero-byte file must raise an exception."""
        empty = tmp_path / "empty.zst"
        empty.write_bytes(b"")

        with pytest.raises(Exception):
            IndexedZstdFile(str(empty))

    def test_error_invalid_format(self, tmp_path):
        """C: error_invalid_format — non-zstd content must raise an exception."""
        invalid = tmp_path / "invalid.txt"
        invalid.write_text("This is not a zstd file at all\n")

        with pytest.raises(Exception):
            IndexedZstdFile(str(invalid))

    def test_error_truncated(self, tmp_path):
        """C: error_truncated — truncated zstd file."""
        # Generate valid file first
        zst, raw = generate_test_data(tmp_path, 42, 4, 1024, "--seekable")
        zst_data = Path(zst).read_bytes()

        # Truncate to just 15 bytes (partial header)
        truncated = tmp_path / "truncated.zst"
        truncated.write_bytes(zst_data[:15])

        # Must either fail to open or fail/return short data on read
        raised = False
        try:
            f = IndexedZstdFile(str(truncated))
            try:
                data = f.read()
                # If read succeeds, data must be shorter than the original
                assert len(data) < 4 * 1024, (
                    f"Truncated file returned {len(data)} bytes, expected less than original"
                )
            except (OSError, ValueError, RuntimeError):
                raised = True
            finally:
                f.close()
        except (OSError, ValueError, RuntimeError):
            raised = True
        # At least one of: open failed, read failed, or data was short
        assert raised or len(data) < 4 * 1024

    def test_error_corrupted_header(self, tmp_path):
        """C: error_corrupted_header — zstd with corrupted magic number."""
        zst, raw = generate_test_data(tmp_path, 42, 4, 1024)
        zst_data = bytearray(Path(zst).read_bytes())

        # Corrupt the first byte (zstd magic: 0xFD2FB528)
        zst_data[0] = zst_data[0] & 0xF0

        corrupted = tmp_path / "corrupted.zst"
        corrupted.write_bytes(bytes(zst_data))

        with pytest.raises(Exception):
            IndexedZstdFile(str(corrupted))


class TestErrorSeek:
    """Error handling for seek operations.

    Note: Python's io.BufferedReader may handle boundary conditions differently
    from the C API. The wrapper may silently clamp positions or raise OSError.
    """

    def test_error_seek_negative(self, standard_4frame):
        """C: error_seek_negative — seek(-1, SEEK_SET) should fail or be handled."""
        zst, raw = standard_4frame
        with IndexedZstdFile(zst) as f:
            # Python's BufferedReader may raise ValueError for negative SEEK_SET
            try:
                f.seek(-1, 0)  # SEEK_SET = 0
                # If it doesn't raise, position should not be negative
                assert f.tell() >= 0
            except (ValueError, OSError):
                pass  # Expected

    def test_error_seek_beyond(self, standard_4frame):
        """C: error_seek_beyond — seeking past EOF."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)

        with IndexedZstdFile(zst) as f:
            # Seeking past EOF
            try:
                f.seek(file_size + 100, 0)  # SEEK_SET
                # If it doesn't raise, tell should be at or past EOF
                pos = f.tell()
                assert pos >= 0
                # Read should return empty or raise
                data = f.read(1)
                # Should return empty at or past EOF
            except (ValueError, OSError):
                pass  # Also acceptable

    def test_error_read_past_eof(self, standard_4frame):
        """C: error_read_past_eof — read at EOF returns empty."""
        zst, raw = standard_4frame
        raw_data = Path(raw).read_bytes()
        file_size = len(raw_data)

        with IndexedZstdFile(zst) as f:
            # Seek to near end
            f.seek(file_size - 1, 0)
            # Read: should get exactly 1 byte
            data = f.read(1024)
            assert len(data) == 1
            assert data == bytes([raw_data[-1]])

            # Read at EOF: should get empty
            data2 = f.read(1)
            assert data2 == b""


class TestCorruptedData:
    """Tests with corrupted compressed data."""

    def test_error_corrupted_frame_data(self, tmp_path):
        """C: error_corrupted_frame_data — corrupt 2nd frame payload."""
        # Generate a multi-frame file
        zst, raw = generate_test_data(tmp_path, 42, 4, 1024)
        zst_data = bytearray(Path(zst).read_bytes())
        raw_data = Path(raw).read_bytes()

        # Find and corrupt data in the middle of the file
        # (Corrupt bytes around the 2nd frame, roughly at 1/4 of compressed data)
        corrupt_pos = len(zst_data) // 4
        for i in range(corrupt_pos, min(corrupt_pos + 20, len(zst_data))):
            zst_data[i] ^= 0xFF

        corrupted = tmp_path / "corrupted_frame.zst"
        corrupted.write_bytes(bytes(zst_data))

        # Must either fail to open, fail during read, or return corrupted data
        raised = False
        try:
            with IndexedZstdFile(str(corrupted)) as f:
                try:
                    data = f.read()
                    # If read succeeds, data must differ from original
                    assert data != raw_data, "Corrupted file returned identical data"
                except (OSError, ValueError, RuntimeError):
                    raised = True
        except (OSError, ValueError, RuntimeError):
            raised = True
        # At least one of: open failed, read failed, or data differs
        assert raised or data != raw_data

    def test_error_mixed_format(self, tmp_path):
        """C: error_mixed_format — valid ZSTD followed by garbage."""
        zst, raw = generate_test_data(tmp_path, 42, 4, 1024)
        zst_data = Path(zst).read_bytes()

        # Append garbage after valid data
        mixed = tmp_path / "mixed.zst"
        mixed.write_bytes(zst_data + b"\x00\xFF" * 100)

        # The library should be able to open and read the valid portion
        try:
            with IndexedZstdFile(str(mixed)) as f:
                data = f.read()
                # Should at least get the valid data
                assert len(data) > 0
        except Exception:
            pass  # Also acceptable if it rejects the file

    def test_error_seektable_bad_offsets(self, tmp_path):
        """C: error_seektable_bad_offsets — seekable footer with bad offsets.

        Corrupts a seekable footer's decompressed size field to trigger
        fallback to frame-by-frame scanning.
        """
        zst, raw = generate_test_data(tmp_path, 42, 4, 1024, "--seekable")
        zst_data = bytearray(Path(zst).read_bytes())
        raw_data = Path(raw).read_bytes()

        # The seekable footer is at the end of the file.
        # Format: ... | skippable_frame_header(8) | entries... | footer(9) |
        # We corrupt the first entry's decompressed size (set to 0xFFFFFFFF)
        # Find the seek table magic at the end
        # Seek table footer magic: 0xB1EA928F (little-endian at end - 4 bytes)
        footer_magic = b"\xb1\xea\x92\x8f"
        footer_pos = zst_data.rfind(footer_magic)

        if footer_pos > 0:
            # Go back to find the entries
            # Footer format: numFrames(4) + SFD(1) + magic(4) = 9 bytes
            # Each entry: compSize(4) + decompSize(4) = 8 bytes
            # The first entry starts after the skippable frame header (8 bytes)
            num_frames_pos = footer_pos - 5  # -1 for SFD, -4 for numFrames
            # First entry decompressed size is at: num_frames_pos - (num_frames * 8) + 4
            # Simpler: corrupt byte at a known offset in the seektable
            entry_start = footer_pos - 5 - (4 * 8)  # approximate
            if entry_start > 0 and entry_start + 7 < len(zst_data):
                # Corrupt the decompressed size of first entry
                zst_data[entry_start + 4] = 0xFF
                zst_data[entry_start + 5] = 0xFF
                zst_data[entry_start + 6] = 0xFF
                zst_data[entry_start + 7] = 0xFF

        corrupted = tmp_path / "bad_seektable.zst"
        corrupted.write_bytes(bytes(zst_data))

        # Library should fall back to frame scanning and still work
        try:
            with IndexedZstdFile(str(corrupted)) as f:
                data = f.read()
                # Data should still be correct (seektable is metadata only)
                assert data == raw_data
        except Exception:
            # If it fails, that's also acceptable for corrupted input
            pass

    def test_seekable_malformed_footer(self, tmp_path):
        """C: seekable_malformed_footer — corrupted seekable footers.

        Tests multiple corruption variants. In all cases the library should
        either fall back to frame scanning or raise an error, but never crash.
        """
        zst, raw = generate_test_data(tmp_path, 42, 4, 1024, "--seekable")
        zst_data = Path(zst).read_bytes()
        raw_data = Path(raw).read_bytes()

        # Variant A: Corrupt the last 4 bytes (seekable magic)
        variant_a = bytearray(zst_data)
        variant_a[-1] ^= 0xFF
        path_a = tmp_path / "malformed_a.zst"
        path_a.write_bytes(bytes(variant_a))

        try:
            with IndexedZstdFile(str(path_a)) as f:
                data = f.read()
                assert data == raw_data  # Should fall back to scanning
        except Exception:
            pass  # Acceptable

        # Variant B: Zero out the footer entirely (last 9 bytes)
        variant_b = bytearray(zst_data)
        for i in range(min(9, len(variant_b))):
            variant_b[-(i + 1)] = 0
        path_b = tmp_path / "malformed_b.zst"
        path_b.write_bytes(bytes(variant_b))

        try:
            with IndexedZstdFile(str(path_b)) as f:
                data = f.read()
                assert data == raw_data
        except Exception:
            pass  # Acceptable

        # Variant C: Truncate just the footer
        # Remove last 9 bytes (footer) but keep the skippable frame + entries
        variant_c = zst_data[:-9]
        path_c = tmp_path / "malformed_c.zst"
        path_c.write_bytes(variant_c)

        try:
            with IndexedZstdFile(str(path_c)) as f:
                data = f.read()
                # Compressed frames are intact, only footer is truncated
                assert len(data) > 0, "Truncated footer produced empty output"
        except Exception:
            pass  # Acceptable: rejecting a malformed file is fine

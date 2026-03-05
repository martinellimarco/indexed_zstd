# Testing

## Overview

The test suite exercises the `indexed_zstd` Python binding across five dimensions:

| Dimension          | Tool                          | What it catches                                       |
|--------------------|-------------------------------|-------------------------------------------------------|
| **Correctness**    | round-trip + byte comparison  | decompression produces bit-identical output           |
| **Seek accuracy**  | random seek/read verification | every byte at every position matches expected content |
| **Reference**      | library vs `zstd` CLI         | output identical to the reference zstd implementation |
| **Stress**         | 10K random byte-range reads   | cross-frame reads, backward jumps, range verification |
| **Realistic data** | SHA256 + t2sz real blobs      | high/low compressibility, many frame sizes & levels   |

176 tests in total: 44 round-trip, 49 API, 11 error-path, 65 reference comparison,
and 7 heavy (realistic data) tests. All tests run unconditionally — no skips.

---

## Prerequisites

| Dependency     | Required for         | macOS                                           | Linux                                           |
|----------------|----------------------|-------------------------------------------------|-------------------------------------------------|
| Python ≥ 3.8   | all tests            | `brew install python`                           | `apt install python3`                           |
| `pytest`       | all tests            | `pip install pytest`                            | `pip install pytest`                            |
| `gen_seekable` | all tests            | build libzstd-seek                              | build libzstd-seek                              |
| `zstd` CLI     | reference tests only | `brew install zstd`                             | `apt install zstd`                              |
| `t2sz`         | heavy tests only     | [t2sz](https://github.com/martinellimarco/t2sz) | [t2sz](https://github.com/martinellimarco/t2sz) |

### Building `gen_seekable`

The test data generator comes from the `libzstd-seek` project:

```bash
cd ../libzstd-seek
cmake -B build -DBUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Debug
cmake --build build --target gen_seekable
# Binary: build/tests/gen_seekable
```

The test suite looks for `gen_seekable` relative to the project layout
(`../libzstd-seek/build/tests/gen_seekable`). If your build is elsewhere,
set the `GEN_SEEKABLE` environment variable or update the path in `tests/conftest.py`.

---

## Quick start

```bash
# Create virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest

# Run all tests
pytest tests/ -v

# Run without heavy tests
pytest tests/ -v -m "not heavy"

# Run without reference tests (no zstd CLI needed)
pytest tests/ -v -m "not reference"

# Run only API tests
pytest tests/test_api.py -v
```

---

## Test categories

### Round-trip tests (`test_roundtrip.py`)

Each test generates deterministic data with `gen_seekable`, reads it back through
`IndexedZstdFile`, and verifies byte-exact match. Every configuration runs 4 checks:
full read, 256-byte chunked read, 1000 random seeks, and byte-by-byte (small files).

| Test                            | Frames | Frame size | Flags                    | What is covered                            |
|---------------------------------|--------|------------|--------------------------|------------------------------------------  |
| `4frames_seekable`              | 4      | 1024       | `--seekable`             | seekable format footer parsing             |
| `4frames_no_seekable`           | 4      | 1024       | —                        | frame header scanning                      |
| `100frames_seekable`            | 100    | 1000       | `--seekable`             | large jump table                           |
| `100frames_no_seekable`         | 100    | 1000       | —                        | frame header scanning at scale             |
| `single_frame`                  | 1      | 65536      | —                        | single-frame edge case                     |
| `single_frame_seekable`         | 1      | 65536      | `--seekable`             | single-frame with seekable footer          |
| `large_frames`                  | 10     | 1 MB       | —                        | large frame decompression                  |
| `no_content_size`               | 4      | 1024       | `--no-content-size`      | full decompression fallback path           |
| `vary_size`                     | 10     | varies     | `--seekable --vary-size` | non-uniform frame sizes                    |
| `seekable_checksum`             | 4      | 1024       | `--seekable --checksum`  | seekable format with checksum entries      |
| `100frames_no_content_size`     | 100    | 1000       | `--no-content-size`      | slow path at scale (full decompression)    |

### API tests (`test_api.py`)

#### Context creation

| Test                       | API variant                                 |
|----------------------------|---------------------------------------------|
| `test_create_from_file`    | `IndexedZstdFile(path)`                     |
| `test_create_file_lazy_jt` | `block_offsets_complete()` progression      |
| `test_create_from_fd`      | `IndexedZstdFile(fd)` via `os.open()`       |
| `test_create_from_fd_lazy` | fd + `block_offsets_complete()` progression |

#### Seek operations

| Test                       | What is covered                                          |
|----------------------------|----------------------------------------------------------|
| `test_seek_set_sequential` | SEEK_SET to every position, forward                      |
| `test_seek_set_backward`   | SEEK_SET from end to beginning                           |
| `test_seek_cur_forward`    | SEEK_CUR relative seeking forward                        |
| `test_seek_cur_backward`   | SEEK_CUR with negative offset, backward traversal        |
| `test_seek_end`            | SEEK_END with offset 0 and -1                            |
| `test_seek_random`         | 10,000 random ops alternating SEEK_SET/CUR/END + verify  |
| `test_seek_out_of_file`    | Boundary cases (SET/CUR/END)                             |

#### Seek edge cases

| Test                      | What is covered                                    |
|---------------------------|----------------------------------------------------|
| `test_seek_cur_zero`      | `seek(0, SEEK_CUR)` no-op at start/mid/eof         |
| `test_seek_to_same_pos`   | seek to current position twice                     |
| `test_seek_forward_large` | `seek(+500, SEEK_CUR)` within frame, data verified |
| `test_frame_boundary`     | read spanning frame boundary                       |

#### Seek stress

| Test                       | What is covered                                          |
|----------------------------|----------------------------------------------------------|
| `test_seek_stress`         | 10,000 random byte-range reads (1–8192 B), all 3 origins|

#### Read patterns

| Test                       | What is covered                                          |
|----------------------------|----------------------------------------------------------|
| `test_read_byte_by_byte`   | sequential 1-byte reads                                  |
| `test_read_chunks`         | chunked reads with verification                          |
| `test_single_frame`        | single-frame file operations                             |
| `test_large_read`          | read buffer larger than file                             |
| `test_read_too_much`       | request 2× file size from pos 0, short read              |
| `test_read_zero_bytes`     | `read(0)` returns empty at start/mid/eof                 |

#### Block offsets (jump table)

| Test                             | What is covered                                    |
|----------------------------------|----------------------------------------------------|
| `test_block_offsets_auto`        | `block_offsets()` triggers full init, monotonicity |
| `test_block_offsets_frame_count` | `number_of_frames()` matches expected              |
| `test_available_block_offsets`   | `available_block_offsets()` grows during reads     |
| `test_set_block_offsets`         | copy offsets between two instances                 |
| `test_jt_progressive_reads`      | JT built incrementally via reads                   |

#### Seekable format

| Test                       | What is covered                                          |
|----------------------------|----------------------------------------------------------|
| `test_seekable_basic`      | file with seekable footer: fast init + read/seek         |
| `test_seekable_checksum`   | seekable format with checksum entries                    |
| `test_seekable_vs_scan`    | seekable vs non-seekable produce identical results       |

#### Info functions

| Test                        | What is covered                                        |
|-----------------------------|--------------------------------------------------------|
| `test_file_size`            | `size()` matches raw file length                       |
| `test_file_size_value`      | `size()` == 4096 for 4×1024 file                       |
| `test_frame_count`          | `number_of_frames()` accuracy                          |
| `test_is_multiframe_true`   | `is_multiframe()` for multi-frame                      |
| `test_is_multiframe_false`  | `is_multiframe()` for single-frame                     |
| `test_fileno`               | `fileno()` returns valid fd                            |
| `test_compressed_tell`      | `tell_compressed()` coherence                          |
| `test_compressed_tell_mono` | `tell_compressed()` never decreases                    |
| `test_compressed_tell_seek` | `tell_compressed()` at frame boundaries                |
| `test_compressed_tell_absolute` | `tell_compressed()` ≤ compressed file size (1×1 MiB frame) |
| `test_last_known_size`      | `available_block_offsets()` → `block_offsets()` growth |

#### Python-specific API

| Test                     | What is covered                                 |
|--------------------------|-------------------------------------------------|
| `test_context_manager`   | `with IndexedZstdFile(path) as f:` + `f.closed` |
| `test_readable`          | `readable()` returns True                       |
| `test_seekable_property` | `seekable()` returns True                       |
| `test_mode`              | `mode == 'rb'`                                  |
| `test_name`              | `name == path`                                  |
| `test_readline`          | `readline()` (inherited from BufferedReader)    |
| `test_closed_property`   | `closed` property after close()                 |
| `test_tell_initial`      | `tell()` returns 0 at start                     |

### Error paths (`test_error_paths.py`)

| Test                         | What is covered                                   |
|------------------------------|---------------------------------------------------|
| `test_error_empty`           | zero-byte file → exception                        |
| `test_error_invalid_format`  | non-zstd file → exception                         |
| `test_error_truncated`       | truncated zstd file → exception or partial read   |
| `test_error_corrupted_header`| corrupted magic number → exception                |
| `test_error_seek_negative`   | `seek(-1, SEEK_SET)` → exception or no-op         |
| `test_error_seek_beyond`     | seek past EOF → exception or clamped              |
| `test_error_read_past_eof`   | read at EOF → empty bytes                         |
| `test_error_corrupted_frame` | corrupt 2nd frame payload → error                 |
| `test_error_mixed_format`    | valid ZSTD + garbage → handled                    |
| `test_error_bad_seektable`   | corrupted seekable footer → fallback to scan      |
| `test_seekable_malformed`    | 3 corrupted footer variants → no crash            |

### Reference comparison tests (`test_reference.py`)

Verify that `IndexedZstdFile` produces byte-identical output to the `zstd` CLI.
Each of 13 configurations is tested with 5 access patterns: read_all, seek_random
(10K ops), read_chunks (256 B), backward traversal, forward sequential.

Skipped automatically if `zstd` is not in PATH.

| Test                        | Frames | Frame size | Flags                    |
|-----------------------------|--------|------------|--------------------------|
| `4frames_seekable`          | 4      | 1024       | `--seekable`             |
| `4frames_no_seekable`       | 4      | 1024       | —                        |
| `100frames_seekable`        | 100    | 1000       | `--seekable`             |
| `100frames_no_seekable`     | 100    | 1000       | —                        |
| `single_frame`              | 1      | 65536      | —                        |
| `single_frame_seekable`     | 1      | 65536      | `--seekable`             |
| `large_frames`              | 10     | 1 MB       | —                        |
| `no_content_size`           | 4      | 1024       | `--no-content-size`      |
| `vary_size`                 | 10     | varies     | `--seekable --vary-size` |
| `seekable_checksum`         | 4      | 1024       | `--seekable --checksum`  |
| `100frames_no_content_size` | 100    | 1000       | `--no-content-size`      |
| `many_small_frames`         | 500    | 64         | `--seekable`             |
| `many_small_no_seekable`    | 500    | 64         | —                        |

### Heavy tests (`test_heavy.py`)

Realistic data blobs compressed with [t2sz](https://github.com/martinellimarco/t2sz).
Each test verifies SHA256 integrity, byte-exact comparison, 10,000 random seeks,
and chunked reads.

Labelled `heavy` in pytest and can be excluded:
```bash
pytest tests/ -m "not heavy"                  # skip heavy tests
SKIP_HEAVY_TESTS=1 pytest tests/              # skip via environment variable
```

If `t2sz` is not in PATH, the tests are skipped automatically.

| Test                  | Data type         | Raw size | Frame size | Level | What it stresses                        |
|-----------------------|-------------------|----------|------------|-------|-----------------------------------------|
| `heavy_text`          | base64 text       | 10 MB    | 300000 B   | 3     | high compression ratio, text patterns   |
| `heavy_binary`        | `/dev/urandom`    | 10 MB    | 250000 B   | 3     | nearly incompressible random data       |
| `heavy_zeros`         | `/dev/zero`       | 50 MB    | 999999 B   | 3     | extreme compression ratio, large file   |
| `heavy_mixed`         | text+binary+pat   | 20 MB    | 500000 B   | 9     | mixed compressibility per frame         |
| `heavy_level_max`     | base64 text       | 5 MB     | 350000 B   | 22    | maximum compression level               |
| `heavy_small_frames`  | `/dev/urandom`    | 5 MB     | 3000 B     | 1     | ~1747 frames, large jump table          |
| `heavy_single_frame`  | `/dev/urandom`    | 20 MB    | 20 MB      | 3     | single huge frame                       |

Frame sizes are deliberately **not** powers of two, forcing misaligned frame
boundary crossings.

---

## Tests not ported from C suite

These tests require C-level API access not exposed in the Python binding:

| C test                     | Reason                                             |
|----------------------------|----------------------------------------------------|
| `create_from_buffer`       | No Python constructor from memory buffer           |
| `create_from_buffer_no_jt` | Same                                               |
| `jump_table_new_free`      | Standalone JT lifecycle, C-only API                |
| `error_null`               | NULL context not applicable in Python              |
| `fileno_buffer`            | Requires buffer-based context                      |
| `error_seek_invalid_origin`| Python io layer handles invalid whence             |

---

## Running subsets

```bash
# All tests (155 total)
pytest tests/ -v

# Exclude heavy tests (~148 tests, < 10 seconds)
pytest tests/ -m "not heavy"

# Exclude reference tests (no zstd CLI needed)
pytest tests/ -m "not reference"

# Only round-trip tests
pytest tests/test_roundtrip.py -v

# Only error path tests
pytest tests/test_error_paths.py -v

# Verbose with short tracebacks
pytest tests/ -v --tb=short
```

[![PyPI version](https://badge.fury.io/py/indexed-zstd.svg)](https://badge.fury.io/py/indexed-zstd)
[![Conda (channel only)](https://img.shields.io/conda/vn/conda-forge/indexed_zstd?label=conda)](https://anaconda.org/conda-forge/indexed_zstd)
[![Python Version](https://img.shields.io/pypi/pyversions/indexed_zstd)](https://pypi.org/project/indexed-zstd/)
[![PyPI Platforms](https://img.shields.io/badge/pypi-linux%20%7C%20macOS%20%7C%20windows-brightgreen)](https://pypi.org/project/indexed-zstd/)
[![Downloads](https://pepy.tech/badge/indexed-zstd/month)](https://pepy.tech/project/indexed-zstd)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/indexed-zstd?period=total&units=INTERNATIONAL_SYSTEM&left_color=GRAY&right_color=BLUE&left_text=downloads)](https://pepy.tech/projects/indexed-zstd)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](http://opensource.org/licenses/MIT)
[![Build Status](https://github.com/martinellimarco/indexed_zstd/workflows/tests/badge.svg)](https://github.com/martinellimarco/indexed_zstd/actions)
![C++17](https://img.shields.io/badge/C++-17-blue.svg)
[![AUR version](https://img.shields.io/aur/version/python-indexed-zstd)](https://aur.archlinux.org/packages/python-indexed-zstd/)

# indexed_zstd

A Python module for fast random access to [zstd](https://github.com/facebook/zstd)-compressed files without full decompression.

`IndexedZstdFile` implements Python's `io.BufferedReader` interface, so it works as a drop-in replacement for `open()` on `.zst` files — supporting `seek()`, `read()`, `readline()`, `tell()`, and context managers.

Under the hood it uses [libzstd-seek](https://github.com/martinellimarco/libzstd-seek) to build a jump table of frame boundaries, enabling O(1) seeking to any position in multi-frame archives.

> This project is based on [indexed_bzip2](https://github.com/mxmlnkn/indexed_bzip2) to target zstd specifically.

## How it works

Zstd files can contain multiple independently compressed frames. `indexed_zstd` scans frame boundaries on first access and builds an in-memory jump table that maps uncompressed offsets to compressed positions. When you `seek()`, only the relevant frame is decompressed.

Seeking *within* a frame is emulated by decompressing from the frame start, so the more frames your archive has, the faster random access will be.

To create multi-frame archives use [t2sz](https://github.com/martinellimarco/t2sz/) or the `--stream-size` option of the `zstd` CLI.

## Installation

### pip (recommended)

Pre-built wheels are available for Linux, macOS, and Windows:

```bash
pip install indexed-zstd
```

If no wheel is available for your platform, pip will build from source automatically.
In that case you need `zstd` development headers and a C++17 compiler:

```bash
# Debian/Ubuntu
sudo apt install libzstd-dev

# macOS
brew install zstd
```

### conda

```bash
conda install -c conda-forge indexed_zstd
```

### Arch Linux (AUR)

```bash
yay -S python-indexed-zstd
```

## Usage

### Basic random access

```python
from indexed_zstd import IndexedZstdFile

with IndexedZstdFile("example.zst") as f:
    f.seek(1024)
    data = f.read(256)
    print(f.tell())       # 1280
    print(f.seekable())   # True
```

### Reading line by line

```python
from indexed_zstd import IndexedZstdFile

with IndexedZstdFile("logfile.zst") as f:
    for line in f:
        if b"ERROR" in line:
            print(line.decode())
```

### Opening by file descriptor

```python
import os
from indexed_zstd import IndexedZstdFile

fd = os.open("example.zst", os.O_RDONLY)
with IndexedZstdFile(fd) as f:
    data = f.read()
```

### Inspecting frame structure

```python
from indexed_zstd import IndexedZstdFile

with IndexedZstdFile("example.zst") as f:
    print(f.size())              # uncompressed size in bytes
    print(f.number_of_frames())  # number of zstd frames
    print(f.is_multiframe())     # True if more than one frame
    print(f.block_offsets())     # {compressed_offset: uncompressed_offset, ...}
```

## API reference

`IndexedZstdFile` inherits from `io.BufferedReader` and adds:

| Method                       | Description                                                               |
|------------------------------|---------------------------------------------------------------------------|
| `size()`                     | Uncompressed file size in bytes                                           |
| `number_of_frames()`         | Total number of zstd frames                                               |
| `is_multiframe()`            | `True` if the file contains more than one frame                           |
| `block_offsets()`            | `dict` mapping compressed offsets to uncompressed offsets                 |
| `available_block_offsets()`  | Same as `block_offsets()`, but returns only the offsets discovered so far |
| `set_block_offsets(offsets)` | Manually set the jump table from a `dict`                                 |
| `block_offsets_complete()`   | `True` if the jump table has been fully built                             |
| `tell_compressed()`          | Current position in the compressed stream                                 |

All standard `io.BufferedReader` methods are available: `read()`, `readline()`, `readlines()`, `seek()`, `tell()`, `seekable()`, `readable()`, `fileno()`, `close()`, etc.

## Testing

The test suite requires [gen_seekable](https://github.com/martinellimarco/libzstd-seek) (built from the bundled submodule) and covers API, error paths, round-trip, reference, and heavy-data scenarios.

```bash
# Build gen_seekable from the submodule
cmake -S indexed_zstd/libzstd-seek -B indexed_zstd/libzstd-seek/build -DBUILD_TESTS=ON
cmake --build indexed_zstd/libzstd-seek/build --target gen_seekable

# Add it to PATH
export PATH="$PWD/indexed_zstd/libzstd-seek/build/tests:$PATH"

# Run the standard test suite (111 tests)
python -m pytest tests/ -v -m "not heavy and not reference"
```

Additional test categories (optional):

| Marker      | Requirements       | Description                               |
|-------------|--------------------|-------------------------------------------|
| `reference` | `zstd` CLI in PATH | Compares library output against `zstd -d` |
| `heavy`     | `t2sz` in PATH     | Large realistic data tests (10-50 MB)     |

```bash
# Run everything including reference and heavy tests
python -m pytest tests/ -v
```

## Building from source

Requires a C++17 compiler, Cython, and platform-specific zstd libraries.

```bash
# Clone with submodules (includes libzstd-seek)
git clone --recurse-submodules https://github.com/martinellimarco/indexed_zstd.git
cd indexed_zstd
pip install cython setuptools
```

### Linux

```bash
sudo apt install libzstd-dev    # Debian/Ubuntu
pip install .
```

### macOS

```bash
brew install zstd
pip install .
```

### Windows

Requires [Visual Studio Build Tools](https://visualstudio.microsoft.com/it/downloads/) with the C++ workload.

```powershell
python libzstd/_get_zstd.py    # downloads zstd headers and DLL
pip install .
```

## License

[MIT](LICENSE)

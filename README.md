[![PyPI version](https://badge.fury.io/py/indexed-zstd.svg)](https://badge.fury.io/py/indexed-zstd)
[![Conda (channel only)](https://img.shields.io/conda/vn/conda-forge/indexed_zstd?label=conda)](https://anaconda.org/conda-forge/indexed_zstd)
[![Python Version](https://img.shields.io/pypi/pyversions/indexed_zstd)](https://pypi.org/project/indexed-zstd/)
[![PyPI Platforms](https://img.shields.io/badge/pypi-linux%20%7C%20macOSs%20%7C%20windows-brightgreen)](https://pypi.org/project/indexed-zstd/)
[![Downloads](https://pepy.tech/badge/indexed-zstd/month)](https://pepy.tech/project/indexed-zstd)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](http://opensource.org/licenses/MIT)
[![Build Status](https://github.com/martinellimarco/indexed_zstd/workflows/tests/badge.svg)](https://github.com/martinellimarco/indexed_zstd/actions)
![C++17](https://img.shields.io/badge/C++-17-blue.svg)
[![AUR version](https://img.shields.io/aur/version/python-indexed-zstd)](https://aur.archlinux.org/packages/python-indexed-zstd/)

# indexed_zstd

This module provides an IndexedZstdFile class, which can be used to seek inside zstd files without having to decompress them first.

It's shamelessy based on [indexed_bzip2](https://github.com/mxmlnkn/indexed_bzip2), which was refactored to support [zstd](https://github.com/facebook/zstd) instead of bzip2 using [libzstd-seek](https://github.com/martinellimarco/libzstd-seek).

Kudos to the author for its work.

Seeking inside a block is only emulated, so IndexedZstdFile will only speed up seeking when there are more than one block.

To create multi-block archives you may use [t2sz](https://github.com/martinellimarco/t2sz/).


# Usage

## Example 1

```python3
from indexed_zstd import IndexedZstdFile

file = IndexedZstdFile( "example.zst" )

# You can now use it like a normal file
file.seek( 123 )
data = file.read( 100 )
```

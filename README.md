# indexed_zstd


This module provides an IndexedZstdFile class, which can be used to seek inside zstd files without having to decompress them first.

It's shamelessy based on [indexed_bzip2](https://github.com/mxmlnkn/indexed_bzip2), which was refactored to support [zstd](https://github.com/facebook/zstd) instead of bzip2 using [libzstd-seek](https://github.com/martinellimarco/libzstd-seek).

Kudos to the author for its work.

Seeking inside a block is only emulated, so IndexedZstdFile will only speed up seeking when there are more than one block, which sadly requires a bit of care in zstd.


# Usage

## Example 1

```python3
from indexed_zstd import IndexedZstdFile

file = IndexedZstdFile( "example.zst" )

# You can now use it like a normal file
file.seek( 123 )
data = file.read( 100 )
```

from libc.stdlib cimport malloc, free
from libc.stdio cimport SEEK_SET
from libcpp.string cimport string
from libcpp.map cimport map
from libcpp cimport bool
from cpython.buffer cimport PyObject_GetBuffer, PyBuffer_Release, PyBUF_ANY_CONTIGUOUS, PyBUF_SIMPLE

import io
import os
import sys

ctypedef (unsigned long long int) size_t
ctypedef (long long int) lli


cdef extern from "Python.h":
    char * PyString_AsString(object)
    object PyString_FromStringAndSize(char*, int)

cdef extern from "ZSTDReader.hpp":
    cppclass ZSTDReader:
        ZSTDReader(string) except +
        ZSTDReader(int) except +
        bool eof() except +
        int fileno() except +
        bool seekable() except +
        void close() except +
        bool closed() except +
        size_t seek(lli, int) except +
        size_t tell() except +
        size_t tellCompressed() except +
        size_t size() except +
        long long read(int, char*, size_t) except +
        bool blockOffsetsComplete() except +
        map[size_t, size_t] blockOffsets() except +
        map[size_t, size_t] availableBlockOffsets() except +
        void setBlockOffsets(map[size_t, size_t]) except +
        size_t numberOfFrames() except +
        bool isMultiframe() except +

cdef class _IndexedZstdFile():
    cdef ZSTDReader* zstdreader

    def __cinit__(self, fileNameOrDescriptor):
        if isinstance(fileNameOrDescriptor, basestring):
            self.zstdreader = new ZSTDReader(<string>fileNameOrDescriptor.encode())
        else:
            self.zstdreader = new ZSTDReader(<int>fileNameOrDescriptor)

    def __dealloc__(self):
        del self.zstdreader

    def close(self):
        self.zstdreader.close()

    def closed(self):
        return self.zstdreader.closed()

    def fileno(self):
        return self.zstdreader.fileno()

    def seekable(self):
        return self.zstdreader.seekable()

    def readinto(self, bytes_like):
        bytes_count = 0

        cdef Py_buffer buffer
        PyObject_GetBuffer(bytes_like, &buffer, PyBUF_SIMPLE | PyBUF_ANY_CONTIGUOUS)
        try:
            bytes_count = self.zstdreader.read(-1, <char*>buffer.buf, len(bytes_like))
        finally:
            PyBuffer_Release(&buffer)

        return bytes_count

    def seek(self, offset, whence = io.SEEK_SET):
        return self.zstdreader.seek(offset, whence)

    def tell(self):
        return self.zstdreader.tell()

    def size(self):
        return self.zstdreader.size()

    def tell_compressed(self):
        return self.zstdreader.tellCompressed()

    def block_offsets_complete(self):
        return self.zstdreader.blockOffsetsComplete()

    def block_offsets(self):
        return <dict>self.zstdreader.blockOffsets()

    def available_block_offsets(self):
        return <dict>self.zstdreader.availableBlockOffsets()

    def set_block_offsets(self, offsets):
        return self.zstdreader.setBlockOffsets(offsets)

    def number_of_frames(self):
        return self.zstdreader.numberOfFrames()

    def is_multiframe(self):
        return self.zstdreader.isMultiframe()


# Extra class because cdefs are not visible from outside but cdef class can't inherit from io.BufferedIOBase

class IndexedZstdFileRaw(io.RawIOBase):
    """Raw I/O adapter that bridges the Cython layer to Python's io hierarchy.

    This is an implementation detail — use IndexedZstdFile instead.
    """

    def __init__(self, filename):
        self.zstdreader = _IndexedZstdFile(filename)
        self.name = filename
        self.mode = 'rb'

        self.readinto = self.zstdreader.readinto
        self.seek     = self.zstdreader.seek
        self.tell     = self.zstdreader.tell
        self.fileno   = self.zstdreader.fileno
        self.seekable = self.zstdreader.seekable

        # IOBase provides sane default implementations for read, readline, readlines, readall, ...

    def close(self):
        if self.closed:
            return
        super().close()
        if hasattr(self, 'zstdreader'):
            self.zstdreader.close()

    def readable(self):
        return True

class IndexedZstdFile(io.BufferedReader):
    """Buffered reader for random access to zstd-compressed files.

    Implements the full ``io.BufferedReader`` interface (``read()``,
    ``readline()``, ``seek()``, ``tell()``, context manager, etc.) and
    adds methods specific to zstd multi-frame archives.

    The file is memory-mapped and a jump table of frame boundaries is
    built lazily on first access, enabling O(1) seeking to any frame.

    Args:
        filename: Path to a zstd-compressed file (str or bytes),
            or an open file descriptor (int).
    """

    def __init__(self, filename):
        fobj = IndexedZstdFileRaw(filename)
        self.zstdreader = fobj.zstdreader

        # Most of the calls like close, seekable, name, mode ... are forwarded to the given raw object
        # by BufferedReader or more specifically _BufferedIOMixin
        super().__init__(fobj, buffer_size=1024**2)

    # These methods delegate through self, which keeps the IndexedZstdFile
    # (and therefore the BufferedReader → RawIOBase → C context chain) alive
    # for the duration of the call.  The previous implementation stored bound
    # methods of _IndexedZstdFile as instance attributes, which bypassed self
    # and allowed CPython to garbage-collect the IndexedZstdFile (triggering
    # BufferedReader.__del__ → close()) before the method body executed.

    def tell_compressed(self):
        """Return the current position in the compressed stream.

        Returns:
            int: Byte offset in the compressed file.
        """
        return self.zstdreader.tell_compressed()

    def block_offsets(self):
        """Build the complete jump table and return all frame offsets.

        Triggers a full scan of the compressed data on first call
        (no-op if already initialized).

        Returns:
            dict: ``{compressed_offset: uncompressed_offset, ...}`` for
            every frame boundary.  The last entry is a sentinel whose
            values are the total compressed and uncompressed sizes.
        """
        return self.zstdreader.block_offsets()

    def set_block_offsets(self, offsets):
        """Manually set the jump table from a dict.

        Records must be in monotonically increasing order of both key
        and value.  Do not mix with automatic jump table initialization
        (i.e. do not call ``block_offsets()`` or ``size()`` before this).

        Args:
            offsets (dict): ``{compressed_offset: uncompressed_offset, ...}``
        """
        return self.zstdreader.set_block_offsets(offsets)

    def block_offsets_complete(self):
        """Check whether the jump table has been fully built.

        Returns:
            bool: True if the jump table is fully initialized.
        """
        return self.zstdreader.block_offsets_complete()

    def available_block_offsets(self):
        """Return the frame offsets discovered so far.

        Unlike ``block_offsets()``, this does not trigger further scanning.

        Returns:
            dict: ``{compressed_offset: uncompressed_offset, ...}``
        """
        return self.zstdreader.available_block_offsets()

    def size(self):
        """Return the total uncompressed size of the file.

        Triggers full jump table initialization on first call.

        Returns:
            int: Uncompressed size in bytes.
        """
        return self.zstdreader.size()

    def number_of_frames(self):
        """Return the total number of zstd frames (data and skippable).

        Scans the compressed data from the beginning on each call;
        the result is not cached.

        Returns:
            int: Number of frames.
        """
        return self.zstdreader.number_of_frames()

    def is_multiframe(self):
        """Check whether the file contains more than one frame.

        More efficient than ``number_of_frames() > 1`` because it
        short-circuits after finding two frames.

        Returns:
            bool: True if the file has at least two frames.
        """
        return self.zstdreader.is_multiframe()

__version__ = '1.7.0'

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
        int read(int, char*, size_t) except +
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

    def seek(self, offset, whence):
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
        self.zstdreader.close()

    def readable(self):
        return True

class IndexedZstdFile(io.BufferedReader):
    def __init__(self, filename):
        fobj = IndexedZstdFileRaw(filename)
        self.zstdreader = fobj.zstdreader

        self.tell_compressed         = self.zstdreader.tell_compressed
        self.block_offsets           = self.zstdreader.block_offsets
        self.set_block_offsets       = self.zstdreader.set_block_offsets
        self.block_offsets_complete  = self.zstdreader.block_offsets_complete
        self.available_block_offsets = self.zstdreader.available_block_offsets
        self.size                    = self.zstdreader.size
        self.number_of_frames        = self.zstdreader.number_of_frames
        self.is_multiframe           = self.zstdreader.is_multiframe

        # Most of the calls like close, seekable, name, mode ... are forwarded to the given raw object
        # by BufferedReader or more specifically _BufferedIOMixin
        super().__init__(fobj, buffer_size=1024**2)

__version__ = '1.1.3'

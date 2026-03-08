#pragma once

#include <algorithm>
#include <cassert>
#include <cstring>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <utility>
#include <vector>

#include "libzstd-seek/zstd-seek.h"
#include "FileReader.hpp"

/**
 * @brief C++ wrapper around libzstd-seek for seekable zstd decompression.
 *
 * Provides random read access to zstd-compressed data by building a jump
 * table of frame boundaries.  The jump table is constructed lazily: it is
 * populated on the first call to blockOffsets() or size(), or incrementally
 * by seek() and read() as needed.
 *
 * All constructors use the @c *WithoutJumpTable variants of the C API,
 * deferring the scan until data is actually requested.
 *
 * Once closed, all methods return zero or false (except fileno(), which
 * throws).  The Python layer guards against double-close.
 */
class ZSTDReader :
    public FileReader
{
public:
    /**
     * @brief Open a zstd file by path.
     *
     * The file is memory-mapped internally.  The mapping is released
     * when close() is called.
     *
     * @param filePath  Path to a zstd-compressed file.
     * @throws std::invalid_argument if the file cannot be opened, cannot
     *         be memory-mapped, or does not start with a valid zstd frame.
     */
    explicit
    ZSTDReader( std::string filePath )
    {
        sctx = ZSTDSeek_createFromFileWithoutJumpTable(filePath.c_str());
        if(!sctx){
            throw std::invalid_argument( "Unable to create a ZSTDSeekContext" );
        }
        m_closed = false;
    }

    /**
     * @brief Open a zstd file by file descriptor.
     *
     * The descriptor is used with mmap.  Ownership is @b not transferred:
     * the caller must close the descriptor after calling close() on this
     * reader.
     *
     * @param fileDescriptor  Open file descriptor for a zstd-compressed file.
     * @throws std::invalid_argument if the descriptor cannot be memory-mapped
     *         or does not contain a valid zstd stream.
     */
    explicit
    ZSTDReader( int fileDescriptor )
    {
        sctx = ZSTDSeek_createFromFileDescriptorWithoutJumpTable(fileDescriptor);
        if(!sctx){
            throw std::invalid_argument( "Unable to create a ZSTDSeekContext" );
        }
        m_closed = false;
    }

    /**
     * @brief Open a zstd stream from an in-memory buffer.
     *
     * The buffer must remain valid and unmodified for the lifetime of
     * this reader.  Ownership is @b not transferred.
     *
     * @param zstdData  Pointer to the compressed data.
     * @param size      Size of the buffer in bytes.
     * @throws std::invalid_argument if the data is not a valid zstd stream.
     */
    ZSTDReader( const char*  zstdData,
               const size_t size )
    {
        sctx = ZSTDSeek_createWithoutJumpTable((void*)zstdData, size);
        if(!sctx){
            throw std::invalid_argument( "Unable to create a ZSTDSeekContext" );
        }
        m_closed = false;
    }

    /**
     * @brief Return the file descriptor associated with the compressed stream.
     *
     * Only meaningful for contexts created from a file path or file descriptor.
     * For buffer-based contexts this always throws.
     *
     * @return File descriptor number.
     * @throws std::invalid_argument if the reader is closed or no descriptor
     *         is available.
     */
    int
    fileno() const override
    {
        if(m_closed) {
            throw std::invalid_argument( "The file is not open!" );
        }
        int fileno = ZSTDSeek_fileno(sctx);
        if(fileno < 0){
            throw std::invalid_argument( "fileno not available" );
        }
        return fileno;
    }

    /** @return Always @c true — zstd readers support seeking. */
    bool
    seekable() const override
    {
        return true;
    }

    /**
     * @brief Release all resources (decompression context, memory mapping).
     *
     * After close(), all other methods return zero or false.
     */
    void
    close() override
    {
        ZSTDSeek_free(sctx);
        m_closed = true;
    }

    /** @return @c true if close() has been called. */
    bool
    closed() const override
    {
        return m_closed;
    }

    /**
     * @return @c true if the reader is closed or the current position
     *         equals the uncompressed size.
     */
    bool
    eof() const override
    {
        if(m_closed){
            return true;
        }
        return size() == tell();
    }

    /**
     * @brief Check whether the jump table has been fully built.
     *
     * @return @c true if the jump table is fully initialized.
     * @see blockOffsets() to trigger a full build.
     */
    bool
    blockOffsetsComplete() const
    {
        if(m_closed){
            return false;
        }
        return ZSTDSeek_jumpTableIsInitialized(sctx);
    }

    /**
     * @brief Build the complete jump table and return all frame offsets.
     *
     * Triggers a full scan of the compressed data on first call (no-op if
     * already initialized).
     *
     * @return Map of {compressed_offset: uncompressed_offset} for every
     *         frame boundary.  The last entry is a sentinel whose values
     *         are the total compressed and uncompressed sizes.
     */
    std::map<size_t, size_t>
    blockOffsets()
    {
        if(!m_closed){
            ZSTDSeek_initializeJumpTable(sctx);
        }
        return availableBlockOffsets();
    }

    /**
     * @brief Return the frame offsets discovered so far.
     *
     * Unlike blockOffsets(), this does @b not trigger further scanning.
     *
     * @return Map of {compressed_offset: uncompressed_offset}.
     */
    std::map<size_t, size_t>
    availableBlockOffsets()
    {
        std::map<size_t, size_t> m_blockToDataOffsets;
        if(!m_closed){
            ZSTDSeek_JumpTable *jt = ZSTDSeek_getJumpTableOfContext(sctx);
            for(uint32_t i = 0; i < jt->length; i++){
                ZSTDSeek_JumpTableRecord r = jt->records[i];
                m_blockToDataOffsets.insert( { r.compressedPos, r.uncompressedPos } );
            }
        }
        return m_blockToDataOffsets;
    }

    /**
     * @brief Manually add entries to the jump table.
     *
     * Records must be in monotonically increasing order of both key and
     * value.  Do not mix with automatic jump table initialization.
     *
     * @param offsets  Map of {compressed_offset: uncompressed_offset} to add.
     */
    void
    setBlockOffsets( std::map<size_t, size_t> offsets )
    {
        if(!m_closed){
            ZSTDSeek_JumpTable *jt = ZSTDSeek_getJumpTableOfContext(sctx);
            for (const auto& kv : offsets) {
                ZSTDSeek_addJumpTableRecord(jt, kv.first, kv.second);
            }
        }
    }

    /**
     * @brief Return the current position in the uncompressed stream.
     * @return Byte offset, or 0 if closed.
     */
    size_t
    tell() const override
    {
        if(m_closed){
            return 0;
        }
        return  ZSTDSeek_tell(sctx);
    }

    /**
     * @brief Return the current position in the compressed stream.
     * @return Byte offset, or 0 if closed.
     */
    size_t
    tellCompressed() const
    {
        if(m_closed){
            return 0;
        }
        return ZSTDSeek_compressedTell(sctx);
    }

    /**
     * @brief Return the total uncompressed size of the stream.
     *
     * Triggers full jump table initialization on first call.
     *
     * @return Uncompressed size in bytes, or 0 if closed.
     */
    size_t
    size() const override
    {
        if(m_closed){
            return 0;
        }
        return ZSTDSeek_uncompressedFileSize(sctx);
    }

    /**
     * @brief Seek to a position in the uncompressed stream.
     *
     * Supports @c SEEK_SET, @c SEEK_CUR, and @c SEEK_END origins.
     * On error (e.g. negative position, beyond EOF) the position is
     * unchanged.
     *
     * @param offset  Byte offset (interpretation depends on @p origin).
     * @param origin  One of @c SEEK_SET, @c SEEK_CUR, or @c SEEK_END.
     * @return New absolute position in the uncompressed stream.
     */
    size_t
    seek( long long int offset,
          int           origin = SEEK_SET ) override
    {
        if(m_closed){
            return 0;
        }
        ZSTDSeek_seek(sctx, offset, origin);
        return ZSTDSeek_tell(sctx);
    }

    /**
     * @brief Read decompressed data from the current position.
     *
     * Reads up to @p nBytesToRead bytes into @p outputBuffer and advances
     * the position accordingly.
     *
     * @param outputFileDescriptor  Unused (kept for FileReader interface
     *                              compatibility).
     * @param outputBuffer          Destination buffer (must be at least
     *                              @p nBytesToRead bytes).
     * @param nBytesToRead          Maximum number of bytes to read.
     * @return Number of bytes actually read (0 at EOF or if closed),
     *         or negative (@c ZSTDSEEK_ERR_READ) on decompression error.
     */
    int64_t
    read( const int    outputFileDescriptor = -1,
          char* const  outputBuffer = nullptr,
          const size_t nBytesToRead = std::numeric_limits<size_t>::max() )
    {
        if(m_closed){
            return 0;
        }
        return ZSTDSeek_read(outputBuffer, nBytesToRead, sctx);
    }

    /**
     * @brief Return the total number of zstd frames (data + skippable).
     *
     * Scans the compressed data from the beginning on each call;
     * the result is not cached.
     *
     * @return Number of frames, or 0 if closed.
     */
    size_t
    numberOfFrames()
    {
        if(m_closed){
            return 0;
        }
        return ZSTDSeek_getNumberOfFrames(sctx);
    }

    /**
     * @brief Check whether the stream contains more than one frame.
     *
     * More efficient than <tt>numberOfFrames() > 1</tt> because it
     * short-circuits after finding two frames.
     *
     * @return @c true if the stream has at least two frames.
     */
    bool
    isMultiframe()
    {
        if(m_closed){
            return 0;
        }
        return ZSTDSeek_isMultiframe(sctx)!=0;
    }

private:
    ZSTDSeek_Context *sctx;
    bool m_closed;
};

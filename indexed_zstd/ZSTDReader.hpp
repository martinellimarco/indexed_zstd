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

class ZSTDReader :
    public FileReader
{
public:
    explicit
    ZSTDReader( std::string filePath )
    {
        sctx = ZSTDSeek_createFromFile(filePath.c_str());
        if(!sctx){
            throw std::invalid_argument( "Unable to create a ZSTDSeekContext" );
        }
        buildBlocToDataOffsetsMap();
        m_closed = false;
    }

    explicit
    ZSTDReader( int fileDescriptor ) //FIXME is it needed?
    {
        m_closed = true;
    }

    ZSTDReader( const char*  zstdData,
               const size_t size )
    {
        sctx = ZSTDSeek_create((void*)zstdData, size);
        if(!sctx){
            throw std::invalid_argument( "Unable to create a ZSTDSeekContext" );
        }
        buildBlocToDataOffsetsMap();
        m_closed = false;
    }

    int
    fileno() const override
    {
        throw std::invalid_argument( "Not Implemented" ); //FIXME is it needed?
    }

    bool
    seekable() const override
    {
        return true;
    }

    void
    close() override
    {
        ZSTDSeek_free(sctx);
        m_closed = true;
    }

    bool
    closed() const override
    {
        return m_closed;
    }

    bool
    eof() const override
    {
        if(m_closed){
            return true;
        }
        return m_fileSize == (size_t)ZSTDSeek_tell(sctx);
    }

    bool
    blockOffsetsComplete() const
    {
        return true;
    }

    /**
     * @return vectors of block data: offset in file, offset in decoded data
     *         (cumulative size of all prior decoded blocks).
     */
    std::map<size_t, size_t>
    blockOffsets()
    {
        return m_blockToDataOffsets;
    }

    /**
     * Same as @ref blockOffsets
     * @return vectors of block data: offset in file, offset in decoded data
     *         (cumulative size of all prior decoded blocks).
     */
    std::map<size_t, size_t>
    availableBlockOffsets()
    {
        return m_blockToDataOffsets;
    }

    void
    setBlockOffsets( std::map<size_t, size_t> offsets )  //FIXME is it needed?
    {
        throw std::invalid_argument( "Not Implemented" );
    }

    size_t
    tell() const override
    {
        return  ZSTDSeek_tell(sctx);
    }

    /**
     * @return number of processed bits of compressed zstd input file stream
     */
    size_t
    tellCompressed() const //FIXME is it needed?
    {
        return 0;
    }

    size_t
    size() const override
    {
        return m_fileSize;
    }

    size_t
    seek( long long int offset,
          int           origin = SEEK_SET )
    {
        ZSTDSeek_seek(sctx, offset, origin);
        return ZSTDSeek_tell(sctx);
    }

    /**
     * @param[out] outputBuffer should at least be large enough to hold @p nBytesToRead bytes
     * @return number of bytes written
     */
    int
    read( const int    outputFileDescriptor = -1,
          char* const  outputBuffer = nullptr,
          const size_t nBytesToRead = std::numeric_limits<size_t>::max() )
    {
        return ZSTDSeek_read(outputBuffer, nBytesToRead, sctx);
    }

private:
    ZSTDSeek_Context *sctx;
    bool m_closed;
    size_t m_fileSize;

    std::map<size_t, size_t> m_blockToDataOffsets;

private:
    void buildBlocToDataOffsetsMap()
    {
        ZSTDSeek_JumpTable *jt = ZSTDSeek_getJumpTableOfContext(sctx);
        for(uint32_t i = 0; i < jt->length; i++){
            ZSTDSeek_JumpTableRecord r = jt->records[i];
            m_blockToDataOffsets.insert( { r.compressedPos, r.uncompressedPos } );
        }
        m_fileSize = jt->uncompressedFileSize;
    }
};

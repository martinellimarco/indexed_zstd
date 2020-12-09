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
        sctx = ZSTDSeek_createFromFileWithoutJumpTable(filePath.c_str());
        if(!sctx){
            throw std::invalid_argument( "Unable to create a ZSTDSeekContext" );
        }
        m_closed = false;
    }

    explicit
    ZSTDReader( int fileDescriptor )
    {
        sctx = ZSTDSeek_createFromFileDescriptorWithoutJumpTable(fileDescriptor);
        if(!sctx){
            throw std::invalid_argument( "Unable to create a ZSTDSeekContext" );
        }
        m_closed = false;
    }

    ZSTDReader( const char*  zstdData,
               const size_t size )
    {
        sctx = ZSTDSeek_createWithoutJumpTable((void*)zstdData, size);
        if(!sctx){
            throw std::invalid_argument( "Unable to create a ZSTDSeekContext" );
        }
        m_closed = false;
    }

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
        return size() == tell();
    }

    bool
    blockOffsetsComplete() const
    {
        if(m_closed){
            return false;
        }
        return ZSTDSeek_jumpTableIsInitialized(sctx) > 0;
    }

    /**
     * @return vectors of block data: offset in file, offset in decoded data
     *         (cumulative size of all prior decoded blocks).
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
     * Same as @ref blockOffsets
     * @return vectors of block data: offset in file, offset in decoded data
     *         (cumulative size of all prior decoded blocks).
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

    size_t
    tell() const override
    {
        if(m_closed){
            return 0;
        }
        return  ZSTDSeek_tell(sctx);
    }

    /**
     * @return number of processed bits of compressed zstd input file stream
     */
    size_t
    tellCompressed() const
    {
        if(m_closed){
            return 0;
        }
        return ZSTDSeek_compressedTell(sctx);
    }

    size_t
    size() const override
    {
        if(m_closed){
            return 0;
        }
        return ZSTDSeek_uncompressedFileSize(sctx);
    }

    size_t
    seek( long long int offset,
          int           origin = SEEK_SET )
    {
        if(m_closed){
            return 0;
        }
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
        if(m_closed){
            return 0;
        }
        return ZSTDSeek_read(outputBuffer, nBytesToRead, sctx);
    }

    size_t
    numberOfFrames()
    {
        if(m_closed){
            return 0;
        }
        return ZSTDSeek_getNumberOfFrames(sctx);
    }

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

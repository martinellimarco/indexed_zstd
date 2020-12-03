from indexed_zstd import IndexedZstdFile
file = IndexedZstdFile( "test.zst" )

print("Block offset completed?: ", file.block_offsets_complete())

print(file.block_offsets())

print("Block offset completed?: ", file.block_offsets_complete())

print("Test reading letters from A to Z")
a = file.read(26)
for i in range(len(a)):
    print(chr(a[i]), end=''),
print("")

print("Tell is 26: ", file.tell())
print("Compressed tell is 78: ", file.tell_compressed())

print("Seeking back to 15")

file.seek(15)
print("Tell is 15?: ", file.tell())
print("Compressed tell is 49: ", file.tell_compressed())

print("Filesize is 26? ", file.size())

print("Compressed tell is 49: ", file.tell_compressed())
print("Reading a byte after EOF")
file.read(1)
print("Compressed tell is 78: ", file.tell_compressed())


print("Test reading again, letters from P to Z")
a = file.read(16)
for i in range(len(a)):
    print(chr(a[i]), end=''),
print("")

print("Testing set_block_offsets")

file2 = IndexedZstdFile( "test.zst" )
print("Block offset completed?: ", file2.block_offsets_complete())
file2.set_block_offsets(file.block_offsets())

print(file2.block_offsets())

print("Block offset completed?: ", file2.block_offsets_complete())

file.close()
file2.close()
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

print("tell is 26: ", file.tell())
print("compressed tell is 78: ", file.tell_compressed())

print("seeking back to 15")

file.seek(15)
print("tell is 15?: ", file.tell())
print("compressed tell is 49: ", file.tell_compressed())

print("filesize is 26? ", file.size())

print("compressed tell is 49: ", file.tell_compressed())
print("reading a byte after eof")
file.read(1)
print("compressed tell is 78: ", file.tell_compressed())


print("Test reading again, letters from P to Z")
a = file.read(16)
for i in range(len(a)):
    print(chr(a[i]), end=''),
print("")

file.close()

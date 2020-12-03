from indexed_zstd import IndexedZstdFile
file = IndexedZstdFile( "test.zst" )

print("Test reading letters from A to Z")
a = file.read(26)
for i in range(len(a)):
	print(chr(a[i]), end=''),
print("")

print("tell: ", file.tell())

print("seeking back to 15")

file.seek(15)
print("tell: ", file.tell())

print("filesize is 26? ", file.size())

print("Test reading again, letters from P to Z")
a = file.read(16)
for i in range(len(a)):
        print(chr(a[i]), end=''),
print("")

file.close()

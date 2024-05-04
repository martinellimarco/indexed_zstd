"""download the latest zstd release for win64"""
import io
import json
import pathlib
import platform
import urllib.request
import zipfile

if platform.system() != "Windows":
    print("windows only")
    raise SystemExit(1)


ZSTD_RELEASE_LATEST = "https://api.github.com/repos/facebook/zstd/releases/latest"

with urllib.request.urlopen(ZSTD_RELEASE_LATEST) as response:
    data = json.load(response)

for asset in data["assets"]:
    if "win64" in asset["name"]:
        break
else:
    print("no release asset found with 'win64' in filename")
    raise SystemExit(1)


with urllib.request.urlopen(asset["browser_download_url"]) as f:
    zip_data = f.read()


SCRIPT_DIR = pathlib.Path(__file__).parent
INCLUDE_DIR = SCRIPT_DIR.joinpath("include")
LIBRARY_DIR = SCRIPT_DIR.joinpath("lib")
INCLUDE_DIR.mkdir(exist_ok=True)
LIBRARY_DIR.mkdir(exist_ok=True)


with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
    files = zf.namelist()
    zstd_h = next((f for f in files if "include/zstd.h" in f), None)
    libzstd_dll = next((f for f in files if "dll/libzstd.dll" in f), None)
    libzstd_lib = next((f for f in files if "dll/libzstd.lib" in f), None)
    libzstd_dll_a = next((f for f in files if "dll/libzstd.dll.a" in f), None)

    INCLUDE_DIR.joinpath("zstd.h").write_bytes(zf.read(zstd_h))
    LIBRARY_DIR.joinpath("libzstd.dll").write_bytes(zf.read(libzstd_dll))
    try:
        _libzstd_lib = zf.read(libzstd_lib)
    except KeyError:
        _libzstd_lib = zf.read(libzstd_dll_a)
    # this renames libzstd.dll.a to libzstd.lib for setuptools to work
    LIBRARY_DIR.joinpath("libzstd.lib").write_bytes(_libzstd_lib)


print("success")

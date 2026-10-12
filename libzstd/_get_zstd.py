"""download the latest zstd release for win64, or build it from source on ARM64"""
import io
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sysconfig
import tarfile
import tempfile
import urllib.request
import zipfile

if platform.system() != "Windows":
    print("windows only")
    raise SystemExit(1)

# zstd releases have no ARM64 binaries, there a static library is built from the sources (needs CMake).
# Check the interpreter, not the machine: x64 Python also runs on ARM64 Windows.
ARM64 = sysconfig.get_platform() == "win-arm64"


ZSTD_RELEASE_LATEST = "https://api.github.com/repos/facebook/zstd/releases/latest"

# Use GITHUB_TOKEN if available (CI) to avoid API rate limits.
request = urllib.request.Request(ZSTD_RELEASE_LATEST)
token = os.environ.get("GITHUB_TOKEN")
if token:
    request.add_header("Authorization", f"token {token}")

with urllib.request.urlopen(request) as response:
    data = json.load(response)

wanted = ".tar.gz" if ARM64 else "-win64.zip"
for asset in data["assets"]:
    if asset["name"].endswith(wanted):
        break
else:
    print(f"no release asset found ending with '{wanted}'")
    raise SystemExit(1)


with urllib.request.urlopen(asset["browser_download_url"]) as f:
    archive = f.read()


SCRIPT_DIR = pathlib.Path(__file__).parent
INCLUDE_DIR = SCRIPT_DIR.joinpath("include")
LIBRARY_DIR = SCRIPT_DIR.joinpath("lib")
INCLUDE_DIR.mkdir(exist_ok=True)
LIBRARY_DIR.mkdir(exist_ok=True)


if ARM64:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
            if hasattr(tarfile, "data_filter"):
                tf.extraction_filter = tarfile.data_filter
            tf.extractall(tmp)
        source_dir = next(pathlib.Path(tmp).iterdir())
        build_dir = pathlib.Path(tmp, "build")

        subprocess.run(["cmake", "-S", source_dir / "build" / "cmake", "-B", build_dir, "-A", "ARM64",
                        "-DZSTD_BUILD_SHARED=OFF", "-DZSTD_BUILD_PROGRAMS=OFF", "-DZSTD_BUILD_TESTS=OFF"],
                       check=True)
        subprocess.run(["cmake", "--build", build_dir, "--config", "Release"], check=True)

        for name in ("zstd.h", "zstd_errors.h", "zdict.h"):
            shutil.copy(source_dir / "lib" / name, INCLUDE_DIR)
        # setuptools links libzstd.lib, here the static library: no DLL to ship
        shutil.copy(build_dir / "lib" / "Release" / "zstd_static.lib", LIBRARY_DIR / "libzstd.lib")

else:
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        files = zf.namelist()
        libzstd_dll = next((f for f in files if "dll/libzstd.dll" in f), None)
        libzstd_lib = next((f for f in files if "dll/libzstd.lib" in f), None)
        libzstd_dll_a = next((f for f in files if "dll/libzstd.dll.a" in f), None)

        # extract all headers (zstd.h, zstd_errors.h, zdict.h)
        for f in files:
            if "/include/" in f and f.endswith(".h"):
                name = pathlib.PurePosixPath(f).name
                INCLUDE_DIR.joinpath(name).write_bytes(zf.read(f))

        LIBRARY_DIR.joinpath("libzstd.dll").write_bytes(zf.read(libzstd_dll))
        try:
            _libzstd_lib = zf.read(libzstd_lib)
        except KeyError:
            _libzstd_lib = zf.read(libzstd_dll_a)
        # this renames libzstd.dll.a to libzstd.lib for setuptools to work
        LIBRARY_DIR.joinpath("libzstd.lib").write_bytes(_libzstd_lib)


print("success")

#!/usr/bin/env bash

# exit when any command fails
set -x -e

#git tag -n99 --sort -refname -l  v* | sed -r 's|^v[^ ]+ +|\n# |; s|^    ||' > CHANGELOG.md

rm -rf build dist *.egg-info __pycache__

# build the C library
python3 setup.py build_clib
# generate indexed_zstd.cpp from indexed_zstd.pyx
python3 setup.py build_ext --inplace --cython
python3 setup.py sdist

pip3 install --user dist/indexed_zstd-*.tar.gz

twine upload dist/indexed_zstd-*.tar.gz

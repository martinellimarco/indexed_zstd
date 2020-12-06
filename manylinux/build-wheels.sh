#!/usr/bin/env bash
set -e -x

PLATFORM=$1

yum -y update
yum -y install libzstd-devel
#yum -y install https://archives.fedoraproject.org/pub/archive/epel/6/x86_64/Packages/l/libzstd-devel-1.4.5-3.el6.x86_64.rpm

# Compile wheels
for PYBIN in /opt/python/*3*/bin; do
(
    buildFolder=$( mktemp -d )
    cd /project
    git worktree add "$buildFolder"
    cd -- "$buildFolder"
    git submodule update

    "${PYBIN}/pip" wheel .  # Compile C++ source code and make wheels
    for wheel in *.whl; do
        # Bundle external shared libraries into the wheels
        auditwheel repair "$wheel" --plat $PLATFORM -w /project/dist/
    done

    cd -
    git worktree remove --force "$buildFolder"
    rm -rf "$buildFolder"
)
done

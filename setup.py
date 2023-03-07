#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import platform
from setuptools import setup
from setuptools.extension import Extension
from Cython.Build import cythonize


if platform.system() == "Darwin":
    extra_compile_args = [ '-std=c++17', '-O3', '-DNDEBUG', '-stdlib=libc++', '-mmacosx-version-min=10.9']
    extra_link_args    = [ '-lzstd', '-stdlib=libc++', '-mmacosx-version-min=10.9' ]
    include_dirs       = [ '.' ]
    libraries          = [ 'm' ]
    library_dirs       = []

elif platform.system() == "Windows":
    _pkg_dir = os.path.dirname(__file__)
    LIBZSTD_DIR = os.getenv('LIBZSTD_DIR', os.path.join(_pkg_dir, 'libzstd'))

    extra_compile_args = [ '/std:c++17', '/O2', '/DNDEBUG' ]  # FIXME
    extra_link_args    = []
    include_dirs       = [ os.path.join(LIBZSTD_DIR, 'include') ]
    libraries          = [ 'libzstd' ]
    library_dirs       = [ os.path.join(LIBZSTD_DIR, 'lib') ]

else:
    extra_compile_args = [ '-std=c++17', '-O3', '-DNDEBUG' ]
    extra_link_args    = [ '-lzstd' ]
    include_dirs       = [ '.' ]
    libraries          = [ 'm' ]
    library_dirs       = []


extensions = [
    Extension(
        name               = 'indexed_zstd',
        sources            = [ 'indexed_zstd/indexed_zstd.pyx' ],
        language           = 'c++',
        include_dirs       = include_dirs,
        extra_compile_args = extra_compile_args,
        extra_link_args    = extra_link_args,
        libraries          = libraries,
        library_dirs       = library_dirs,
    ),
]
extensions = cythonize(extensions, compiler_directives={'language_level': '3'})

zstd_seek = ('zstd_zeek', {
    'sources': [ 'indexed_zstd/libzstd-seek/zstd-seek.c' ],
    'include_dirs': include_dirs
})


scriptPath = os.path.abspath( os.path.dirname( __file__ ) )
with open( os.path.join( scriptPath, 'README.md' ), encoding = 'utf-8' ) as file:
    readmeContents = file.read()


setup(
    name             = 'indexed_zstd',
    version          = '1.5.1',

    description      = 'Fast random access to zstd files',
    url              = 'https://github.com/martinellimarco/indexed_zstd',
    author           = 'Marco Martinelli with the help of Maximilian Knespel',
    license          = 'MIT',
    classifiers      = [ 'License :: OSI Approved :: MIT License',
                         'Development Status :: 5 - Production/Stable',
                         'Intended Audience :: Developers',
                         'Operating System :: MacOS',
                         'Operating System :: POSIX',
                         'Operating System :: Unix',
                         'Operating System :: Windows',
                         'Programming Language :: Python :: 3',
                         'Programming Language :: Python :: 3.6',
                         'Programming Language :: Python :: 3.7',
                         'Programming Language :: Python :: 3.8',
                         'Programming Language :: Python :: 3.9',
                         'Programming Language :: Python :: 3.10',
                         'Programming Language :: Python :: 3.11',
                         'Programming Language :: C++',
                         'Topic :: Software Development :: Libraries',
                         'Topic :: Software Development :: Libraries :: Python Modules',
                         'Topic :: System :: Archiving' ],

    long_description = readmeContents,
    long_description_content_type = 'text/markdown',

    py_modules       = [ 'indexed_zstd' ],
    libraries        = [ zstd_seek ],
    ext_modules      = extensions
)


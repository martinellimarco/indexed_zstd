#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from setuptools import setup
from setuptools.extension import Extension
from sys import platform

buildCython = '--cython' in sys.argv

extensions = [
    Extension(
        name               = 'indexed_zstd',
        sources            = [ 'indexed_zstd/indexed_zstd.pyx' ] if buildCython
                            else [ 'indexed_zstd/indexed_zstd.cpp' ],
        include_dirs       = [ '.' ],
        language           = 'c++',
        extra_compile_args = [ '-std=c++11', '-O3', '-DNDEBUG', '-stdlib=libc++', '-mmacosx-version-min=10.9' ] if platform == "darwin"
                             else [ '-std=c++11', '-O3', '-DNDEBUG' ],
        extra_link_args=[ '-lzstd', '-stdlib=libc++', '-mmacosx-version-min=10.9' ] if platform == "darwin" else [ '-lzstd' ],
        libraries = [ 'm' ],
    ),
]

zstd_seek = ('zstd_zeek', {
    'sources': [ 'indexed_zstd/libzstd-seek/zstd-seek.c' ]
})

if buildCython:
    from Cython.Build import cythonize
    extensions = cythonize( extensions, compiler_directives = { 'language_level' : '3' } )
    del sys.argv[sys.argv.index( '--cython' )]

scriptPath = os.path.abspath( os.path.dirname( __file__ ) )
with open( os.path.join( scriptPath, 'README.md' ), encoding = 'utf-8' ) as file:
    readmeContents = file.read()


setup(
    name             = 'indexed_zstd',
    version          = '1.3.2',

    description      = 'Fast random access to zstd files',
    url              = 'https://github.com/martinellimarco/indexed_zstd',
    author           = 'Martinelli Marco with help of Maximilian Knespel',
    license          = 'MIT',
    classifiers      = [ 'License :: OSI Approved :: MIT License',
                         'Development Status :: 5 - Production/Stable',
                         'Operating System :: POSIX',
                         'Operating System :: Unix',
                         'Programming Language :: Python :: 3',
                         'Topic :: System :: Archiving' ],

    long_description = readmeContents,
    long_description_content_type = 'text/markdown',

    py_modules       = [ 'indexed_zstd' ],
    libraries        = [ zstd_seek ],
    ext_modules      = extensions
)


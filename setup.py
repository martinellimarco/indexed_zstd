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
        extra_compile_args = [ '-std=c++17', '-O3', '-DNDEBUG', '-stdlib=libc++', '-mmacosx-version-min=10.9' ] if platform == "darwin"
                             else [ '-std=c++17', '-O3', '-DNDEBUG' ],
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
    version          = '1.5.0',

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
                         'Programming Language :: Python :: 3',
                         'Programming Language :: Python :: 3.6',
                         'Programming Language :: Python :: 3.7',
                         'Programming Language :: Python :: 3.8',
                         'Programming Language :: Python :: 3.9',
                         'Programming Language :: Python :: 3.10',
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


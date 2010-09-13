#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2006 Ashwin Phatak
# Copyright (C) 2007 Dave Gynn (dgynn@optaros.com)
# Copyright (C) 2010 Brian Meeker (meeker.brian@gmail.com)

from setuptools import setup, find_packages

PACKAGE = 'BatchModify'
VERSION = '0.8.0a1-trac0.12'

setup(
    name=PACKAGE, version=VERSION,
    description='Allows batch modification of tickets',
    author="Brian Meeker", author_email="meeker.brian@gmail.com",
    license='BSD', url='http://trac-hacks.org/wiki/BatchModifyPlugin',
    packages = ['batchmod'],
    package_data={
        'batchmod': [
            'templates/*.html',
            'htdocs/js/*.js',
            'htdocs/css/*.css',
        ]
    },
    entry_points = {
        'trac.plugins': [
            'batchmod.web_ui = batchmod.web_ui',
        ]
    }
)

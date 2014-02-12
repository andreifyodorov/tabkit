#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name="Tabkit",
    version="0.1",
    packages=['tabkit'],
    entry_points={
        "console_scripts": [
            'tcat = tcat:main'
        ]
    },
    scripts=[],
    author="Andrei Fyodorov",
    author_email="sour-times@yandex.ru",
    description="Coreutils-like kit for headed tab-separated files processing",
)
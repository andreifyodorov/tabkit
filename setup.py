#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name="Tabkit",
    version="0.1",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            'tcat = tabkit.scripts:cat',
            'tcut = tabkit.scripts:cut',
            'tsrt = tabkit.scripts:sort',
            'tmap_awk = tabkit.scripts:map',
        ]
    },
    author="Andrei Fyodorov",
    author_email="sour-times@yandex.ru",
    description="Coreutils-like kit for headed tab-separated files processing",
)
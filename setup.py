#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name="tabkit",
    version="0.2",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            'tcat = tabkit.scripts:cat',
            'tcut = tabkit.scripts:cut',
            'tsrt = tabkit.scripts:sort',
            'tjoin = tabkit.scripts:join',
            'tmap_awk = tabkit.scripts:map',
            'tpretty = tabkit.scripts:pretty'
        ]
    },
    author="Andrei Fyodorov",
    author_email="sour-times@yandex.ru",
    description="Coreutils-like kit for headed tab-separated files processing",
    license="PSF"
)

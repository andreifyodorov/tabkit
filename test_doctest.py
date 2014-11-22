#!/usr/bin/env python

import tabkit.exception
import tabkit.header
import tabkit.scripts
import tabkit.type
import tabkit.utils
import tabkit.awk
import tabkit.awk.map
import tabkit.awk.group


if __name__ == '__main__':
    import doctest
    doctest.testmod(tabkit.exception)
    doctest.testmod(tabkit.header)
    doctest.testmod(tabkit.scripts)
    doctest.testmod(tabkit.type)
    doctest.testmod(tabkit.utils)
    doctest.testmod(tabkit.awk)
    doctest.testmod(tabkit.awk.map)
    doctest.testmod(tabkit.awk.group)

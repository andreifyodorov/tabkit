tabkit
======

Coreutils-like kit for headed tab-separated files


tcat
----

Concatenate FILE(s), or standard input, to standard output.

1.tsv::

    # apples    oranges
    1   foo
    2   bar

2.tsv::

    # apples    oranges
    3   baz
    4   bam

::

    $ tcat 1.tsv 2.tsv
    # apples    oranges
    1   foo
    2   bar
    3   baz
    4   bam


tcut
----

Print selected columns from each FILE to standard output.

input.csv::

    # good  bad also_good
    1   apple   foo
    2   orange  bar
    3   lemon   baz

::

    $ cat input.csv | tcut -f good,also_good
    #   good    also_good
    1   foo
    2   bar
    3   baz


tsrt
----

Write sorted concatenation of all FILE(s) to standard output.

input.csv::

    # number    fruit
    10  apple
    3   orange
    10  lemon

::

    $ cat input.csv | tsrt -k good:num,fruit:desc
    # number    fruit   # ORDER: number:num, fruit:desc
    3   orange
    10  lemon
    10  apple


tmap_awk
--------

Perform a map operation on the input FILE(s).

input.csv::

    # x
    .1
    4
    -0.5
    0

::

    $ cat input.csv | tmap_awk -f 'x>0' -o 'y=log(x)'
    # y:float
    -2.30259
    1.38629



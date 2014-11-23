tabkit
======

A CLI TSV MR kit (a command-line interface tab-separated values map-reduce kit).
Powered by coreutils.


Overview
--------

::

	$ cat fruits | tpretty

	 fruit   | price:float
	---------+-------------
	 apple   | 1.04
	 kumquat | 4.99
	 orange  | 2.07

	$ cat sales | tpretty

	 fruit   | qty:int | paid:bool
	---------+---------+-----------
	 apple   | 10      | 1
	 apple   | 7       | 0
	 apple   | 1       | 1
	 orange  | 3       | 1
	 orange  | 18      | 1
	 orange  | 4       | 0
	 orange  | 2       | 1
	 kumquat | 1       | 1
	 kumquat | 2       | 1

	$ cat sales \
		| tmap_awk -f paid \
		| tsrt -k fruit \
		| tjoin -j fruit - fruits \
		| tgrp_awk -g fruit -o "sum_qty=sum(qty)" -o "sum_paid=sum(qty*price)" \
		| tpretty

	 fruit   | sum_qty:int | sum_paid:float
	---------+-------------+----------------
	 apple   | 11          | 11.44
	 kumquat | 3           | 14.97
	 orange  | 23          | 47.61

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



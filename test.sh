#!/usr/bin/env bash

set -o pipefail
set -o errexit

function tempfile {
    mktemp /tmp/tabkit_tmp.XXXXXX
}

function failed {
    echo "Failed test '$@'"; exit 1
}

function run {
    python -mtabkit.scripts "$@"
}

###### doctests
./test_doctest.py || failed doctests



###### cat

# bad_header
diff -b <(
    run cat <( echo "bad header" ) 2>&1
) <(cat <<EOCASE
cat: Bad header in file '/dev/fd/63'
EOCASE) || failed bad_header

# bad_type
diff -b <(
    run cat <( echo "# field:badtype" ) 2>&1
) <(cat <<EOCASE
cat: Unknown type 'badtype' in file '/dev/fd/63'
EOCASE) || failed bad_type

# incompatible_header
diff -b <(
    run cat <( echo "# a" ) <( echo "# a:int" ) <( echo "# b" ) 2>&1
) <(cat <<EOCASE
cat: Incompatible headers in file '/dev/fd/61'
EOCASE) || failed incompatible_header

# compatible_header
diff -b <(
    run cat <( echo "# a:int" ) <( echo "# a:float" ) <( echo "# a:bool" ) <( echo "# a:str" ) <( echo "# a" )
) <(cat <<EOCASE
# a
EOCASE) || failed compatible_header

# cat_from_stream
diff -b <(
    echo -e "# a:int, b:float\n1\t0.1\n2\t0.2" | run cat - <( echo -e "# a:int, b:float\n3\t0.3\n4\t0.4" )
) <(cat <<EOCASE
# a:int b:float
1   0.1
2   0.2
3   0.3
4   0.4
EOCASE) || failed cat_from_stream

# cat_unknow_order_field
diff -b <(
    echo -e "# a:int, b:float # ORDER: a,b,c" | run cat 2>&1
) <(cat <<EOCASE
cat: Unknown order field 'c' in file '<stdin>'
EOCASE) || failed cat_unknow_order_field

# cat_remove_order
diff -b <(
    run cat <( echo -e "# a:int, b:float # ORDER: a,b:desc" ) <( echo -e "# a:int, b:float" )
) <(cat <<EOCASE
# a:int b:float
EOCASE) || failed cat_remove_order

# cat_order_ok
diff -b <(
    echo -e "# a:int, b:float # ORDER: a,b:desc" | run cat
) <(cat <<EOCASE
# a:int b:float # ORDER: a, b:desc
EOCASE) || failed cat_order_ok


# cat_from_file
temp_file1=$(tempfile)
temp_file2=$(tempfile)
trap "rm -f $temp_file1 $temp_file2" EXIT
echo -e "# a:int, b:float\n1\t0.1\n2\t0.2" > $temp_file1
echo -e "# a:int, b:float\n3\t0.3\n4\t0.4" > $temp_file2
diff -b <(
    run cat $temp_file1 $temp_file2
) <(cat <<EOCASE
# a:int b:float
1   0.1
2   0.2
3   0.3
4   0.4
EOCASE) || failed cat_from_file
rm -r $temp_file1 $temp_file2
trap - EXIT


###### tcut

# cut_keep
diff -b <(
    echo -e "# a:int, b:float, c:str\n1\t0.1\ta\n2\t0.2\tb" | run cut -f a,c
) <(cat <<EOCASE
# a:int c
1   a
2   b
EOCASE) || failed cut_keep

# cut_keep_unknown_field
diff -b <(
    echo -e "# a:int, b:float, c:str\n1\t0.1\ta\n2\t0.2\tb" | run cut -f a,c,d 2>&1
) <(cat <<EOCASE
cut: No such field 'd'
EOCASE) || failed cut_keep_unknown_field

# cut_remove
diff -b <(
    echo -e "# a:int, b:float, c:str\n1\t0.1\ta\n2\t0.2\tb" | run cut -r a,c
) <(cat <<EOCASE
# b:float
0.1
0.2
EOCASE) || failed cut_remove

# cut_remove_unknown_field
diff -b <(
    echo -e "# a:int, b:float, c:str\n1\t0.1\ta\n2\t0.2\tb" | run cut -r a,c,d 2>&1
) <(cat <<EOCASE
cut: No such field 'd'
EOCASE) || failed cut_remove_unknown_field

# cut_keep_order
diff -b <(
    echo -e "# a,b,c,d # ORDER: a,b,c,d" | run cut -f a,b,d
) <(cat <<EOCASE
# a b d # ORDER: a, b
EOCASE) || failed cut_keep_order


###### tmap_awk

# map_uknown_identifier
diff -b <(
    echo -e "# a, b, c, d" | run map -o "z" 2>&1
) <(cat <<EOCASE
map: Unknown identifier 'z' in output expressions
EOCASE) || failed map_uknown_identifier

# map_bad_output_expr
diff -b <(
    echo -e "# a, b, c, d" | run map -o "a==b and b==c" 2>&1
) <(cat <<EOCASE
map: Syntax error: assign statements or field names expected in output expressions
EOCASE) || failed map_bad_output_expr

# map_int
diff -b <(
    echo -e "# a\n0.1\n1.5\n1.9" | run map -o "x=int(a)" 2>&1
) <(cat <<EOCASE
# x:int
0
1
1
EOCASE) || failed map_int

# map_sprintf
diff -b <(
    echo -e "# a, b\n1\ta'\n2\t\"b\n3\tc" | run map -o "x=sprintf('%.02f,%s', a, b)"
) <(
    echo '# x'
    echo "1.00,a'"
    echo '2.00,"b'
    echo '3.00,c'
) || failed map_sprintf

# map_math
diff -b <(
    echo -e "# a\n2\n3\n4" | run map -o "v=a+a;w=a-a;x=a*a;y=a/a;z=a**2"
) <(cat <<EOCASE
# v:int w:int   x:int   y:float z:int
4  0   4   1   4
6  0   9   1   9
8  0  16   1  16
EOCASE) || failed map_power

# map_log_exp
diff -b <(
    echo -e "# a\n2\n3\n4" | run map -o "x=log(exp(a))"
) <(cat <<EOCASE
# x:float
2
3
4
EOCASE) || failed map_log_exp


###### tgrp_awk

# grp_no_aggr

diff -b <(
    echo -e "# a, b" | run group -o 'x=a;y=b' 2>&1
) <(cat <<EOCASE
group: Syntax error: need aggregate function in aggregate expressions
EOCASE) || failed grp_no_aggr


# grp_implicit_group

diff -b <(
    echo -e "# a, b\n1\t3\n2\t4\n3\t5\n" | run group -o 'x=sum(a)/sum(b)'
) <(cat <<EOCASE
# x:float
0.5
EOCASE) || failed grp_implicit_group



###### tsrt

# sort_num
diff -b <(
    echo -e "# a, b\na\t10\na\t2\nb\t3" | run sort -k a:desc,b:num
) <(cat <<EOCASE
# a b # ORDER: a:desc, b:num
b  3
a  2
a  10
EOCASE) || failed sort_num

# sort_generic
diff -b <(
    echo -e "# a\n.1e5\n.2e4\n.3e3" | run sort -k a:generic
) <(cat <<EOCASE
# a # ORDER: a:generic
.3e3
.2e4
.1e5
EOCASE) || failed sort_generic


###### tpretty

# pretty
diff -b <(
    echo -e "# a:int, b\n1\t12123123\t1\n3\t2\n\na" | python -mtabkit.scripts pretty
) <( cat <<EOCASE
 a:int | b
-------+----------
 1     | 12123123
 3     | 2
       |
 a     |
EOCASE) || failed pretty


###### tjoin

# join_unsorted
diff -b <(
    python -mtabkit.scripts join -j id <(
        echo -e "# id:int # ORDER: id"
    ) <(
        echo -e "# id:str"
    ) 2>&1
) <( cat <<EOCASE
join: File '/dev/fd/62' must be sorted lexicographicaly ascending by the field 'id'
EOCASE) || failed join_unsorted

# join_generic_key
diff -b <(
    python -mtabkit.scripts join -j id <(
        echo -e "# id:int # ORDER:id\n1\n2\n3\n"
    ) <(
        echo -e "# id # ORDER:id\n3\nfoo\n"
    )
) <( cat <<EOCASE
# id:int    # ORDER: id
3
EOCASE) || failed join_generic_key

# join
diff -b <(
    python -mtabkit.scripts join -1 id -2 ID <(
        echo -e "# id:int, fruit # ORDER: id, fruit\n1\tapple\n1\tpomegranate\n2\torange\n3\tcucumber"
    ) <(
        echo -e "# ID, color # ORDER: ID, color\n1\tred\n1\truby\n3\tgreen\nfoo\tpurple"
    )
) <( cat <<EOCASE
# id:int    fruit   color # ORDER: id, fruit, color
1   apple       red
1   apple       ruby
1   pomegranate red
1   pomegranate ruby
3   cucumber    green
EOCASE) || failed join

# join_a
diff -b <(
    python -mtabkit.scripts join -1 id -2 ID -a2 -e- <(
        echo -e "# id:float, fruit # ORDER: id, fruit\n1\tapple\n1\tpomegranate\n1.5\torange\n3\tcucumber"
    ) <(
        echo -e "# ID:int, color # ORDER: ID, color\n1\tred\n1\truby\n3\tgreen\n4\tpurple"
    )
) <( cat <<EOCASE
# id:int    fruit   color # ORDER: id, fruit, color
1   apple       red
1   apple       ruby
1   pomegranate red
1   pomegranate ruby
3   cucumber    green
4   -           purple
EOCASE) || failed join_a

# join_a_generic_key
diff -b <(
    python -mtabkit.scripts join -1 id -2 ID -a1 -a2 -e- <(
        echo -e "# id:float, fruit # ORDER: id, fruit\n1\tapple\n1\tpomegranate\n1.5\torange\n3\tcucumber"
    ) <(
        echo -e "# ID:int, color # ORDER: ID, color\n1\tred\n1\truby\n3\tgreen\n4\tpurple"
    )
) <( cat <<EOCASE
# id:float    fruit   color # ORDER: id, fruit, color
1   apple       red
1   apple       ruby
1   pomegranate red
1   pomegranate ruby
1.5 orange      -
3   cucumber    green
4   -           purple
EOCASE) || failed join_a_generic_key


# join_v
diff -b <(
    python -mtabkit.scripts join -1 id -2 ID -v1 <(
        echo -e "# id:int, fruit # ORDER: id, fruit\n1\tapple\n1\tpomegranate\n2\torange\n3\tcucumber"
    ) <(
        echo -e "# ID, color # ORDER: ID, color\n1\tred\n1\truby\n3\tgreen\n4\tpurple"
    )
) <( cat <<EOCASE
# id:int    fruit # ORDER: id, fruit
2   orange
EOCASE) || failed join_v1


# join_v_generic_key
diff -b <(
    python -mtabkit.scripts join -1 id -2 ID -v1 -v2 -e- <(
        echo -e "# id, fruit # ORDER: id, fruit\n1\tapple\n1\tpomegranate\n2\torange\n3\tcucumber"
    ) <(
        echo -e "# ID:int, color # ORDER: ID, color\n1\tred\n1\truby\n3\tgreen\n4\tpurple"
    )
) <( cat <<EOCASE
# id    fruit   color # ORDER: id, fruit, color
2   orange  -
4   -   purple
EOCASE) || failed join_v_generic_key
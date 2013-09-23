#!/bin/bash

set -o pipefail
set -o errexit

function tempfile {
    mktemp /tmp/tabkit_tmp.XXXXXX
}

function failed {
    echo "Failed test '$@'"; exit 1
}

###### doctests
(
    cd tabkit
    ls *.py | xargs -n1 python
)



###### cat

# bad_header
diff -b <(
    ./tcat.py <( echo "bad header" ) 2>&1
) <(cat <<EOCASE 
./tcat.py: Bad header in file '/dev/fd/63'
EOCASE) || failed bad_header

# bad_type
diff -b <(
    ./tcat.py <( echo "# field:badtype" ) 2>&1
) <(cat <<EOCASE 
./tcat.py: Unknown type 'badtype' in file '/dev/fd/63'
EOCASE) || failed bad_type

# incompatible_header
diff -b <(
    ./tcat.py <( echo "# a" ) <( echo "# a:int" ) <( echo "# b" ) 2>&1
) <(cat <<EOCASE 
./tcat.py: Incompatible headers in file '/dev/fd/61'
EOCASE) || failed incompatible_header

# compatible_header
diff -b <(
    ./tcat.py <( echo "# a:int" ) <( echo "# a:float" ) <( echo "# a:bool" ) <( echo "# a:str" ) <( echo "# a" )
) <(cat <<EOCASE 
# a
EOCASE) || failed compatible_header

# cat_from_stream
diff -b <(
    echo -e "# a:int, b:float\n1\t0.1\n2\t0.2" | ./tcat.py - <( echo -e "# a:int, b:float\n3\t0.3\n4\t0.4" )
) <(cat <<EOCASE 
# a:int b:float
1   0.1
2   0.2
3   0.3
4   0.4
EOCASE) || failed cat_from_stream

# cat_unknow_order_field
diff -b <(
    echo -e "# a:int, b:float # ORDER: a,b,c" | ./tcat.py 2>&1
) <(cat <<EOCASE 
./tcat.py: Unknown order field 'c' in file '<stdin>'
EOCASE) || failed cat_unknow_order_field

# cat_remove_order
diff -b <(
    ./tcat.py <( echo -e "# a:int, b:float # ORDER: a,b:desc" ) <( echo -e "# a:int, b:float" )
) <(cat <<EOCASE 
# a:int b:float
EOCASE) || failed cat_remove_order

# cat_order_ok
diff -b <(
    echo -e "# a:int, b:float # ORDER: a,b:desc" | ./tcat.py
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
    ./tcat.py $temp_file1 $temp_file2
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
    echo -e "# a:int, b:float, c:str\n1\t0.1\ta\n2\t0.2\tb" | ./tcut.py -f a,c
) <(cat <<EOCASE
# a:int c:str
1   a
2   b
EOCASE) || failed cut_keep

# cut_keep_unknown_field
diff -b <(
    echo -e "# a:int, b:float, c:str\n1\t0.1\ta\n2\t0.2\tb" | ./tcut.py -f a,c,d 2>&1
) <(cat <<EOCASE
./tcut.py: No such field 'd'
EOCASE) || failed cut_keep_unknown_field

# cut_remove
diff -b <(
    echo -e "# a:int, b:float, c:str\n1\t0.1\ta\n2\t0.2\tb" | ./tcut.py -r a,c
) <(cat <<EOCASE 
# b:float
0.1
0.2
EOCASE) || failed cut_remove

# cut_remove_unknown_field
diff -b <(
    echo -e "# a:int, b:float, c:str\n1\t0.1\ta\n2\t0.2\tb" | ./tcut.py -r a,c,d 2>&1
) <(cat <<EOCASE
./tcut.py: No such field 'd'
EOCASE) || failed cut_remove_unknown_field


###### tmap_awk

# map_uknown_identifier
diff -b <(
    echo -e "# a, b, c, d" | ./tmap_awk.py -o "z" 2>&1
) <(cat <<EOCASE
./tmap_awk.py: Unknown identifier 'z'
EOCASE) || failed map_uknown_identifier

# map_bad_output_expr
diff -b <(
    echo -e "# a, b, c, d" | ./tmap_awk.py -o "a==b and b==c" 2>&1
) <(cat <<EOCASE
./tmap_awk.py: Syntax error: assign statement or field name expected
EOCASE) || failed map_bad_output_expr

# map_int
diff -b <(
    echo -e "# a\n0.1\n1.5\n1.9" | ./tmap_awk.py -o "x=int(a)" 2>&1
) <(cat <<EOCASE
# x:int
0
1
1
EOCASE) || failed map_int

# map_sprintf
diff -b <(
    echo -e "# a, b\n1\ta'\n2\t\"b\n3\tc" | ./tmap_awk.py -o "x=sprintf('%.02f,%s', a, b)"
) <(
    echo '# x:str'
    echo "1.00,a'"
    echo '2.00,"b'
    echo '3.00,c'
) || failed map_sprintf

#!/bin/bash

set -o pipefail
set -o errexit

###### cat

# bad_header
diff -b <(
    ./tcat.py <( echo "bad header" ) 2>&1
) <(cat <<EOCASE 
./tcat.py: Bad header in file '/dev/fd/63'
EOCASE) || echo "Failed test 'bad_header'" && false

# bad_type
diff -b <(
    ./tcat.py <( echo "# field:badtype" ) 2>&1
) <(cat <<EOCASE 
./tcat.py: Unknown type 'badtype' in file '/dev/fd/63'
EOCASE) || echo "Failed test 'bad_type'" && false

# incompatible_header
diff -b <(
    ./tcat.py <( echo "# a" ) <( echo "# a:int" ) <( echo "# b" ) 2>&1
) <(cat <<EOCASE 
./tcat.py: Incompatable headers in file '/dev/fd/61'
EOCASE) || echo "Failed test 'incompatible_header'" && false

# compatible_header
diff -b <(
    ./tcat.py <( echo "# a:int" ) <( echo "# a:float" ) <( echo "# a:bool" ) <( echo "# a:str" ) <( echo "# a" )
) <(cat <<EOCASE 
# a
EOCASE) || echo "Failed test 'compatible_header'" && false

# cat_from_stream
diff -b <(
    echo -e "# a:int, b:float\n1\t0.1\n2\t0.2" | ./tcat.py - <( echo -e "# a:int, b:float\n3\t0.3\n4\t0.4" )
) <(cat <<EOCASE 
# a:int b:float
1   0.1
2   0.2
3   0.3
4   0.4
EOCASE) || echo "Failed test 'cat_from_stream'" && false

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
EOCASE) || echo "Failed test 'cat_from_file'" && false
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
EOCASE) || echo "Failed test 'cut_keep'" && false

# cut_keep_unknown_field
diff -b <(
    echo -e "# a:int, b:float, c:str\n1\t0.1\ta\n2\t0.2\tb" | ./tcut.py -f a,c,d 2>&1
) <(cat <<EOCASE
./tcut.py: No such field 'd'
EOCASE) || echo "Failed test 'cut_keep_unknown_field'" && false

# cut_remove
diff -b <(
    echo -e "# a:int, b:float, c:str\n1\t0.1\ta\n2\t0.2\tb" | ./tcut.py -r a,c
) <(cat <<EOCASE 
# b:float
0.1
0.2
EOCASE) || echo "Failed test 'cut_remove'" && false

# cut_remove_unknown_field
diff -b <(
    echo -e "# a:int, b:float, c:str\n1\t0.1\ta\n2\t0.2\tb" | ./tcut.py -r a,c,d 2>&1
) <(cat <<EOCASE
./tcut.py: No such field 'd'
EOCASE) || echo "Failed test 'cut_remove_unknown_field'" && false

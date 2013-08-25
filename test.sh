#!/bin/bash

set -o pipefail
set -o errexit

# bad_header
diff -b <(
    ./tcat.py <( echo "bad header" ) 2>&1
) <(cat <<EOCASE 
./tcat.py: Bad header in file '/dev/fd/63'
EOCASE) || echo "Failed test 'bad_header'"

# bad_type
diff -b <(
    ./tcat.py <( echo "# field:badtype" ) 2>&1
) <(cat <<EOCASE 
./tcat.py: Unknown type 'badtype' in file '/dev/fd/63'
EOCASE) || echo "Failed test 'bad_type'"

# incompatible_header
diff -b <(
    ./tcat.py <( echo "# a" ) <( echo "# a:int" ) <( echo "# b" ) 2>&1
) <(cat <<EOCASE 
./tcat.py: Incompatable headers in file '/dev/fd/61'
EOCASE) || echo "Failed test 'incompatible_header'"

# compatible_header
diff -b <(
    ./tcat.py <( echo "# a:int" ) <( echo "# a:float" ) <( echo "# a:bool" ) <( echo "# a:str" ) <( echo "# a" )
) <(cat <<EOCASE 
# a
EOCASE) || echo "Failed test 'compatible_header'"

# cat_from_stream
diff -b <(
    echo -e "# a:int, b:float\n1\t0.1\n2\t0.2" | ./tcat.py - <( echo -e "# a:int, b:float\n3\t0.3\n4\t0.4" )
) <(cat <<EOCASE 
# a:int b:float
1   0.1
2   0.2
3   0.3
4   0.4
EOCASE) || echo "Failed test 'cat_from_stream'"

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
EOCASE) || echo "Failed test 'cat_from_file'"
rm -r $temp_file1 $temp_file2
trap - EXIT
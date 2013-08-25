#!/usr/bin/python

import sys
import argparse
import subprocess
import re

def main():
    parser = argparse.ArgumentParser(
        add_help=True, 
        description="Perform a map operation on the input"
    )
    parser.add_argument('files', metavar='FILE', type=argparse.FileType('r'), nargs="*")
    parser.add_argument('-f', '--filter', help="Filter expression")
    parser.add_argument('-o', '--output', help="Output fields")
    args = parser.parse_args()
    files = Files(args.files)
    data_desc = files.data_desc()

    # ....

    subprocess.call(['cat'] + list(files.descriptors()))

if __name__ == "__main__":
    main()
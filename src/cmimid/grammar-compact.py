# This source code is from Mimid
#   https://github.com/vrthra/mimid/
# Copyright (c) 2018-2020 Saarland University, CISPA, authors, and contributors
# This source code is licensed under The Fuzzing Book License found in the
# 3rd-party-licenses.txt file in the root directory of this source tree.

import sys
sys.setrecursionlimit(99000)
import json
import cmimid.grammartools as grammartools

def usage():
    print('''
grammar-compact.py <grammar>
    Given an inferred grammar, remove redundant rules and definitions
            ''')
    sys.exit(0)

def main(args):
    if not args or args[0] == '-h': usage()
    gfname = args[0]
    with open(gfname) as f:
        gf = json.load(fp=f)
    grammar = gf['[grammar]']
    start = gf['[start]']
    command = gf['[command]']


    # now, what we want to do is first regularize the grammar by splitting each
    # multi-character tokens into single characters.
    g = grammartools.compact_grammar(grammar, start)
    print(json.dumps({'[start]': start, '[grammar]':g, '[command]': command}, indent=4))

if __name__ == '__main__':
    main(sys.argv[1:])

#!/usr/bin/env python
import os
tests = """
make help
make t01 123
#!!! add fac calls for every option!
#!!! add types for every option
# make t01 a=123
make t02 123
make t02 123 b=2
# make t02 a=123 b=2
make t03 b=2
make ext1 x y z d=1
# in this example d is not cast to boolean but 1 works
# remember that this signature cannot have 'a' in kwargs: ext2(a,*args,**kwargs)
make ext2 x y z d=1
make ext2 x y z d=1
make ext3 x y z d=1
./fac ext2 x y z --d
./fac ext2 x y z --d=0
""".strip('\n').split('\n')
for test in tests:
	print('[TEST] %s'%test)
	os.system("CLI=lib/tests/statetools_parser_cli_test.py "+test)

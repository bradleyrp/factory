#!/bin/bash
set -e

## BOOTSTRAP via conda
## this test clears the environments and installs conda and a minimal env
## note that the sequence test on macos fails (!) with a conda lib error

SUFFIX=${1:-""}
if [ ! -z $SUFFIX ]; then SUFFIX=_$SUFFIX; fi
echo "[STATUS] starting test"
#!!! dangerous command. resolve this with cli.Parser.bootstrap
./fac nuke --sure
time ./fac conda specs/env_conda_min.yaml --spot=local/conda$SUFFIX # 24.9s
# activate the specifc environment here
./fac activate local/conda$SUFFIX/envs/min
echo "import sys,os;print(os.path.realpath(sys.executable))" | ./fac run python
# both make and ./fac take only 0.1s natively
time ./fac # 0.1s
time make
# confirm the result
EXPECTED="{'envs': {'local/conda$SUFFIX/envs/min': {'kind': 'conda', 'file': 'specs/env_conda_min.yaml', 'uname': {'sysname': 'Darwin', 'release': '18.7.0', 'machine': 'x86_64', 'nodename': 'MacBook-Pro-7.local'}}}, 'spots': {}}"
# check the result
echo $EXPECTED | ./fac check_config
echo "[STATUS] passed"

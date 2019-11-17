#!/bin/bash
set -e

## BOOTSTRAP via venv
## this test clears the environments and installs a venv
## note that the sequence test on macos fails (!) with a conda lib error

SUFFIX=${1:-""}
if [ ! -z $SUFFIX ]; then SUFFIX=_$SUFFIX; fi
echo "[STATUS] starting test"
#!!! dangerous command. resolve this with cli.Parser.bootstrap
./fac nuke --sure
# venv takes 4.3s
time ./fac venv create --spot=local/venv$SUFFIX --file=specs/env_venv.txt
./fac activate local/venv$SUFFIX
echo "import sys,os;print(sys.executable)" | ./fac run python
# both make and ./fac take only 0.1s natively
time ./fac # 0.1s
time make
# confirm the result
EXPECTED="{'envs': {'local/venv$SUFFIX': {'kind': 'venv', 'file': 'specs/env_venv.txt', 'uname': {'sysname': 'Darwin', 'release': '18.7.0', 'machine': 'x86_64', 'nodename': 'MacBook-Pro-7.local'}}}, 'spots': {}}"
# check the result
echo $EXPECTED | ./fac check_config
echo "[STATUS] passed"

#!/bin/bash

## BOOTSTRAP via venv
## this test clears the environments and installs a venv
## note that the sequence test on macos fails (!) with a conda lib error

SUFFIX=${1:-""}
if [ ! -z $SUFFIX ]; then SUFFIX=_$SUFFIX; fi
echo $SUFFIX

set -e
echo "[STATUS] starting test"
./fac nuke
# venv takes 4.3s
time ./fac venv create --spot=local/venv$SUFFIX --file=specs/env_venv.txt
./fac activate local/venv$SUFFIX
echo "import sys,os;print(sys.executable)" | ./fac run python
# both make and ./fac take only 0.1s natively
time ./fac # 0.1s
time make


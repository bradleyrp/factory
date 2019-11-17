#!/bin/bash

## BOOTSTRAP via conda
## this test clears the environments and installs conda and a minimal env
## note that the sequence test on macos fails (!) with a conda lib error

SUFFIX=${1:-""}
if [ ! -z $SUFFIX ]; then SUFFIX=_$SUFFIX; fi
echo $SUFFIX

set -e
echo "[STATUS] starting test"
./fac nuke
time ./fac conda specs/env_conda_min.yaml --spot=local/conda$SUFFIX # 24.9s
# activate the specifc environment here
./fac activate local/conda$SUFFIX/envs/min
echo "import sys,os;print(os.path.realpath(sys.executable))" | ./fac run python
# both make and ./fac take only 0.1s natively
time ./fac # 0.1s
time make

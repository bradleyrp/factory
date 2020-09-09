#!/bin/bash
# detect the LMOD_SPOT
#! make this path more programmatic
LMOD_SPOT=~/local/stack/linux-centos8-zen/gcc-8.3.1/lmod-*
#! simplify to a one-liner?
LMOD_SPOT_FOUND=($LMOD_SPOT)
if [ ! ${#LMOD_SPOT_FOUND[@]} -eq 1 ]; then
	echo "[ERROR] multiple Lmod somehow"; exit 1; fi
source $LMOD_SPOT/lmod/lmod/init/bash
export MODULEPATH=$HOME/local/stack/lmod/linux-centos8-x86_64/Core
export LMOD_SYSTEM_DEFAULT_MODULES="openmpi"

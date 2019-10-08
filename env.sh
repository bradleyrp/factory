#!/bin/bash
# source the conda environments quickly
if [ -z $1 ]; then
	./fac envs
else
	cmd="source conda/bin/activate conda/envs/$1"
	echo "[STATUS] running: $cmd"
	eval $cmd
fi

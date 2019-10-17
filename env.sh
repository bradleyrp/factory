#!/bin/bash
# source the conda environments quickly
if [ -z $1 ]; then
	./fac envs
else
	# identify the parent directory via https://stackoverflow.com/a/246128/3313859
	DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
	cmd="source $DIR/conda/bin/activate $DIR/conda/envs/$1"
	echo "[STATUS] running: $cmd"
	eval $cmd
fi

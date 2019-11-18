#!/bin/bash
if [ -z "$1" ]; then 
	make envs
	echo "[USAGE] see the list above for environments:"
	echo "[USAGE] source env.sh <name>"
else
	#! could we detect a lack of source command because otherwise pointless?
	# source  the environment
	cmd=$(make envs name=$1 | perl -ne 'print if s/source (.+)$/$1/')
	# source the correct environment
	#! possibly dangerous?
	source $cmd
fi

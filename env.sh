#!/bin/bash
if [[ ! $_ == $0 ]]; then
	echo "[ERROR] you must source env.sh"
	echo "[ERROR] source env.sh without arguments for usage notes"
# note that we nest all conditionals because exit in a sourced script
# causes you to leave a screen which is very annoying
else
	DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
	if [ -z "$1" ]; then 
		make envs
		echo "[USAGE] see the list above for environments"
		echo "[USAGE] use spack: source env.sh spack"
		echo "[USAGE] use an environment: source env.sh <name>"
	else
		# special name for sourcing spack
		if [ "$1" == "spack" ]; then name=_spack
		else name=$1; fi
		# confirm that the environment exists
		make -C $DIR envs name=$name > /dev/null 2>&1
		if [ ! $? -eq 0 ]; then
			# repeat the command to show the error
			make -C $DIR envs name=$name
		# source the right environment
		else
			# remote directory via https://stackoverflow.com/a/246128/3313859
			read -a paths <<<$(make -C $DIR envs name=$name \
				| perl -ne 'print if s/source (.+)$/$1/')
			# source the correct environment
			if [ "$name" == "_spack" ]; then
				echo "[STATUS] sourcing spack"
				# the call to get the spack environment yields the spack setup
				source $paths
			else	
				echo "[STATUS] sourcing the \"$name\" environment"
				echo "[STATUS] use \"conda deactivate\" to exit"
				# requesting an environment gives a relative path
				resolved="$DIR/${paths[0]} $DIR/${paths[1]}"
				source $resolved
			fi
		fi
	fi
fi
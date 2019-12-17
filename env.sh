#!/usr/bin/env bash
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
	echo "[ERROR] you must source env.sh"
	echo "[ERROR] source env.sh without arguments for usage notes"
# note that we nest all conditionals because exit in a sourced script
# causes you to leave a screen which is very annoying
else
	if [ "$SHELL" = "/bin/zsh" ]; then 
		# via https://stackoverflow.com/a/3572105
		realpath() {
	    	[[ $1 = /* ]] && echo "$1" || echo "$PWD/${1#./}"
		}
		DIR=$(dirname $(realpath "$0"))
	else
		# standard bash method
		DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
	fi
	if [ -z "$1" ]; then 
		make -C $DIR envs
		echo "[USAGE] see the list above for environments"
		echo "[USAGE] use spack: source env.sh spack"
		echo "[USAGE] use an environment: source env.sh <name>"
	else
		# special name for sourcing spack
		# not zsh compatible: if [ "$1" == "spack" ]; then name=_spack
		if [ "$1" = "spack" ]; then name=_spack
		else name=$1; fi
		# confirm that the environment exists
		make -C $DIR envs name=$name > /dev/null 2>&1
		if [ ! $? -eq 0 ]; then
			# repeat the command to show the error
			make -C $DIR envs name=$name
		# source the right environment
		else
			# remote directory via https://stackoverflow.com/a/246128/3313859
			if [ "$SHELL" = "/bin/zsh" ]; then read_flag="-A"
			else read_flag="-a"; fi
			read $read_flag paths <<<$(make -C $DIR envs name=$name \
				| perl -ne 'print if s/source (.+)$/$1/')
			# source the correct environment
			if [ "$name" = "_spack" ]; then
				echo "[STATUS] sourcing spack"
				# the call to get the spack environment yields the spack setup
				source $paths
			else	
				echo "[STATUS] sourcing the \"${name}\" environment"
				echo "[STATUS] use \"conda deactivate\" to exit"
				if [ "$SHELL" = "/bin/zsh" ]; then 
					# requesting an environment gives a relative path
					source "$DIR/${paths[1]}" "$DIR/${paths[2]}"
					 $resolved
				else
					# requesting an environment gives a relative path
					resolved="$DIR/${paths[0]} $DIR/${paths[1]}"
					source $resolved
				fi
			fi
		fi
	fi
fi
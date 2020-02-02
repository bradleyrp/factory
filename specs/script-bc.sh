#!/bin/bash
#SBATCH -p gpuv100
#SBATCH --qos=gpuv100
#SBATCH --res=image_tests
#SBATCH -c 12
#SBATCH --gres=gpu:1
#SBATCH -t 120
usage () { 
	echo "[USAGE] salloc <opts> $0 <name> (live)" 
	echo "[NOTE] the following are example commands you might use"
	echo "salloc --qos=gpuv100 -w gpudev002 --res image_tests"\
		"-c 12 --gres=gpu:1 srun --pty /bin/bash"\
		"-c 'source specs/script-bc.sh bc-std live'"
	echo "sbatch specs/script-bc.sh bc-std"
	echo "[NOTE] alternately in srun: make do specs/spack_hpc_go.yaml"  
	exit 1
}
if [ -z $1 ]; then usage; fi
if [[ $2 =~ (live) ]]; then 
	flags=" --live"
else flags=""; fi
#! make this a relative path
cd /exec/rbradley/buildsite/factory
source env.sh min
module purge
./fac spack_hpc specs/spack_hpc_go.yaml --name=$1$flags 

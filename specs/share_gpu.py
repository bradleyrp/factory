#!/usr/bin/env python

"""
Task queue to share NVidia GPUs.
"""

import os,sys,re,subprocess,argparse,time

#! dev
# iterative reexection
import sys
__me__ = sys.argv[0]
assert __me__.endswith('.py')
def go(): exec(open(__me__).read(),globals())

def run(cmd):
	"""Handler for nvidia-smi."""
	proc = subprocess.Popen(cmd.split(),
		stdout=subprocess.PIPE,stderr=subprocess.PIPE)
	stdout,stderr = [i.decode() for i in proc.communicate()]
	if proc.returncode:
		raise Exception(
			('[ERROR] failed to check nvidia-smi with "%s":\n'
				'stdout:n%s\nstderr:\n%s')%(cmd,stdout,stderr))
	lines = stdout.splitlines()
	header,lines = lines[0],lines[1:]
	header = [i.strip() for i in header.split(',')]
	return [dict(zip(header,[i.strip() for i in line.split(',')])) for line in lines]

def interp_mem(i):
	"""Interpret a memory string."""
	#! nvidia-smi uses MiB but this might change
	match = re.match('(\d+) MiB',i)
	if not match: raise Exception('dev: cannot interpret %s'%i)
	return float(match.group(1))

def gpu_monitor(gpu_inds,cycles=3,interval=3,mem_limit=1000):
	print('[STATUS] MONITOR GPU (cycles: %d, interval: %d, memory limit: %d)'%(cycles,interval,mem_limit))
	print('[STATUS] using GPUs %s'%(','.join(['%d'%i for i in gpu_inds])))
	# main monitor loop
	busy = [0 for g in gpu_inds]
	for cnum in range(cycles):
		for gnum in gpu_inds:
			# skip redundant checks if we already know it is busy
			if busy[gpu_inds.index(gnum)]: continue
			cmd = ('nvidia-smi '
				'--query-compute-apps=pid,process_name,used_memory '
				'--format=csv --id=%d')%gnum
			result = run(cmd)
			if result:
				# interpret results here
				mem_key = 'used_gpu_memory [MiB]'
				rollup = []
				for item in result:
					if mem_key not in item:
						raise Exception('expecting to find used_gpu_memory')
					else: rollup.append({'mem':interp_mem(item[mem_key])})
				# summary of memory usage on this GPU
				#! note that we wish to add a percentage workload but this is difficult
				mems = sum([i['mem'] for i in rollup])
				if mems>mem_limit:
					print('[STATUS] GPU %d is busy!'%gnum)
					busy[gpu_inds.index(gnum)] = 1
		# sleep between cycles
		time.sleep(interval)
	avail = [g for g in gpu_inds if busy[gpu_inds.index(g)]==0]
	if len(avail)>0:
		print('[STATUS] gpu ready: %s'%','.join(['%d'%a for a in avail]))
	else: print('[STATUS] all GPUs are busy')
	return avail

if __name__=='__main__':
	parser = argparse.ArgumentParser(description="Monitor GPUs for sharing.")
	parser.add_argument('-n',dest='num',help="Number of GPUs.")
	parser.add_argument('-g',dest='gpus',help="List of GPU indices to address.")
	parser.add_argument('-m',dest='mem_limit',
		help="Memory limit for idle (MB).",default=1000)
	parser.add_argument('-i',dest='interval',
		help="Interval in seconds to monitor.",default=3,type=int)
	parser.add_argument('-c',dest='cycles',
		help="Cycles before all-clear.",default=3,type=int)
	args = parser.parse_args()
	# infer gpus if necessary
	if args.gpus:
		raise Exception('under development')
	elif not args.num:
		n_gpus = len(run('nvidia-smi --query-gpu=name --format=csv'))
	else:
		n_gpus = int(args.num)
	gpu_inds = range(n_gpus)
	gpu_monitor(cycles=args.cycles,gpu_inds=gpu_inds,
		interval=args.interval,mem_limit=args.mem_limit)

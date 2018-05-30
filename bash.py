#!/usr/bin/env python

from __future__ import print_function
import os,subprocess

def command_check(command):
	"""Run a command and see if it completes with returncode zero."""
	print('[STATUS] checking command "%s"'%command)
	try:
		with open(os.devnull,'w') as FNULL:
			proc = subprocess.Popen(command,stdout=FNULL,stderr=FNULL,shell=True,executable='/bin/bash')
			proc.communicate()
			return proc.returncode==0
	except Exception as e: 
		print('warning','caught exception on command_check: %s'%e)
		return False

def bash(command,log=None,cwd=None,inpipe=None,show=False):
	"""
	Run a bash command.
	Development note: tee functionality would be useful however you cannot use pipes with subprocess here.
	"""
	if not cwd: cwd = './'
	if log == None and not show: 
		if inpipe: raise Exception('under development')
		kwargs = dict(cwd=cwd,shell=True,executable='/bin/bash',
			stdout=subprocess.PIPE,stderr=subprocess.PIPE)
		proc = subprocess.Popen(command,**kwargs)
		stdout,stderr = proc.communicate()
	elif log == None and show:
		if inpipe: raise Exception('under development')
		kwargs = dict(cwd=cwd,shell=True,executable='/bin/bash')
		proc = subprocess.Popen(command,**kwargs)
		stdout,stderr = proc.communicate()
	else:
		output = open(log,'w')
		kwargs = dict(cwd=cwd,shell=True,executable='/bin/bash',
			stdout=output,stderr=output)
		if inpipe: kwargs['stdin'] = subprocess.PIPE
		proc = subprocess.Popen(command,**kwargs)
		if not inpipe: stdout,stderr = proc.communicate()
		else: stdout,stderr = proc.communicate(input=inpipe)
	if stderr: 
		print('error','stdout: %s'%stdout)
		print('error','stderr: %s'%stderr)
		raise Exception('bash returned error state')
	if proc.returncode: 
		if log: raise Exception('bash error, see %s'%log)
		else: 
			extra = '\n'.join([i for i in [stdout,stderr] if i])
			raise Exception('bash error with returncode %d. stdout: "%s"\nstderr: "%s"'%(proc.returncode,
				stdout,stderr))
	return {'stdout':stdout,'stderr':stderr}

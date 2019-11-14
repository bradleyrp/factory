#!/usr/bin/env python

"""
Command-line hooks that supply an interface to replicator functions
so that you can execute different commands inside of alternate environments.
"""

import sys,os
import ortho
from ortho.replicator.replicator_dev import ReplicateCore
from ortho.replicator.replicator import replicator_read_yaml,many_files
from ortho import path_resolver

def feedback_args_to_command(*args,**kwargs):
	"""
	Convert arguments back into a command which is composed with a replicator.
	"""
	here = os.getcwd()
	cmd = "make -C %s "%here+' '.join(args)
	# note that we use the make syntax here rather than ./fac
	if kwargs: cmd += ' '+' '.join(['%s=%s'%(i,j) for i,j in kwargs.items()])
	return cmd

def docker(recipe,*args,**kwargs):
	"""
	Run anything in a docker using `ReplicatorCore`.
	make docker spot=./here script specs/demo_script.yaml delay
	"""
	cmd = feedback_args_to_command(*args,**kwargs)
	if 0:
		sources = many_files(ortho.conf['replicator_recipes'])
		this_test = replicator_read_yaml(name=recipe,sources=sources)
		#! major hack we need to connect this somehow or systematize it
		#! or just point to test_gromacs_docker.yaml instead?
		docker_container = this_test['meta']['complete'][recipe][
			'compose']['services']['deploy']['image']
		docker_volume = 't01-factory-tests-a01'
		ReplicateCore(script=cmd,docker_container=docker_container,
			docker_volume=docker_volume)
	#! HACKING HERE
	ReplicateCore(
		root=os.getcwd(),
		line="echo HELLOWORLD",
		docker_container='factory:centos7_user')

def screen(*args,screen='screen_anon',**kwargs):
	"""
	Run anything in a screen using `ReplicatorCore`.
	e.g. make screen screen=anon script specs/demo_script.yaml delay spot=./here
	"""
	# note that running in a remote location typically uses a 'spot' flag
	#   however everything is passed through so the reciever has to accept it
	cmd = feedback_args_to_command(*args,**kwargs)
	ReplicateCore(script=cmd,screen=screen)

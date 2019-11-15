#!/usr/bin/env python

"""
Command-line hooks that supply an interface to replicator functions
so that you can execute different commands inside of alternate environments.
"""

import sys,os
import ortho
from ortho.replicator.replicator_dev import ReplicateCore,RecipeRead
from ortho.replicator.replicator_dev import promise_run
#! from ortho.replicator.replicator import replicator_read_yaml,many_files
from ortho import path_resolver

def feedback_args_to_command(*args,**kwargs):
	"""
	Convert arguments back into a command which is composed with a replicator.
	"""
	here = os.getcwd()
	#cmd = "make -C %s "%here+' '.join(args)
	#! fac has no path variable
	cmd = "cd %s "%here + "&& ./fac "+' '.join(args)
	# note that we use the make syntax here rather than ./fac
	if kwargs: cmd += ' '+' '.join(['%s=%s'%(i,j) for i,j in kwargs.items()])
	return cmd

def docker(recipe,*args,**kwargs):
	"""
	Run anything in a docker using `ReplicatorCore`.
	make docker spot=./here script specs/demo_script.yaml delay
	"""
	visit = kwargs.pop('visit',False)
	#! need better hook-ups
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

	# STEP A: get the recipe
	#! intervene here with a basic default recipe if no yaml
	# a path to a recipe file skips all of the gathering
	if os.path.isfile(recipe):
		# test: make docker specs/recipes/basics_redev.yaml
		recipe = RecipeRead(path=recipe).solve
	else: raise Exception('dev')

	# STEP B: translate recipe into call to ReplicateCore
	# empty arguments triggers a visit to the container
	if not args: cmd,visit = '/bin/bash',True
	else: cmd = feedback_args_to_command(*args,**kwargs)
	image = recipe['image_name']
	# the incoming site can have a hook
	local_root = promise_run(recipe['site'])
	# +++ assume we want the Volume.local method to mount this volume
	# we connect the spot from the recipe to the root for container volume
	volume = dict(root=local_root)
	ReplicateCore(line=cmd,visit=visit,volume=volume,image=image)

def docker_shell(recipe,*args):
	cmd = ' '.join(args)
	ReplicateCore(root=os.getcwd(),
		line=cmd,visit=False,
		#! fix this
		image='factory:centos7_user')

def screen(screen='screen_anon',*args,**kwargs):
	"""
	Run anything in a screen using `ReplicatorCore`.
	e.g. make screen screen=anon script specs/demo_script.yaml delay spot=./here
	"""
	# note that running in a remote location typically uses a 'spot' flag
	#   however everything is passed through so the reciever has to accept it
	cmd = feedback_args_to_command(*args,**kwargs)
	ReplicateCore(script=cmd,screen=screen)

#!/usr/bin/env python

"""
Command-line hooks that supply an interface to replicator functions
so that you can execute different commands inside of alternate environments.
"""

import sys,os
import ortho
from ortho.replicator.replicator_dev import ReplicateCore
from ortho.replicator.replicator_dev import RecipeRead
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

	# STEP A: get the recipe
	#! intervene here with a basic default recipe if no yaml?
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
	ReplicateCore(line=cmd,visit=visit,volume=recipe['site'],image=image)

def docker_shell(recipe,*args):
	raise Exception('dev')
	cmd = ' '.join(args)
	ReplicateCore(root=os.getcwd(),
		line=cmd,visit=False,
		#! fix this
		image='factory:centos7_user')

def screen(*args,**kwargs):
	"""
	Run anything in a screen using `ReplicatorCore`.
	e.g. make screen screen=anon script specs/demo_script.yaml delay spot=./here
	"""
	screen_name = kwargs.pop('screen','screen_anon')
	# note that running in a remote location typically uses a 'spot' flag
	#   however everything is passed through so the reciever has to accept it
	cmd = feedback_args_to_command(*args,**kwargs)
	ReplicateCore(script=cmd,screen=screen_name)

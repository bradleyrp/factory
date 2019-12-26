#!/usr/bin/env python

"""
Command-line hooks that supply an interface to replicator functions
so that you can execute different commands inside of alternate environments.
!! Note that this file works with replicator_dev.py closely and we might wish
to consolidate these.
"""

import sys,os
import ortho
from ortho.replicator.replicator_dev import ReplicateCore
from ortho.replicator.replicator_dev import RecipeRead
from ortho.replicator.replicator_dev import SpotPath
from ortho import requires_python_check
#! deprecated replicator_read_yaml,many_files
from ortho import path_resolver

def feedback_args_to_command(*args,**kwargs):
	"""
	Convert arguments back into a command which is composed with a replicator.
	This function helps us to reconstitute arguments when calling the make/fac
	interface from a replicator method such as screen or docker.
	"""
	here = os.getcwd()
	#cmd = "make -C %s "%here+' '.join(args)
	#! fac has no path variable
	cmd = "cd %s "%here + "&& ./fac "+' '.join(args)
	# note that we use the make syntax here rather than ./fac
	if kwargs: cmd += ' '+' '.join(['%s=%s'%(i,j) for i,j in kwargs.items()])
	return cmd

def docker(recipe,*args,name=None,**kwargs):
	"""
	Run anything in a docker using `ReplicatorCore`.
	make docker spot=./here script specs/demo_script.yaml delay
	"""
	visit = kwargs.pop('visit',False)

	# transform incoming arguments to RecipeRead
	kwargs_recipe_read = {}
	if kwargs: raise Exception('unprocessed kwargs: %s'%kwargs)
	# we must use kwargs to handle the combinations of arguments
	# the only exception is a single argument which is a spec file
	if not name and len(args)==1: name,args = args[0],()
	if name: kwargs_recipe_read['subselect_name'] = name

	# STEP A: get the recipe
	#! intervene here with a basic default recipe if no yaml?
	# a path to a recipe file skips all of the gathering
	if os.path.isfile(recipe):
		# test: make docker specs/recipes/basics_redev.yaml
		recipe_pack = RecipeRead(path=recipe,**kwargs_recipe_read).solve
	else: raise Exception('dev')
	# unpack the recipe
	recipe = recipe_pack['recipe']
	ref = recipe_pack['ref']
	
	# STEP B: translate recipe into call to ReplicateCore
	# empty arguments triggers a visit to the container

	# use of explicit kwargs for name, spec above mean that args can
	#   pass through to another call to fac to nest/compose the replicator
	if not args: cmd,visit = '/bin/bash',True
	# the following allows args to be reformulated for fac specifically
	else: cmd = feedback_args_to_command(*args,**kwargs)

	image = recipe['image_name']
	# bundle the compose portion in case we need to build
	compose_bundle = dict(
		dockerfile=recipe.get('dockerfile'),
		compose=recipe.get('compose'),
		# dockerfile reference comes from the dockerfiles key on the parent
		#   file but can be imported there from another file
		#! note that this scheme does not allow dockerfiles from many sources
		dockerfiles_index=ref['dockerfiles'])
	# the reference data that is paired with recipe from RecipeRead passes
	#   through to meta for the handler so ReplicateCore methods have access
	ReplicateCore(line=cmd,visit=visit,
		volume=recipe['site'],image=image,
		compose_bundle=compose_bundle,meta=ref)

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

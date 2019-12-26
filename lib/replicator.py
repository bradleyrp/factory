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
#! from ortho.replicator.replicator import replicator_read_yaml,many_files
from ortho import path_resolver

"""
note that import of replicator_dev also provides handlers
including !spots and !selector
"""

def constructor_site_hook(loader,node):
	"""
	Use this as a constructor for the `!spots` yaml tag to get an alternate
	location for running something. Works with SpotPath and sends to Volume.
	"""
	name = loader.construct_scalar(node)
	# process the site
	from ortho import conf
	spots = conf.get('spots',{})
	if name in spots: 
		return SpotPath(**spots[name]).solve
	# the root keyword points to the local directory
	elif name=='root': return dict(local='./')
	# pass through the name for a literal path
	else: return dict(local=name)

def subselect_hook(loader,node):
	"""Select a portion of a recipe."""
	# note that ortho.replicator.replicator_dev is expecting this function
	#   to make a subselection and identifies the function below by name
	subtree = loader.construct_mapping(node)
	def tree_subselect(name):
		"""Promote a child node to the parent to whittle a tree."""
		return subtree.get(name)
	return tree_subselect

def spec_import_hook(loader,node):
	"""Import another spec file."""
	requires_python_check('yaml')
	import yaml
	this = loader.construct_mapping(node)
	parent_fn = loader.name
	if not os.path.isfile(parent_fn):
		raise Exception('failed to check file: %s'%parent_fn)
	# import from the other file as either relative or absolute path
	path = os.path.join(os.path.dirname(parent_fn),this['from'])
	if not os.path.isfile(path):
		path = os.path.realpath(this['from'])
		if not os.path.isfile(path):
			raise Exception('cannot find: %s'%this['from'])
	with open(path) as fp: 
		imported = yaml.load(fp,Loader=yaml.Loader)
	if this['what'] not in imported:
		raise Exception('cannot find %s in %s'%(this['what'],this['from']))
	return imported[this['what']]

# package hooks
yaml_hooks = {
	'!spots':constructor_site_hook,
	'!select':subselect_hook,
	'!import_spec':spec_import_hook,}

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
		recipe_pack = RecipeRead(path=recipe,hooks=yaml_hooks,
			**kwargs_recipe_read).solve
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
		compose=recipe.get('compose'))
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

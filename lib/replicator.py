#!/usr/bin/env python

"""
Command-line hooks that supply an interface to replicator functions
so that you can execute different commands inside of alternate environments.
!! Note that this file works with replicator_dev.py closely and we might wish
to consolidate these.
"""

import sys,os,copy
import ortho
from ortho.replicator.replicator_dev import ReplicateCore
from ortho.replicator.replicator_dev import RecipeRead
from ortho.replicator.replicator_dev import SpotPath
from ortho import requires_python_check
#! deprecated replicator_read_yaml,many_files
from ortho import path_resolver
from ortho import Handler
from ortho import catalog,delveset

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

class ReplicateWrap(Handler):
	def std(self,args,site,image_name,command,compose,dockerfile,notes=None):
		"""Standard method for translating a recipe into a ReplicateCore."""
		# STEP B: translate recipe into call to ReplicateCore
		# empty arguments triggers a visit to the container
		# use of explicit kwargs for name, spec above mean that args can
		#   pass through to another call to fac to nest/compose the replicator
		if not args: cmd,visit = '/bin/bash',True
		# the following allows args to be reformulated for fac specifically
		else: cmd = feedback_args_to_command(*args,**kwargs)
		ref = self.meta
		# bundle the compose portion in case we need to build
		compose_bundle = dict(
			dockerfile=dockerfile,
			compose=compose,
			# dockerfile reference comes from the dockerfiles key on the parent
			#   file but can be imported there from another file
			#! note that this scheme does not allow dockerfiles from many sources
			dockerfiles_index=ref['dockerfiles'])
		# the reference data that is paired with recipe from RecipeRead passes
		#   through to meta for the handler so ReplicateCore methods have access
		ReplicateCore(line=cmd,visit=visit,
			volume=site,image=image_name,
			compose_bundle=compose_bundle,meta=ref)

	def via(self,via,args=None,mods=None,notes=None):
		"""Extend one recipe with another."""
		if not mods: mods = {}
		recipe_pack = self.meta
		# assemble the entire tree of selections
		from ortho.replicator.replicator_dev import get_recipe_subselector
		subselect_func = get_recipe_subselector(recipe_pack['parent'])
		recipe_tree = subselect_func(name=None)
		# collect via DAG in from the full tree of recipes under the select tag
		vias = dict([(i,j['via']) for i,j in recipe_tree.items() if 'via' in j])
		paths = {}
		via_keys = list(vias.keys())
		for key in via_keys:
			paths[key] = [key]
			val = key
			while val in vias:
				key_this = vias[val]
				if key_this in paths[key]:
					raise Exception(('detected circular reference in "via" '
						'methods starting from: %s: %s')%(key,str(paths[key])))
				else: paths[key].append(key_this)
				val = key_this
		# construct a path through via arguments
		if via not in paths: 
			first = via
			paths_this = []
		else:
			paths_this = tuple(paths[via])[::-1]
			first = tuple(paths[via])[-1]
		#! protection against an upstream parent that is also a via recipe?
		# recurively update the recipe
		outgoing = copy.deepcopy(recipe_tree[first])
		if 'via' in outgoing: raise Exception('root recipe has via')
		# apply mods for the entire loop
		for stage in paths_this:
			print('status applying recipe "%s"'%stage)
			mods_this = recipe_tree[stage].pop('mods',{})
			if mods_this:
				for path,value in catalog(mods_this):
					delveset(outgoing,*path,value=value)
		# apply the final set of mods for the leaf recipe
		for path,value in catalog(mods_this):
			delveset(outgoing,*path,value=value)
		import ipdb;ipdb.set_trace()
		# make sure the last modifications are the ones for this recipe
		return self.std(args=args,**outgoing)

	# inspecting old code
	if 0:
		fname = self._classify(*self.meta['complete'][first].keys())
		if fname=='via': 
			raise Exception(
				'eldest parent of this "via" graph needs a parent: %s'%str(
					paths_this))
		outgoing = copy.deepcopy(self.meta['complete'][first])
		for stage in paths_this[1:]:
			outgoing.update(**copy.deepcopy(self.meta['complete'][stage].get('overrides',{})))
		# for the simplest case we must apply the overrides
		outgoing.update(**overrides)
		#!!! this needs tested!
		# the mods keyword can be used to surgically alter the tree of hashes
		if mods:
			for path,value in catalog(mods):
				delveset(outgoing,*path,value=value)
		# via calls docker_compose typically
		#! make sure the following does not cause conflicts
		outgoing['indirect'] = False
		#! pass cname from CLI to the target function
		if cname: outgoing['cname'] = cname
		getattr(self,fname)(**outgoing)

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
	# STEP A: get the recipe note that step B occurs in ReplicateWrap
	#! intervene here with a basic default recipe if no yaml?
	# a path to a recipe file skips all of the gathering
	if os.path.isfile(recipe):
		# test: make docker specs/recipes/basics_redev.yaml
		recipe_pack = RecipeRead(path=recipe,**kwargs_recipe_read).solve
	else: raise Exception('dev')
	# unpack the recipe
	recipe = recipe_pack['recipe']
	ref = recipe_pack['ref']
	# further steps are handled elsewhere to account for different recipes
	# we cannot encode recursion through multiple "via" keys by directly
	#   calling the ReplicateWrap with the current recipe hence we have a 
	#!! is this true?
	recipe_out = ReplicateWrap(meta=recipe_pack,args=args,**recipe)

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

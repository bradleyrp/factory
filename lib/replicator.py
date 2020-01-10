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
	A composition: allow `./fac docker` to host another `./fac` command.
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
	def std(self,args,image_name,compose,dockerfile,
		site=None,command=None,notes=None,script=None,visit=False,
		#! note that there is kwargs bloat here
		# user-facing meta-level arguments
		nickname=None,rebuild=False,unlink=False,
		macos_gui=False):
		"""Standard method for translating a recipe into a ReplicateCore."""
		if args and command:
			raise Exception(
				'cannot choose between args and command: "%s" vs "%s"'%
				(str(args),command))
		elif args and not command:
			# arguments trigger a composed/recursive call to the factory
			command = feedback_args_to_command(*args,**kwargs)
			mode = 'compose'
		elif not args and command: 
			mode = 'compose'
		elif not args and not command:
			# visit if empty arguments and no command from the recipe
			command = '/bin/bash'
			mode = 'visit'
		else: raise Exception('invalid')
		# pass the reference data
		ref = self.meta.get('ref',{})

		# bundle the compose portion in case we need to build
		compose_bundle = dict(
			dockerfile=dockerfile,
			compose=compose,
			# dockerfile reference comes from the dockerfiles key on the parent
			#   file but can be imported there from another file
			#! note this scheme does not allow dockerfiles from many sources
			dockerfiles_index=ref.get('dockerfiles'))

		# the reference data that is paired with recipe from RecipeRead passes
		#   through to meta for the handler so ReplicateCore methods can see
		# nickname and mode come from the code. the rest comes from the recipe
		ReplicateCore(mode=mode,
			# user-facing meta-level arguments from the CLI
			nickname=nickname,rebuild=rebuild,
			visit=visit,macos_gui=macos_gui,unlink=unlink,
			volume=site,image=image_name,line=command,
			compose_bundle=compose_bundle,meta=ref)

	def via(self,via,args=None,mods=None,notes=None,
		# user-facing meta-level arguments
		nickname=None,rebuild=False,unlink=False):
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
		for path,value in catalog(mods):
			delveset(outgoing,*path,value=value)
		# make sure the last modifications are the ones for this recipe
		return self.std(args=args,
			# user-facing meta-level arguments
			nickname=nickname,rebuild=rebuild,unlink=unlink,
			**outgoing)

def docker(recipe,*args,name=None,unlink=False,rebuild=False,**kwargs):
	"""
	Run anything in a docker using `ReplicatorCore`.
	make docker spot=./here script specs/demo_script.yaml delay
	"""
	#! is this deprecated by the new workflow
	visit = kwargs.pop('visit',False)
	# transform incoming arguments to RecipeRead
	kwargs_recipe_read = {}
	if kwargs: raise Exception('unprocessed kwargs: %s'%kwargs)
	# we must use kwargs to handle the combinations of arguments
	# the only exception is a single argument which is a spec file
	if not name and len(args)==1: name,args = args[0],()
	if name: kwargs_recipe_read['subselect_name'] = name
	# STEP A: get the recipe. note that step B occurs in ReplicateWrap
	#! intervene here with a basic default recipe if no yaml?
	if os.path.isfile(recipe):
		# test: make docker specs/recipes/basics_redev.yaml
		recipe_pack = RecipeRead(path=recipe,**kwargs_recipe_read).solve
	else: raise Exception('dev')
	# unpack the recipe
	recipe = recipe_pack['recipe']
	recipe_out = ReplicateWrap(meta=recipe_pack,args=args,
		# user-facing meta-level arguments
		nickname=name,rebuild=rebuild,unlink=unlink,
		**recipe)

def compose_cleanup(dn,sure=False):
	"""Clean up a compose link from ReplicateCore."""
	from ortho import confirm
	import shutil
	if not os.path.islink(dn):
		raise Exception('not a link: %s'%dn)
	if sure or confirm('okay to remove %s'%dn):
		remote = os.readlink(dn)
		print('status removing %s'%remote)
		shutil.rmtree(remote)
		print('status removing %s'%dn)
		os.unlink(dn)
		return True
	else: return False

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

#!/usr/bin/env python

import os,copy
import ortho
import yaml
from lib.yaml_mods import YAMLObjectInit
from ortho import Handler
from ortho import path_resolver
from ortho import catalog
from ortho import delveset

#! note hardcoded default below needs a way to define the defaults with a dict
#!   merge on the incoming tree but this depends on its structure

# builtin defaults for the spack tree (override in the yaml root)
#! note that there is no CLI override yet
spack_tree_defaults = {
	'spot':'./local',
	'spot_envs':'./local/envs_spack',}

#! config mappings see "+++ add" below and consider standardizing this?
#!   spot in spack tree > spack in the config
#!   spot_envs in spack tree > spack_envs in the config

def spack_clone(where=None):
	"""
	Clone a copy of spack for local use.
	"""
	# hardcoded default
	where = where or 'local'
	where = path_resolver(where)
	os.makedirs(where,exist_ok=True)
	# the clone target must be called spack
	if where.split(os.path.sep)[-1]=='spack':
		raise Exception('invalid path cannot end in "spack": %s'%where)
	print('status cloning spack at %s'%where)
	ortho.bash('git clone https://github.com/spack/spack',cwd=where)
	#! should we have a central conf registrar?
	ortho.conf['spack'] = os.path.join(where,'spack')
	# +++ add spack location to the conf
	ortho.write_config()
	#! should we confirm the spack clone and commit?
	return ortho.conf['spack']

def spack_init_envs(where=None):
	"""
	Make a directory for spack environments.
	"""
	#! this logic is wrong we should get this from the config.json ...!!!
	# hardcoded default
	where = where or 'local/envs_spack'
	where = path_resolver(where)
	if not os.path.isdir(where): 
		print('status initializing spack environments at %s'%where)
		os.makedirs(where,exist_ok=True)
	# +++ add spack envs location to the conf
	ortho.conf['spack_envs'] = where
	ortho.write_config()
	return where

def config_or_make(config_key,builder,where=None):
	"""
	Check the config for a key otherwise build the target.
	"""
	# check the config for the target
	target = ortho.conf.get('spack',None)
	#! tell ther user if the target goes missing?
	if not target or not os.path.isdir(target): 
		return builder(where=where)
	else: return target

class SpackEnvMaker(Handler):
	def _run_via_spack(self,spack_spot,env_spot,command):
		starter = os.path.join(spack_spot,'share/spack/setup-env.sh')
		#! replace this with a pointer like the ./fac pointer to conda?
		ortho.bash('source %s && %s'%
			(starter,command),cwd=env_spot)
	def std(self,spack,where,spack_spot):
		os.makedirs(where,exist_ok=True)
		with open(os.path.join(where,'spack.yaml'),'w') as fp:
			yaml.dump({'spack':spack},fp)
		self._run_via_spack(spack_spot=spack_spot,env_spot=where,
			command='spack concretize -f')

def spack_env_maker(what):
	"""
	Command line interface to install a spack environment.
	#! previously this was exposed to the CLI so you could directly
	#!   use a yaml in a spack environment
	"""
	spack = ortho.conf.get('spack',None)
	if not spack: spack_clone()
	with open(what) as fp: 
		instruct = yaml.load(fp,Loader=yaml.SafeLoader)
	SpackEnvMaker(spack_spot=spack,**instruct).solve

class SpackEnvSeqItem(Handler):
	"""
	Convert an item
	"""
	def via(via,**kwargs):
		import ipdb;ipdb.set_trace()

class SpackSeq(Handler):
	def seq_envs(self,envs,notes=None):
		"""
		Install a sequence of spack environments.
		"""
		# configure paths from parent: self.meta
		spack_dn = config_or_make(
			config_key='spack',builder=spack_clone,
			where=self.meta.get('spot'))
		spack_envs_dn = config_or_make(
			config_key='spack_envs',builder=spack_init_envs,
			where=self.meta.get('spot_envs'))
		for env in envs:
			name = env.pop('name')
			spot = os.path.join(spack_envs_dn,name)
			# typically use a Handler here but we need meta so simplifying
			if 'via' in env.keys():
				# start with a template from the parent file in meta
				instruct = copy.deepcopy(self.meta[env.pop('via')])
				# merge the trees
				for route,val in catalog(env):
					delveset(instruct,*route,value=val)
			else: raise Exception('unclear env format')
			print('status building spack environment at "%s"'%spot)
			SpackEnvMaker(spack_spot=spack_dn,where=spot,spack=instruct)

class SpackSeqSub(Handler):
	_internals = {'name':'basename','meta':'meta'}
	def subselect(self,name,tree):
		"""
		One file and one choice (the name selects 
		part of the tree to run). 
		#! Consider a name for this pattern?
		"""
		self.name = name
		# builtin defaults from a dictionary above
		self.tree = copy.deepcopy(spack_tree_defaults)
		self.tree.update(**tree)
		self.deploy = SpackSeq(meta=self.tree,**tree[name])
		return self

def spack_tree(what,name):
	"""
	Install a sequence of spack environments.
	"""
	notes = """
		reqs:
			lib/spack.py
			specs/spack_tree.yaml
			specs/cli_spack.yaml
		use:
			make use specs/cli_spack.yaml
			make spack_tree specs/spack_tree.yaml seq01
		pseudocode:
			command provides a file and a name
			name is a key in the file
			SpackSeqSub has the global scope of the file in meta
			and sends the subtree keyed by name to SpackSeq
			which use Handler to install packages with spack
		clean:
			rm -rf config.json local && python -c "import ortho;ortho.conf['replicator_recipes'] = 'specs/recipes/*.yaml';ortho.write_config(ortho.conf)" && make use specs/cli_spack.yaml
		test:
			make spack_tree specs/spack_tree.yaml gromacs_gcc6
	"""
	print('status installing spack seq from %s with name %s'%(what,name))
	with open(what) as fp: 
		tree = yaml.load(fp,Loader=yaml.SafeLoader)
	SpackSeqSub(name=name,tree=tree).solve

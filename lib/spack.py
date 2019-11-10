#!/usr/bin/env python

import os,copy
import ortho
import yaml
from lib.yaml_mods import YAMLObjectInit
from ortho import Handler

def spack_clone(where=None):
	"""
	Clone a copy of spack for local use.
	"""
	where = where or 'local'
	os.makedirs(where,exist_ok=True)
	if where.split(os.path.sep)[-1]=='spack':
		raise Exception('invalid path cannot end in "spack": %s'%where)
	ortho.bash('git clone https://github.com/spack/spack',cwd=where)
	#! should we have a central conf registrar?
	ortho.conf['spack'] = os.path.realpath(os.path.join(where,'spack'))
	# +++ add spack location to the conf
	ortho.write_config()
	#! should we confirm the spack clone and commit?
	return ortho.conf['spack']

def get_spack(where=None):
	"""
	Ensure that we have an active copy of spack.
	"""
	# get spack and clone it again if missing
	spack = ortho.conf.get('spack',None)
	if not spack or not os.path.isdir(spack): 
		return spack_clone(where=None)
	else: return spack

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
	"""
	spack = ortho.conf.get('spack',None)
	if not spack: spack_clone()
	with open(what) as fp: 
		instruct = yaml.load(fp,Loader=yaml.SafeLoader)
	print(instruct)
	SpackEnvMaker(spack_spot=spack,**instruct).solve

class SpackSeq(Handler):
	def seq_envs(self,envs):
		"""
		Install a sequence of spack environments.
		"""
		# set the spack spot in the tree to override default
		#! should the user also set the spot from the CLI?
		spack_dn = get_spack(where=self.meta.get('spot'))
		import ipdb;ipdb.set_trace()

class SpackSeqSub(Handler):
	_internals = {'name':'basename','meta':'meta'}
	def subselect(self,name,tree):
		self.name = name
		self.tree = tree
		self.deploy = SpackSeq(meta=tree,**tree[name])
		return self

def spack_seq_maker(what,name):
	"""
	Install a sequence of spack environments.
	"""
	print('status installing spack seq from %s with name %s'%(what,name))
	"""
	reqs:
		lib/spack.py
		specs/spack_tree.yaml
		specs/cli_spack.yaml
	use this with:
		make use specs/cli_spack.yaml
		make spack_seq specs/spack_tree.yaml seq01
	pseudocode:
		command provides a file and a name
		file and name go to a subselector handler which just applies one
	"""
	with open(what) as fp: tree = yaml.load(fp,Loader=yaml.SafeLoader)
	this = SpackSeqSub(name=name,tree=tree).solve
	import ipdb;ipdb.set_trace()
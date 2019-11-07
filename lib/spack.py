#!/usr/bin/env python

import os,copy
import ortho
import yaml
from lib.yaml_mods import YAMLObjectInit
from ortho import Handler

class OrthoSync(YAMLObjectInit):
	"""Trivial wrapper around ortho sync."""
	#! find a more elegant, perhaps automatic way to do this? or is this a hook?
	yaml_tag = '!ortho_sync'
	def __init__(self,**kwargs):
		self.sources = kwargs
		if kwargs.get('until',False): return
		else: self._run()
	def _run(self):
		# reformulate the modules
		kwargs_out = {}
		for key in self.sources:
			spot = self.sources[key]['spot']
			if spot in kwargs_out:
				raise Exception('repeated key: %s'%spot)
			kwargs_out[spot] = dict([(i,j) 
				for i,j in self.sources[key].items()
				if i!='spot'])
		ortho.sync(modules=kwargs_out)

class SpackManager(YAMLObjectInit):
	yaml_tag = '!SpackManager'
	def __init__(self,source,apps,envs):
		"""
		Deploy spack.
		"""
		print('status starting SpackManager')
		# the source should be an !ortho_sync to clone spack
		self.source = source
		self.envs = envs
		self.apps = apps
		# this root object is prepared last so we actually install the 
		#   environments here, passing down the source
		for env in self.envs: 
			env.go(source=self.source)

class SpackEnvManager(YAMLObjectInit):
	yaml_tag = '!spack_env'
	def __init__(self,spack,spot,apps):
		self.spack = spack
		self.spot = spot
		self.apps = apps
	def go(self,source):
		"""
		Execute a spack installation in a spack environment.
		"""
		print('status starting SpackEnvManager: %s'%self.spot)
		# get the prefix for the environment
		self.source = source
		self.prefix = '. %s && '%(
			os.path.join(os.getcwd(),self.source.sources['spack']['spot'],
			'share/spack/setup-env.sh'))
		# make the environment folder
		if not os.path.isdir(self.spot):
			os.mkdir(self.spot)
		# augment the environment
		self.spack['config'] = {
			'install_tree':self.apps.spot,
			'checksum':False,} 
		with open(os.path.join(self.spot,'spack.yaml'),'w') as fp:
			yaml.dump({'spack':self.spack},fp)
		ortho.bash(self.prefix+' spack install',
			cwd=self.spot,log='log-spack')

class SpackTree(yaml.YAMLObject):
	yaml_tag = '!spack_tree'
	def __init__(self,spot):
		self.spot = spot
		if not os.path.isdir(self.spot):
			os.mkdir(self.env)

#!!! redeveloping here

def spack_clone(where='local'):
	"""
	Clone a copy of spack for local use.
	"""
	os.makedirs(where,exist_ok=True)
	if where.split(os.path.sep)[-1]=='spack':
		raise Exception('invalid path cannot end in "spack": %s'%where)
	ortho.bash('git clone https://github.com/spack/spack',cwd=where)
	#! should we have a central conf registrar?
	ortho.conf['spack'] = os.path.realpath(os.path.join(where,'spack'))
	ortho.write_config()

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
	Install a spack environment.
	"""
	spack = ortho.conf.get('spack',None)
	if not spack: spack_clone()
	with open(what) as fp: 
		instruct = yaml.load(fp,Loader=yaml.SafeLoader)
	print(instruct)
	SpackEnvMaker(spack_spot=spack,**instruct).solve

#!/usr/bin/env python

import os,copy
import ortho
import yaml
from lib.yaml_mods import YAMLObjectInit

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
		for key in kwargs:
			spot = kwargs[key]['spot']
			if spot in kwargs_out:
				raise Exception('repeated key: %s'%spot)
			kwargs_out[spot] = dict([(i,j) 
				for i,j in kwargs[key].items()
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

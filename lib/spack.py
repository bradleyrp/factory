#!/usr/bin/env python

import ortho
from lib.yaml_mods import YAMLObjectInit

class OrthoSync(YAMLObjectInit):
	"""Trivial wrapper around ortho sync."""
	#! find a more elegant way to do this
	yaml_tag = '!ortho_sync'
	def __init__(self,**kwargs):
		print('status sync: %s'%str(kwargs))
		ortho.sync(modules=kwargs)

class SpackManager(YAMLObjectInit):
	"""
	# (. spack/share/spack/setup-env.sh && spack spec gromacs)
	"""
	yaml_tag = '!SpackManager'
	def __init__(self,source,packages,spot,env):
		"""
		Deploy spack.
		"""
		print('status starting SpackManager')
		# the source should bae an !ortho_sync to clone spack
		self.source = source
		
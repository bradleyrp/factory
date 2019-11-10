#!/usr/bin/env python

from lib.yaml_mods import YAMLObjectInit

class OrthoSync(YAMLObjectInit):
	"""Trivial wrapper around ortho sync."""
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
		from ortho import sync
		sync(modules=kwargs_out)

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

### YAML examples

class ExampleYAMLClass(YAMLObjectInit):
	"""An example class called via yaml."""
	yaml_tag = "!example_yaml_class"
	def __init__(self,*args,**kwargs):
		print(('status created %s object with: '
			'args = %s and kwargs = %s'%(self.__class__.__name__,
				str(args),str(kwargs))))
		self.args = args
		self.kwargs = kwargs
		# cli.Interface.do discards the object so we take action here
		self.method()
	def method(self):
		"""Example method."""
		print('status example method for %s'%self)
		print('status the object is: %s'%str(self.__dict__))

def example_yaml_function(*args,**kwargs):
	"""An example function called via yaml."""
	print('args = %s and kwargs = %s'%(str(args),str(kwargs)))
	# the following return value goes back to cli.Interface.do and is unused
	return 'meaningless'

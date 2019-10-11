#!/usr/bin/env python

from ortho.yaml_mods import YAMLObjectInit

class Program(YAMLObjectInit):
	"""
	Manage assoiciated applications.
	"""
	yaml_tag = '!program'
	def __init__(self,**kwargs):
		print('status Program: %s'%str(kwargs))
		import ipdb;ipdb.set_trace()

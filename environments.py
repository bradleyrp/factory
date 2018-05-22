#!/usr/bin/env python

from __future__ import print_function
from __future__ import unicode_literals
import sys,os

class Factory:
	def __init__(self,*args,**kwargs):
		self.conf = conf # pylint: disable=undefined-variable
		self.envs = self.conf.get('envs',{})
		self.logs_space()
		if not self.envs: raise Exception('no environments yet!')
		for name,detail in self.envs.items(): self.validate(name,detail)
	def logs_space(self):
		"""Logs are always written to the same place."""
		if not os.path.isdir('logs'): os.mkdir('logs')
	def validate(self,name,detail):
		"""Check or create an environment."""
		where = detail.pop('where')
		sources = detail.pop('sources')
		style = detail.pop('style')
		install_commands = detail.pop('install_commands',install_defaults[style])
		raise Exception('dev')

def env(*args,**kwargs): Factory(*args,**kwargs)

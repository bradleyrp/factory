#!/usr/bin/env python

import os
import ortho
from ortho import path_resolver

class MacosImager:
	"""
	Confirm or create an image on macos.
	"""
	def register_spots(self,name,**detail):
		"""
		Add a "spot" i.e. a disk location to the config.
		"""
		#! generalize this pattern somewhere?
		if 'spots' not in ortho.conf:
			ortho.conf['spots'] = {}
		ortho.conf['spots'][name] = detail
		ortho.write_config()
	def __init__(self,name,mount,path,size='1g',fs='hfsx',sparse=False):
		if sparse and not path.endswith('.sparseimage'):
			raise Exception('spare image paths must end with .sparseimage '
				'but this path is: %s'%path)
		if os.path.isfile(path):
			self.register_spots(name,dmg=path,mount=mount)
		else: 
			"""
			hdiutil create -size 10g -type SPARSE -fs hfsx ./nix.dmg 
			# creates nix.dmg.sparseimage so be careful with the name
			hdiutil attach -nobrowse -mountpoint nix nix.dmg.sparseimage
			hdiutil detach nix
			"""
			raise Exception('dev: need to build the image here')

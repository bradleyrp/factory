#!/usr/bin/env python

""" #!!!!!!!!!!!!!! put this in a readme
How to use standard hooks:
Run the following command, replacing hook_name, filename, and function:
	make set_hook HOOK_NAME="\"{'s':'FILENAME','f':'FUNCTION'}\""
The filename should be this file. The function should be a function in this file.
The hook_name can be used in the following code.
	...!!!

How to use a hook collection:
Run the following command, replacing hook_name, filename, and function:
	make set_hook HOOK_NAME="\"{'s':'FILENAME','collect':True}\""
	make set_hook replicator_hooks="\"{'s':'hooks/macos_vagrant.py','collect':True}\""
...!!!
"""

import os
import ortho
from ortho import Handler

# this file extends the existing replicator classes
from ortho.replicator.formula import *

#! full on override
#! adding to an existing class??? is this how you do it?
class ReplicatorGuide(ReplicatorGuide):
	def singularity_via_vagrant(self,site,singularity_version):
		"""
		Run something in Singularity in Vagrant (on macos).
		"""
		recipe = """
		vagrant init singularityware/singularity-%(singularity_version).1f
		vagrant up
		vagrant ssh
		"""%dict(singularity_version=singularity_version)
		spot = SpotLocal(site=site,persist=True)
		for line in recipe.strip('\n').splitlines(): 
			ortho.bash(line.strip(),cwd=spot.abspath,announce=True)

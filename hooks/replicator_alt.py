#!/usr/bin.

"""
EXTEND the ReplicatorGuide class
make set_hook replicator="\"{'s':'hooks/replicator_alt.py','f':'update_replicator_guide'}\""
"""

# import the class, subclass it, and export that inside a function
from ortho.replicator.formula import ReplicatorGuide

class ReplicatorGuide(ReplicatorGuide):
	def new_handler(self,param):
		# do things and return to ReplicatorGuide(param=1).solve
		return dict(result=123)

def update_replicator_guide(): 
	# this hook function adds the updated guide
	return dict(ReplicatorGuide=ReplicatorGuide)

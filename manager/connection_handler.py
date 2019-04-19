#!/usr/bin/env python

import glob,os
from ortho import Hook,requires_python

connection_spot = 'connections'

def read_connection(*args):
	"""
	Parse a connection yaml file.
	"""
	import yaml
	toc = {}
	for arg in args:
		with open(arg) as fp: 
			contents = yaml.safe_load(fp.read())
			for key,val in contents.items():
				if key in toc: 
					raise Exception(('found key %s in the toc already. '
						'redundant copy in %s')%(key,arg))
				toc.update(**{key:val})
	return toc

def connection_handler():
	"""
	Read connections from a standard location. 
	Returns a dictionary of connections.
	Hook with the "connection_handler" key in the config.
	"""
	connects = glob.glob(os.path.join(connection_spot,'*.yaml'))
	if not connects: raise Exception('no connections available. '
		'try `make template` for some examples.')
	toc = read_connection(*connects)
	return toc

@requires_python('yaml')
def template_to_connection(name,specs):
	"""Standard way to make a connection from a template."""
	import yaml
	if not os.path.isdir(connection_spot): os.mkdir(connection_spot)
	fn = '%s.yaml'%name
	fn_full = os.path.join(connection_spot,fn)
	if os.path.isfile(fn_full):
		raise Exception('cannot make template because %s exists'%fn_full)
	with open(fn_full,'w') as fp: 
		yaml.dump({name:specs},fp,default_flow_style=False)

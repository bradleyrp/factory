#!/usr/bin/env python

import re

__all__ = ['repl','pipe','test_clean','test_help','docker_clean']

# standard handlers from ortho
from .formula import *

from ortho import hook_merge
# +++ allow user to hook in other handlers here
hook_merge(hook='replicator',namespace=globals())

### READERS

@requires_python('yaml')
def replicator_read_yaml(source,name=None,args=None,kwargs=None):
	"""
	Read a replicator instruction and send it to the Guide for execution.
	"""
	import yaml
	with open(source) as fp: 
		# we load into a MultiDict to forbid spaces (replaced with 
		#   underscores) in top-level dictionary.
		instruct = MultiDict(base=yaml.load(fp.read()),
			underscores=True,strict=True)
	# special handling
	reference = {}
	# previously used custom taxonomy but here we infer it via inspect
	taxonomy_rs = ReplicatorSpecial(inspect=True).taxonomy
	for key in taxonomy_rs:
		if key in instruct: 
			reference[key] = ReplicatorSpecial(name=key,
				**{key:instruct.pop(key)})
	# leftovers from special handling must be tests
	if not name and len(instruct)>1: 
		raise Exception(
			('found multiple keys in source %s. you must choose '
				'one with the name argument: %s')%(source,instruct.keys()))
	elif not name and len(instruct)==1: 
		test_name = instruct.keys()[0]
		print('status','found one instruction in source %s: %s'%(
			source,test_name))
	elif name:test_name = name
	else: raise Exception('source %s is empty'%source)
	if test_name not in instruct: 
		raise Exception('cannot find replicate %s'%test_name)
	test_detail = instruct[test_name]
	reference['complete'] = instruct
	return dict(name=test_name,detail=test_detail,meta=reference)

### INTERFACE

def test_clean():
	#! needs more care?
	os.system(' rm -rf repl_*')

def docker_clean():
	"""Remove unused docker images and completed processes."""
	os.system('docker rm $(docker ps -a -q)')
	os.system('docker rmi $(docker images -f "dangling=true" -q)')

def repl(*args,**kwargs):
	"""
	Run a test.
	Disambiguates incoming test format and sends it to the right reader.
	Requires explicit kwargs from the command line.
	"""
	# allow args to be handled by the interface key for easier CLI
	if args:
		raise Exception('under construction')
		#! hard coded for now
		this_test = replicator_read_yaml(args=args,kwargs=kwargs,
			source='pipelines.yaml')
		#! import ipdb;ipdb.set_trace()
	# specific format uses only kwargs
	elif (set(kwargs.keys())<={'source','name'} 
		and re.match(r'^(.*)\.(yaml|yml)$',kwargs['source'])):
		this_test = replicator_read_yaml(**kwargs)
		# run the replicator
		rg = ReplicatorGuide(name=this_test['name'],
			meta=this_test['meta'],**this_test['detail'])
	else: raise Exception('unclear request')

# alias for the replicator
pipe = repl

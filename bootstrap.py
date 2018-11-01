#!/usr/bin/env python

from __future__ import print_function

"""
BOOTSTRAP the FACTORY configuration
"""

# default configuration is written to config.json on first make
default_configuration = {
	'commands':['manager','ortho/replicator/replicator.py','ortho/queue'],
	'docks_config':'ortho/replicator/docker_config.py',
	'user_creds':'password',
	'automacs':{'address':'http://github.com/biophyscode/automacs','branch':'ortho'},
	'omnicalc':{'address':'http://github.com/biophyscode/omnicalc','branch':'ortho'},
	'locks':['lock.queue'],
	'docs':{'list':{
		'factory':{'source':'manager/docs_source','build':'docs_factory'},
		'ortho':{'source':'ortho/docs_source','build':'docs_ortho'}}}}

def bootstrap_default(): return default_configuration
def bootstrap_post(): return

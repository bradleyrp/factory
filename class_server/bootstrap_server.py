#!/usr/bin/env python

"""
INSTRUCTIONS
# see bootstrap_server.yaml for some settings
make setlist commands class_server/bootstrap_server.py
# previously replicator_recipes = deploy_series_no*.yaml
make set replicator_recipes="class_server/deploy_*yaml"
make repl factory_server_base rebuild
make class_server_setup class_server/bootstrap_server.yaml && make repl c01
"""

import os
import json
import ortho
from ortho import Handler
from ortho import catalog
from ortho import delve

__all__ = ['class_server_setup']

replicate_template = """
%(name)s:
  via: factory_server_base
  mods:
    compose: 
      services:
        site:
          volumes:
            - ./:/home/user/extern
            - %(connections)s:/home/user/extern/server/factory/connections
          ports: 
            - "%(port_site)d:8000"
            - "%(port_note)d:8001"
          # entrypoint: ['/bin/bash']
          entrypoint: ['/bin/bash','script.sh']
          container_name: %(name)s
  overrides:
    # toggle this and above to run in foreground or background
    command: docker-compose up -d site
    # command: docker-compose run --service-ports site
    script: |
      cd server/factory
      rm -f pid* TASK_QUEUE
      make connect %(name)s
      make run %(name)s public
      sleep infinity
"""

connection_template = """
%(name)s:
  name: %(name)s
  calc_spot: calc/PROJECT_NAME
  plot_spot: data/PROJECT_NAME/plot
  post_spot: data/PROJECT_NAME/post
  calculations: 
    address: http://github.com/biophyscode/omnicalc
    branch: master
  public:
    port: 8000
    notebook_port: 8001
    hostname: localhost
    notebook_hostname: localhost
    notebook_port_apparent: %(port_note)s
    jupyter_localhost: 0.0.0.0
    credentials: {'stat':'mech'}
"""

class Site(Handler):
	def confirm(self,confirm):
		"""
		Check the configuration to confirm some keys.
		"""
		cat = list(catalog(confirm))
		for path,val in cat:
			print('status checking that config has %s set to %s'%(
				str(path),val))
			if delve(ortho.conf,*path)!=val:
				return False
		return True

class Containers(Handler):
	def main(self,number):
		start_port = 9001
		name = 'c%02d'
		connections_dn = os.path.join(os.getcwd(),'class_server','connections')
		with open('class_server/deploy_loop.yaml','w') as fp:
			for num in range(1,1+number):
				name_this = name%num
				print('status preparing %s'%name_this)
				detail = {'name':name_this,
					'port_site':start_port+num*2+0,
					'port_note':start_port+num*2+1,
					'connections':connections_dn}
				fp.write('\n'+replicate_template%detail)
		connection_fn = os.path.join(
			os.getcwd(),'class_server','connections',
			'server_connections.yaml')
		with open(connection_fn,'w') as fp:
			for num in range(1,1+number):
				name_this = name%num
				detail = {
					'port_note':start_port+num*2+2,
					'name':name_this}
				fp.write('\n'+connection_template%detail)

def class_server_setup(arg):
	"""
	Prepare commands for a server
	"""
	import yaml
	with open(arg) as fp:
		spec = yaml.load(fp)
	#! ignoring this check for now
	if False:
		has_site = Site(**spec['site']).solve
		if not has_site: raise Exception('site is not ready!')
	# how many containers
	Containers(**spec['containers']).solve
	print('status ready')
	print('status run `make repl factory_server_base rebuild` to build')
	print('status run `make repl <name>` to start the first container')
	print('status container names are given above')

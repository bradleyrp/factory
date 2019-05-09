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
        %(name)s_service:
          volumes:
            - ./:/home/user/extern
            - %(connections)s:/home/user/extern/server/factory/connections
          ports: 
            - "%(port_site)d:%(port_site)d"
            - "%(port_note)d:%(port_note)d"
          # entrypoint: ['/bin/bash']
          entrypoint: ['/bin/bash','script.sh']
          container_name: %(name)s
          image: factory:factory_server_base
  overrides:
    # toggle this and above to run in foreground or background
    command: docker-compose -p p_%(name)s up -d %(name)s_service 
    # command: docker-compose run --service-ports %(name)s_service
    script: |
      cd server/factory
      source /usr/local/gromacs/bin/GMXRC
      rm -f pid* TASK_QUEUE
      make connect %(name)s public
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

connection_template_legacy = """
# FACTORY PROJECT (the base case example "demo")
%(name)s:
  # include this project when reconnecting everything
  enable: true 
  site: site/PROJECT_NAME  
  calc: calc/PROJECT_NAME
  repo: http://github.com/biophyscode/omni-basic
  database: data/PROJECT_NAME/db.factory.sqlite3
  post_spot: data/PROJECT_NAME/post
  plot_spot: data/PROJECT_NAME/plot
  simulation_spot: data/PROJECT_NAME/sims
  development: True
  cluster: cluster/cluster-%(name)s
  gromacs_config: gromacs_config.py
  # serve the factory by running "make connect <name> public" and later "make run <name> public"
  public:
    port: %(port_site)s
    notebook_port: %(port_note)s
    # use "notebook_hostname" if you have a router or zeroes if using docker
    notebook_hostname: '0.0.0.0'
    # you must replace the IP address below with yours
    hostname: ['158.130.113.128','127.0.0.1']
    credentials: {'%(user)s':'%(pass)s'}
  # import previous data or point omnicalc to new simulations, each of which is called a "spot"
  # note that prepared slices from other integrators e.g. NAMD are imported via post with no naming rules
  spots:
    # colloquial name for the default "spot" for new simulations given as simulation_spot above
    sims:
      # name downstream postprocessing data according to the spot name (above) and simulation folder (top)
      # the default namer uses only the name (you must generate unique names if importing from many spots)
      namer: "lambda name,spot=None: name"
      # parent location of the spot_directory (may be changed if you mount the data elsewhere)
      route_to_data: data/PROJECT_NAME
      # path of the parent directory for the simulation data
      spot_directory: sims
      # rules for parsing the data in the spot directories
      regexes:
        # each simulation folder in the spot directory must match the top regex
        top: '(.+)'
        # each simulation folder must have trajectories in subfolders that match the step regex (can be null)
        # note: you must enforce directory structure here with not-slash
        step: '([stuv])([0-9]+)-([^\/]+)'
        # each part regex is parsed by omnicalc
        part: 
          xtc: 'md\.part([0-9]{4})\.xtc'
          trr: 'md\.part([0-9]{4})\.trr'
          edr: 'md\.part([0-9]{4})\.edr'
          tpr: 'md\.part([0-9]{4})\.tpr'
          # specify a naming convention for structures to complement the trajectories
          structure: '(system|system-input|structure)\.(gro|pdb)'
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
	def main(self,number,passwords={}):
		start_port = 9002
		name = 'c%02d'
		connections_dn = os.path.join(os.getcwd(),'class_server','connections')
		if not os.path.isdir(connections_dn):
			os.mkdir(connections_dn)
		with open('class_server/deploy_loop.yaml','w') as fp:
			for num in range(1,1+number):
				name_this = name%num
				print('status preparing %s'%name_this)
				detail = {'name':name_this,
					'port_site':start_port+(num-1)*2+0,
					'port_note':start_port+(num-1)*2+1,
					'connections':connections_dn}
				fp.write('\n'+replicate_template%detail)
		connection_fn = os.path.join(
			os.getcwd(),'class_server','connections',
			'server_connections.yaml')
		with open(connection_fn,'w') as fp:
			for num in range(1,1+number):
				name_this = name%num
				detail = {
					'port_site':start_port+(num-1)*2+0,
					'port_note':start_port+(num-1)*2+1,
					'user':passwords.get(name_this,{}).get('name','detailed'),
					'pass':passwords.get(name_this,{}).get('pass','balance'),
					'name':name_this}
				fp.write('\n'+connection_template_legacy%detail)

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

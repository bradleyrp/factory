#!/usr/bin/env python

import os,re,datetime,shutil,time,glob
import ortho
from ortho import read_config,Hook,treeview,Handler,str_types,mkdirs
from ortho import modules,check_port,backrun,tracebacker
from .deploy import start_site,start_cluster,start_notebook,stop_locked
from .sites import site_setup,abspath
from .settings import *

# hook to find connection files
default_connection_handler = {
	'source':'manager/connection_handler.py',
	'target':'connection_handler'}

# hook to get a function for sending templates to connection files
#! repetitive with the handler above
connection_to_template = {
	'source':'manager/connection_handler.py',
	'target':'template_to_connection'}

default_omnicalc_repo = 'https://github.com/biophyscode/omnicalc'

### COMMAND-LINE INTERFACE

class OmniFromFactory(Handler):
	"""
	Connect a connection.
	"""
	def connect(self,project_name,calc_spot,post_spot,settings_custom,
		plot_spot,sims=None,calculations=None):
		"""Basic connection from the factory to omnicalc."""
		self.config = read_config()
		# make directories minus calc spot which is cloned
		dns = [post_spot,plot_spot]+([sims] if sims!=None else [])
		for dn in dns:
			if dn==None: continue
			if not os.path.isdir(dn): mkdirs(dn)
		calc_root = os.path.join('calc',project_name)
		# clone omnicalc into the calculation folder
		modules_this = {calc_root:
			self.config.get('omnicalc',default_omnicalc_repo)}
		try: modules.sync(modules=modules_this,current=True)
		except Exception as e: 
			print('warning got error on sync: '+str(e))
			print('warning failed to sync the repo: %s'%modules_this)
		# clone and synchronize calculations reposotory
		if calculations: 
			modules_calcs_this = {
				os.path.join('calc',project_name,'calcs'):calculations}
			try: modules.sync(modules=modules_calcs_this)
			except: print('warning failed to sync the repo: %s'%
				modules_calcs_this)
		# update the postprocssing locations
		ortho.bash('make set post_plot_spot %s'%plot_spot,cwd=calc_root)
		ortho.bash('make set post_data_spot %s'%post_spot,cwd=calc_root)
		# prepare the site
		site_setup(project_name,settings_custom=settings_custom)

def connection_template(kind,name):
	"""Make a template and write the file."""
	config = read_config()
	connection_templates = {
		'basic':{
			'calc_spot':'calc/PROJECT_NAME',
			'post_spot':'data/PROJECT_NAME/post',
			'plot_spot':'plot/PROJECT_NAME/plot',},}
	template_handler = config.get(
		'connection_to_template',connection_to_template)
	hook = Hook(**template_handler)
	hook.function(name=name,specs=connection_templates[kind])

def get_connections(name):
	"""
	Get connections via hook.
	"""
	config = read_config()
	connection_handler = config.get(
		'connection_handler',default_connection_handler)
	hook = Hook(**connection_handler)
	toc = hook.function()
	if name not in toc: 
		treeview(dict(connections=toc.keys()))
		raise Exception(
			'cannot find connection in the list of connections above: %s'%name)
	return toc[name]

def prep_settings_custom(project_name,**specs):
	"""Prepare settings for Django."""
	# first define folders and (possibly) http git repos
	settings_custom = {
		'SIMSPOT':abspath(specs.get('simulation_spot',
			os.path.join('data',project_name,'sims'))),
		#! hard-coded. get it from config.py??
		'AUTOMACS':ortho.conf['automacs'],
		'PLOT':abspath(specs['plot_spot']),
		'POST':abspath(specs['post_spot']),
		#! what is the purpose of COORDS?
		'COORDS':abspath(specs.get('coords_spot',
			os.path.join('data',project_name,'coords')),),
		# omnicalc locations are fixed
		'CALC':abspath(os.path.join('calc',project_name)),
		'FACTORY':os.getcwd(),
		#! get this from config.py
		'CLUSTER':'cluster'}
	#! some items like the github links are going to become dictionaries soon
	for key,val in settings_custom.items():
		if not isinstance(val,str_types): settings_custom[key] = str(val)
	# all paths are absolute unless they have a colon in them, in which case it is ssh or http
	# we attach filesystem separators as well so that e.g. settings.SPOT can be added to relative paths
	settings_custom = dict([(key,os.path.join(os.path.abspath(val),'') if ':' not in val else val)
		for key,val in settings_custom.items()])

	#! previously in a separate file
	# cluster namer is set in a separate file
	cluster_namer = {}
	#with open('manager/cluster_spec.py') as fp: exec(fp.read(),cluster_namer) 
	"""
	File naming conventions for the "cluster".
	Important to the connection between factory and the cluster.
	"""
	cluster_namer = dict(
		keepsakes = 'waiting running finished'.split(),
		#---extract the stamp with e.g.: '^%s$'%re.sub('STAMP','(.+)',waiting)
		#---glob the files with e.g.: re.sub('STAMP','*',waiting)
		waiting = 'STAMP.req',
		running = 'run-STAMP',
		finished = 'fin-STAMP',
		)
	for key in [i for i in cluster_namer if i not in cluster_namer['keepsakes']]: del cluster_namer[key]

	settings_custom['CLUSTER_NAMER'] = cluster_namer
	# if the user does not supply a gromacs_config.py the default happens
	# option to specify gromacs config file for automacs
	if 'gromacs_config' in specs: 
		gromacs_config_fn = specs['gromacs_config']
		if not os.path.isfile(gromacs_config_fn):
			raise Exception('cannot find gromacs_config file at %s'%gromacs_config_fn)
		settings_custom['GROMACS_CONFIG'] = os.path.join(os.getcwd(),gromacs_config_fn)
	else: settings_custom['GROMACS_CONFIG'] = False
	# additional custom settings which are not paths
	# if there is a public dictionary and we receive the "public" flag from make we serve public site
	if specs.get('public',None):
		site_port = specs['public'].get('port',8000)
		#---the notebook IP for django must be the public hostname, however in the get_public_ports function
		#---...we have an internal notebook_hostname for users who have a router
		if 'hostname' not in specs['public']:
			raise Exception('for public deployment you must add the hostname to the connection')
		#---the hostnames are a list passed to ALLOWED_HOSTS starting with localhost
		if type(specs['public']['hostname']) in str_types: hostnames = [specs['public']['hostname']]
		elif type(specs['public']['hostname'])==list: hostnames = specs['public']['hostname']
		else: raise Exception('cannot parse hostname')
		hostnames.append('localhost')
		settings_custom['extra_allowed_hosts'] = list(set(hostnames))
		#---the first hostname is the primary one
		settings_custom['NOTEBOOK_IP'] = hostnames[0]
		settings_custom['NOTEBOOK_PORT'] = specs['public'].get('notebook_port',site_port+1)
	#---serve locally
	else:
		#---note that notebook ports are always one higher than the site port
		site_port = specs.get('port',8000)
		settings_custom['NOTEBOOK_IP'] = 'localhost'
		settings_custom['NOTEBOOK_PORT'] = specs.get('port_notebook',site_port+1)
		settings_custom['extra_allowed_hosts'] = []
	#---name this project
	settings_custom['NAME'] = project_name

	###---END DJANGO SETTINGS
	if False:
		#---make local directories if they are absent or do nothing if the user points to existing data
		root_data_dir = 'data/'+project_name
		#---always make data/PROJECT_NAME for the default simulation_spot therein
		mkdir_or_report(root_data_dir)
		for key in ['post_spot','plot_spot','simulations_spot']: 
			mkdir_or_report(abspath(specs[key]))
		#---we always include a "sources" folder in the new simulation spot for storing input files
		mkdir_or_report(abspath(specs.get('coords_spot',os.path.join('data',project_name,'coords'))))

		#---check if database exists and if so, don't make superuser
		make_superuser = not os.path.isfile(specs['database'])
	if False:
		#---get automacs,omnicalc from a central place if it is empty
		automacs_upstream = specs.get('automacs',config.get('automacs',None))
		msg = 'You can tell the factory where to get omnicalc/automacs by running e.g. '+\
			'`make set automacs=http://github.com/someone/automacs`.' 
		if not automacs_upstream: 
			raise Exception('need automacs in config.py for factory or the connection. '+msg)
		#---! automacs_upstream is not being used?
		settings_custom['AUTOMACS'] = automacs_upstream
		automacs_branch = config.get('automacs_branch',None)
		if automacs_branch != None: settings_custom['AUTOMACS_BRANCH'] = automacs_branch

	return settings_custom

def connect(name):
	"""
	Refresh an omnicalc project.
	"""
	#! arguments to specify whether we repack the web interface, etc
	specs = get_connections(name)
	# substitute PROJECT_NAME with the root
	if ' ' in name: raise Exception('name cannot contain spaces: %s'%name)
	for key,val in specs.items():
		if isinstance(val,str_types):
			specs[key] = re.sub('PROJECT_NAME',name,val)
	settings_custom = prep_settings_custom(project_name=name,**specs)
	# run the connection handler
	connector = OmniFromFactory(
		project_name=name,settings_custom=settings_custom,
		**specs).result

def shutdown_stop_locked(name,**locks):
	# we try/except on these since any one may have failed
	try: stop_locked(lock=locks['lock_site'],log=locks['log_site'])
	except: pass
	try: stop_locked(lock=locks['lock_cluster'],log=locks['log_cluster'])
	except: pass
	try: stop_locked(lock=locks['lock_notebook'],log=locks['log_notebook'])
	except: pass

def run(name,public=False):
	"""
	Start a factory.
	"""
	from ortho import check_port
	# start the site first before starting the cluster
	specs = get_connections(name)
	if not public:
		# local runs always use the next port for the notebook
		site_port = specs.get('port',8000)
		nb_port = site_port + 1
	else:
		# get ports for public run before checking them
		site_port = specs.get('public',{}).get('port',8000)
		nb_port = specs.get('public',{}).get('notebook_port',site_port+1)
	# check the ports before continuing
	check_port(site_port)
	check_port(nb_port)
	locks = {}
	# master try except loop so everything runs together or not at all
	try:
		lock_site,log_site = start_site(name,port=site_port,public=public)
		locks.update(lock_site=lock_site,log_site=log_site)
		lock_cluster,log_cluster = start_cluster(name,public=public)
		locks.update(lock_cluster=lock_cluster,log_cluster=log_cluster)
		lock_notebook,log_notebook = start_notebook(name,port=nb_port,public=public)
		locks.update(lock_notebook=lock_notebook,log_notebook=log_notebook)
	except Exception as e:
		print('status failed to start the site so we are shutting down')
		shutdown_stop_locked(name,**locks)
		raise e

	#! need to report public use here
	if False:
		if False:
			try: lock_cluster,log_cluster = start_cluster(name,public=public)
			except Exception as e:
				stop_locked(lock=lock_site,log=log_site)
				ortho.tracebacker(e)
				raise Exception('failed to start the cluster so we shut down the site. exception: %s'%str(e)) 
			try: lock_notebook,log_notebook = start_notebook(name,nb_port,public=public)
			except Exception as e:
				stop_locked(lock=lock_site,log=log_site)
				stop_locked(lock=lock_cluster,log=log_cluster)
				raise Exception('failed to start the notebook so we shut down the site and cluster. '
					'exception: %s'%str(e))
		# custom check that the notebook has found its port
		# wait for the notebook to start up and then check for a port failure
		time.sleep(2)
		if False:
			with open(log_notebook) as fp: log_text = fp.read()
			if re.search('is already in use',log_text,re.M): 
				stop_locked(lock=lock_site,log=log_site)
				stop_locked(lock=lock_notebook,log=log_notebook)
				stop_locked(lock=lock_cluster,log=log_cluster)
				raise Exception('failed to start the notebook so we shut down the site and cluster. '
					'possible port error in %s'%log_notebook)
		# report the status to the user
		url = 'http://%s:%d'%('localhost',site_port)
		if public:
			#! previously in a try/except/pass loop
			this_hostnames = specs['public']['hostname']
			this_hostnames = [this_hostnames] if type(this_hostnames) in str_types else this_hostnames
			for this_hostname in this_hostnames:
				url = 'http://%s:%d'%(this_hostname,specs['public']['port'])
				print('status serving from: %s'%url)

def shutdown(name=None):
	"""Shutdown every running job."""
	# note that previous shutdown routines were much more complicated 
	#   but here we just run the lock files which serve as kill switches
	regex_pid = r'^pid\.(?P<site>.*?)\.(?P<component>.*?)\.lock$'
	runs = {}
	sites = list(set([re.match(regex_pid,i).groupdict()['site'] for i in glob.glob('pid.*')]))
	for site in sites:
		runs[site] = dict([(re.match(regex_pid,i).groupdict()['component'],i) for i in glob.glob('pid.*')
			if re.match(regex_pid,i).groupdict()['site']==site])
	if not name:
		treeview(dict(projects=runs))
		print('status use `make shutdown <name>` to close one of the projects above')
	else:
		for i,fn in runs[name].items():
			print('status shutting down %s'%fn)
			ortho.bash('bash %s'%fn)

def show_running_factories():
	"""
	Show all factory processes.
	Note that jupyter notebooks cannot be easily killed manually so use the full path and try `pkill -f`.
	Otherwise this function can help you clean up redundant factories by username.
	"""
	cmd = 'ps xao pid,user,command | egrep "([c]luster|[m]anage.py|[m]od_wsgi-express|[j]upyter)"'
	try: ortho.bash(cmd)
	except: print('[NOTE] no processes found using bash command: `%s`'%cmd)

# alias for the background jobs
ps = show_running_factories

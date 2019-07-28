#!/usr/bin/env python

import os,re,datetime,shutil,time,glob
import ortho
from ortho import read_config,Hook,treeview,Handler,str_types,mkdirs
from ortho import modules,check_port,backrun,tracebacker
from .deploy import start_site,start_cluster,start_notebook,stop_locked
from .sites import site_setup,abspath
from .settings import *

# +++ HOOK: hook to find connection files
default_connection_handler = {
	'source':'manager/connection_handler.py',
	'target':'connection_handler'}

# +++ HOOK: hook to get a function for sending templates to connection files
connection_to_template = {
	'source':'manager/connection_handler.py',
	'target':'template_to_connection'}

default_omnicalc_repo = 'https://github.com/biophyscode/omnicalc'

### COMMAND-LINE INTERFACE

def cluster_namer_settings(settings,specs):
	#!!! deprecated. needs reworked. remains here as placeholder for interface
	# cluster namer is set in a separate file
	cluster_namer = {}
	#! with open('manager/cluster_spec.py') as fp: exec(fp.read(),cluster_namer) 
	"""
	File naming conventions for the "cluster".
	Important to the connection between factory and the cluster.
	"""
	cluster_namer = dict(
		keepsakes = 'waiting running finished'.split(),
		# extract the stamp with e.g.: '^%s$'%re.sub('STAMP','(.+)',waiting)
		# glob the files with e.g.: re.sub('STAMP','*',waiting)
		waiting = 'STAMP.req',
		running = 'run-STAMP',
		finished = 'fin-STAMP',)
	for key in [i for i in cluster_namer if i 
		not in cluster_namer['keepsakes']]: del cluster_namer[key]
	settings['CLUSTER_NAMER'] = cluster_namer

def gromacs_config_settings(settings,specs):
	# if the user does not supply a gromacs_config.py the default happens
	# option to specify gromacs config file for automacs8
	if 'gromacs_config' in specs: 
		gromacs_config_fn = specs['gromacs_config']
		if not os.path.isfile(gromacs_config_fn):
			raise Exception('cannot find gromacs_config file at %s'%gromacs_config_fn)
		settings['GROMACS_CONFIG'] = os.path.join(os.getcwd(),gromacs_config_fn)
	else: settings['GROMACS_CONFIG'] = False

def base_settings(**specs):
	"""Basic settings for all projects."""
	settings = {
		#! hard-coded from automacs in the conf. needs default?
		'AUTOMACS':ortho.conf.get('automacs',
			'https://github.com/biophyscode/automacs'),
		'PLOT':abspath(specs['plot_spot']),
		'POST':abspath(specs['post_spot']),
		#! what is the purpose of COORDS?
		'COORDS':abspath(specs.get('coords_spot',
			os.path.join('data',specs['project_name'],'coords')),),
		# omnicalc locations are fixed
		'CALC':abspath(os.path.join('calc',specs['project_name'])),
		'SIMSPOT':None,
		'FACTORY':os.getcwd(),
		#! cluster is under construction
		'CLUSTER':'cluster'}
	settings['NAME'] = specs['project_name']
	#! necessary?
	if False:
		# all paths are absolute unless they have a colon in them, in which case it 
		#   is ssh or http. we attach filesystem separators as well so that e.g. 
		#   settings.SPOT can be added to relative paths
		settings_custom = dict([(key,os.path.join(os.path.abspath(val),'') 
			if ':' not in val else val)
			for key,val in settings_custom.items()])
	return settings

def init_settings(project_name,calculations,calc_spot,post_spot,plot_spot):
	"""Prepare all settings for the site with modular functions."""
	#! python3 might have a nice args object to convert args to kwargs
	specs = dict(project_name=project_name,calculations=calculations,
		calc_spot=calc_spot,post_spot=post_spot,plot_spot=plot_spot)
	settings = base_settings(**specs)
	# add cluster namer, gromacs configuration
	cluster_namer_settings(settings,specs)
	gromacs_config_settings(settings,specs)
	return settings

def connect_run(project_name,settings_custom,post_spot,plot_spot,calculations,
	public=False,development=False,sims=None,meta_filter=None,omnicalc=None):
	"""
	Instantiate a connection. Called by OmniFromFactory.
	"""
	config = read_config()
	# make directories minus calc spot which is cloned
	dns = [post_spot,plot_spot]+([sims] if sims!=None else [])
	for dn in dns:
		if dn==None: continue
		if not os.path.isdir(dn): mkdirs(dn)
	calc_root = os.path.join('calc',project_name)
	# clone omnicalc into the calculation folder
	modules_this = {calc_root:omnicalc if omnicalc else
		config.get('omnicalc',default_omnicalc_repo)}
	try: modules.sync(modules=modules_this,current=True)
	except Exception as e: 
		print('warning got error on sync: '+str(e))
		print('warning failed to sync the repo: %s'%modules_this)
	# clone and synchronize calculations reposotory
	if calculations: 
		modules_calcs_this = {
			os.path.join('calc',project_name,'calcs'):calculations}
		try: modules.sync(modules=modules_calcs_this,current=True)
		except: print('warning failed to sync the repo: %s'%
			modules_calcs_this)
	# absolute paths
	plot_spot = os.path.realpath(plot_spot)
	post_spot = os.path.realpath(post_spot)
	# update the postprocssing locations
	ortho.bash('make set post_plot_spot %s'%plot_spot,cwd=calc_root)
	ortho.bash('make set post_data_spot %s'%post_spot,cwd=calc_root)
	if meta_filter:
		ortho.bash('make unset meta_filter',cwd=calc_root)
		meta_filter = ortho.listify(meta_filter)
		ortho.bash('make setlist meta_filter %s'%
			' '.join(meta_filter),cwd=calc_root)
	# prepare the site, with some yaml keys passed through
	#! could also pass through database, calc
	site_setup(project_name,settings_custom=settings_custom,
		public=public,development=development)
	# propagate the flag to activate the environment
	spec_py3 = config.get('installed',{}).get('conda_py3',{})
	if spec_py3:
		activate_path = os.path.realpath(
			os.path.join(spec_py3['where'],'bin','activate'))
		ortho.bash('make set activate_env="%s py3"'%activate_path,cwd=calc_root)
	#! currently we only pass the conda_py3 environment
	else: pass

class OmniFromFactory(Handler):
	"""
	Route requests for an omnicalc project to the connect_run function
	with settings depending on the connection dictionary.
	"""
	def connection_development(self,project_name,
		calculations,calc_spot,post_spot,plot_spot,omnicalc=None,meta_filter=None):
		"""Main handler for the development environment."""
		settings = init_settings(project_name,
			calculations,calc_spot,post_spot,plot_spot)
		settings['NOTEBOOK_IP'] = 'localhost'
		settings['extra_allowed_hosts'] = []
		site_port = 8000
		settings['NOTEBOOK_PORT'] = site_port+1
		#! added meta_filter here but not below
		connect_run(project_name=project_name,settings_custom=settings,
			post_spot=post_spot,plot_spot=plot_spot,calculations=calculations,
			meta_filter=meta_filter,omnicalc=omnicalc)
	def connection_public(self,project_name,
		calculations,calc_spot,post_spot,plot_spot,public,
		omnicalc=None,meta_filter=None):
		"""Main handler for the development environment."""
		# initialize settings (repetitive with connection_development above)
		settings = init_settings(project_name,
			calculations,calc_spot,post_spot,plot_spot)
		site_port = 8000
		settings['NOTEBOOK_IP'] = 'localhost'
		# additional commands because public
		# the apparent notebook port is used to set the NOTEBOOK_PORT in django
		#   in case we are in a container and the link to the notebook needs to
		#   happen on another port
		settings['NOTEBOOK_PORT'] = public.get('notebook_port_apparent',
			public.get('notebook_port',site_port+1))
		settings['extra_allowed_hosts'] = []
		#! added meta_filter above but not here
		#! could we consolidate the connections?
		connect_run(public=public,
			project_name=project_name,settings_custom=settings,
			post_spot=post_spot,plot_spot=plot_spot,meta_filter=meta_filter,
			calculations=calculations,omnicalc=omnicalc)

class OmniFromFactoryDEPRECATED(Handler):
	"""
	Connect a connection.
	DEPRECATED above in kind and in connect_run
	"""
	def connect(self,project_name,calc_spot,post_spot,settings_custom,
		plot_spot,sims=None,calculations=None,public=False,development=True):
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
		# prepare the site, with some yaml keys passed through
		#! could also pass through database, calc
		site_setup(project_name,settings_custom=settings_custom,
			public=public,development=development)

def connection_template(kind,name):
	"""
	Make a template and write the file.

	:kind: a style (basic)
	:name: the name of the project
	"""
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
	specs = toc[name]
	# multiple connections can map to the same project by setting the name here
	name = specs.pop('name',name)
	specs['project_name'] = name
	return specs

#! this function is not long for this world
def prep_settings_custom(project_name,**specs):
	#! previously in a separate file
	# additional custom settings which are not paths
	# if there is a public dictionary and we receive the "public" flag from make we serve public site
	if specs.get('public',None):
		site_port = specs['public'].get('port',8000)
		# the notebook IP for django must be the public hostname, however in the get_public_ports function
		#   we have an internal notebook_hostname for users who have a router
		if 'hostname' not in specs['public']:
			raise Exception('for public deployment you must add the hostname to the connection')
	    # the hostnames are a list passed to ALLOWED_HOSTS starting with localhost
		if type(specs['public']['hostname']) in str_types: hostnames = [specs['public']['hostname']]
		elif type(specs['public']['hostname'])==list: hostnames = specs['public']['hostname']
		else: raise Exception('cannot parse hostname')
		hostnames.append('localhost')
		settings_custom['extra_allowed_hosts'] = list(set(hostnames))
		# the first hostname is the primary one
		settings_custom['NOTEBOOK_IP'] = hostnames[0]
		settings_custom['NOTEBOOK_PORT'] = specs['public'].get('notebook_port',site_port+1)
	# serve locally
	else:
		# note that notebook ports are always one higher than the site port
		site_port = specs.get('port',8000)
		settings_custom['NOTEBOOK_IP'] = 'localhost'
		settings_custom['NOTEBOOK_PORT'] = specs.get('port_notebook',site_port+1)
		settings_custom['extra_allowed_hosts'] = []
	# name this project
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
	"""
{'AUTOMACS': '/Users/rpb/worker/factory/{/',
 'CALC': '/Users/rpb/worker/factory/calc/actinlink_dev/',
 'CLUSTER': '/Users/rpb/worker/factory/cluster/',
 'CLUSTER_NAMER': {'finished': 'fin-STAMP',
                   'running': 'run-STAMP',
                   'waiting': 'STAMP.req'},
 'COORDS': '/Users/rpb/worker/factory/data/actinlink_dev/coords/',
 'FACTORY': '/Users/rpb/worker/factory/',
 'GROMACS_CONFIG': False,
 'NAME': 'actinlink_dev',
 'NOTEBOOK_IP': 'localhost',
 'NOTEBOOK_PORT': 8001,
 'PLOT': '/Users/rpb/worker/post-factory-demo/plot/',
 'POST': '/Users/rpb/worker/post-factory-demo/post/',
 'SIMSPOT': '/Users/rpb/worker/factory/data/actinlink_dev/sims/',
 'extra_allowed_hosts': []}
	"""
	return settings_custom

def connect(name):
	"""
	Refresh an omnicalc project.
	"""
	print('status connecting to %s'%name)
	specs = get_connections(name)
	# multiple connections can map to the same project by setting the name here
	name = specs.pop('name',name)
	specs['project_name'] = name
	# substitute PROJECT_NAME with the root
	if ' ' in name: raise Exception('name cannot contain spaces: %s'%name)
	for key,val in specs.items():
		if isinstance(val,str_types):
			specs[key] = re.sub('PROJECT_NAME',name,val)
	# run the connection handler
	connector = OmniFromFactory(**specs).result

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
	# the command-line name can be overridden by the connection dict
	project_name = specs['project_name']
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
		lock_site,log_site = start_site(project_name,connection_name=name,
			port=site_port,public=public)
		locks.update(lock_site=lock_site,log_site=log_site)
		lock_cluster,log_cluster = start_cluster(project_name,public=public)
		locks.update(lock_cluster=lock_cluster,log_cluster=log_cluster)
		lock_notebook,log_notebook = start_notebook(project_name,connection_name=name,
			port=nb_port,public=public)
		locks.update(lock_notebook=lock_notebook,log_notebook=log_notebook)
	except Exception as e:
		print('status failed to start the site so we are shutting down')
		print('warning exception that caused the failure was: %s'%e)
		shutdown_stop_locked(name,**locks)
		raise e

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

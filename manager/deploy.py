#!/usr/bin/env python

import os,sys,datetime,re,shutil,time
import ortho
from ortho import check_port,backrun,str_types
from .settings import *
import pwd,grp

#! add "job cancelled" to kill_switch_coda below

def get_group():
	"""Get the gid."""
	groupnames = ['users','everyone']
	for groupname in groupnames:
		try: 
			gid = grp.getgrnam(groupname).gr_gid
			return groupname
		except: pass
	#! this needs redeveloped
	raise Exception('cannot identify the group for this user from: %s'%groupnames)

def get_user():
	"""..."""
	username = pwd.getpwuid(os.getuid())[0]
	uid = pwd.getpwnam(username).pw_uid
	return username,uid

def chown_user(fn):
	try: os.chown(fn,uid,gid)
	except: 
		print('warning CHOWN fail on %s'%fn)
		pass

def get_conda_bin(name):
	"""..."""
	#! repetitive with path_wsgi
	# get installed from conf
	installed = ortho.conf.get('installed',{})
	if len(installed)!=1: raise Exception('develpment')
	this_env = list(installed.values())[0]
	path = os.path.join(this_env['where'],'envs',this_env['name'],'bin',name)
	if not os.path.isfile(path):
		raise Exception('cannot find %s'%path)
	return path

def get_public_ports(name):
	"""Get public ports and details before serving."""
	#! why does this import fail above?
	from .cli import get_connections
	#ensure sudo
	#if not os.geteuid()==0:
	#	raise Exception('you must run public as sudo!')
	# collect details from the connection
	reqs = 'port hostname'.split()
	public_details = get_connections(name).get('public',{})
	if not public_details:
		raise Exception('need "public" details for connection %s'%name)
	missing_keys = [i for i in reqs if i not in public_details]
	if any(missing_keys):
		raise Exception('missing keys from connection: %s'%missing_keys)
	username,uid = get_user()
	groupname = get_group()
	# previously set user and group manually in the public dictionary but now we detect it
	user,group = username,groupname
	port_site = public_details['port']
	port_notebook = public_details.get('notebook_port',port_site+1)
	notebook_ip = public_details.get('hostname_notebook',public_details.get('hostname','localhost'))
	# if we have a list of hostnames then the first is the primary
	if type(notebook_ip) not in str_types: notebook_ip = notebook_ip[0]
	details = dict(user=user,group=group,port_notebook=port_notebook,
		port_site=port_site,notebook_ip=notebook_ip,
		jupyter_localhost=public_details.get('jupyter_localhost',False))
	#! why are there three different IPs, one for the notebook and one for the jupyter_localhost?
	return details

def start_site(name,connection_name,port,public=False,sudo=False):
	"""
	Run the mod_wsgi server to serve the site.
	Note that mod_wsgi must be in reqs.yaml and you may need apache2 and apache2-devel rpms.
	"""
	# start django
	site_dn = os.path.join('site',name)
	if not os.path.isdir(site_dn): 
		raise Exception('missing project named "%s". did you forget to connect it?'%name)
	# if public we require an override port so that users are careful
	if public:
		public_details = get_public_ports(connection_name)
		port = public_details['port_site']
		# previously got user/group from the public dictionary but now we just use the current user
		username,uid = get_user()
		groupname = get_group()
		user,group = username,groupname
	check_port(port)
	# for some reason you have to KILL not TERM the runserver
	#! replace runserver with something more appropriate? a real server?
	lock = 'pid.%s.site.lock'%name
	log = log_site%name
	if not public:
		cmd = 'python %s runserver 0.0.0.0:%s'%(os.path.join(os.getcwd(),site_dn,'manage.py'),port)
	else:
		try: wsgi_path = get_conda_bin('mod_wsgi-express')
		except Exception as e: 
			print('warning you may need to ensure mod_wsgi is in the pip list in '
				'reqs.yaml (followed by a `make env <name>` command), and that '
				'apache, apache-devel are installed in your operating system')
			raise Exception(e)
		#! hard-coded development static paths
		cmd = ('%s%s start-server '%('sudo ' if sudo else '',wsgi_path)+
			'--port %d site/%s/%s/wsgi.py --user %s --group %s '+
			'--python-path site/%s %s')%(port,name,name,user,group,name,
			('--url-alias /static %s'%'interface/static'))
		#! previously used ('interface/static' if not public else 'site/%s/static_root'%name)
		#!   which requires a section in the connection in which we run collectstatic. instead we opt for
		#!   a direct approach. to use this again, you have to change STATICFILES_DIRS as well
		auth_fn = os.path.join('site',name,name,'wsgi_auth.py')
		if os.path.isfile(auth_fn): cmd += ' --auth-user-script=%s'%auth_fn
	backrun(cmd=cmd,log=log,lock=lock,killsig='KILL',sudo=sudo,
		scripted=False,kill_switch_coda='rm %s'%lock,notes=('# factory run is public' if public else None))
	if public: chown_user(log)
	return lock,log

def daemon_ender(fn,cleanup=True):
	"""
	Read a lock file and end the job with a particular message
	"""
	try: ortho.bash('bash %s'%fn)
	except Exception as e: 
		print('warning failed to shutdown lock file %s with exception:\n%s'%(fn,e))
	if cleanup: 
		print('status daemon successfully shutdown via %s'%fn)
		os.remove(fn)

def stop_locked(lock,log,cleanup=False):
	"""
	Save the logs and terminate the server.
	"""
	print('status stopping log=%s lock=%s'%(log,lock))
	# terminate first in case there is a problem saving the log
	daemon_ender(lock,cleanup=cleanup)
	stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
	if not os.path.isdir('logs'): raise Exception('logs directory is missing')
	name = re.match(r'^pid\.(.*?)\.lock$',lock).group(1)
	shutil.move(log,'logs/arch.%s.%s.log'%(name,stamp))

def start_cluster(name,public=False,sudo=False):
	"""
	Start a calculation cluster.
	"""
	from ortho.queue import simple_task_queue
	queue_spec = simple_task_queue(log=log_cluster%name,
		lock='pid.%s.cluster.lock'%name)
	return queue_spec['lock'],queue_spec['log']

def start_notebook(name,connection_name,port,public=False,sudo=False):
	"""
	Start a Jupyter notebook server.
	"""
	# if public we require an override port so that users are careful
	if public: 
		public_details = get_public_ports(connection_name)
		port,notebook_ip = [public_details[i] for i in ['port_notebook','notebook_ip']]
		#! low ports are on. to turn them off remove False below and 
		if port<=1024: raise Exception('cannot use port %d for this project. '%port+
			'even public projects need high notebook ports for security reasons. '+
			'you will need to run `make connect <name> public` after you fix the ports')
	if not os.path.isdir(os.path.join('site',name)):
		raise Exception('cannot find site for %s'%name)
	# note that TERM safely closes the notbook server
	lock = 'pid.%s.notebook.lock'%name
	log = log_notebook%name
	# root location to serve the notebook
	note_root = os.path.join(os.getcwd(),'calc',name)
	#! demo to try to serve higher for automacs simulations via notebook
	note_root = os.getcwd()
	# higher rates (increased from 10M to 10**10 for XTC downloads)
	rate_cmd = '--NotebookApp.iopub_data_rate_limit=10000000000'
	# if you want django data in IPython, use:
	#   'python site/%s/manage.py shell_plus --notebook --no-browser'%name,
	#! we never figured out how to set ports, other jupyter settings, with shell_plus
	#! jupyter doesn't recommend allowing root but we do so here so you can call
	#! `sudo make run <name> public` which prevents us from having to add sudo ourselves
	if not public:
		cmd = 'jupyter notebook --no-browser --port %d --port-retries=0 %s--notebook-dir="%s"'%(
			port,('%s '%rate_cmd if rate_cmd else ''),note_root)
	# note that without zeroing port-retries, jupyter just tries random ports nearby (which is bad)
	else: 
		#! note try: jupyter notebook password --generate-config connections/config_jupyter_actinlink.py
		#!   which will give you a one-per-machine password to link right to the notebook
		#!   note that you must write that password to logs/token.PROJECT_NAME with a trailing space!
		#! unsetting this variable because some crazy run/user error
		if 'XDG_RUNTIME_DIR' in os.environ: del os.environ['XDG_RUNTIME_DIR']
		path_jupyter = get_conda_bin('jupyter-notebook')
		cmd = (('sudo -i -u %s '%username if sudo else '')+'%s '%(
			os.path.join(os.getcwd(),path_jupyter))+
			('--user=%s '%username if sudo else '')+(' %s '%rate_cmd if rate_cmd else '')+
			'--port-retries=0 '+'--port=%d --no-browser --ip="%s" --notebook-dir="%s"'%(port,
				#! notebook_ip if not public_details.get('jupyter_localhost',False) else 'localhost',
				#! changed the above to get the jupuyter_localhost directly
				#! note that we have three different hostname equivalents
				public_details.get('jupyter_localhost',notebook_ip),
				note_root))
	backrun(cmd=cmd,log=log,lock=lock,killsig='TERM',
		scripted=False,kill_switch_coda='rm %s'%lock,sudo=sudo,
		notes=('# factory run is public' if public else None))
	if sudo: chown_user(log)
	#! the following section is not useful. it should possibly write the token to a separate file
	#!   i.e. not log_notebook but the recently-removed log_token. in any case the calculator/interact
	#!   function that gets the token is now just looking right at the jupyuter log
	if False:
		#! see the note above about jupyter notebook password. this is a hack to get the password working
		token_log = log_notebook%name
		if public and os.path.isfile(token_log):
			time.sleep(3) # sleep to be sure that the log is ready
			with open(token_log) as fp: token = fp.read().strip()
			# route the token to the notebook log where it is picked up in the usual way
			with open(log,'a') as fp: fp.write('\n[TOKEN] http://localhost:8888/?token=%s \n'%token)
	# note that the calling function should make sure the notebook started
	return lock,log

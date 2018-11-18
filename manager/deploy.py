#!/usr/bin/env python

import os,sys,datetime,re,shutil
import ortho
from ortho import check_port,backrun
from .settings import *

def start_site(name,port,public=False,sudo=False):
	"""
	Run the mod_wsgi server to serve the site.
	"""
	# start django
	site_dn = os.path.join('site',name)
	if not os.path.isdir(site_dn): 
		raise Exception('missing project named "%s". did you forget to connect it?'%name)
	# if public we require an override port so that users are careful
	if public:
		public_details = get_public_ports(name)
		port = public_details['port_site']
		# previously got user/group from the public dictionary but now we just use the current user
		user,group = username,groupname
	check_port(port)
	# for some reason you have to KILL not TERM the runserver
	#! replace runserver with something more appropriate? a real server?
	lock = 'pid.%s.site.lock'%name
	log = log_site%name
	if not public:
		cmd = 'python %s runserver 0.0.0.0:%s'%(os.path.join(os.getcwd(),site_dn,'manage.py'),port)
	else:
		#! hard-coded development static paths
		cmd = ('%senv/envs/py2/bin/mod_wsgi-express start-server '%('sudo ' if sudo else '')+
			'--port %d site/%s/%s/wsgi.py --user %s --group %s '+
			'--python-path site/%s %s')%(port,name,name,user,group,name,
			('--url-alias /static %s'%('interface/static' if not public else 'site/%s/static_root'%name)))
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
	queue_spec = simple_task_queue(log='logs/log-cluster',lock='pid.%s.cluster.lock'%name)
	return queue_spec['lock'],queue_spec['log']

def start_notebook(name,port,public=False,sudo=False):
	"""
	Start a Jupyter notebook server.
	"""
	# if public we require an override port so that users are careful
	if public: 
		public_details = get_public_ports(name)
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
		raise Exception('path below is wrong')
		cmd = (('sudo -i -u %s '%username if sudo else '')+'%s '%(
			os.path.join(os.getcwd(),'env/envs/py2/bin/jupyter-notebook'))+
			('--user=%s '%username if sudo else '')+(' %s '%rate_cmd if rate_cmd else '')+
			'--port-retries=0 '+'--port=%d --no-browser --ip="%s" --notebook-dir="%s"'%(port,
				notebook_ip if not public_details.get('jupyter_localhost',False) else 'localhost',
				note_root))
	backrun(cmd=cmd,log=log,lock=lock,killsig='TERM',
		scripted=False,kill_switch_coda='rm %s'%lock,sudo=sudo,
		notes=('# factory run is public' if public else None))
	if sudo: chown_user(log)
	#! see the note above about jupyter notebook password. this is a hack to get the password working
	token_log = log_token%name
	if public and os.path.isfile(token_log):
		time.sleep(3) # sleep to be sure that the log is ready
		with open(token_log) as fp: token = fp.read().strip()
		# route the token to the notebook log where it is picked up in the usual way
		with open(log,'a') as fp: fp.write('\n[TOKEN] http://localhost:8888/?token=%s \n'%token)
	# note that the calling function should make sure the notebook started
	return lock,log

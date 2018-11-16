#!/usr/bin/env python

import os,sys
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
	try: bash('bash %s'%fn)
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
	"""
	from ortho.queue import simple_task_queue
	queue_spec = simple_task_queue(log='logs/log-cluster',lock='pid.%s.cluster.lock'%name)
	return queue_spec['lock'],queue_spec['log']
	
	if False:
		# hook for flock which installs it if necessary on macos
		flock_bin = ortho.config_hook_get('flock1','flock')
		ortho.bash('FLOCK_CMD=%s bash ortho/queue/lockness.sh'%flock_bin,announce=True)
		print('status lockness is running!')
		#! need a lock file and a log file
		return "LOCK.lockness.sh","logs/log-cluster"
		#import ipdb;ipdb.set_trace()
	if False:
		#---start the cluster. argument is the location of the kill switch for clean shutdown
		#---! eventually the cluster should move somewhere safe and the kill switches should be hidden
		lock = 'pid.%s.cluster.lock'%name
		log = log_cluster%name
		#---! ...make shutdown should manage the clean shutdown
		#---cluster never requires sudo but we require sudo to run publicly so we pass it along
		#---! run the cluster as the user when running public?
		backrun(cmd='python -u manager/cluster_start.py %s'%lock,
			log=log,stopper=lock,killsig='INT',scripted=False,sudo=sudo,
			notes=('# factory run is public' if public else None))
		if sudo: chown_user(log)
		return lock,log

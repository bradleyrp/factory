#!/usr/bin/env python

"""
Manage the execution of the factory.
"""

from __future__ import print_function
import os,sys,glob,re,shutil,subprocess,textwrap,datetime,time
#! from config import bash,read_config
#! from makeface import abspath
#! from datapack import treeview
from ortho import read_config,treeview
from ortho import bash as ortho_bash
def bash(*args,**kwargs): 
	kwargs['announce'] = True
	return ortho_bash(*args,**kwargs)
import manager
manager.cluster.read_config = read_config
from manager.cluster import backrun

__all__ = ['connect','template','connect','run','shutdown','prepare_server','show_running_factories','ps']

#! from setup import FactoryEnv

str_types = [str,unicode] if sys.version_info<(3,0) else [str]

log_site = 'logs/site.%s'
log_cluster = 'logs/cluster.%s'
log_notebook = 'logs/notebook.%s'
log_token = 'logs/token.%s'

def abspath(fn): return os.path.expanduser(os.path.abspath(fn))

import pwd,grp
username = pwd.getpwuid(os.getuid())[0]
uid = pwd.getpwnam(username).pw_uid
#---! dangerous if the user is not in
try: 
	groupname = 'users'
	gid = grp.getgrnam(groupname).gr_gid
except: 
	groupname = 'everyone'
	try: gid = grp.getgrnam(groupname).gr_gid
	except: raise Exception('cannot get the group. we tried "users" and "everyone"')

###---CONNECT PROCEDURE PORTED FROM original FACTORY

def chown_user(fn):
	try: os.chown(fn,uid,gid)
	except: 
		print('CHOWN fail')
		pass

def find_and_replace(fn,*args):
	"""
	Mimic sed.
	"""
	#---replace some key lines
	with open(fn) as fp: text = fp.read()
	for f,t in args: text = re.sub(f,t,text,flags=re.M)
	with open(fn,'w') as fp: fp.write(text)

def package_django_module(source,projname):
	"""
	Packages and installs a django module.
	Note that this is necessary for the initial connection, even if you use the development code.
	"""
	dev_dn = os.path.join(source,projname)
	pack_dn = os.path.join('pack',projname)
	if not os.path.isdir(dev_dn): raise Exception('cannot find %s'%dev_dn)
	if os.path.isdir(pack_dn): raise Exception('%s already exists'%pack_dn)
	#---copy the generic python packager
	shutil.copytree('manager/packer',pack_dn)
	#---copy the development code into the same directory
	#---! make this pythonic
	bash('cp -a %s %s'%(dev_dn,os.path.join(pack_dn,'')))
	find_and_replace(os.path.join('pack',projname,'setup.py'),
		('^#---SETTINGS','packname,packages = \"%s\",[\"%s\"]'%(projname,projname)))
	find_and_replace(os.path.join('pack',projname,'MANIFEST.in'),
		('APPNAME',projname))
	#---prepare the package
	bash('python %s sdist'%os.path.join('pack',projname,'setup.py'))
	#---uninstall the package
	#try: bash('echo -e "y\n" | pip uninstall %s &> logs/log-pip-$projname'%projname)
	#except: pass
	#---install the package
	bash('pip install -U pack/%s/dist/%s-0.1.tar.gz'%(projname,projname),log='logs/log-pip-%s'%projname)

#---! note no calculator below
#---do not even think about changing this without MIRRORING the change in the development version
project_settings_addendum = """
#---django settings addendum
INSTALLED_APPS = tuple(list(INSTALLED_APPS)+['django_extensions','simulator','calculator'])
#---common static directory
STATIC_ROOT = os.path.join(BASE_DIR,'static_root')
TEMPLATES[0]['OPTIONS']['libraries'] = {'code_syntax':'calculator.templatetags.code_syntax'}
TEMPLATES[0]['OPTIONS']['context_processors'].append('calculator.context_processors.global_settings')
#---all customizations
from custom_settings import *
#---addenda from custom settings
ALLOWED_HOSTS += extra_allowed_hosts
"""

#---project-level URLs really ties the room together
project_urls = """
from django.conf.urls import url,include
from django.contrib import admin
from django.views.generic.base import RedirectView
urlpatterns = [
	url(r'^$',RedirectView.as_view(url='simulator/',permanent=False),name='index'),
	url(r'^simulator/',include('simulator.urls',namespace='simulator')),
	url(r'^calculator/',include('calculator.urls',namespace='calculator')),
	url(r'^admin/', admin.site.urls),]
"""

#---authorization for public sites
code_check_passwd = """		
def check_password(environ,user,password):
	creds = %s
	if (user,password) in creds: return True
	else: False
"""

def connect_single(connection_name,**specs):
	"""
	The big kahuna. Revamped recently.
	"""
	config = read_config()
	#---skip a connection if enabled is false
	if not specs.get('enable',True): return
	mkdir_or_report('data')
	mkdir_or_report('site')
	mkdir_or_report('calc')
	#---the site is equivalent to a django project
	#---the site draws on either prepackaged apps in the pack folder or the in-development versions in dev
	#---since the site has no additional data except that specified in connect.yaml, we can always remake it
	if os.path.isdir('site/'+connection_name):
		print("[STATUS] removing the site for \"%s\" to remake it"%connection_name)
		shutil.rmtree('site/'+connection_name)
	#---regex PROJECT_NAME to the connection names in the paths sub-dictionary	
	#---note that "PROJECT_NAME" is therefore protected and always refers to the 
	#---...top-level key in connect.yaml
	#---! note that you cannot use PROJECT_NAME in spots currently
	for key,val in specs.items():
		if type(val)==str: specs[key] = re.sub('PROJECT_NAME',connection_name,val)
		elif type(val)==list:
			for ii,i in enumerate(val): val[ii] = re.sub('PROJECT_NAME',connection_name,i)
	#---paths defaults
	specs['plot_spot'] = specs.get('plot_spot',os.path.join('data',connection_name,'plot')) 
	specs['post_spot'] = specs.get('post_spot',os.path.join('data',connection_name,'post')) 
	specs['simulations_spot'] = specs.get('simulations_spot',os.path.join('data',connection_name,'sims'))
	specs['coords_spot'] = specs.get('coords_spot',os.path.join('data',connection_name,'coords'))
	#---intervene here to replace PROJECT_NAME in the string values of each spot
	for spotname,spot_details in specs.get('spots',{}).items():
		for key,val in spot_details.items():
			if type(val) in str_types:
				specs['spots'][spotname][key] = re.sub('PROJECT_NAME',connection_name,val)
			#---we also expand paths for route_to_data
			specs['spots'][spotname]['route_to_data'] = abspath(
				specs['spots'][spotname]['route_to_data'])

	#---cluster namer is set in a separate file
	cluster_namer = {}
	with open('manager/cluster_spec.py') as fp: exec(fp.read(),cluster_namer) 
	for key in [i for i in cluster_namer if i not in cluster_namer['keepsakes']]: del cluster_namer[key]

	###---DJANGO SETTINGS

	#---first define folders and (possibly) http git repos
	settings_custom = {
		'SIMSPOT':abspath(specs['simulations_spot']),
		#---! hard-coded. get it from config.py??
		'AUTOMACS':'http://github.com/biophyscode/automacs',
		'PLOT':abspath(specs['plot_spot']),
		'POST':abspath(specs['post_spot']),
		'COORDS':abspath(specs['coords_spot']),
		#---omnicalc locations are fixed
		'CALC':abspath(os.path.join('calc',connection_name)),
		'FACTORY':os.getcwd(),
		#---! get this from config.py
		'CLUSTER':'cluster'}
	#---all paths are absolute unless they have a colon in them, in which case it is ssh or http
	#---we attach filesystem separators as well so that e.g. settings.SPOT can be added to relative paths
	settings_custom = dict([(key,os.path.join(os.path.abspath(val),'') if ':' not in val else val)
		for key,val in settings_custom.items()])
	settings_custom['CLUSTER_NAMER'] = cluster_namer
	#---if the user does not supply a gromacs_config.py the default happens
	#---option to specify gromacs config file for automacs
	if 'gromacs_config' in specs: 
		gromacs_config_fn = specs['gromacs_config']
		if not os.path.isfile(gromacs_config_fn):
			raise Exception('cannot find gromacs_config file at %s'%gromacs_config_fn)
		settings_custom['GROMACS_CONFIG'] = os.path.join(os.getcwd(),gromacs_config_fn)
	else: settings_custom['GROMACS_CONFIG'] = False
	#---additional custom settings which are not paths
	#---if there is a public dictionary and we receive the "public" flag from make we serve public site
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
	settings_custom['NAME'] = connection_name

	###---END DJANGO SETTINGS

	#---make local directories if they are absent or do nothing if the user points to existing data
	root_data_dir = 'data/'+connection_name
	#---always make data/PROJECT_NAME for the default simulation_spot therein
	mkdir_or_report(root_data_dir)
	for key in ['post_spot','plot_spot','simulations_spot']: 
		mkdir_or_report(abspath(specs[key]))
	#---we always include a "sources" folder in the new simulation spot for storing input files
	mkdir_or_report(abspath(specs.get('coords_spot',os.path.join('data',connection_name,'coords'))))

	#---check if database exists and if so, don't make superuser
	make_superuser = not os.path.isfile(specs['database'])

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
	omnicalc_upstream = specs.get('omnicalc',config.get('omnicalc',None))
	if not omnicalc_upstream: 
		raise Exception('need omnicalc in config.py for factory or the connection. '+msg)

	#---note that previous version of factory prepended a source command in front of every call
	#---...however the factory handles this for us now
	#---django is accessed via packages imported in settings.py which is why we have to package them
	#---...this saves us from making N copies of the development code

	#---! YOU NEED TO MAKE THE DEVELOPMENT POSSIBLE SOMEHWERE HEREABOUTS

	#---! hard-coding the location of the sources
	django_source = 'interface'
	#---! switching to new development codes...calculator not available yet
	for app in ['simulator','calculator']: 
		if os.path.isdir('pack/%s'%app): shutil.rmtree('pack/%s'%app)
		#---always repackage!
		package_django_module(source=django_source,projname=app)
	
	#---one new django project per connection
	bash('django-admin startproject %s'%connection_name,
		log='logs/log-%s-startproject'%connection_name,cwd='site/')

	#---if the user specifies a database location we override it here
	if specs.get('database',None):
		database_path_change = "\nDATABASES['default']['NAME'] = '%s'"%(
			os.path.abspath(specs['database']))
	else: database_path_change = ''

	#---all settings are handled by appending to the django-generated default
	#---we also add changes to django-default paths
	with open(os.path.join('site',connection_name,connection_name,'settings.py'),'a') as fp:
		fp.write(project_settings_addendum+database_path_change)
		#---only use the development code if the flag is set and we are not running public
		if specs.get('development',True) and not specs.get('public',False):
			fp.write('\n#---use the development copy of the code\n'+
				'import sys;sys.path.insert(0,os.path.join(os.getcwd(),"%s"))'%django_source) 
		#---one more thing: custom settings specify static paths for local or public serve
		#if specs.get('public',None):
		#	fp.write("\nSTATICFILES_DIRS = [os.path.join(BASE_DIR,'static')]")
		#else:
		fp.write("\nSTATICFILES_DIRS = [os.path.join('%s','interface','static')]"%
			os.path.abspath(os.getcwd()))

	#---write custom settings
	#---some settings are literals
	custom_literals = ['CLUSTER_NAMER']
	with open(os.path.join('site',connection_name,connection_name,'custom_settings.py'),'w') as fp:
		#---! proper way to write python constants?
		fp.write('#---custom settings are auto-generated from manager.factory.connect_single\n')
		for key,val in settings_custom.items():
			#---! is there a pythonic way to write a dictionary to a script of immutables
			if ((type(val) in str_types and re.match('^(False|True)$',val)) or key in custom_literals
				or type(val) in [bool,list,tuple]):
				out = '%s = %s\n'%(key,val)
			else: out = '%s = "%s"\n'%(key,val)
			fp.write(out)

	#---development uses live copy of static files in interface/static
	if not specs.get('public',None):
		#---link the static files to the development codes (could use copytree)
		os.symlink(os.path.join(os.getcwd(),django_source,'static'),
			os.path.join('site',connection_name,'static'))
	#---production collects all static files
	else: 
		os.mkdir(os.path.join(os.getcwd(),'site',connection_name,'static_root'))
		bash('python manage.py collectstatic',cwd='site/%s'%connection_name)

	#---write project-level URLs
	with open(os.path.join('site',connection_name,connection_name,'urls.py'),'w') as fp:
		fp.write(project_urls)

	#---clone omnicalc if necessary
	omnicalc_previous = os.path.isdir('calc/%s'%connection_name)
	if not omnicalc_previous:
		if isinstance(omnicalc_upstream,dict):
			address = omnicalc_upstream.pop('address')
			if omnicalc_upstream: raise Exception('unprocessed git directives: %s'%omnicalc_upstream)
			bash('git clone %s calc/%s'%(address,connection_name),
				 log='logs/log-%s-git-omni'%connection_name)
		else:
			bash('git clone %s calc/%s'%(omnicalc_upstream,connection_name),
				 log='logs/log-%s-git-omni'%connection_name)
		#---if this is fresh we run `make setup` because that provides a minimal config.py
		bash('make setup',cwd=specs['calc'])
	else: print('[NOTE] found calc/%s'%connection_name)

	#---initial migration for all new projects to start the database
	#---...!!!!!!!!!!!!!!
	print('[NOTE] migrating ...')
	bash('python site/%s/manage.py makemigrations'%connection_name,
		log='logs/log-%s-migrate'%connection_name)
	bash('python site/%s/manage.py migrate --run-syncdb'%connection_name,
		log='logs/log-%s-migrate'%connection_name)
	print('[NOTE] migrating ... done')
	if make_superuser:
		print("[STATUS] making superuser")
		su_script = "from django.contrib.auth.models import User; "+\
			"User.objects.create_superuser('admin','','admin');print;quit();"
		p = subprocess.Popen('python ./site/%s/manage.py shell'%(connection_name),		
			stdin=subprocess.PIPE,stderr=subprocess.PIPE,stdout=open(os.devnull,'w'),
			shell=True,executable='/bin/bash')
		catch = p.communicate(input=su_script if sys.version_info<(3,0) else su_script.encode())[0]
	print("[STATUS] new project \"%s\" is stored at ./data/%s"%(connection_name,connection_name))
	print("[STATUS] replace with a symlink if you wish to store the data elsewhere")

	#---now that site is ready we can write credentials
	if specs.get('public',None):
		#---write key,value pairs as Basic Auth user/passwords
		creds = specs['public'].get('credentials',{})
		if creds: 
			with open(os.path.join('site',connection_name,connection_name,'wsgi_auth.py'),'w') as fp:
				fp.write(code_check_passwd%str([(k,v) for k,v in creds.items()]))

	raise Exception('no connection here now')		
	return
	#! retiring the code below

	#---set up the calculations directory in omnicalc
	#---check if the repo pointer in the connection is a valid path
	new_calcs_repo = not (os.path.isdir(abspath(specs['repo'])) and (
		os.path.isdir(abspath(specs['repo'])+'/.git') or os.path.isfile(abspath(specs['repo'])+'/HEAD')))
	downstream_git_fn = os.path.join('calc',connection_name,'calcs','.git')
	#---if the repo key gives a web address and we already cloned it, then we do nothing and suggest a pull
	if ':' in specs['repo'] and os.path.isdir(downstream_git_fn):
		print('[NOTE] the calc repo (%s) appears to be remote and %s exists.'%(
			specs['calc'],downstream_git_fn)+'you should pull the code manually to update it')
	#---check that a calcs repo from the internet exists
	elif new_calcs_repo and re.match('^http',specs['repo']):
		#---see if the repo is a URL. code 200 means it exists
		if sys.version_info<(3,0): from urllib2 import urlopen
		else: from urllib.request import urlopen
		code = urlopen(specs['repo']).code
		if code!=200: raise Exception('repo appears to be http but it does not exist')
		else: bash('make clone_calcs source="%s"'%specs['repo'],cwd=specs['calc'])
	#---check that the repo has a colon in the path, implying a remote ssh connection is necessary
	elif new_calcs_repo and ':' in specs['repo']:
		print('[WARNING] assuming that the calcs repository is on a remote machine: %s'%specs['repo'])
		bash('make clone_calcs source="%s"'%specs['repo'],cwd=specs['calc'])
	#---if the calcs repo exists locally, we just clone it
	elif not new_calcs_repo and os.path.isdir(downstream_git_fn): 
		print('[NOTE] git appears to exist at %s already and connection does not specify '%
			os.path.join(abspath(specs['repo']),'.git')+
			'an upstream calcs repo so we are continuing without action')
	elif not new_calcs_repo and not os.path.isfile(downstream_git_fn): 
		bash('make clone_calcs source="%s"'%specs['repo'],cwd=specs['calc'])
	#---make a fresh calcs repo because the meta file points to nowhere
	else:
		os.mkdir(specs['repo'])
		bash('git init',cwd=specs['repo'])
		#---after making a blank repo we put a placeholder in the config
		bash('make set calculations_repo="no_upstream"',cwd=specs['calc'])
		#---also generate a blank metadata so that the interface works
		bash('make blank_meta make_template=False',cwd=specs['calc'])
		msg = ('When connecting to project %s, the "repo" flag in your connection file points to nowhere. '
			'We made a blank git repository at %s. You should develop your calculations there, push that '
			'repo somewhere safe, and distribute it to all your friends, who can use the "repo" flag to '
			'point to it when they start their factories.')
		print('\n'.join(['[NOTE] %s'%i for i in textwrap.wrap(
			msg%(connection_name,specs['repo']),width=60)]))

	#---pass a list of meta_filters through (can be list of strings which are paths or globs)
	calc_meta_filters = specs.get('calc_meta_filters',None)
	if calc_meta_filters:
		bash('make unset meta_filter',cwd=specs['calc'])
		for filt in calc_meta_filters:
			#---note that meta_filter is turned into a list in config.py in omnicalc
			bash('make set meta_filter="%s"'%filt,cwd=specs['calc'])

	#---configure omnicalc 
	#---note that make set commands can change the configuration without a problem
	bash('make set post_data_spot=%s'%settings_custom['POST'],cwd=specs['calc'])
	bash('make set post_plot_spot=%s'%settings_custom['PLOT'],cwd=specs['calc'])
	#---! needs to interpret simulation_spot, add spots functionality
	#---! previously ran register_calculation.py here -- may be worth recapping in this version?
	#---! prepare vhost file here when it's ready
	#---??? IS THIS IT ???
	#---write spots to config
	if 'spots' in specs:
		config_fn = os.path.join(specs['calc'],'config.py')
		with open(config_fn) as fp: config_omni = eval(fp.read())
		config_omni['spots'] = specs['spots']
		import pprint
		#---write the config
		with open(config_fn,'w') as fp: 
			fp.write('#!/usr/bin/env python -B\n'+str(pprint.pformat(config_omni,width=110)))
	#---add the environment to omnicalc. this allows the publicly-served omnicalc to find the environment 
	#---...when root is running it. it also means users do not have to remember to source the environment 
	#---...when they are doing calculations "manually" from their project's omnicalc folder. note that there
	#---...is a slowdown if you are used to always sourcing the environment yourself, but you could just as 
	#---...easily remove the flag from the config.py to recover the original behavior
	if 'activate_env' in config:
		env_path = "%s %s"%(os.path.join(os.path.abspath(config['activate_env'].split()[0])),
			config['activate_env'].split()[1])
		bash('make set activate_env="%s"'%env_path,cwd=specs['calc'])

#---! later you need to add omnicalc functionality
if False: get_omni_dataspots = """if os.path.isfile(CALCSPOT+'/paths.py'):
    omni_paths = {};execfile(CALCSPOT+'/paths.py',omni_paths)
    DATASPOTS = omni_paths['paths']['data_spots']
    del omni_paths
"""

###---UTILITY FUNCTIONS

def prepare_server():
	"""
	Confirm that we are ready to serve.
	"""
	#---mod_wsgi is not available for conda on python 2
	bash('LDLIBS=-lm pip install -U --no-cache-dir mod_wsgi')

def template(template=None,connection_file=None,project_name=None):
	"""
	List templates and possibly create one for the user.
	Use the connection_file and project_name flags to set these options.
	Otherwise, only the template name is required.
	"""
	if not os.path.isdir('connections'): os.mkdir('connections')
	template_source = 'connection_templates.py'
	if sys.version_info<(3,0):
		templates = {}
		execfile(os.path.join(os.path.dirname(__file__),template_source),templates)
		for key in [i for i in templates if not re.match('^template_',i)]: templates.pop(key)
		treeview({'templates':[re.match('^template_(.+)$',k).group(1) for k in templates.keys()]})
	else: raise Exception('dev')
	#---if the user requests a template, write it for them
	if not template and not connection_file: print('[NOTE] rerun with e.g. '+
		'`make template <template_name>` to make a new connection with the same name as the template. '+
		'you can also supply keyword arguments for the connection_file and project name')
	elif connection_file and not template: raise Exception('you must supply a template_name')
	elif template not in templates and 'template_%s'%template not in templates: 
		raise Exception('cannot find template "%s"'%template)
	elif not connection_file and template: connection_file = template+'.yaml'
	#---write the template
	if template:
		fn = os.path.join('connections',connection_file)
		if not re.match('^.+\.yaml$',fn): fn = fn+'.yaml'
		with open(fn,'w') as fp:
			template_text = templates.get(template,templates['template_%s'%template])
			if project_name: 
				template_text = re.sub('^([^\s]+):','%s:'%project_name,template_text,flags=re.M)
			fp.write(template_text)
		print('[NOTE] wrote a new template to %s'%fn)

def mkdir_or_report(dn):
	"""
	"""
	if os.path.isdir(dn): print("[STATUS] found %s"%(dn))
	else: 
		os.mkdir(dn)
		print("[STATUS] created %s"%dn)

def read_connection(*args):
	"""
	Parse a connection yaml file.
	"""
	import yaml
	toc = {}
	for arg in args:
		with open(arg) as fp: 
			contents = yaml.load(fp.read())
			for key,val in contents.items():
				if key in toc: 
					raise Exception('found key %s in the toc already. redundant copy in %s'%(key,arg))
				toc.update(**{key:val})
	return toc

def collect_connections(name):
	"""
	reads all avaialble connections
	"""
	connects = glob.glob('connections/*.yaml')
	if not connects: raise Exception('no connections available. try `make template` for some examples.')
	#---read all connection files into one dictionary
	toc = read_connection(*connects)
	if name and name not in toc: raise Exception('cannot find project named "%s" in the connections'%name)
	return toc

def connect(name=None,public=False):
	"""
	Connect or reconnect a particular project.
	"""
	if not name: raise Exception('development. cannot connect multiple projects now. please provide a name.')
	#---check that we have already installed mod_wsgi before continuing
	if public:
		if not os.path.isfile('env/envs/py2/bin/mod_wsgi-express'):
			raise Exception('please install mod_wsgi before continuing with a public factory. '
				'try `make prepare_server`')
	#---get all available connections
	toc = collect_connections(name)
	#---which connections we want to make
	targets = [name] if name else toc.keys()
	#---loop over desired connection
	for project in targets: 
		#---hide the "public" subdictionary if we are not running public
		if not public: toc[project].pop('public',None)
		connect_single(project,**toc[project])

def check_port(port,strict=False):
	"""
	"""
	free = True
	import socket
	s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
	try: s.bind(("127.0.0.1",port))
	except socket.error as e: 
		free = False
		if strict: raise Exception('port %d is not free: %s'%(port,str(e)))
		else: 
			raise Exception('port %d is occupied'%port)

	s.close()
	return free

def start_site(name,port,public=False,sudo=False):
	"""
	"""
	#---start django
	site_dn = os.path.join('site',name)
	if not os.path.isdir(site_dn): 
		raise Exception('missing project named "%s". did you forget to connect it?'%name)
	#---if public we require an override port so that users are careful
	if public:
		public_details = get_public_ports(name)
		port = public_details['port_site']
		#---previously got user/group from the public dictionary but now we just use the current user
		user,group = username,groupname
	check_port(port)
	#---for some reason you have to KILL not TERM the runserver
	#---! replace runserver with something more appropriate? a real server?
	lock = 'pid.%s.site.lock'%name
	log = log_site%name
	if not public:
		cmd = 'python %s runserver 0.0.0.0:%s'%(os.path.join(os.getcwd(),site_dn,'manage.py'),port)
	else:
		#---! hard-coded development static paths
		cmd = ('%senv/envs/py2/bin/mod_wsgi-express start-server '%('sudo ' if sudo else '')+
			'--port %d site/%s/%s/wsgi.py --user %s --group %s '+
			'--python-path site/%s %s')%(port,name,name,user,group,name,
			('--url-alias /static %s'%('interface/static' if not public else 'site/%s/static_root'%name)))
		auth_fn = os.path.join('site',name,name,'wsgi_auth.py')
		if os.path.isfile(auth_fn): cmd += ' --auth-user-script=%s'%auth_fn
	backrun(cmd=cmd,log=log,stopper=lock,killsig='KILL',sudo=sudo,
		scripted=False,kill_switch_coda='rm %s'%lock,notes=('# factory run is public' if public else None))
	if public: chown_user(log)
	return lock,log

def start_cluster(name,public=False,sudo=False):
	"""
	"""
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

def daemon_ender(fn,cleanup=True):
	"""
	Read a lock file and end the job with a particular message
	"""
	try: bash('bash %s'%fn)
	except Exception as e: 
		print('[WARNING] failed to shutdown lock file %s with exception:\n%s'%(fn,e))
	if cleanup: 
		print('[STATUS] daemon successfully shutdown via %s'%fn)
		os.remove(fn)

def stop_locked(lock,log,cleanup=False):
	"""
	Save the logs and terminate the server.
	"""
	#---terminate first in case there is a problem saving the log
	daemon_ender(lock,cleanup=cleanup)
	stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
	if not os.path.isdir('logs'): raise Exception('logs directory is missing')
	name = re.match(r'^pid\.(.*?)\.lock$',lock).group(1)
	shutil.move(log,'logs/arch.%s.%s.log'%(name,stamp))

def get_public_ports(name):
	"""Get public ports and details before serving."""
	#---ensure sudo
	#if not os.geteuid()==0:
	#	raise Exception('you must run public as sudo!')
	#---collect details from the connection
	reqs = 'port hostname'.split()
	toc  = collect_connections(name)
	if not toc[name].get('public',None): raise Exception('need "public" for connection %s'%name)
	public_details = toc[name]['public']
	missing_keys = [i for i in reqs if i not in public_details]
	if any(missing_keys):
		raise Exception('missing keys from connection: %s'%missing_keys)
	#---previously set user and group manually in the public dictionary but now we detect it
	user,group = username,groupname
	port_site = public_details['port']
	port_notebook = public_details.get('notebook_port',port_site+1)
	notebook_ip = public_details.get('notebook_hostname',public_details.get('hostname','localhost'))
	#---if we have a list of hostnames then the first is the primary
	if type(notebook_ip) not in str_types: notebook_ip = notebook_ip[0]
	details = dict(user=user,group=group,port_notebook=port_notebook,
		port_site=port_site,notebook_ip=notebook_ip,
		jupyter_localhost=toc[name]['public'].get('jupyter_localhost',False))
	return details

def start_notebook(name,port,public=False,sudo=False):
	"""
	"""
	#---if public we require an override port so that users are careful
	if public: 
		public_details = get_public_ports(name)
		port,notebook_ip = [public_details[i] for i in ['port_notebook','notebook_ip']]
		#---! low ports are on. to turn them off remove False below and 
		if port<=1024: raise Exception('cannot use port %d for this project. '%port+
			'even public projects need high notebook ports for security reasons. '+
			'you will need to run `make connect <name> public` after you fix the ports')
	if not os.path.isdir(os.path.join('site',name)):
		raise Exception('cannot find site for %s'%name)
	#---note that TERM safely closes the notbook server
	lock = 'pid.%s.notebook.lock'%name
	log = log_notebook%name
	# root location to serve the notebook
	note_root = os.path.join(os.getcwd(),'calc',name)
	#! demo to try to serve higher for automacs simulations via notebook
	note_root = os.getcwd()
	#---higher rates (increased from 10M to 10**10 for XTC downloads)
	rate_cmd = '--NotebookApp.iopub_data_rate_limit=10000000000'
	#---if you want django data in IPython, use:
	#---...'python site/%s/manage.py shell_plus --notebook --no-browser'%name,
	#---! we never figured out how to set ports, other jupyter settings, with shell_plus
	#---! jupyter doesn't recommend allowing root but we do so here so you can call
	#---! `sudo make run <name> public` which prevents us from having to add sudo ourselves
	if not public:
		cmd = 'jupyter notebook --no-browser --port %d --port-retries=0 %s--notebook-dir="%s"'%(
			port,('%s '%rate_cmd if rate_cmd else ''),note_root)
	#---note that without zeroing port-retries, jupyter just tries random ports nearby (which is bad)
	else: 
		#! note try: jupyter notebook password --generate-config connections/config_jupyter_actinlink.py
		#! ... which will give you a one-per-machine password to link right to the notebook
		#! ... note that you must write that password to logs/token.PROJECT_NAME with a trailing space!
		#---! unsetting this variable because some crazy run/user error
		if 'XDG_RUNTIME_DIR' in os.environ: del os.environ['XDG_RUNTIME_DIR']
		cmd = (('sudo -i -u %s '%username if sudo else '')+'%s '%(
			os.path.join(os.getcwd(),'env/envs/py2/bin/jupyter-notebook'))+
			('--user=%s '%username if sudo else '')+(' %s '%rate_cmd if rate_cmd else '')+
			'--port-retries=0 '+'--port=%d --no-browser --ip="%s" --notebook-dir="%s"'%(port,
				notebook_ip if not public_details.get('jupyter_localhost',False) else 'localhost',
				note_root))
	backrun(cmd=cmd,log=log,stopper=lock,killsig='TERM',
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
	#---note that the calling function should make sure the notebook started
	return lock,log

def run(name,public=False):
	"""
	"""
	#---start the site first before starting the cluster
	toc  = collect_connections(name)
	if not public:
		#---local runs always use the next port for the notebook
		site_port = toc[name].get('port',8000)
		nb_port = site_port + 1
	else:
		#---get ports for public run before checking them
		site_port = toc[name].get('public',{}).get('port',8000)
		nb_port = toc[name].get('public',{}).get('notebook_port',site_port+1)
	#---check the ports before continuing
	check_port(site_port)
	check_port(nb_port)
	lock_site,log_site = start_site(name,site_port,public=public)
	try: lock_cluster,log_cluster = start_cluster(name,public=public)
	except Exception as e:
		stop_locked(lock=lock_site,log=log_site)
		raise Exception('failed to start the cluster so we shut down the site. exception: %s'%str(e)) 
	try: lock_notebook,log_notebook = start_notebook(name,nb_port,public=public)
	except Exception as e:
		stop_locked(lock=lock_site,log=log_site)
		stop_locked(lock=lock_cluster,log=log_cluster)
		raise Exception('failed to start the notebook so we shut down the site and cluster. '
			'exception: %s'%str(e))
	#---custom check that the notebook has found its port
	#---wait for the notebook to start up and then check for a port failure
	time.sleep(2)
	with open(log_notebook) as fp: log_text = fp.read()
	if re.search('is already in use',log_text,re.M): 
		stop_locked(lock=lock_site,log=log_site)
		stop_locked(lock=lock_notebook,log=log_notebook)
		stop_locked(lock=lock_cluster,log=log_cluster)
		raise Exception('failed to start the notebook so we shut down the site and cluster. '
			'possible port error in %s'%log_notebook)
	#---report the status to the user
	url = 'http://%s:%d'%('localhost',site_port)
	if public:
		try:
			this_hostnames = toc[name]['public']['hostname']
			this_hostnames = [this_hostnames] if type(this_hostnames) in str_types else this_hostnames
			for this_hostname in this_hostnames:
				url = 'http://%s:%d'%(this_hostname,toc[name]['public']['port'])
				print('[STATUS] serving from: %s'%url)
		except: pass

def shutdown_stop_locked(name):
	"""
	"""
	try: stop_locked(lock='pid.%s.notebook.lock'%name,log=log_notebook%name)
	except Exception as e: print('[WARNING] failed to stop notebook. exception: %s'%str(e))
	try: stop_locked(lock='pid.%s.site.lock'%name,log=log_site%name)
	except Exception as e: print('[WARNING] failed to stop site. exception: %s'%str(e))
	#---the cluster cleans up after itself so we do not run the cleanup
	try: stop_locked(lock='pid.%s.cluster.lock'%name,log=log_cluster%name)
	except Exception as e: print('[WARNING] failed to stop cluster. exception: %s'%str(e))

def shutdown(name=None,public=False):
	"""
	"""
	if public: 
		shutdown_public(name=name)
		return
	#---maximum number of seconds to wait for all ports to close
	max_wait,interval = 90.,3.
	if not name:
		locks = glob.glob('pid.*.lock')
		names = list(set([re.match(r'pid\.(.*?)\.(cluster|site|notebook)\.lock',lock).group(1)
			for lock in locks]))
	else: names=[name]
	#---check for sudo in the lock files
	for name in names:
		for style in 'cluster site notebook'.split():
			fn = 'pid.%s.%s.lock'%(name,style)
			if os .path.isfile(fn):
				with open(fn) as fp: text = fp.read()
				if re.search('sudo',text,re.M+re.DOTALL):
					raise Exception(
						'found sudo in %s. use `shutdown <name> public`'%fn)
	#---collecting ports that we need to check closed
	toc  = collect_connections(name)
	ports_need_closed = []
	for name in names:
		#---for each name we check for a site pid file that says whether it is public or not
		if (os.path.isfile('pid.%s.site.lock'%name) and 
			re.search('factory run is public',open('pid.%s.site.lock'%name).read(),flags=re.M)):
			ports_need_closed.append(toc[name].get('public',{}).get('port',8000))
		#---if we cannot find the site pid file to check for public we assume local
		else: ports_need_closed.append(toc[name].get('port',8000))
		shutdown_stop_locked(name)
	waits = 0
	while True:
		ports_occupied = [p for p in set(ports_need_closed) if not check_port(p,strict=False)]
		print('[STATUS] ports_occupied: %s'%ports_occupied)
		if any(ports_occupied) and waits < max_wait:
			waits += interval
			print('[STATUS] waiting for ports to close: %s'%ports_occupied)
			time.sleep(interval)
		else: break

def shutdown_public(name=None):
	"""
	Tired of typing the same thing over and over again.
	"""
	if not name:
		su_jobs = []
		for fn in glob.glob('pid.*.*.lock'):
			with open(fn) as fp:
				if re.search('sudo',fp.read()):
					su_jobs.append(re.match('^pid\.(.*?)\.(.*?)\.lock$',os.path.basename(fn)).group(1))
		su_jobs = list(set(su_jobs))
		if su_jobs: raise Exception('`make shutdown <name> public` needs a name. found publics: %s'%su_jobs)
		else: raise Exception('no sudo jobs running')
	#---ensure sudo
	#if not os.geteuid()==0:
	#	raise Exception('you must run `shutdown <name> public` as sudo!')
	shutdown_stop_locked(name)

def show_running_factories():
	"""
	Show all factory processes.
	Note that jupyter notebooks cannot be easily killed manually so use the full path and try `pkill -f`.
	Otherwise this function can help you clean up redundant factories by username.
	"""
	cmd = 'ps xao pid,user,command | egrep "([c]luster|[m]anage.py|[m]od_wsgi-express|[j]upyter)"'
	try: bash(cmd)
	except: print('[NOTE] no processes found using bash command: `%s`'%cmd)

#---alias for the background jobs
ps = show_running_factories

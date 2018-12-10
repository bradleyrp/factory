#!/usr/bin/env python

import os,re,subprocess,sys,shutil
from ortho import bash,str_types

#! hard-coded location of the site. can be moved to config
django_source = 'interface'

#! note no calculator below
#! do not even think about changing this without MIRRORING the change in 
#!   the development version at interface/interface/settings.py
project_settings_addendum = """
# django settings addendum
INSTALLED_APPS = tuple(list(INSTALLED_APPS)+['django_extensions','simulator','calculator'])
# common static directory
STATIC_ROOT = os.path.join(BASE_DIR,'static_root')
TEMPLATES[0]['OPTIONS']['libraries'] = {'code_syntax':'calculator.templatetags.code_syntax'}
TEMPLATES[0]['OPTIONS']['context_processors'].append('calculator.context_processors.global_settings')
# all customizations
from .custom_settings import *
# addenda from custom settings
ALLOWED_HOSTS += extra_allowed_hosts
"""

# project-level URLs really ties the room together
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

def abspath(fn):
	"""Return absolute paths even inside user directory."""
	return os.path.expanduser(os.path.abspath(fn))

def clear_site(name):
	"""
	Prepare the site for rebuilding.
	Currently we delete the site because it holds no important information
	!!! Confirm that this is the most efficient way to build things.
	"""
	# the site is equivalent to a django project
	# the site draws on either prepackaged apps in the pack folder or the in-development versions in dev
	# since the site has no additional data except that specified in connect.yaml, we can always remake it
	#! be more careful here
	if os.path.isdir('site/'+name):
		print("status removing the site for \"%s\" to remake it"%name)
		shutil.rmtree('site/'+name)

#! should we have separate settings custom or what?
def site_setup(name,settings_custom,make_superuser=True,specs=None):
	"""
	Sandbox the management of the Django site here.
	"""
	if not os.path.isdir('site'): os.mkdir('site')
	clear_site(name)
	if not specs: specs = {}
	connection_name = name
	# one new django project per connection
	bash('django-admin startproject %s'%connection_name,
		log='logs/log-%s-startproject'%connection_name,cwd='site/')

	# if the user specifies a database location we override it here
	#! currently deprecated and untested
	if specs.get('database',None):
		database_path_change = "\nDATABASES['default']['NAME'] = '%s'"%(
			os.path.abspath(specs['database']))
	else: database_path_change = ''

	# all settings are handled by appending to the django-generated default
	# here we also add changes to django-default paths
	with open(os.path.join('site',connection_name,connection_name,'settings.py'),'a') as fp:
		fp.write(project_settings_addendum+database_path_change)
		# only use the development code if the flag is set and we are not running public
		if specs.get('development',True) and not specs.get('public',False):
			fp.write('\n# use the development copy of the code\n'+
				'import sys;sys.path.insert(0,os.path.join(os.getcwd(),"%s"))'%django_source)
			#! get access to ortho
			#! this was a long saga: hard to install ortho the way I want
			fp.write("\nsys.path.insert(0,os.path.join(os.getcwd()))") 
		# one more thing: custom settings specify static paths for local or public serve
		fp.write("\nSTATICFILES_DIRS = [os.path.join('%s','interface','static')]"%
			os.path.abspath(os.getcwd()))

	# write custom settings
	custom_literals = ['CLUSTER_NAMER']
	with open(os.path.join('site',connection_name,connection_name,'custom_settings.py'),'w') as fp:
		#! proper way to write python constants?
		fp.write('# custom settings are auto-generated from manager.factory.connect_single\n')
		for key,val in settings_custom.items():
			#! is there a pythonic way to write a dictionary to a script of immutables?
			if ((type(val) in str_types and re.match('^(False|True)$',val)) or key in custom_literals
				or type(val) in [bool,list,tuple]):
				out = '%s = %s\n'%(key,val)
			else: out = '%s = "%s"\n'%(key,val)
			fp.write(out)

	# development uses live copy of static files in interface/static
	if not specs.get('public',None):
		try:
			# link the static files to the development codes (could use copytree)
			os.symlink(os.path.join(os.getcwd(),django_source,'static'),
				os.path.join('site',connection_name,'static'))
		#! already exists?
		except: pass
	# production collects all static files
	else: 
		os.mkdir(os.path.join(os.getcwd(),'site',connection_name,'static_root'))
		bash('python manage.py collectstatic',cwd='site/%s'%connection_name)

	# write project-level URLs
	with open(os.path.join('site',connection_name,connection_name,'urls.py'),'w') as fp:
		fp.write(project_urls)

	#!!! replace this with sync
	# clone omnicalc if necessary
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
		# if this is fresh we run `make setup` because that provides a minimal config.py
		bash('make setup',cwd=specs['calc'])
	else: print('[NOTE] found calc/%s'%connection_name)

	# initial migration for all new projects to start the database
	print('note migrating ...')
	bash('python site/%s/manage.py makemigrations'%connection_name,
		log='logs/log-%s-migrate'%connection_name,announce=True)
	bash('python site/%s/manage.py migrate --run-syncdb'%connection_name,
		log='logs/log-%s-migrate'%connection_name,announce=True)
	print('note migrating ... done')
	if make_superuser:
		print("[STATUS] making superuser")
		su_script = "from django.contrib.auth.models import User; "+\
			"User.objects.create_superuser('admin','','admin');print;quit();"
		p = subprocess.Popen('python ./site/%s/manage.py shell'%(connection_name),		
			stdin=subprocess.PIPE,stderr=subprocess.PIPE,stdout=open(os.devnull,'w'),
			shell=True,executable='/bin/bash')
		catch = p.communicate(input=su_script if sys.version_info<(3,0) else su_script.encode())[0]
	print("status new project \"%s\" is stored at ./data/%s"%(connection_name,connection_name))
	print("status replace with a symlink if you wish to store the data elsewhere")

	# now that site is ready we can write credentials
	if specs.get('public',None):
		# write key,value pairs as Basic Auth user/passwords
		creds = specs['public'].get('credentials',{})
		if creds: 
			with open(os.path.join('site',connection_name,connection_name,'wsgi_auth.py'),'w') as fp:
				fp.write(code_check_passwd%str([(k,v) for k,v in creds.items()]))

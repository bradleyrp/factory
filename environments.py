#!/usr/bin/env python

from __future__ import print_function
from __future__ import unicode_literals
from .bash import bash
import sys,os

#! the docs for the bash script below should include a link to the bootstrap docs
#! update the example in the bash script below

"""
ALTERNATE FACTORY INSTALLATION
Use the following bash script to bootstrap an alternate factory method.
This method pipes a new `envs` variable into the config.json and hence overwrites the previous one.
Note that you can also use the standard bootstrap.py method to include these instructions in a default config.

#!/bin/bash

<<EOF

Instructions for installing anaconda from the factory.
Run `bash instruct_anaconda.sh` to set these.
Note that this file may be redundant with defaults in environments.py.

EOF
read -d '' incoming << EOF

{'conda_py2':{
	'where':'env',
	'style':'anaconda',
	'sources':{
		'installer':'./Miniconda3-latest-Linux-x86_64.sh',
		'vmd':'./vmd-1.9.1.bin.LINUXAMD64.opengl.tar',
		},
	},
}

EOF
# use `make set` to overwrite the environment in config.json
incoming=$(echo $incoming | sed -e 's/ //g')
make set envs=\"$incoming\"
"""

#!? previous set of codes for some kind of avoiding ~/.local method?
"""
#---we use the conda environment handler to avoid using the user site-packages in ~/.local
env_etc = 'env/envs/py2/etc'
env_etc_conda = 'env/envs/py2/etc/conda'
for dn in [env_etc,env_etc_conda]:
	if not os.path.isdir(dn): os.mkdir(dn)
for dn in ['activate.d','deactivate.d']: os.mkdir(os.path.join(env_etc_conda,dn))
with open(os.path.join(env_etc_conda,'activate.d','env_vars.sh'),'w') as fp:
	fp.write('#!/bin/sh\nexport PYTHONNOUSERSITE=True\n')
with open(os.path.join(env_etc_conda,'deactivate.d','env_vars.sh'),'w') as fp:
	fp.write('#!/bin/sh\nunset PYTHONNOUSERSITE\n')
"""

# default environments if they are absent from config.json
default_envs = {
	'conda_py2':{
		'where':'env',
		'style':'anaconda',
		'sources':{
			'installer':'./Miniconda3-latest-Linux-x86_64.sh',
			'vmd':'./vmd-1.9.1.bin.LINUXAMD64.opengl.tar',
			'reqs':'reqs_conda.yaml',},
		'name':'py2',
		'python_version':2,
		'install_commands':[
			"this = dict(sources_installer=self.sources['installer'],where=self.where)",
			"bash('bash %(sources_installer)s -b -p %(where)s'%this,log='logs/log-anaconda-env')",
			"bash('source env/bin/activate && conda update -y conda',log='logs/log-conda-update')",
			"bash('source env/bin/activate && conda create "+
				"python=%(version)s -y -n %(name)s'%dict(name=self.name,version=self.python_version),"+
				"log='logs/log-create-%s'%self.name)",
			"bash('source env/bin/activate py2 && conda env update --file %(reqs)s'%"+
				"dict(reqs=self.sources['reqs']),log='logs/log-conda-refresh')",
			"bash('make set activate_env=\"env/bin/activate %s\"'%self.name)",],
		'refresh_commands':[
			"bash('source env/bin/activate py2 && conda env update --file %(reqs)s'%"+
				"dict(reqs=self.sources['reqs']),log='logs/log-conda-refresh')",],},}

class Factory:
	def __init__(self,*args,**kwargs):
		self.conf = conf # pylint: disable=undefined-variable
		self.envs = self.conf.get('envs',default_envs)
		self.logs_space()
		if not self.envs: raise Exception('no environments yet!')
		for name,detail in self.envs.items(): self.validate(name,detail)
	def logs_space(self):
		"""Logs are always written to the same place."""
		if not os.path.isdir('logs'): os.mkdir('logs')
	def validate(self,name,detail):
		"""
		Check or create an environment.
		Environment data comes from only one place in the `envs` key of the config.json file however it can 
		be placed there by a bootstrap.py with a default configuration or a BASH script described above.
		The only requirement is that it has the following keys: where, sources, style, and install_commands.
		The install commands are exec'd in place in this function. The default envs are set above.
		"""
		self.install_commands = detail.pop('install_commands',[])
		self.sources = detail.pop('sources',{})
		# all top level keys are part of self
		self.__dict__.update(**detail)
		if 'sources' not in self.__dict__: self.sources = []
		missing_keys = [i for i in ['install_commands'] if i not in self.__dict__]
		if any(missing_keys): raise Exception('environment definition is missing %s'%missing_keys)
		print('status','running commands to install the environment')
		# check sources to preempt an anaconda error
		for source_name,source_fn in self.sources.items():
			if not os.path.isfile(source_fn):
				raise Exception('cannot find source "%s" requested by env %s: %s'%(
					source_name,name,source_fn))
		# use exec to loop over commands. note that the install_commands can use the where, sources, style,
		# ... etc which are set above by default from the detail. note that the default configuration above
		# ... provides an example for using self-referential syntax
		for cmd in self.install_commands: 
			print('run','`%s`'%cmd)
			exec(cmd)

def env(*args,**kwargs): 
	"""The env command instantiates a Factory."""
	Factory(*args,**kwargs)

if False:
	def setup_anaconda_refresh(self):
		if self.use_python2:
			#! note that anaconda may have deprecated use of env/envs/py2/bin/activate
			self.loader_commands['env_activate'] = 'env/bin/activate py2'
			self.source_cmd = 'source env/bin/activate py2'
		#---we consult a conda YAML file and a PIP text list to install packages
		#---default values are built into the class above but they can be overridden
		config = read_config()
		reqs_conda = config.get('reqs_conda',self.reqs_conda)
		reqs_pip = config.get('reqs_pip',self.reqs_pip)
		if type(reqs_conda)!=list: reqs_conda = [reqs_conda]
		if type(reqs_pip)!=list: reqs_pip = [reqs_pip]
		#---install from the conda requirements list followed by pip (for packages not available on conda)
		for fn in reqs_conda:
			print('[STATUS] installing packages via conda from %s'%fn)
			#---we tell conda to ignore local user site-packages because version errors
			bash(self.source_cmd+' && conda env update --file %s'%fn,
				log='logs/log-anaconda-conda-%s'%os.path.basename(fn))
		for fn in reqs_pip:
			print('[STATUS] installing packages via pip from %s'%fn)
			bash(self.source_cmd+' && pip install -r %s'%fn,
				log='logs/log-anaconda-conda-%s'%os.path.basename(fn))


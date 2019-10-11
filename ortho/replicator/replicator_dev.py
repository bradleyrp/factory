#!/usr/bin/env pythonm

"""
Replicator REDEVELOPMENT
Rebuild a replicator feature to replace ortho.replicator, specifically `repl`.
"""

import os,re,tempfile,subprocess
#! refer to ortho by name for top-level imports simplified by init?
from ..bash import bash
from ..dictionary import DotDict
from ..yaml_mods import YAMLObjectInit
from ..handler import Handler
from ..requires import requires_program

class Volume(Handler):
	"""
	Handle external volumes for a replicator.
	Note that this class is used by the Volume class exposed to yaml.
	"""
	def docker(self,docker):
		"""Use a docker volume."""
		volumes = bash('docker volume ls -q',scroll=False,v=True)
		avail = volumes['stdout'].split()
		if docker not in avail:
			print('status adding docker volume %s'%docker)
			out = bash('docker volume create %s'%docker,scroll=False,v=True)
		else: print('status found docker volume %s'%docker)
		return dict(name=docker,args='-v %s:%%s'%docker)

#! abandoned
class VolumeWrap(YAMLObjectInit):
	"""The Volume class wraps VolumeCore which handles different uses."""
	yaml_tag = '!volume'
	def __init__(self,**kwargs):
		self.volume = VolumeCore(**kwargs).solve

#! abandoned		
class Executor(YAMLObjectInit):
	yaml_tag = '!executor'
	def __init__(self,sequence): 
		self.sequence = sequence
		for item in self.sequence:
			if hasattr(item,'_run'):
				print('status found _run for %s'%str(item))
				getattr(item,'_run')()

#! abandoned
class Replicate(YAMLObjectInit):
	yaml_tag = '!replicate'
	def __init__(self,**kwargs):
		print('status inside the Replicate')
		self.spot = kwargs.pop('spot',None)
		self.inside = kwargs.pop('inside',None)
		if kwargs: raise Exception('unprocessed kwargs: %s'%str(kwargs))
		import ipdb;ipdb.set_trace()

class DockerContainer(Handler):
	_internals = {'name':'real_name','meta':'meta'}
	def get_container(self,name):
		"""Get an existing container by name."""
		# get the repo and tag from the docker name
		try: repo,name = re.match('^(.+):(.+)$',name).groups()
		except: 
			raise Exception(
				'docker container name must be <repo>:<tag> but we got: %s:%s'%
				name)
		containers = bash(
			'docker images --format "{{.Repository}} {{.Tag}}"',
			scroll=False,v=True)
		avail = [tuple(i.split()) for i in containers['stdout'].splitlines()]
		translate_none = lambda x: None if x=='<none>' else x
		avail = [tuple(translate_none(i) for i in j) for j in avail]
		avail = [(i,j) for i,j in avail if not (i==None and j==None)]
		if (repo,name) in avail:
			return '%s:%s'%(repo,name)
		#! is this a possible outcome?
		elif repo==None and (None,name) in avail:
			return name
		else: 
			import ipdb;ipdb.set_trace()
			raise Exception('cannot find image: %s in repo: %s'%(name,repo))

class DockerExecution(Handler):
	def line(self,line):
		"""
		Turn a script into a one-liner for a `docker run` command.
		Not suitable for complex scripts with variable substitutions.
		"""
		regex_hashbang = r'^(#!.*?s*\n)?(.+)$'
		match = re.match(regex_hashbang,line,flags=re.M+re.DOTALL)
		hashbang,contents = re.match(
			regex_hashbang,line,flags=re.M+re.DOTALL).groups()
		# confirm bash or sh hashbang
		if hashbang:
			hashbang_path = re.match(r'^#!(.*?)\s*$',hashbang).group(1)
			if hashbang_path not in ['/bin/bash','/bin/sh']:
				raise Exception('invalid hashbang for one-liner to docker: %s'%
					hashbang_path)
		# fix quotes
		contents_safe = re.sub('"','\\"',contents.strip('\n'))
		return dict(line='"%s"'%contents_safe,kind='line')
	def script(self,script):
		"""Scripts pass through to the function that calls docker."""
		return dict(script=script,kind='script')

class ReplicateCore(Handler):
	"""
	DEV: replacement for the replicator functions
	"""
	@requires_program('docker')
	def docker_container_volume(self,
		docker_container,docker_volume,**kwargs):
		"""
		Run a one-liner command in docker.
		Not suitable for complex bash commands.
		"""
		# step 1: assemble the volume
		self.spot = Volume(docker=docker_volume).solve
		if self.spot.get('args',None):
			docker_args = self.spot['args']%'/home/user/outside'+' '
		else: docker_args = ''
		# step 2: locate the container
		self.container = DockerContainer(name=docker_container).solve
		# step 3: prepare the content of the execution
		#! keep the '-i' flag?
		cmd = 'docker run -u 0 -i %s%s'%(docker_args,self.container)
		self.do = DockerExecution(**kwargs).solve
		# case A: one-liner
		if self.do['kind']=='line':
			cmd += ' /bin/sh -c %s'%self.do['line']
		# case B: write a script
		elif self.do['kind']=='script': pass
		else: raise Exception('dev')
		# step 4: execute the docker run command
		#! announcement for the script is clumsy because of newlines and
		#!   escaped characters
		# script execution via stdin to docker
		if self.do['kind']=='script':
			script = self.do['script']
			print('status script:\n'+str(script))
			print('status command: %s'%cmd)
			proc = subprocess.Popen(cmd.split(),stdin=subprocess.PIPE)
			proc.communicate(script.encode())
		# standard execution
		else: bash(cmd,scroll=True,v=True)

class Replicate(YAMLObjectInit):
	"""Wrap a handler with a yaml recipe."""
	yaml_tag = '!replicate'
	def __init__(self,**kwargs):
		self.out = ReplicateCore(**kwargs).solve		

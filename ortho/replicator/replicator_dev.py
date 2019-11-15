#!/usr/bin/env pythonm

"""
Replicator REDEVELOPMENT
Rebuild a replicator feature to replace ortho.replicator, specifically `repl`.
"""

import os,re,tempfile,subprocess,string,sys
#! refer to ortho by name for top-level imports simplified by init?
from ..bash import bash
from ..dictionary import DotDict
from ..handler import Handler
from ..requires import requires_program,is_terminal_command
from ..requires import requires_python_check
from ..misc import path_resolver
from .templates import screen_maker

class HookPromise:
	"""Run a hook later."""
	def __init__(self,hook,**kwargs):
		#! check for handler type and return solve?
		self.kwargs = kwargs
		self.hook = hook
	def run(self):
		return self.hook(**self.kwargs)

def promise_run(this):
	if this.__class__.__name__=='HookPromise':
		return this.run()
	else: return this

def mount_macos(dmg,mount):
	"""
	Mount an image in macos.
	"""
	# assume it is mounted if the directory exists
	if not os.path.isdir(mount):
		bash('hdiutil attach -nobrowse -mountpoint %s %s'%(mount,dmg))
	return mount

class SpotPath(Handler):
	def macos_mount(self,dmg,mount):
		"""
		Mount a dmg file.
		This interpreter takes a spot from the config created 
		by lib.macos.MacosImager and passes along a hook for mounting.
		"""
		return HookPromise(hook=mount_macos,dmg=dmg,mount=mount)

def constructor_site_hook(loader,node):
	"""
	Use this as a constructor for the `!spots` yaml tag to get an alternate
	location for running something.
	"""
	name = loader.construct_scalar(node)
	# process the site
	from ortho import conf
	spots = conf.get('spots',{})
	if name in spots:
		return SpotPath(**spots[name]).solve
	# the root keyword points to the local directory
	elif name=='root': return './'
	# pass through the name for a literal path
	else: return name

class Volume(Handler):
	"""
	Handle external volumes for a replicator.
	Note that this class is used by the Volume class exposed to yaml.
	"""
	"""
	See docker volume "consistent" option which may be important for low-level
	file operations and performance: 
		https://docs.docker.com/docker-for-mac/osxfs-caching/
	Note that the cached/consistent/delegated flags can be used in mounts.
	"""
	def _check_darwin(self):
		if sys.platform=='darwin':
			raise Exception('Your platform is darwin. '
				'We require a hook to mount a case-sensitive filesystem. '
				'If you already have one, this is a development exception '
				'and we need to detect the case-sensitivity directly.')

	def docker(self,docker):
		"""Use a docker volume."""
		volumes = bash('docker volume ls -q',scroll=False,v=True)
		avail = volumes['stdout'].split()
		if docker not in avail:
			print('status adding docker volume %s'%docker)
			out = bash('docker volume create %s'%docker,scroll=False,v=True)
		else: print('status found docker volume %s'%docker)
		#! hardcoded link to the outside should be configurable
		args_out = ('-v %s:%%s'%docker)%'/home/user/outside'
		return dict(name=docker,docker_args=args_out)

	def local(self,root):
		"""Add the current directory to the volume."""
		self._check_darwin()
		args_out = '-v %s:%s -w %s'%(root,root,root)
		return dict(docker_args=args_out)

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
		return dict(line='%s'%contents_safe,kind='line')
	def script(self,script):
		"""Scripts pass through to the function that calls docker."""
		return dict(script=script,kind='script')

class ScriptPrelim(Handler):
	def fileprep(self,files=None,specs=None):
		staged = {}
		# specs are yaml trees that are dumped to files
		if specs:
			for name,tree in specs.items():
				with tempfile.NamedTemporaryFile(delete=False) as fp:
					tmp_fn = fp.name
					fp.write(yaml.dump(tree).encode())
					fp.close()
				staged[name] = tmp_fn
		return staged

class RecipeRead(Handler):
	"""Interpret the reproducibility recipes."""

	def explicit_path(self,path): 
		"""Process a recipe from an explicit path."""
		requires_python_check('yaml')
		import yaml
		# +++ HOOKS are loaded here
		#! addition of hooks could itself be a hook from ortho.conf
		yaml.add_constructor('!spots',constructor_site_hook)
		with open(path) as fp: 
			recipe = yaml.load(fp,Loader=yaml.Loader)
		return recipe

class ReplicateCore(Handler):
	"""
	DEV: replacement for the replicator functions
	"""
	def docker_container_volume(self,
		docker_container,docker_volume,**kwargs):
		"""
		Run a one-liner command in docker.
		Not suitable for complex bash commands.
		"""
		#!!! retire this after re-factor below
		# you cannot use decorators with Handler
		is_terminal_command('docker')
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
	
	def _docker(self,image,volume={},visit=False,**kwargs):
		"""
		Run a one-liner command in docker.
		Not suitable for complex bash commands.
		"""
		# you cannot use decorators with Handler
		is_terminal_command('docker')

		# step 1: assemble the volume
		self.spot = Volume(**volume).solve
		docker_args = self.spot['docker_args']

		# step 2: locate the container
		self.container = DockerContainer(name=image).solve

		# step 3: prepare the content of the execution
		#! keep the '-i' flag?
		if docker_args: docker_args += ' '
		cmd = 'docker run -u 0 -i%s %s%s'%('t' if visit else '',
			docker_args,self.container)
		# kwargs contains either line or script for the execution step
		self.do = DockerExecution(**kwargs).solve

		# case A: one-liner
		if visit:
			if not self.do['kind']=='line': 
				raise Exception('visit requires line')
			cmd += ' '+self.do['line']
		elif self.do['kind']=='line':
			cmd += ' /bin/sh -c "%s"'%self.do['line']
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
		# we require a TTY to enter the container so we use os.system
		elif visit:
			# possible security issue
			print('status running docker: %s'%cmd)
			os.system(cmd)
		# standard execution
		else: bash(cmd,scroll=True if not visit else False,v=True)

	def docker_mimic(self,image,volume,visit=False,**kwargs):
		"""
		Run a docker container in "mimic" mode where it substitutes for the
		host operation system and maintains the right paths.
		"""
		return self._docker(volume=volume,image=image,visit=visit,**kwargs)

	def screen(self,screen,script,**kwargs):
		"""
		Run something in a screen.
		"""
		print('status starting a screen named: %s'%screen)
		spot = kwargs.pop('spot',None)
		# spillover kwargs go to a ScriptPrelim class
		if kwargs: prelim = ScriptPrelim(**kwargs).solve
		else: prelim = {}
		# prepare a location
		if spot and not os.path.isdir(spot): 
			os.mkdir(spot)
			spot = path_resolver(spot)
		# detect string interpolation
		#! finish this feature! protect against wonky scripts
		if 0:
			formatter = string.Formatter()
			reqs = formatter.parse(script)
			import ipdb;ipdb.set_trace()
		script = script%dict(spot=spot if spot else '')
		# add staged variables to the script
		if prelim:
			staged_flag = 'staged here'
			if not re.search(r'#\s*%s\s*'%staged_flag,script):
				raise Exception('we have variables for injection into your '
					'script. please include a comment "%s" in the script'%
					staged_flag)
			else:
				#! scape sequences below
				variable_injection = '# injected variables\n' + \
					'\n'.join(['%s="%s"'%(i,j) for i,j in prelim.items()])+'\n'
				script = re.sub(r'#\s*%s\s*'%staged_flag,
					variable_injection,script)
		# prepare the execution script
		screen_log = os.path.join(os.getcwd(),'screen-%s.log'%screen)
		detail = dict(screen_name=screen,contents=script,screen_log=screen_log,
			prelim='' if not spot else '\ncd %s'%spot)
		with tempfile.NamedTemporaryFile(delete=False) as fp:
			tmp_fn = fp.name
			# the CLEANUP_FILES are deleted at the end of the screened script
			detail['post'] = "\nCLEANUP_FILES=%s"%fp.name
			fp.write((screen_maker%detail).encode())
			fp.close()
		print('status executing temporary script: %s'%tmp_fn)
		bash('bash %s'%tmp_fn,v=True)
		if os.path.isfile(tmp_fn): os.remove(tmp_fn)
		tmp_screen_conf = 'screen-%s.tmp'%screen
		#! the following caused a race condition
		#!   if os.path.isfile(tmp_screen_conf): os.remove(tmp_screen_conf)

	def direct_raw(self,script): 
		return self._direct(script=script,spot=None)

	def direct_spot(self,script,spot): 
		return self._direct(script=script,spot=spot)

	def _direct(self,script,**kwargs):
		#!!! function is hidden because collision with script. fix later
		"""
		Run a script directly.
		"""
		spot = kwargs.pop('spot',None)
		if kwargs: prelim = ScriptPrelim(**kwargs).solve
		else: prelim = {}
		# prepare a location
		if spot and not os.path.isdir(spot): os.mkdir(spot)
		elif not spot: spot = './'
		script = script%dict(spot=os.path.abspath(spot))
		# add staged variables to the script
		if prelim:
			staged_flag = 'staged here'
			if not re.search(r'#\s*%s\s*'%staged_flag,script):
				raise Exception('we have variables for injection into your '
					'script. please include a comment "%s" in the script'%
					staged_flag)
			else:
				#! scape sequences below
				variable_injection = '# injected variables\n' + \
					'\n'.join(['%s="%s"'%(i,j) for i,j in prelim.items()])+'\n'
				script = re.sub(r'#\s*%s\s*'%staged_flag,
					variable_injection,script)
		with tempfile.NamedTemporaryFile(delete=False) as fp:
			tmp_fn = fp.name
			fp.write(script.encode())
			fp.close()
		print('status executing temporary script: %s'%tmp_fn)
		bash('bash %s'%tmp_fn,v=True,cwd=spot)
